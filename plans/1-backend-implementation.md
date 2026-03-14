# Plan: WrenchAI Python Backend

## Context

Build the Python backend for an AI-powered car repair assistant that:
- Ingests car user manuals (PDF) via an admin UI and processes them into searchable chunks using Unsiloed.ai + ChromaDB RAG
- Serves a REST API for the iOS app: Firebase auth verification, conversation sessions, and AI-assisted message responses (Claude + RAG)
- Provides a NiceGUI admin panel for uploading manuals, monitoring processing status, and browsing extracted content

Key constraints:
- Hackathon project — ship fast, keep it simple
- SQLite (async) for metadata — no external DB dependency
- Unsiloed.ai for PDF parsing (cloud API, not local Docling)
- Firebase Auth for mobile users, simple username/password for admin
- ChromaDB with sentence-transformers for vector search
- NiceGUI mounted inside FastAPI at `/admin`

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    FastAPI Application                        │
│                                                              │
│  ┌─────────────────────┐     ┌────────────────────────────┐  │
│  │   /api  (REST)      │     │   /admin  (NiceGUI)        │  │
│  │                     │     │                            │  │
│  │  POST /auth/verify  │     │  /login  → admin login     │  │
│  │  POST /sessions     │     │  /       → dashboard+upload│  │
│  │  GET  /sessions     │     │  /browse → view content    │  │
│  │  POST /sessions/    │     │                            │  │
│  │    {id}/message     │     └────────────┬───────────────┘  │
│  │  GET  /sessions/    │                  │                  │
│  │    {id}/messages    │                  │                  │
│  │  POST /manuals/     │                  ▼                  │
│  │    search           │     ┌────────────────────────────┐  │
│  └────────┬────────────┘     │  pdf_processor.py          │  │
│           │                  │  Unsiloed.ai API → chunks  │  │
│           ▼                  └────────────┬───────────────┘  │
│  ┌─────────────────────┐                  │                  │
│  │  session_manager.py  │                  ▼                  │
│  │  ClaudeSDKClient per │     ┌────────────────────────────┐  │
│  │  session (Agent SDK) │◄───►│  rag.py                    │  │
│  │  + MCP search_manual │     │  ChromaDB + sentence-xfmrs │  │
│  └─────────────────────┘     └────────────────────────────┘  │
│                                                              │
│  ┌─────────────────────┐     ┌────────────────────────────┐  │
│  │  SQLite (aiosqlite) │     │  firebase_auth.py          │  │
│  │  admins, manuals,   │     │  verify Firebase tokens    │  │
│  │  sessions, messages │     └────────────────────────────┘  │
│  └─────────────────────┘                                     │
└──────────────────────────────────────────────────────────────┘
```

---

## New File Structure

```
backend/
├── pyproject.toml                         # NEW — project deps + metadata
├── .env.example                           # NEW — env var template
├── conftest.py                            # NEW — shared pytest fixtures
├── app/
│   ├── __init__.py                        # NEW — package marker
│   ├── main.py                            # NEW — FastAPI + NiceGUI entry point
│   ├── config.py                          # NEW — pydantic-settings config
│   ├── db/
│   │   ├── __init__.py                    # NEW — package marker
│   │   ├── database.py                    # NEW — async engine + session factory
│   │   ├── models.py                      # NEW — ORM models (Admin, Manual, Session, Message)
│   │   └── seed.py                        # NEW — seed default admin user
│   ├── api/
│   │   ├── __init__.py                    # NEW — package marker
│   │   ├── router.py                      # NEW — aggregate API routers
│   │   ├── deps.py                        # NEW — FastAPI dependencies (get_db, get_current_user)
│   │   ├── auth.py                        # NEW — POST /api/auth/verify
│   │   ├── sessions.py                    # NEW — POST/GET /api/sessions
│   │   ├── messages.py                    # NEW — POST/GET /api/sessions/{id}/message(s)
│   │   └── manuals.py                     # NEW — POST /api/manuals/search
│   ├── admin/
│   │   ├── __init__.py                    # NEW — package marker
│   │   └── pages.py                       # NEW — NiceGUI admin pages
│   ├── services/
│   │   ├── __init__.py                    # NEW — package marker
│   │   ├── pdf_processor.py              # NEW — Unsiloed.ai parse pipeline
│   │   ├── rag.py                         # NEW — ChromaDB + embeddings
│   │   ├── session_manager.py              # NEW — Claude Agent SDK session manager
│   │   └── firebase_auth.py              # NEW — Firebase token verification
│   └── schemas/
│       ├── __init__.py                    # NEW — package marker
│       └── api.py                         # NEW — Pydantic request/response models
├── data/                                  # RUNTIME — gitignored
│   ├── uploads/
│   ├── processed/
│   ├── wrenchai.db
│   ├── sessions/                          # RUNTIME — per-session agent working dirs
│   └── chromadb/
└── tests/
    ├── __init__.py                        # NEW
    ├── conftest.py                        # NEW — test DB fixtures
    ├── test_config.py                     # NEW — Phase 1
    ├── test_database.py                   # NEW — Phase 1
    ├── test_rag.py                        # NEW — Phase 2
    ├── test_pdf_processor.py             # NEW — Phase 3
    ├── test_session_manager.py             # NEW — Phase 4
    ├── test_api_auth.py                   # NEW — Phase 5
    ├── test_api_sessions.py              # NEW — Phase 5
    └── test_api_messages.py              # NEW — Phase 5
