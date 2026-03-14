"""PDF processing pipeline using Unsiloed.ai."""

import asyncio
import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from unsiloed_sdk import UnsiloedClient

from app.config import settings
from app.db.models import Manual, ManualStatus
from app.services.rag import RAGService

# Polling settings for Unsiloed job status
_POLL_INTERVAL = 3.0
_MAX_WAIT = 600.0


def _parse_pdf_sync(api_key: str, file_path: str) -> object:
    """Call Unsiloed API synchronously (meant to run in a thread)."""
    with UnsiloedClient(api_key=api_key) as client:
        response = client.parse(file=file_path)
        job_id = response.job_id

        # Poll until complete
        start = time.time()
        while True:
            time.sleep(_POLL_INTERVAL)
            result = client.get_parse_result(job_id)

            if result.status in ("Succeeded", "completed"):
                return result
            if result.status in ("Failed", "failed"):
                error = getattr(result, "error", None) or getattr(result, "message", "Unknown error")
                raise RuntimeError(f"Unsiloed job failed: {error}")
            if time.time() - start > _MAX_WAIT:
                raise RuntimeError(f"Timed out after {_MAX_WAIT}s waiting for Unsiloed job {job_id}")


async def process_pdf(
    file_path: str,
    manual_id: str,
    rag_service: RAGService,
    db: AsyncSession,
    processed_dir: str | None = None,
) -> None:
    """Process a PDF through Unsiloed.ai, index chunks, and update the manual record.

    Steps:
    1. Set manual status to 'processing'
    2. Call Unsiloed API to parse the PDF
    3. Map chunks and index into ChromaDB via RAGService
    4. Write concatenated markdown to processed_dir/{manual_id}.md
    5. Update manual status to 'completed' with chunk/page counts
    On error: set status to 'failed' with error message.
    """
    if processed_dir is None:
        processed_dir = settings.processed_dir

    # 1. Set status to processing
    result = await db.execute(select(Manual).where(Manual.id == manual_id))
    manual = result.scalar_one()
    manual.status = ManualStatus.processing
    await db.commit()

    try:
        # 2. Parse PDF via Unsiloed (synchronous SDK, run in thread)
        parse_result = await asyncio.to_thread(
            _parse_pdf_sync, settings.unsiloed_api_key, file_path
        )

        # 3. Map chunks for RAG indexing
        chunks = []
        all_markdown = []
        for i, chunk in enumerate(parse_result.chunks):
            embed_text = chunk.get("embed", "") if isinstance(chunk, dict) else getattr(chunk, "embed", "")
            if not embed_text:
                continue

            chunks.append({
                "text": embed_text,
                "metadata": {
                    "manual_id": manual_id,
                    "chunk_index": i,
                },
            })
            all_markdown.append(f"## Chunk {i}\n\n{embed_text}\n")

        # Index into ChromaDB
        rag_service.index_chunks(manual_id, chunks)

        # 4. Write markdown output
        out_dir = Path(processed_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        md_path = out_dir / f"{manual_id}.md"
        md_path.write_text("\n".join(all_markdown))

        # 5. Update manual to completed
        result = await db.execute(select(Manual).where(Manual.id == manual_id))
        manual = result.scalar_one()
        manual.status = ManualStatus.completed
        manual.chunk_count = len(chunks)
        manual.page_count = getattr(parse_result, "page_count", None)
        await db.commit()

    except Exception as e:
        # Set status to failed with error message
        result = await db.execute(select(Manual).where(Manual.id == manual_id))
        manual = result.scalar_one()
        manual.status = ManualStatus.failed
        manual.error_message = str(e)
        await db.commit()
