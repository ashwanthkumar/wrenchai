"""
Ingest a vehicle service manual PDF via Unsiloed.ai and store chunks in ChromaDB.
Query the manual with AI-powered answers using Claude Sonnet.

Usage:
    uv run main.py ingest <path-to-pdf>       # Parse PDF and store in ChromaDB
    uv run main.py query  "your question"      # Query the manual with AI-powered answers
    uv run main.py serve                       # Start the HTTP API server
"""

import argparse
import asyncio
import base64
import json
import os
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.utils.embedding_functions import VoyageAIEmbeddingFunction
from dotenv import load_dotenv
from pydantic import BaseModel
from unsiloed_sdk import UnsiloedClient

import anyio
from claude_agent_sdk import (
    tool,
    create_sdk_mcp_server,
    query as claude_query,
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    UserMessage,
    SystemMessage,
    ResultMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
)

load_dotenv()

# ---------------------------------------------------------------------------
# Session store for persistent WebSocket conversations
# ---------------------------------------------------------------------------
_sessions: dict[str, ClaudeSDKClient] = {}
_sessions_lock = asyncio.Lock()

CHROMA_DIR = Path(__file__).parent / "chroma_db"
COLLECTION_NAME = "vehicle_manual"
OUTPUT_DIR = Path(__file__).parent / "output"
IMAGES_DIR = Path(__file__).parent / "images"

voyage_ef = VoyageAIEmbeddingFunction(
    api_key=os.environ.get("VOYAGE_API_KEY", ""),
    model_name="voyage-4",
)

SYSTEM_PROMPT = """\
You are a vehicle manual assistant. Answer the user's question using ONLY \
information retrieved via the search_manual tool.

Instructions:
1. Use the search_manual tool to find relevant manual sections. You may search \
   multiple times with different queries to gather comprehensive information.
2. Answer ONLY the question asked. Be direct and concise. Do NOT add extra \
   information, tips, warnings, or tangential context beyond what is asked.
3. For procedural questions (how to do something), give numbered steps.
4. For factual questions, give a direct answer.
5. Cite page numbers from the search results.
6. If the manual doesn't contain the answer, say so briefly.
7. Structure your answer as: a brief summary, then individual steps (each a short \
   actionable instruction), and list all page numbers referenced.
8. If images are provided, examine them carefully to understand what the user \
   is asking about — identify parts, warning lights, or damage shown.
"""

# Module-level collection reference, set before calling _ask_claude
_collection = None


@tool(
    name="search_manual",
    description="Search the vehicle service manual for relevant excerpts. Use specific keywords related to the question. Call multiple times with different queries to find all relevant information.",
    input_schema={"query": str},
)
async def _search_manual_tool(args):
    query_text = args["query"]
    results = _collection.query(query_texts=[query_text], n_results=5)

    parts = []
    for i, (doc, meta, dist) in enumerate(
        zip(results["documents"][0], results["metadatas"][0], results["distances"][0])
    ):
        score = 1 - dist
        if score < 0.3:
            continue
        pages = meta.get("pages", "unknown")
        parts.append(
            f"--- Excerpt {i + 1} (pages: {pages}, relevance: {score:.3f}) ---\n{doc}"
        )

    if not parts:
        return {"content": [{"type": "text", "text": "No relevant results found for this query."}]}

    return {"content": [{"type": "text", "text": "\n\n".join(parts)}]}


_manual_server = create_sdk_mcp_server(name="manual", tools=[_search_manual_tool])


class ManualAnswer(BaseModel):
    summary: str
    steps: list[str]
    pages_referenced: list[str]


ANSWER_SCHEMA = ManualAnswer.model_json_schema()


