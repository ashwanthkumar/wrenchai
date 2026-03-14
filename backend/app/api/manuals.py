"""Manual search API endpoint."""

from fastapi import APIRouter, Depends

from app.api.deps import get_rag_service
from app.schemas.api import ManualSearchRequest, ManualSearchResponse
from app.services.rag import RAGService

router = APIRouter(prefix="/manuals", tags=["manuals"])


@router.post("/search", response_model=ManualSearchResponse)
async def search_manuals(
    req: ManualSearchRequest,
    rag_service: RAGService = Depends(get_rag_service),
) -> ManualSearchResponse:
    """Search manual chunks using RAG vector search."""
    results = rag_service.search(
        query=req.query,
        manual_id=req.manual_id,
    )
    return ManualSearchResponse(results=results)
