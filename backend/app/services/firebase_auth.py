"""Firebase token verification."""

import asyncio

import firebase_admin
from firebase_admin import auth as firebase_auth, credentials


_initialized = False


def init_firebase(credentials_path: str) -> None:
    """Initialize Firebase Admin SDK with service account credentials."""
    global _initialized
    if _initialized:
        return
    if credentials_path:
        cred = credentials.Certificate(credentials_path)
        firebase_admin.initialize_app(cred)
    else:
        firebase_admin.initialize_app()
    _initialized = True


async def verify_token(token: str) -> str:
    """Verify a Firebase ID token and return the user's UID.

    Raises ValueError if the token is invalid.
    """
    decoded = await asyncio.to_thread(firebase_auth.verify_id_token, token)
    return decoded["uid"]