async def _ask_claude(question: str, image_paths: list[Path] | None = None) -> ManualAnswer:
    """Use Claude Sonnet as an agent with a ChromaDB search tool to answer the question."""
    prompt = question
    if image_paths:
        refs = " ".join(f"@{p.resolve()}" for p in image_paths)
        prompt = f"{refs} {question}"

    allowed_tools = ["mcp__manual__search_manual"]
    opts = dict(
        model="claude-sonnet-4-6",
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={"manual": _manual_server},
        allowed_tools=allowed_tools,
        permission_mode="default",
        max_turns=6,
        output_format={
            "type": "json_schema",
            "schema": ANSWER_SCHEMA,
        },
        extra_args={"debug-to-stderr": None},
        stderr=lambda line: print(line, file=sys.stderr),
    )
    if image_paths:
        allowed_tools.append("Read")
        opts["add_dirs"] = [str(IMAGES_DIR)]

    result = None
    async for message in claude_query(
        prompt=prompt,
        options=ClaudeAgentOptions(**opts),
    ):
        if isinstance(message, ResultMessage) and message.structured_output:
            result = message.structured_output

    if result is None:
        return ManualAnswer(
            summary="Something went wrong and I couldn't get an answer.",
            steps=[],
            pages_referenced=[],
        )
    return ManualAnswer.model_validate(result)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize ChromaDB collection and images directory on server startup."""
    global _collection
    if not CHROMA_DIR.exists():
        raise RuntimeError("No ChromaDB found. Run 'ingest' first.")
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    _collection = client.get_collection(name=COLLECTION_NAME, embedding_function=voyage_ef)
    IMAGES_DIR.mkdir(exist_ok=True)
    yield
    # Shutdown: disconnect all persistent sessions
    for client in _sessions.values():
        try:
            await client.disconnect()
        except Exception:
            pass
    _sessions.clear()


app = FastAPI(title="Vehicle Manual Q&A", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryResponse(BaseModel):
    answer: ManualAnswer


@app.post("/query", response_model=QueryResponse)
async def query_endpoint(
    question: str = Form(...),
    images: list[UploadFile] = File(default=[]),
) -> QueryResponse:
    image_paths: list[Path] = []
    for img in images:
        dest = IMAGES_DIR / f"{uuid.uuid4().hex}_{img.filename}"
        dest.write_bytes(await img.read())
        image_paths.append(dest)

    answer = await _ask_claude(question, image_paths=image_paths)
    return QueryResponse(answer=answer)


async def _get_or_create_session(session_id: str) -> ClaudeSDKClient:
    """Return an existing ClaudeSDKClient for session_id, or create a new one."""
    async with _sessions_lock:
        if session_id in _sessions:
            return _sessions[session_id]

        opts = ClaudeAgentOptions(
            model="claude-sonnet-4-6",
            system_prompt=SYSTEM_PROMPT,
            mcp_servers={"manual": _manual_server},
            allowed_tools=["mcp__manual__search_manual", "Read"],
            permission_mode="default",
            add_dirs=[str(IMAGES_DIR)],
            extra_args={"debug-to-stderr": None},
            stderr=lambda line: print(line, file=sys.stderr),
        )
        client = ClaudeSDKClient(options=opts)
        await client.connect()
        _sessions[session_id] = client
        return client


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    try:
        client = await _get_or_create_session(session_id)

        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            if data.get("type") != "message":
                await websocket.send_json({"type": "error", "message": f"Unknown message type: {data.get('type')}"})
                continue

            text = data.get("text", "")

            # Handle base64 images: decode, save, and prepend @path refs
            image_refs = []
            for img in data.get("images", []):
                img_data = base64.b64decode(img["data"])
                filename = f"{uuid.uuid4().hex}_{img.get('filename', 'image.jpg')}"
                dest = IMAGES_DIR / filename
                dest.write_bytes(img_data)
                image_refs.append(f"@{dest.resolve()}")

            prompt = f"{' '.join(image_refs)} {text}" if image_refs else text

            start_time = time.monotonic()
            try:
                await client.query(prompt)
                async for msg in client.receive_response():
                    if isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, TextBlock):
                                await websocket.send_json({"type": "assistant_text", "text": block.text})
                            elif isinstance(block, ToolUseBlock):
                                await websocket.send_json({
                                    "type": "tool_use",
                                    "tool": block.name,
                                    "input": block.input,
                                })
                    elif isinstance(msg, UserMessage):
                        if isinstance(msg.content, list):
                            for block in msg.content:
                                if isinstance(block, ToolResultBlock):
                                    content = block.content
                                    if isinstance(content, list):
                                        content = json.dumps(content)
                                    await websocket.send_json({
                                        "type": "tool_result",
                                        "tool_use_id": block.tool_use_id,
                                        "content": content or "",
                                    })
                    elif isinstance(msg, ResultMessage):
                        duration_ms = int((time.monotonic() - start_time) * 1000)
                        await websocket.send_json({
                            "type": "result",
                            "cost_usd": msg.total_cost_usd,
                            "duration_ms": duration_ms,
                        })
            except Exception as e:
                await websocket.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        pass
    finally:
        # Clean up session on disconnect
        async with _sessions_lock:
            removed = _sessions.pop(session_id, None)
        if removed:
            try:
                await removed.disconnect()
            except Exception:
                pass


def ingest(pdf_path: str) -> None:
    api_key = os.environ.get("UNSILOED_API_KEY")
    if not api_key:
        sys.exit("Error: UNSILOED_API_KEY not set. Add it to .env file.")

    pdf_path = Path(pdf_path).resolve()
    if not pdf_path.exists():
        sys.exit(f"Error: File not found: {pdf_path}")

    file_size_mb = pdf_path.stat().st_size / (1024 * 1024)
    print(f"[1/4] Submitting {pdf_path.name} ({file_size_mb:.1f} MB) to Unsiloed.ai ...")

    with UnsiloedClient(api_key=api_key) as client:
        submit_start = time.time()
        response = client.parse(file=str(pdf_path))
        job_id = response.job_id
        elapsed = time.time() - submit_start
        print(f"       Job submitted in {elapsed:.1f}s — job_id: {job_id}")
        print(f"       Status: {response.status}")

        # Poll with verbose logging
        poll_interval = 3.0
        max_wait = 600.0
        poll_start = time.time()
        poll_count = 0

        while True:
            time.sleep(poll_interval)
            poll_count += 1
            elapsed = time.time() - poll_start
            result = client.get_parse_result(job_id)
            status = result.status

            page_info = f", pages: {result.page_count}" if result.page_count else ""
            msg_info = f" — {result.message}" if result.message else ""
            print(f"       [{elapsed:5.1f}s] Poll #{poll_count}: status={status}{page_info}{msg_info}")

            if status in ("Succeeded", "completed"):
                break
            if status in ("Failed", "failed"):
                sys.exit(f"Error: Unsiloed job failed: {result.error or result.message}")
            if elapsed > max_wait:
                sys.exit(f"Error: Timed out after {max_wait}s waiting for job {job_id}")

    total_time = time.time() - submit_start
    print(f"       Parsing complete in {total_time:.1f}s — {result.total_chunks} chunks, {result.page_count or '?'} pages")
    print(f"       Credits used: {result.credit_used}, remaining: {result.quota_remaining}")

    print(f"\n[2/4] Processing {result.total_chunks} chunks ...")
    OUTPUT_DIR.mkdir(exist_ok=True)
    chunks_data = []
    all_markdown = []
    empty_count = 0

    for i, chunk in enumerate(result.chunks):
        chunk_dict = {
            "chunk_id": chunk.get("chunk_id", i),
            "embed": chunk.get("embed", ""),
            "segments": chunk.get("segments", []),
        }
        chunks_data.append(chunk_dict)

        embed_text = chunk.get("embed", "")
        if embed_text:
            all_markdown.append(f"## Chunk {i}\n\n{embed_text}\n")
        else:
            empty_count += 1

        if (i + 1) % 50 == 0:
            print(f"       Processed {i + 1}/{result.total_chunks} chunks ...")

    if empty_count:
        print(f"       Skipped {empty_count} empty chunks")

    print(f"\n[3/4] Writing output files ...")
    # Write structured JSON
    json_path = OUTPUT_DIR / f"{pdf_path.stem}.json"
    with open(json_path, "w") as f:
        json.dump(chunks_data, f, indent=2, default=str)
    json_size_kb = json_path.stat().st_size / 1024
    print(f"       Saved JSON ({json_size_kb:.0f} KB): {json_path}")

    # Write combined markdown
    md_path = OUTPUT_DIR / f"{pdf_path.stem}.md"
    with open(md_path, "w") as f:
        f.write(f"# {pdf_path.stem}\n\n")
        f.write("\n".join(all_markdown))
    md_size_kb = md_path.stat().st_size / 1024
    print(f"       Saved Markdown ({md_size_kb:.0f} KB): {md_path}")

    print(f"\n[4/4] Storing in ChromaDB ...")
    chroma_start = time.time()
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
        embedding_function=voyage_ef,
    )

    # Batch insert (ChromaDB limit is 5461 per batch)
    batch_size = 5000
    ids = []
    documents = []
    metadatas = []

    for i, chunk in enumerate(chunks_data):
        text = chunk["embed"]
        if not text.strip():
            continue
        ids.append(f"{pdf_path.stem}_{i}")
        documents.append(text)
        meta = {"source": pdf_path.name, "chunk_index": i}
        # Add page numbers from segments if available
        segments = chunk.get("segments", [])
        if segments:
            pages = sorted({s.get("page_number", 0) for s in segments if isinstance(s, dict)})
            if pages:
                meta["pages"] = ",".join(str(p) for p in pages)
        metadatas.append(meta)

    print(f"       Prepared {len(ids)} non-empty chunks for embedding")
    for start in range(0, len(ids), batch_size):
        end = min(start + batch_size, len(ids))
        print(f"       Upserting batch {start + 1}–{end} ...")
        collection.upsert(
            ids=ids[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )

    chroma_elapsed = time.time() - chroma_start
    total_elapsed = time.time() - submit_start
    print(f"       ChromaDB done in {chroma_elapsed:.1f}s")
    print(f"\nAll done! {len(ids)} chunks stored in {CHROMA_DIR}")
    print(f"Total time: {total_elapsed:.1f}s")


def query(question: str, image_files: list[str] | None = None) -> None:
    global _collection
    if not CHROMA_DIR.exists():
        sys.exit("Error: No ChromaDB found. Run 'ingest' first.")

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    _collection = client.get_collection(name=COLLECTION_NAME, embedding_function=voyage_ef)
    IMAGES_DIR.mkdir(exist_ok=True)

    image_paths: list[Path] = []
    for img_file in image_files or []:
        src = Path(img_file).resolve()
        if not src.exists():
            sys.exit(f"Error: Image not found: {src}")
        dest = IMAGES_DIR / f"{uuid.uuid4().hex}_{src.name}"
        shutil.copy2(src, dest)
        image_paths.append(dest)

    print(f"\nSearching manual and generating answer...\n")

    async def _run():
        return await _ask_claude(question, image_paths=image_paths)

    answer = anyio.run(_run)
    print(answer.summary)
    for i, step in enumerate(answer.steps, 1):
        print(f"  {i}. {step}")
    if answer.pages_referenced:
        print(f"\nPages: {', '.join(answer.pages_referenced)}")


def main():
    parser = argparse.ArgumentParser(description="Vehicle manual ingester")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Parse PDF and store in ChromaDB")
    ingest_parser.add_argument("pdf", help="Path to the PDF file")

    query_parser = subparsers.add_parser("query", help="Query the stored manual")
    query_parser.add_argument("question", help="Question to search for")
    query_parser.add_argument("--image", action="append", default=[], help="Image file(s) to include")

    serve_parser = subparsers.add_parser("serve", help="Start the HTTP API server")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to bind to")

    args = parser.parse_args()

    if args.command == "ingest":
        ingest(args.pdf)
    elif args.command == "query":
        query(args.question, image_files=args.image)
    elif args.command == "serve":
        import uvicorn
        uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