```

---

## Detailed Design

### 1. `backend/app/config.py` — Application settings

Central configuration via pydantic-settings. Reads `.env` file and environment variables.

```python
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    # Unsiloed.ai
    unsiloed_api_key: str = ""

    # Claude Agent SDK
    claude_model: str = "claude-sonnet-4-20250514"
    session_idle_timeout_minutes: int = 30
    session_cleanup_interval_minutes: int = 5
    sessions_dir: str = "data/sessions"

    # Admin credentials
    admin_username: str = "admin"
    admin_password: str = "changeme"

    # Database
    database_url: str = "sqlite+aiosqlite:///data/wrenchai.db"

    # ChromaDB
    chromadb_path: str = "data/chromadb"

    # File paths
    upload_dir: str = "data/uploads"
    processed_dir: str = "data/processed"

    # NiceGUI
    storage_secret: str = "wrenchai-secret"

    # Firebase
    firebase_credentials_path: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

settings = Settings()
```

### 2. `backend/app/db/database.py` — Async database engine

Creates async SQLAlchemy engine and session factory for SQLite.

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from collections.abc import AsyncGenerator

async def init_db() -> None: ...
async def get_db() -> AsyncGenerator[AsyncSession, None]: ...
```

### 3. `backend/app/db/models.py` — ORM models

Four tables: `admins`, `manuals`, `sessions`, `messages`.

```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, JSON, ForeignKey
import enum

class Base(DeclarativeBase): ...

class ManualStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"

class Admin(Base):
    __tablename__ = "admins"
    id: Mapped[int]  # primary_key, autoincrement
    username: Mapped[str]  # unique, String(100)
    password_hash: Mapped[str]  # String(255)

class Manual(Base):
    __tablename__ = "manuals"
    id: Mapped[str]  # primary_key, UUID string
    filename: Mapped[str]
    car_make: Mapped[str]
    car_model: Mapped[str]
    car_year: Mapped[int]
    status: Mapped[ManualStatus]  # default=pending
    error_message: Mapped[str | None]
    page_count: Mapped[int | None]
    chunk_count: Mapped[int | None]
    created_at: Mapped[datetime]

class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str]  # primary_key, UUID string
    user_id: Mapped[str]  # Firebase UID
    manual_id: Mapped[str]  # ForeignKey("manuals.id")
    title: Mapped[str]
    created_at: Mapped[datetime]

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str]  # primary_key, UUID string
    session_id: Mapped[str]  # ForeignKey("sessions.id")
    role: Mapped[str]  # "user" or "assistant"
    content: Mapped[str]  # Text
    rag_context: Mapped[dict | None]  # JSON, nullable
    created_at: Mapped[datetime]
```

### 4. `backend/app/db/seed.py` — Seed default admin

```python
from passlib.hash import bcrypt
from sqlalchemy import select

async def seed_admin(db: AsyncSession) -> None: ...
```

Creates the default admin user if it doesn't already exist. Uses bcrypt for password hashing.

### 5. `backend/app/services/rag.py` — ChromaDB vector search

```python
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

class RAGService:
    def __init__(self, persist_path: str) -> None: ...
    def index_chunks(self, manual_id: str, chunks: list[dict]) -> int: ...
    def search(self, query: str, manual_id: str | None = None, top_k: int = 5) -> list[dict]: ...
    def delete_manual(self, manual_id: str) -> None: ...
```

- `index_chunks`: Takes `[{"text": str, "metadata": dict}]`, generates IDs as `{manual_id}_{chunk_index}`, adds to collection. Returns count indexed.
- `search`: Queries collection with optional `where={"manual_id": id}` filter. Returns `[{"text": str, "metadata": dict, "distance": float}]`.
- `delete_manual`: Deletes all documents where `manual_id` matches.

### 6. `backend/app/services/pdf_processor.py` — Unsiloed.ai PDF pipeline

```python
from unsiloed_sdk import UnsiloedClient

async def process_pdf(
    file_path: str,
    manual_id: str,
    rag_service: RAGService,
    db: AsyncSession,
) -> None: ...
```

Steps:
1. Set manual status to `processing` in DB
2. Call `client.parse_and_wait(file=file_path)` via `asyncio.to_thread`
3. Map `result.chunks` → `[{"text": chunk["embed"], "metadata": {"manual_id": ..., "chunk_index": ...}}]`
4. Call `rag_service.index_chunks(manual_id, chunks)`
5. Concatenate chunk markdown, write to `data/processed/{manual_id}.md`
6. Update manual: `status=completed`, `chunk_count=len(chunks)`
7. On error: `status=failed`, `error_message=str(e)`

### 7. `backend/app/services/session_manager.py` — Claude Agent SDK session manager

