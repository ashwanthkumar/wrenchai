# WrenchAI - Implementation Plan

## Context

Build an AI-powered car repair assistant that ingests car user manuals (PDF) and provides voice-guided repair/diagnosis assistance via an iOS app. The backend processes manuals into searchable content using RAG, and the iOS app enables hands-free voice conversations where AI guides the user through repairs step-by-step.

This is a hackathon project. Prioritize shipping speed over perfection.

---

## Architecture Overview

```
┌─────────────────────────┐         ┌──────────────────────────────┐
│   iOS App (WrenchAI)    │         │   Python Backend (FastAPI)   │
│                         │         │                              │
│  WhisperKit (STT)       │ ──────► │  /api/sessions/{id}/message  │
│  Silero VAD             │         │     ├─ RAG lookup (ChromaDB) │
│  Kokoro TTS (sherpa)    │ ◄────── │     ├─ Claude API response   │
│  Firebase Auth          │         │     └─ Return text           │
│                         │         │                              │
│  AVAudioEngine pipeline │         │  /admin (NiceGUI)            │
└─────────────────────────┘         │     ├─ Upload PDFs           │
                                    │     ├─ Unsiloed.ai parsing   │
                                    │     └─ Browse content        │
                                    └──────────────────────────────┘
```

---

## Part 1: Python Backend (`backend/`)

### Tech Stack
- **uv** for dependency management
- **FastAPI** for REST API
- **NiceGUI** for admin frontend (mounted at `/admin`)
- **Unsiloed.ai** (`unsiloed-sdk`) for PDF → structured markdown/chunks via API
- **ChromaDB** + **sentence-transformers** for RAG
- **Anthropic SDK** for Claude conversations
- **SQLite** (via SQLAlchemy async) for metadata
- **firebase-admin** for token verification

### Directory Structure

```
backend/
├── pyproject.toml
├── .env.example
├── .gitignore
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI + NiceGUI mount, entry point
│   ├── config.py                  # pydantic-settings
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py            # Async SQLite engine + session factory
│   │   ├── models.py              # ORM: admins, manuals, sessions, messages
│   │   └── seed.py                # Default admin user
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py              # Aggregates API routers
│   │   ├── deps.py                # Depends(): get_db, get_current_user
│   │   ├── auth.py                # POST /api/auth/verify
│   │   ├── sessions.py            # POST/GET /api/sessions
│   │   ├── messages.py            # POST/GET /api/sessions/{id}/message(s)
│   │   └── manuals.py             # POST /api/manuals/search
│   ├── admin/
│   │   ├── __init__.py
│   │   ├── pages.py               # NiceGUI pages: login, dashboard, browse
│   ├── services/
│   │   ├── __init__.py
│   │   ├── pdf_processor.py       # Unsiloed.ai parse + poll pipeline
│   │   ├── rag.py                 # ChromaDB + embeddings
│   │   ├── llm.py                 # Anthropic SDK wrapper
│   │   └── firebase_auth.py       # Firebase token verification
│   └── schemas/
│       ├── __init__.py
│       └── api.py                 # All Pydantic request/response models
├── data/                          # gitignored runtime data
│   ├── uploads/
│   ├── processed/
│   ├── magicball.db
│   └── chromadb/
└── tests/
```

### Key Files & Implementation Details

#### `pyproject.toml`
Dependencies: `fastapi`, `uvicorn[standard]`, `nicegui>=2.0`, `sqlalchemy`, `aiosqlite`, `pydantic-settings`, `anthropic`, `unsiloed-sdk`, `chromadb`, `sentence-transformers`, `firebase-admin`, `python-multipart`, `passlib[bcrypt]`

#### `app/main.py` - Entry Point
- Create FastAPI app with lifespan (init DB, init RAG on startup)
- Register API routers at `/api`
- Setup NiceGUI admin pages
- Mount NiceGUI via `ui.run_with(fastapi_app, mount_path="/admin", storage_secret=...)`
- Run with `uvicorn`

#### `app/db/models.py` - Database Tables
| Table | Key Fields |
|-------|-----------|
| `admins` | id, username, password_hash |
| `manuals` | id (UUID), filename, car_make, car_model, car_year, status (pending/processing/completed/failed), error_message, page_count, chunk_count |
| `sessions` | id (UUID), user_id (Firebase UID), manual_id (FK), title |
| `messages` | id (UUID), session_id (FK), role (user/assistant), content, rag_context (JSON) |

