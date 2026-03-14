"""Tests for the PDF processing pipeline."""

import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.db.models import Manual, ManualStatus
from app.services.pdf_processor import process_pdf
from app.services.rag import RAGService


@pytest_asyncio.fixture
async def manual(db):
    """Create a test manual in the database."""
    manual_id = str(uuid.uuid4())
    manual = Manual(
        id=manual_id,
        filename="test_manual.pdf",
        car_make="Toyota",
        car_model="Camry",
        car_year=2024,
        status=ManualStatus.pending,
        created_at=datetime.utcnow(),
    )
    db.add(manual)
    await db.commit()
    return manual


@pytest.fixture
def rag_service(tmp_path):
    """Provide a RAG service backed by a temp directory."""
    return RAGService(str(tmp_path / "chromadb"))


@pytest.fixture
def mock_unsiloed_result():
    """Create a mock Unsiloed parse result."""
    result = MagicMock()
    result.status = "Succeeded"
    result.page_count = 10
    result.total_chunks = 3
    result.chunks = [
        {"chunk_id": 0, "embed": "How to change oil in your Toyota Camry.", "segments": [{"page_number": 1}]},
        {"chunk_id": 1, "embed": "Tire pressure should be 32 PSI for front tires.", "segments": [{"page_number": 2}]},
        {"chunk_id": 2, "embed": "Check brake fluid level monthly.", "segments": [{"page_number": 3}]},
    ]
    return result


@pytest.fixture
def mock_client(mock_unsiloed_result):
    """Create a mock UnsiloedClient."""
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    parse_response = MagicMock()
    parse_response.job_id = "test-job-123"
    parse_response.status = "processing"
    client.parse.return_value = parse_response
    client.get_parse_result.return_value = mock_unsiloed_result
    return client


@pytest.mark.asyncio
async def test_process_pdf_sets_status_processing(db, manual, rag_service, mock_client, tmp_path):
    """Manual status changes to 'processing' at start."""
    # We'll track status changes by patching to capture the intermediate state
    statuses_seen = []
    original_commit = db.commit

    async def tracking_commit(*args, **kwargs):
        result = await db.execute(select(Manual).where(Manual.id == manual.id))
        m = result.scalar_one()
        statuses_seen.append(m.status)
        return await original_commit(*args, **kwargs)

    db.commit = tracking_commit

    with patch("app.services.pdf_processor.UnsiloedClient", return_value=mock_client):
        await process_pdf(
            file_path=str(tmp_path / "test.pdf"),
            manual_id=manual.id,
            rag_service=rag_service,
            db=db,
            processed_dir=str(tmp_path / "processed"),
        )

    assert ManualStatus.processing in statuses_seen


@pytest.mark.asyncio
async def test_process_pdf_calls_unsiloed(db, manual, rag_service, mock_client, tmp_path):
    """UnsiloedClient.parse is called with the file path."""
    with patch("app.services.pdf_processor.UnsiloedClient", return_value=mock_client):
        await process_pdf(
            file_path=str(tmp_path / "test.pdf"),
            manual_id=manual.id,
            rag_service=rag_service,
            db=db,
            processed_dir=str(tmp_path / "processed"),
        )

    mock_client.parse.assert_called_once()
    call_kwargs = mock_client.parse.call_args
    assert str(tmp_path / "test.pdf") in str(call_kwargs)


@pytest.mark.asyncio
async def test_process_pdf_indexes_chunks(db, manual, rag_service, mock_client, tmp_path):
    """Chunks from Unsiloed response are indexed into RAG service."""
    with patch("app.services.pdf_processor.UnsiloedClient", return_value=mock_client):
        await process_pdf(
            file_path=str(tmp_path / "test.pdf"),
            manual_id=manual.id,
            rag_service=rag_service,
            db=db,
            processed_dir=str(tmp_path / "processed"),
        )

    # RAG service should have 3 chunks indexed
    results = rag_service.search("oil change", manual_id=manual.id)
    assert len(results) > 0


@pytest.mark.asyncio
async def test_process_pdf_sets_status_completed(db, manual, rag_service, mock_client, tmp_path):
    """Manual status is 'completed' after successful processing."""
    with patch("app.services.pdf_processor.UnsiloedClient", return_value=mock_client):
        await process_pdf(
            file_path=str(tmp_path / "test.pdf"),
            manual_id=manual.id,
            rag_service=rag_service,
            db=db,
            processed_dir=str(tmp_path / "processed"),
        )

    result = await db.execute(select(Manual).where(Manual.id == manual.id))
    m = result.scalar_one()
    assert m.status == ManualStatus.completed


@pytest.mark.asyncio
async def test_process_pdf_sets_chunk_count(db, manual, rag_service, mock_client, tmp_path):
    """manual.chunk_count equals number of chunks returned."""
    with patch("app.services.pdf_processor.UnsiloedClient", return_value=mock_client):
        await process_pdf(
            file_path=str(tmp_path / "test.pdf"),
            manual_id=manual.id,
            rag_service=rag_service,
            db=db,
            processed_dir=str(tmp_path / "processed"),
        )

    result = await db.execute(select(Manual).where(Manual.id == manual.id))
    m = result.scalar_one()
    assert m.chunk_count == 3


@pytest.mark.asyncio
async def test_process_pdf_writes_markdown(db, manual, rag_service, mock_client, tmp_path):
    """Markdown file exists at processed_dir/{manual_id}.md."""
    processed_dir = str(tmp_path / "processed")

    with patch("app.services.pdf_processor.UnsiloedClient", return_value=mock_client):
        await process_pdf(
            file_path=str(tmp_path / "test.pdf"),
            manual_id=manual.id,
            rag_service=rag_service,
            db=db,
            processed_dir=processed_dir,
        )

    md_path = Path(processed_dir) / f"{manual.id}.md"
    assert md_path.exists()
    content = md_path.read_text()
    assert "oil" in content.lower()
    assert "tire pressure" in content.lower()


@pytest.mark.asyncio
async def test_process_pdf_error_sets_failed(db, manual, rag_service, tmp_path):
    """On Unsiloed API error, status is 'failed' and error_message is set."""
    error_client = MagicMock()
    error_client.__enter__ = MagicMock(return_value=error_client)
    error_client.__exit__ = MagicMock(return_value=False)
    error_client.parse.side_effect = RuntimeError("Unsiloed API unavailable")

    with patch("app.services.pdf_processor.UnsiloedClient", return_value=error_client):
        await process_pdf(
            file_path=str(tmp_path / "test.pdf"),
            manual_id=manual.id,
            rag_service=rag_service,
            db=db,
            processed_dir=str(tmp_path / "processed"),
        )

    result = await db.execute(select(Manual).where(Manual.id == manual.id))
    m = result.scalar_one()
    assert m.status == ManualStatus.failed
    assert "Unsiloed API unavailable" in m.error_message


@pytest.mark.asyncio
async def test_process_pdf_sets_page_count(db, manual, rag_service, mock_client, tmp_path):
    """manual.page_count is set from the Unsiloed result."""
    with patch("app.services.pdf_processor.UnsiloedClient", return_value=mock_client):
        await process_pdf(
            file_path=str(tmp_path / "test.pdf"),
            manual_id=manual.id,
            rag_service=rag_service,
            db=db,
            processed_dir=str(tmp_path / "processed"),
        )

    result = await db.execute(select(Manual).where(Manual.id == manual.id))
    m = result.scalar_one()
    assert m.page_count == 10
