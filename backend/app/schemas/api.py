"""Pydantic request/response models for the REST API."""

from datetime import datetime

from pydantic import BaseModel


class AuthVerifyRequest(BaseModel):
    firebase_token: str


class AuthVerifyResponse(BaseModel):
    user_id: str


class SessionCreate(BaseModel):
    manual_id: str
    title: str


class SessionResponse(BaseModel):
    id: str
    manual_id: str
    title: str
    created_at: datetime


class MessageCreate(BaseModel):
    content: str


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime


class ManualSearchRequest(BaseModel):
    query: str
    manual_id: str | None = None


class ManualSearchResponse(BaseModel):
    results: list[dict]