Uses [claude-agent-sdk](https://github.com/anthropics/claude-agent-sdk-python) to maintain long-running Claude sessions per conversation.

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, tool, create_sdk_mcp_server

SYSTEM_PROMPT = """You are WrenchAI, an expert car repair and maintenance assistant.
You help users diagnose issues, perform repairs, and understand their vehicle
using their specific car's user manual.
- Give clear, step-by-step instructions suitable for someone working with their hands.
- Use the search_manual tool to look up relevant sections before answering technical questions.
- Warn about safety hazards (hot engine, jack stands, battery disconnect, etc.).
- Keep responses concise but thorough — the user may be listening via text-to-speech.
"""

def _build_search_manual_tool(rag_service: RAGService, manual_id: str):
    """Create a search_manual MCP tool bound to a specific manual's RAG index."""
    @tool("search_manual", "Search the car's user manual for relevant info.", {"query": str})
    async def search_manual(args: dict) -> dict:
        results = rag_service.search(query=args["query"], manual_id=manual_id, top_k=5)
        # format results as text content blocks
    return search_manual

@dataclass
class SessionState:
    client: ClaudeSDKClient
    last_activity: datetime
    manual_id: str
    session_dir: Path

class SessionManager:
    def __init__(self, rag_service: RAGService, sessions_dir: str, model: str,
                 idle_timeout_minutes: int, cleanup_interval_minutes: int) -> None: ...
    async def start_cleanup_task(self) -> None: ...       # background asyncio task, runs every N min
    async def get_or_create_session(self, session_id: str, manual_id: str) -> SessionState: ...
    async def send_message(self, session_id: str, user_message: str, manual_id: str) -> str: ...
    async def close_session(self, session_id: str) -> None: ...
    async def close_all(self) -> None: ...                # shutdown: close all sessions, cancel cleanup
```

Key design:
- **One `ClaudeSDKClient` per conversation session** — SDK maintains context automatically across `query()` calls (no manual history management needed)
- **RAG exposed as MCP tool** — `search_manual` is registered via `create_sdk_mcp_server()`. Claude decides when/what to search (can search multiple times with refined queries)
- **`_build_search_manual_tool` closure** — binds the tool to a specific `manual_id` so Claude always searches the correct manual
- **`asyncio.Lock`** protects `_sessions` dict for concurrent access
- **Background cleanup loop** — runs every `cleanup_interval_minutes`, closes sessions idle > `idle_timeout_minutes`
- **Per-session directories** at `data/sessions/{session_id}/` used as agent `cwd`

### 8. `backend/app/services/firebase_auth.py` — Firebase token verification

```python
import firebase_admin
from firebase_admin import auth as firebase_auth

def init_firebase(credentials_path: str) -> None: ...
async def verify_token(token: str) -> str: ...  # returns uid
```

### 9. `backend/app/schemas/api.py` — Pydantic models

```python
from pydantic import BaseModel
from datetime import datetime

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
```

### 10. `backend/app/api/deps.py` — FastAPI dependencies

```python
from fastapi import Depends, Header, HTTPException
from app.services.session_manager import SessionManager

async def get_db() -> AsyncGenerator[AsyncSession, None]: ...
async def get_current_user(authorization: str = Header(...)) -> str: ...  # returns Firebase UID
def get_session_manager() -> SessionManager: ...  # returns the global SessionManager instance
def set_session_manager(sm: SessionManager) -> None: ...  # called once at startup
```

### 11. `backend/app/api/auth.py` — Auth endpoint

```python
router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/verify", response_model=AuthVerifyResponse)
async def verify_firebase_token(req: AuthVerifyRequest) -> AuthVerifyResponse: ...
```

### 12. `backend/app/api/sessions.py` — Session endpoints

```python
router = APIRouter(prefix="/sessions", tags=["sessions"])

@router.post("/", response_model=SessionResponse)
async def create_session(req: SessionCreate, user_id: str = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> SessionResponse: ...

@router.get("/", response_model=list[SessionResponse])
async def list_sessions(user_id: str = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list[SessionResponse]: ...
```

### 13. `backend/app/api/messages.py` — Message endpoints (core conversation)

```python
router = APIRouter(prefix="/sessions/{session_id}", tags=["messages"])

@router.post("/message", response_model=MessageResponse)
async def send_message(session_id: str, req: MessageCreate, user_id: str = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> MessageResponse: ...

@router.get("/messages", response_model=list[MessageResponse])
async def get_messages(session_id: str, user_id: str = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list[MessageResponse]: ...
```

`send_message` flow: verify ownership → save user msg → `session_manager.send_message()` → save assistant msg → return. RAG search happens inside the agent via the `search_manual` MCP tool (no explicit RAG call in the endpoint).

### 14. `backend/app/api/manuals.py` — Manual search endpoint

```python
router = APIRouter(prefix="/manuals", tags=["manuals"])

@router.post("/search", response_model=ManualSearchResponse)
async def search_manuals(req: ManualSearchRequest) -> ManualSearchResponse: ...
```

### 15. `backend/app/api/router.py` — Aggregate routers

```python
from fastapi import APIRouter
api_router = APIRouter(prefix="/api")
# includes auth, sessions, messages, manuals routers
```

### 16. `backend/app/admin/pages.py` — NiceGUI admin pages

Three pages:
- `/admin/login`: username/password form, verifies against DB, sets `app.storage.user`
- `/admin/`: dashboard with file upload, car metadata fields, status table with auto-refresh
- `/admin/browse`: list completed manuals, view markdown, test RAG search

### 17. `backend/app/main.py` — Application entry point

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with async_session() as db:
        await seed_admin(db)

    # Initialize services
    rag_service = RAGService(settings.chromadb_path)
    session_manager = SessionManager(
        rag_service=rag_service,
        sessions_dir=settings.sessions_dir,
        model=settings.claude_model,
        idle_timeout_minutes=settings.session_idle_timeout_minutes,
        cleanup_interval_minutes=settings.session_cleanup_interval_minutes,
    )
    await session_manager.start_cleanup_task()
    set_session_manager(session_manager)

    yield

    await session_manager.close_all()

app = FastAPI(lifespan=lifespan)
app.include_router(api_router)
# NiceGUI page registrations
# ui.run_with(app, mount_path="/admin", storage_secret=settings.storage_secret)
```

---

## Phase-by-Phase Execution

> **Execution note:** Each phase below should be executed by a separate Agent invocation
> (subagent_type: "general-purpose", model: "claude-opus-4-6") to ensure a full context window per phase.
> The orchestrator launches one Agent per phase sequentially.

---

### Phase 1: Project Scaffold + Config + Database

**Goal**: Set up project structure, configuration, database engine, ORM models, and admin seeding.

**RED — Write failing tests**

Test file: `backend/tests/test_config.py`

| Test | What it checks |
|------|----------------|
| `test_settings_defaults` | `Settings()` loads with expected default values (admin_username="admin", etc.) |
| `test_settings_database_url_default` | Default database_url contains "sqlite+aiosqlite" |

Test file: `backend/tests/test_database.py`

| Test | What it checks |
|------|----------------|
| `test_init_db_creates_tables` | After `init_db()`, all four tables exist (admins, manuals, sessions, messages) |
| `test_create_admin` | Can insert an `Admin` row and read it back |
| `test_create_manual` | Can insert a `Manual` with all fields, default status is "pending" |
| `test_create_session_with_manual_fk` | `Session.manual_id` references an existing `Manual` |
| `test_create_message_with_session_fk` | `Message.session_id` references an existing `Session` |
| `test_manual_status_enum` | `ManualStatus` has exactly: pending, processing, completed, failed |
| `test_seed_admin_creates_user` | `seed_admin()` creates an admin when none exists |
| `test_seed_admin_idempotent` | Calling `seed_admin()` twice doesn't create duplicates |

Test fixture file: `backend/tests/conftest.py` — provides `db` fixture using in-memory SQLite (`sqlite+aiosqlite://`).

Run: `cd backend && uv run pytest tests/test_config.py tests/test_database.py -v` — expect FAIL (ImportError).

**GREEN — Implement**

1. Create `backend/pyproject.toml` with all dependencies and `[project.scripts]` entry
2. Create `backend/.env.example` with template env vars
3. Create `backend/app/__init__.py`, `backend/app/db/__init__.py`, `backend/app/api/__init__.py`, `backend/app/admin/__init__.py`, `backend/app/services/__init__.py`, `backend/app/schemas/__init__.py`
4. Create `backend/app/config.py` — `Settings` class with all fields
5. Create `backend/app/db/models.py` — `Base`, `ManualStatus`, `Admin`, `Manual`, `Session`, `Message`
6. Create `backend/app/db/database.py` — `engine`, `async_session`, `init_db()`, `get_db()`
7. Create `backend/app/db/seed.py` — `seed_admin()`
8. Create `backend/tests/__init__.py`, `backend/tests/conftest.py` with in-memory DB fixture
9. Create `backend/app/main.py` — minimal FastAPI app with lifespan (init_db + seed)
10. Run `cd backend && uv sync` to install deps

Run: `cd backend && uv run pytest tests/test_config.py tests/test_database.py -v` — expect PASS.

**REVIEW+FIX CYCLE**

```
Launch Agent (subagent_type: "general-purpose", model: "claude-opus-4-6"):
  "Review Phase 1 of plans/3-backend.md: Project scaffold, config, and database.
   Files to review: backend/pyproject.toml, backend/app/config.py, backend/app/db/database.py,
   backend/app/db/models.py, backend/app/db/seed.py, backend/app/main.py,
   backend/tests/conftest.py, backend/tests/test_config.py, backend/tests/test_database.py.
   Check: all tests pass (cd backend && uv run pytest tests/ -v), code matches plan spec, no regressions.
   Phase-specific: Are all four ORM tables correct with proper types and FKs? Does seed_admin use bcrypt?
   Does the in-memory test fixture properly isolate tests? Does config load .env correctly?
   If issues found: fix them, re-run tests, and review again. Repeat until review is clean.
   When review is clean and all tests pass, report DONE with a summary of changes made."
```

**FULL SUITE**: `cd backend && uv run pytest tests/ -v` — no regressions.

**COMMIT**: `/commit` with message `"Phase 1: Project scaffold, config, and database layer"`

**Files Created**:
- `backend/pyproject.toml`
- `backend/.env.example`
- `backend/app/__init__.py`, `app/db/__init__.py`, `app/api/__init__.py`, `app/admin/__init__.py`, `app/services/__init__.py`, `app/schemas/__init__.py`
- `backend/app/config.py`
- `backend/app/db/database.py`
- `backend/app/db/models.py`
- `backend/app/db/seed.py`
- `backend/app/main.py`
- `backend/tests/__init__.py`
- `backend/tests/conftest.py`
- `backend/tests/test_config.py`
- `backend/tests/test_database.py`

---

### Phase 2: RAG Service (ChromaDB)

**Goal**: Implement the ChromaDB-backed vector search service with indexing, search, and deletion.

**RED — Write failing tests**

Test file: `backend/tests/test_rag.py`

| Test | What it checks |
|------|----------------|
| `test_index_chunks_returns_count` | `index_chunks()` returns the number of chunks indexed |
| `test_index_chunks_stores_documents` | After indexing, collection count matches chunk count |
| `test_search_returns_results` | `search(query)` returns list of dicts with text, metadata, distance |
| `test_search_with_manual_id_filter` | `search(query, manual_id="X")` only returns chunks from manual X |
| `test_search_top_k_limits_results` | `search(query, top_k=2)` returns at most 2 results |
| `test_search_empty_collection` | `search()` on empty collection returns empty list |
| `test_delete_manual_removes_chunks` | After `delete_manual(id)`, those chunks no longer appear in search |
| `test_delete_manual_preserves_others` | Deleting manual A doesn't affect manual B's chunks |

Use a temporary directory for ChromaDB persistence in tests (via `tmp_path` fixture).

Run: `cd backend && uv run pytest tests/test_rag.py -v` — expect FAIL (ImportError).

**GREEN — Implement**

1. Create `backend/app/services/rag.py` — `RAGService` class with `__init__`, `index_chunks`, `search`, `delete_manual`
2. Use `SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")`
3. Collection name: `"car_manuals"`, metadata: `{"hnsw:space": "cosine"}`
4. `index_chunks`: generate IDs as `f"{manual_id}_{chunk['metadata']['chunk_index']}"`, call `collection.add()`
5. `search`: build `where` filter if `manual_id` provided, call `collection.query()`, map results
6. `delete_manual`: call `collection.delete(where={"manual_id": manual_id})`

Run: `cd backend && uv run pytest tests/test_rag.py -v` — expect PASS.

**REVIEW+FIX CYCLE**

```
Launch Agent (subagent_type: "general-purpose", model: "claude-opus-4-6"):
  "Review Phase 2 of plans/3-backend.md: RAG service with ChromaDB.
   Files to review: backend/app/services/rag.py, backend/tests/test_rag.py.
   Check: all tests pass (cd backend && uv run pytest tests/ -v), code matches plan spec, no regressions.
   Phase-specific: Are ChromaDB IDs deterministic and unique? Does the where filter correctly scope by manual_id?
   Does delete_manual actually remove from the collection (not just hide)? Is the embedding function initialized once?
   If issues found: fix them, re-run tests, and review again. Repeat until review is clean.
   When review is clean and all tests pass, report DONE with a summary of changes made."
```

**FULL SUITE**: `cd backend && uv run pytest tests/ -v` — no regressions from Phase 1.

**COMMIT**: `/commit` with message `"Phase 2: RAG service with ChromaDB vector search"`

**Files Created**:
- `backend/app/services/rag.py`
- `backend/tests/test_rag.py`

---

### Phase 3: PDF Processing (Unsiloed.ai)

**Goal**: Implement the PDF processing pipeline that calls Unsiloed.ai, maps chunks, indexes into ChromaDB, and updates manual status.

**RED — Write failing tests**

Test file: `backend/tests/test_pdf_processor.py`

| Test | What it checks |
|------|----------------|
| `test_process_pdf_sets_status_processing` | Manual status changes to "processing" at start |
| `test_process_pdf_calls_unsiloed` | `UnsiloedClient.parse_and_wait` is called with the file path |
| `test_process_pdf_indexes_chunks` | Chunks from Unsiloed response are indexed into RAG service |
| `test_process_pdf_sets_status_completed` | Manual status is "completed" after successful processing |
| `test_process_pdf_sets_chunk_count` | `manual.chunk_count` equals number of chunks returned |
| `test_process_pdf_writes_markdown` | Markdown file exists at `data/processed/{manual_id}.md` |
| `test_process_pdf_error_sets_failed` | On Unsiloed API error, status is "failed" and error_message is set |

Mock `UnsiloedClient` in all tests. Use the in-memory DB fixture + a temp RAG service.

Run: `cd backend && uv run pytest tests/test_pdf_processor.py -v` — expect FAIL (ImportError).

**GREEN — Implement**

1. Create `backend/app/services/pdf_processor.py`
2. Implement `process_pdf(file_path, manual_id, rag_service, db)`:
   - Update manual status to `processing`
   - Run `client.parse_and_wait(file=file_path)` in `asyncio.to_thread()`
   - Map chunks: `{"text": chunk["embed"], "metadata": {"manual_id": manual_id, "chunk_index": i}}`
   - Call `rag_service.index_chunks(manual_id, chunks)`
   - Write concatenated markdown to `data/processed/{manual_id}.md`
   - Update manual: `status=completed`, `chunk_count=len(chunks)`
   - Wrap in try/except: on error, set `status=failed`, `error_message=str(e)`

Run: `cd backend && uv run pytest tests/test_pdf_processor.py -v` — expect PASS.

**REVIEW+FIX CYCLE**

```
Launch Agent (subagent_type: "general-purpose", model: "claude-opus-4-6"):
  "Review Phase 3 of plans/3-backend.md: PDF processing with Unsiloed.ai.
   Files to review: backend/app/services/pdf_processor.py, backend/tests/test_pdf_processor.py.
   Check: all tests pass (cd backend && uv run pytest tests/ -v), code matches plan spec, no regressions.
   Phase-specific: Is the Unsiloed call wrapped in asyncio.to_thread since the SDK is synchronous?
   Does error handling properly set failed status AND commit the DB change? Is the markdown file path correct?
   Are chunks correctly mapped from the Unsiloed response format (chunk['embed'] for text)?
   If issues found: fix them, re-run tests, and review again. Repeat until review is clean.
   When review is clean and all tests pass, report DONE with a summary of changes made."
```

**FULL SUITE**: `cd backend && uv run pytest tests/ -v` — no regressions from Phase 1-2.

**COMMIT**: `/commit` with message `"Phase 3: PDF processing pipeline with Unsiloed.ai"`

**Files Created**:
- `backend/app/services/pdf_processor.py`
- `backend/tests/test_pdf_processor.py`

---

### Phase 4: Session Manager (Claude Agent SDK)

**Goal**: Implement the Claude Agent SDK session manager with per-session clients, idle cleanup, and a custom MCP tool for RAG search.

**RED — Write failing tests**

Test file: `backend/tests/test_session_manager.py`

| Test | What it checks |
|------|----------------|
| `test_get_or_create_session_creates_new` | First call creates a `SessionState` and adds to `_sessions` dict |
| `test_get_or_create_session_returns_existing` | Second call with same `session_id` returns the same `SessionState` |
| `test_get_or_create_session_creates_directory` | Session directory `data/sessions/{session_id}/` is created |
| `test_send_message_returns_string` | `send_message()` returns a non-empty string response |
| `test_send_message_updates_last_activity` | `last_activity` is updated after `send_message()` |
| `test_send_message_calls_query_and_receive` | Client's `query()` is called with user message, then `receive_response()` is iterated |
| `test_close_session_removes_from_dict` | After `close_session()`, session is no longer in `_sessions` |
| `test_close_session_calls_aexit` | `close_session()` calls `__aexit__` on the client |
| `test_close_idle_sessions` | Sessions idle longer than timeout are closed automatically |
| `test_active_sessions_not_closed` | Sessions with recent activity survive the cleanup sweep |
| `test_close_all_cleans_everything` | `close_all()` closes all sessions and cancels the cleanup task |
| `test_search_manual_tool_returns_results` | The `search_manual` MCP tool function returns formatted RAG results |
| `test_search_manual_tool_no_results` | The tool returns "No relevant sections found" when RAG returns empty |
| `test_system_prompt_contains_persona` | `SYSTEM_PROMPT` contains "WrenchAI" and car repair guidance |

Mock `ClaudeSDKClient` as async context manager. Mock `query()` and `receive_response()`. Mock `RAGService` for tool tests.

Run: `cd backend && uv run pytest tests/test_session_manager.py -v` — expect FAIL (ImportError).

**GREEN — Implement**

1. Create `backend/app/services/session_manager.py`
2. Define `SYSTEM_PROMPT` constant with WrenchAI car repair persona (mentions `search_manual` tool)
3. Implement `_build_search_manual_tool(rag_service, manual_id)` — returns `@tool`-decorated function bound to the manual
4. Implement `SessionState` dataclass with `client`, `last_activity`, `manual_id`, `session_dir`
5. Implement `SessionManager`:
   - `__init__`: stores config, creates empty `_sessions` dict and `asyncio.Lock`
   - `start_cleanup_task()`: launches background `asyncio.Task` that calls `_close_idle_sessions()` periodically
   - `get_or_create_session(session_id, manual_id)`: creates session dir, builds MCP server with `search_manual` tool, creates `ClaudeSDKClient` with `ClaudeAgentOptions`, enters async context
   - `send_message(session_id, user_message, manual_id)`: gets/creates session, calls `client.query()`, collects `TextBlock` content from `receive_response()`, returns joined text
   - `close_session(session_id)`: pops from dict, calls `client.__aexit__()`
   - `close_all()`: cancels cleanup task, closes all sessions

Run: `cd backend && uv run pytest tests/test_session_manager.py -v` — expect PASS.

**REVIEW+FIX CYCLE**

```
Launch Agent (subagent_type: "general-purpose", model: "claude-opus-4-6"):
  "Review Phase 4 of plans/1-backend-implementation.md: Session Manager with Claude Agent SDK.
   Files to review: backend/app/services/session_manager.py, backend/tests/test_session_manager.py.
   Check: all tests pass (cd backend && uv run pytest tests/ -v), code matches plan spec, no regressions.
   Phase-specific: Does get_or_create_session properly handle concurrent access via asyncio.Lock?
   Does close_session call __aexit__ on the client? Does the MCP tool correctly bind to the manual_id?
   Does the cleanup loop close sessions idle > 30 min? Is the system prompt appropriate for a car repair assistant?
   Does send_message correctly collect all TextBlock content from the response stream?
   If issues found: fix them, re-run tests, and review again. Repeat until review is clean.
   When review is clean and all tests pass, report DONE with a summary of changes made."
```

**FULL SUITE**: `cd backend && uv run pytest tests/ -v` — no regressions from Phase 1-3.

**COMMIT**: `/commit` with message `"Phase 4: Session manager with Claude Agent SDK and MCP search tool"`

**Files Created**:
- `backend/app/services/session_manager.py`
- `backend/tests/test_session_manager.py`

---

### Phase 5: API Endpoints

**Goal**: Implement all REST API endpoints: auth verification, session CRUD, message send/list, and manual search.

**RED — Write failing tests**

Test file: `backend/tests/test_api_auth.py`

| Test | What it checks |
|------|----------------|
| `test_verify_valid_token` | POST `/api/auth/verify` with valid token returns `{"user_id": "..."}` |
| `test_verify_invalid_token` | POST with invalid token returns 401 |

Test file: `backend/tests/test_api_sessions.py`

| Test | What it checks |
|------|----------------|
| `test_create_session` | POST `/api/sessions/` with valid body creates session, returns 200 with id |
| `test_create_session_invalid_manual` | POST with non-existent manual_id returns 404 |
| `test_list_sessions` | GET `/api/sessions/` returns only sessions owned by the authenticated user |
| `test_list_sessions_empty` | GET returns empty list for user with no sessions |

Test file: `backend/tests/test_api_messages.py`

| Test | What it checks |
|------|----------------|
| `test_send_message_returns_response` | POST `/api/sessions/{id}/message` returns assistant message |
| `test_send_message_saves_both_messages` | After sending, DB contains both user and assistant messages |
| `test_send_message_wrong_session` | POST to session owned by different user returns 403 |
| `test_get_messages` | GET `/api/sessions/{id}/messages` returns messages in order |
| `test_get_messages_empty_session` | GET on new session returns empty list |

Use `httpx.AsyncClient` with FastAPI `TestClient`. Mock Firebase auth to return a test UID. Mock `SessionManager.send_message`. Use in-memory DB.

Run: `cd backend && uv run pytest tests/test_api_auth.py tests/test_api_sessions.py tests/test_api_messages.py -v` — expect FAIL (ImportError).

**GREEN — Implement**

1. Create `backend/app/schemas/api.py` — all Pydantic request/response models
2. Create `backend/app/services/firebase_auth.py` — `init_firebase()`, `verify_token()`
3. Create `backend/app/api/deps.py` — `get_db()` (reuses database.get_db), `get_current_user()` (extracts Bearer token, calls verify_token), `get_session_manager()` / `set_session_manager()`
4. Create `backend/app/api/auth.py` — `POST /auth/verify`
5. Create `backend/app/api/sessions.py` — `POST /sessions/`, `GET /sessions/`
6. Create `backend/app/api/messages.py` — `POST /sessions/{id}/message`, `GET /sessions/{id}/messages` (uses `SessionManager` dependency)
7. Create `backend/app/api/manuals.py` — `POST /manuals/search`
8. Create `backend/app/api/router.py` — aggregate all routers under `/api`
9. Update `backend/app/main.py` — register `api_router`, initialize `SessionManager` + RAG in lifespan, call `close_all()` on shutdown
10. Update `backend/tests/conftest.py` — add `client` fixture with dependency overrides for DB, auth, `SessionManager`

Run: `cd backend && uv run pytest tests/test_api_auth.py tests/test_api_sessions.py tests/test_api_messages.py -v` — expect PASS.

**REVIEW+FIX CYCLE**

```
Launch Agent (subagent_type: "general-purpose", model: "claude-opus-4-6"):
  "Review Phase 5 of plans/3-backend.md: API endpoints.
   Files to review: backend/app/schemas/api.py, backend/app/services/firebase_auth.py,
   backend/app/api/deps.py, backend/app/api/auth.py, backend/app/api/sessions.py,
   backend/app/api/messages.py, backend/app/api/manuals.py, backend/app/api/router.py,
   backend/app/main.py, backend/tests/conftest.py, backend/tests/test_api_auth.py,
   backend/tests/test_api_sessions.py, backend/tests/test_api_messages.py.
   Check: all tests pass (cd backend && uv run pytest tests/ -v), code matches plan spec, no regressions.
   Phase-specific: Does send_message correctly call session_manager.send_message() and save both user+assistant
   messages to DB? Is session ownership checked before message operations? Does get_current_user properly extract
   the Bearer token? Are dependency overrides in test fixtures complete and correct? Are all routes properly
   prefixed under /api?
   If issues found: fix them, re-run tests, and review again. Repeat until review is clean.
   When review is clean and all tests pass, report DONE with a summary of changes made."
```

**FULL SUITE**: `cd backend && uv run pytest tests/ -v` — no regressions from Phase 1-4.

**COMMIT**: `/commit` with message `"Phase 5: REST API endpoints for auth, sessions, and messages"`

**Files Created**:
- `backend/app/schemas/__init__.py` (if not already)
- `backend/app/schemas/api.py`
- `backend/app/services/firebase_auth.py`
- `backend/app/api/deps.py`
- `backend/app/api/auth.py`
- `backend/app/api/sessions.py`
- `backend/app/api/messages.py`
- `backend/app/api/manuals.py`
- `backend/app/api/router.py`
- `backend/tests/test_api_auth.py`
- `backend/tests/test_api_sessions.py`
- `backend/tests/test_api_messages.py`

**Files Modified**:
- `backend/app/main.py` — add router registration, SessionManager + RAG initialization in lifespan
- `backend/tests/conftest.py` — add client fixture with dependency overrides for DB, auth, SessionManager

---

### Phase 6: Admin UI (NiceGUI)

**Goal**: Implement the NiceGUI admin pages: login, dashboard with file upload + processing trigger, and browse page.

This phase is primarily UI code. TDD is limited for NiceGUI pages, so the RED step covers importability and basic page registration.

**RED — Write failing tests**

Test file: `backend/tests/test_admin.py`

| Test | What it checks |
|------|----------------|
| `test_admin_pages_importable` | `from app.admin.pages import setup_admin_pages` doesn't raise |
| `test_admin_login_page_registered` | NiceGUI has a page registered at `/admin/login` |

Run: `cd backend && uv run pytest tests/test_admin.py -v` — expect FAIL (ImportError).

**GREEN — Implement**

1. Create `backend/app/admin/pages.py`:
   - `setup_admin_pages(app: FastAPI, rag_service: RAGService, db_session_factory)` function
   - Login page (`/admin/login`): username/password form, verify with bcrypt against DB, set `app.storage.user["authenticated"] = True`
   - Dashboard (`/admin/`): auth guard, file upload widget with car make/model/year fields, processing status table with `ui.timer(5, refresh_table)`, trigger `asyncio.create_task(process_pdf(...))` on upload
   - Browse (`/admin/browse`): auth guard, list completed manuals, expandable sections showing markdown content, search box for testing RAG queries
2. Update `backend/app/main.py` — call `setup_admin_pages()` in lifespan, add `ui.run_with(app, mount_path="/admin", storage_secret=settings.storage_secret)`

Run: `cd backend && uv run pytest tests/test_admin.py -v` — expect PASS.

**REVIEW+FIX CYCLE**

```
Launch Agent (subagent_type: "general-purpose", model: "claude-opus-4-6"):
  "Review Phase 6 of plans/3-backend.md: NiceGUI admin UI.
   Files to review: backend/app/admin/pages.py, backend/app/main.py, backend/tests/test_admin.py.
   Check: all tests pass (cd backend && uv run pytest tests/ -v), code matches plan spec, no regressions.
   Phase-specific: Does login verify password with bcrypt? Does dashboard have auth guard (redirect to /admin/login
   if not authenticated)? Does file upload trigger background processing via asyncio.create_task? Does the
   status table auto-refresh? Does browse page read markdown from data/processed/?
   If issues found: fix them, re-run tests, and review again. Repeat until review is clean.
   When review is clean and all tests pass, report DONE with a summary of changes made."
```

**FULL SUITE**: `cd backend && uv run pytest tests/ -v` — no regressions from Phase 1-5.

**COMMIT**: `/commit` with message `"Phase 6: NiceGUI admin UI with login, dashboard, and browse"`

**Files Created**:
- `backend/app/admin/pages.py`
- `backend/tests/test_admin.py`

**Files Modified**:
- `backend/app/main.py` — NiceGUI integration

---

## Verification

After all phases are complete, run the following end-to-end checks:

```bash
# 1. Start the server
cd backend && uv run python -m app.main

# 2. Verify admin login page loads
curl -s http://localhost:8000/admin/login | grep -q "Login"

# 3. Verify API is reachable
curl -s http://localhost:8000/api/auth/verify \
  -H "Content-Type: application/json" \
  -d '{"firebase_token": "test"}' \
  | grep -q "user_id\|401"

# 4. Full test suite
cd backend && uv run pytest tests/ -v --tb=short

# 5. Manual browser check
# Open http://localhost:8000/admin/login
# Login with admin/changeme
# Upload a test PDF
# Verify processing completes
# Browse extracted content
# Test RAG search
```