"""Auth API endpoints."""

from fastapi import APIRouter, HTTPException

from app.schemas.api import AuthVerifyRequest, AuthVerifyResponse
from app.services.firebase_auth import verify_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/verify", response_model=AuthVerifyResponse)
async def verify_firebase_token(req: AuthVerifyRequest) -> AuthVerifyResponse:
    """Verify a Firebase ID token and return the user ID."""
    try:
        uid = await verify_token(req.firebase_token)
        return AuthVerifyResponse(user_id=uid)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