#### `app/services/pdf_processor.py` - PDF Pipeline (Unsiloed.ai)
Uses the Unsiloed.ai API (`unsiloed-sdk`) for cloud-based document parsing. Async, job-based workflow:

1. Upload PDF via `client.parse_and_wait(file=path)` (handles submit + polling internally)
2. SDK returns chunks with `embed` (text for embedding), markdown, HTML, segments, and layout metadata
3. Each chunk includes segment types: Title, SectionHeader, Text, ListItem, Table, Picture, Caption, etc.
4. Map chunks to ChromaDB documents: use `chunk['embed']` as the document text, attach metadata (manual_id, chunk_index, segment_types)
5. Index chunks into ChromaDB via `rag.index_chunks()`
6. Store raw markdown in `data/processed/{manual_id}.md` for admin browse view

```python
from unsiloed_sdk import UnsiloedClient

async def process_pdf(file_path: str, manual_id: str):
    with UnsiloedClient(api_key=settings.unsiloed_api_key) as client:
        result = client.parse_and_wait(file=file_path)
        chunks = [
            {"text": chunk["embed"], "metadata": {"manual_id": manual_id, "chunk_index": i}}
            for i, chunk in enumerate(result.chunks)
        ]
        await rag_service.index_chunks(manual_id, chunks)
```

Config: `UNSILOED_API_KEY` in `.env`. API base: `https://prod.visionapi.unsiloed.ai`. Max file size: 100MB.
Supported formats: PDF, DOCX, PPTX, images (PNG, JPEG, TIFF).

#### `app/services/rag.py` - Vector Search
- `SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")`
- `chromadb.PersistentClient(path="data/chromadb")`
- Collection `"car_manuals"` with cosine similarity
- `search(query, manual_id=None, top_k=5)` with optional `where={"manual_id": id}` filter
- `index_chunks(manual_id, chunks)` for batch indexing
- `delete_manual(manual_id)` for re-processing

#### `app/services/llm.py` - Claude Conversations
- Use `anthropic.AsyncAnthropic` client
- System prompt: car repair expert persona with injected RAG context
- Conversation history capped at last 10 messages
- Model: `claude-sonnet-4-20250514` for conversation speed

#### `app/api/messages.py` - Core Conversation Endpoint
`POST /api/sessions/{session_id}/message` flow:
1. Verify user owns session
2. Save user message to DB
3. RAG search with message content, scoped to session's manual
4. Build Claude prompt: system + RAG context + conversation history + user message
5. Call Claude API
6. Save assistant response to DB
7. Return response text

#### `app/admin/pages.py` - NiceGUI Admin
- **Login page** (`/admin/login`): username/password form, sets `app.storage.user['authenticated']`
- **Dashboard** (`/admin/`): file upload widget, car make/model/year fields, processing status table with auto-refresh timer, background processing via `asyncio.create_task()`
- **Browse** (`/admin/browse`): list completed manuals, view extracted markdown, test RAG search

### Implementation Order (Backend)
1. Project setup: `pyproject.toml`, `config.py`, basic `main.py` → verify FastAPI + NiceGUI run
2. Database: `database.py`, `models.py`, `seed.py` → verify tables created
3. Admin UI: login + dashboard + upload (without processing)
4. PDF processing: `pdf_processor.py` (Unsiloed.ai) + `rag.py` → upload a PDF, verify parsing + chunking + indexing
5. API endpoints: auth, sessions, messages with RAG + Claude integration
6. Browse page for viewing processed content

---

## Part 2: iOS App (`ios/WrenchAI/`)

### Tech Stack
- **Swift 5.9+**, iOS 17.0 minimum, SwiftUI
- **XcodeGen** for project management
- **Firebase Auth** (Google + Apple sign-in)
- **WhisperKit** for on-device STT (~140MB base model)
- **Sherpa-ONNX** for Kokoro TTS + Silero VAD (single framework for both)
- **AVAudioEngine** for audio capture
- **MVVM** architecture

### Why Sherpa-ONNX
Sherpa-ONNX provides a unified framework that runs both **Kokoro TTS** and **Silero VAD** via ONNX Runtime on iOS. This means:
- Single dependency for both VAD and TTS
- Pre-built iOS Swift examples
- Supports iOS 13+ (well within our iOS 17 target)
- Kokoro models available in INT8 quantized form (~88MB)
- No need for separate ONNX Runtime + VAD library dependencies

### Directory Structure

