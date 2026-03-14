"""
Ingest a vehicle service manual PDF via Unsiloed.ai and store chunks in ChromaDB.
Query the manual with AI-powered answers using Claude Sonnet.

Usage:
    uv run main.py ingest <path-to-pdf>       # Parse PDF and store in ChromaDB
    uv run main.py query  "your question"      # Query the manual with AI-powered answers
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.utils.embedding_functions import VoyageAIEmbeddingFunction
from dotenv import load_dotenv
from unsiloed_sdk import UnsiloedClient

import anyio
from claude_agent_sdk import (
    tool,
    create_sdk_mcp_server,
    query as claude_query,
    AssistantMessage,
    TextBlock,
    ResultMessage,
    ClaudeAgentOptions,
)

load_dotenv()

CHROMA_DIR = Path(__file__).parent / "chroma_db"
COLLECTION_NAME = "vehicle_manual"
OUTPUT_DIR = Path(__file__).parent / "output"

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


async def _ask_claude(question: str) -> str:
    """Use Claude Sonnet as an agent with a ChromaDB search tool to answer the question."""
    result: Optional[str] = None
    async for message in claude_query(
        prompt=question,
        options=ClaudeAgentOptions(
            model="claude-sonnet-4-6",
            system_prompt=SYSTEM_PROMPT,
            mcp_servers={"manual": _manual_server},
            allowed_tools=["mcp__manual__search_manual"],
            permission_mode="default",
            max_turns=6,
        ),
    ):
        if isinstance(message, ResultMessage) and message.result:
            result = message.result

    return result or "Something went wrong and I couldn't get an answer from the manual."


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


def query(question: str) -> None:
    global _collection
    if not CHROMA_DIR.exists():
        sys.exit("Error: No ChromaDB found. Run 'ingest' first.")

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    _collection = client.get_collection(name=COLLECTION_NAME, embedding_function=voyage_ef)

    print(f"\nSearching manual and generating answer...\n")
    answer = anyio.run(_ask_claude, question)
    print(answer)


def main():
    parser = argparse.ArgumentParser(description="Vehicle manual ingester")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Parse PDF and store in ChromaDB")
    ingest_parser.add_argument("pdf", help="Path to the PDF file")

    query_parser = subparsers.add_parser("query", help="Query the stored manual")
    query_parser.add_argument("question", help="Question to search for")

    args = parser.parse_args()

    if args.command == "ingest":
        ingest(args.pdf)
    elif args.command == "query":
        query(args.question)


if __name__ == "__main__":
    main()