```
ios/WrenchAI/
├── project.yml                       # XcodeGen spec
├── Makefile                          # generate, open, clean targets
├── GoogleService-Info.plist          # Firebase config
├── WrenchAI/
│   ├── App/
│   │   ├── WrenchAIApp.swift         # @main entry, RootView
│   │   └── AppDelegate.swift         # Firebase init, Google URL handling
│   ├── Models/
│   │   ├── AppUser.swift
│   │   ├── Session.swift
│   │   └── Message.swift
│   ├── Views/
│   │   ├── Auth/
│   │   │   └── LoginView.swift       # Google + Apple sign-in
│   │   ├── Home/
│   │   │   ├── HomeView.swift        # Session list + new session
│   │   │   └── NewSessionView.swift  # Car selection + start
│   │   ├── Conversation/
│   │   │   ├── ConversationView.swift     # Active voice session UI
│   │   │   ├── ConversationBubbleView.swift
│   │   │   └── SessionDetailView.swift    # Read-only past session
│   │   └── Components/
│   │       ├── PulsingMicButton.swift
│   │       └── StatusIndicatorView.swift
│   ├── ViewModels/
│   │   ├── AuthViewModel.swift
│   │   ├── HomeViewModel.swift
│   │   └── ConversationViewModel.swift
│   ├── Services/
│   │   ├── Auth/
│   │   │   └── AuthService.swift          # Firebase wrapper
│   │   ├── API/
│   │   │   ├── APIClient.swift            # URLSession + auth headers
│   │   │   └── APIEndpoints.swift
│   │   └── Audio/
│   │       ├── AudioSessionManager.swift  # AVAudioSession config
│   │       ├── AudioCaptureService.swift  # AVAudioEngine mic → 16kHz mono
│   │       ├── VADService.swift           # Silero VAD via sherpa-onnx
│   │       ├── TranscriptionService.swift # WhisperKit wrapper
│   │       ├── TTSService.swift           # Kokoro via sherpa-onnx
│   │       └── VoicePipelineCoordinator.swift  # Orchestrates the loop
│   ├── Resources/
│   │   └── Assets.xcassets/
│   ├── Extensions/
│   │   └── Color+Theme.swift
│   └── WrenchAI.entitlements
```

### Key Files & Implementation Details

#### `project.yml` - XcodeGen Config
```yaml
name: WrenchAI
options:
  bundleIdPrefix: com.wrenchai
  deploymentTarget:
    iOS: "17.0"
packages:
  FirebaseSDK:
    url: https://github.com/firebase/firebase-ios-sdk.git
    from: "11.0.0"
  GoogleSignIn:
    url: https://github.com/google/GoogleSignIn-iOS.git
    from: "8.0.0"
  WhisperKit:
    url: https://github.com/argmaxinc/WhisperKit.git
    from: "0.9.0"
targets:
  WrenchAI:
    type: application
    platform: iOS
    sources: [WrenchAI]
    dependencies:
      - package: FirebaseSDK
        product: FirebaseAuth
      - package: GoogleSignIn
        product: GoogleSignIn
      - package: GoogleSignIn
        product: GoogleSignInSwift
      - package: WhisperKit
    settings:
      base:
        PRODUCT_BUNDLE_IDENTIFIER: com.wrenchai.app
    info:
      properties:
        NSMicrophoneUsageDescription: "..."
        NSSpeechRecognitionUsageDescription: "..."
        NSCameraUsageDescription: "..."
    entitlements:
      properties:
        com.apple.developer.applesignin: [Default]
```

**Note on sherpa-onnx:** Sherpa-ONNX doesn't have an official SPM package. It will be integrated via pre-built xcframework (download from their GitHub releases) or by building from source. Add as a binary framework dependency in project.yml.

#### Voice Pipeline State Machine (`VoicePipelineCoordinator.swift`)

This is the heart of the app. States:

```
.idle → [user taps Start] → .listening → [VAD: speech start] → .recording
  → [VAD: speech end] → .transcribing → [WhisperKit done] → .waitingForAPI
  → [API response] → .speaking → [TTS done] → .listening (loop)
```

Key behaviors:
- **Pause mic capture during TTS** to avoid recording the AI's voice
- **Max recording duration**: 30 seconds, auto-stop to prevent memory issues
- **Error recovery**: on API failure, speak "Sorry, I had trouble processing that. Can you repeat?" and return to `.listening`

#### Audio Capture (`AudioCaptureService.swift`)
- `AVAudioEngine` with tap on `inputNode`
- Convert from hardware format (48kHz) to 16kHz mono Float32 via `AVAudioConverter`
- Feed converted buffers to VAD and accumulate during speech for STT

#### VAD (`VADService.swift`)
- Use sherpa-onnx's built-in Silero VAD support
- Feed 16kHz audio frames
- Callbacks: `onSpeechStart()`, `onSpeechEnd(audioData: [Float])`

#### Transcription (`TranscriptionService.swift`)
- WhisperKit with `"base"` model (good speed/accuracy for hackathon)
- Auto-downloads model on first launch (~140MB)
- `transcribe(audioArray: [Float]) async -> String`

#### TTS (`TTSService.swift`)
- Sherpa-ONNX with Kokoro model (INT8 quantized, ~88MB)
- `speak(text: String)` → generates audio → plays via `AVAudioPlayer`
- Callback: `onFinished()`

#### Conversation UI (`ConversationView.swift`)
Voice-first, minimal design:
```
┌─────────────────────────┐
│ [←]   WrenchAI    [End] │
├─────────────────────────┤
│                         │
│  Message bubbles        │
│  (scrollable)           │
│                         │
│  [live transcription]   │
│  [AI response text]     │
│                         │
├─────────────────────────┤
│                         │
│  "Listening..."         │
│  ┌─────────────┐        │
│  │  mic (pulse) │       │
│  └─────────────┘        │
│  [Start / Stop]         │
└─────────────────────────┘
```

- `PulsingMicButton`: large circle, pulses green when listening, orange when processing, blue when speaking
- `StatusIndicatorView`: text label for current state
- Messages auto-scroll to bottom

### Implementation Order (iOS)
1. Project setup: `project.yml`, `WrenchAIApp.swift`, `AppDelegate.swift` → verify Xcode project generates and builds
2. Auth: `AuthService`, `AuthViewModel`, `LoginView` → test Google + Apple sign-in
3. API layer: `APIClient`, `APIEndpoints` → test with backend
4. Audio pipeline (core, ~2-3 hours):
   a. `AudioSessionManager` → mic permissions
   b. `AudioCaptureService` → verify audio capture + format conversion
   c. `VADService` → verify speech detection
   d. `TranscriptionService` → verify WhisperKit transcription
   e. `TTSService` → verify Kokoro speaks text
   f. `VoicePipelineCoordinator` → wire everything together
5. Conversation UI: `ConversationView`, `ConversationViewModel`, components
6. Session management: `HomeView`, `HomeViewModel`, session list

---

## Part 3: Documentation (`docs/`)

Store vendor/library reference docs for offline/LLM use:

```
docs/
├── unsiloed/
│   └── llms.txt                  # Unsiloed.ai API reference (from docs.unsiloed.ai/llms.txt)
├── nicegui/
│   └── llms.txt                  # NiceGUI reference
├── whisperkit/
│   └── llms.txt                  # WhisperKit reference
└── sherpa-onnx/
    └── llms.txt                  # Sherpa-ONNX reference
```

---

## Part 4: Shared Configuration

### `.env.example` (backend)
```
ANTHROPIC_API_KEY=
UNSILOED_API_KEY=
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme
```

### `.gitignore` (root)
```
# Python
backend/data/
backend/.env
backend/.venv/
__pycache__/

# iOS
ios/WrenchAI/*.xcodeproj
ios/WrenchAI/build/
*.xcworkspace

# General
.DS_Store
```

---

## Verification Plan

### Backend
1. `cd backend && uv run python -m app.main` → server starts, `/admin/login` shows login page
2. Login to admin → upload a car manual PDF → status goes pending → processing → completed
3. Browse processed content → verify markdown extraction quality
4. `curl -X POST /api/auth/verify` with Firebase token → returns user_id
5. `curl -X POST /api/sessions` → creates session
6. `curl -X POST /api/sessions/{id}/message -d '{"content":"How do I change the oil?"}` → returns AI response with RAG context

### iOS
1. `cd ios/WrenchAI && xcodegen generate && open WrenchAI.xcodeproj`
2. Build and run on device/simulator
3. Sign in with Google/Apple
4. Create new session → tap Start → speak → verify transcription → verify API call → verify TTS response
5. End session → verify it appears in session list → tap to view history

### End-to-End
1. Upload a car manual via admin UI
2. Open iOS app, create session for that car
3. Ask "How do I check the tire pressure?" via voice
4. AI should respond with relevant manual content via voice
