# WrenchAI

Your AI-powered car repair companion. Upload your car's user manual, then get hands-free, voice-guided assistance for any repair, diagnosis, or maintenance task.

## The Problem

Car repairs and maintenance shouldn't require juggling a 500-page manual while your hands are covered in grease. Today, when you need to check tire pressure, replace a cabin filter, or diagnose a warning light, you're stuck flipping through dense PDFs or scrolling through generic YouTube videos that may not match your exact car model.

**WrenchAI solves this by turning your car's user manual into a voice-activated expert that knows your specific vehicle.**

You speak. It listens. It guides you step-by-step — hands-free.

## How It Works

1. **Upload your car manual** via the admin dashboard. WrenchAI processes the PDF — extracting text, tables, diagrams, and images — into searchable, structured content.

2. **Open the iOS app and start a session.** Select your car and describe what you need help with, using your voice.

3. **Have a conversation.** WrenchAI retrieves the relevant sections from your manual, combines them with AI reasoning, and speaks the answer back to you. Ask follow-up questions naturally — it maintains context throughout the session.

4. **Work hands-free.** The app uses voice activity detection to know when you're speaking and when you're done. No buttons to press mid-repair.

## Architecture

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
                                    │     ├─ Docling processing    │
                                    │     └─ Browse content        │
                                    └──────────────────────────────┘
```

### Backend (`backend/`)

- **FastAPI** REST API serving the iOS app
- **NiceGUI** admin panel for uploading and managing car manuals
- **Docling** for intelligent PDF processing — extracts text, tables, and images preserving document structure
- **ChromaDB** + **sentence-transformers** for RAG-based semantic search over manual content
- **Claude API** (Anthropic) for generating contextual, step-by-step repair guidance
- **SQLite** for session and manual metadata
- **uv** for dependency management

### iOS App (`ios/WrenchAI/`)

- **SwiftUI** with MVVM architecture
- **WhisperKit** for on-device speech-to-text (runs locally, no cloud transcription)
- **Kokoro TTS** via Sherpa-ONNX for natural-sounding on-device text-to-speech
- **Silero VAD** for voice activity detection (knows when you start/stop talking)
- **Firebase Auth** with Google and Apple sign-in
- **AVAudioEngine** for real-time audio capture and processing

### Voice Pipeline

```
.idle → .listening → .recording → .transcribing → .waitingForAPI → .speaking → .listening
         (VAD)        (VAD end)    (WhisperKit)     (Claude + RAG)   (Kokoro)     (loop)
```

The mic pauses during TTS playback to avoid echo. Max recording is 30 seconds per utterance. On API failure, the assistant gracefully recovers and asks the user to repeat.

## Getting Started

### Backend

```bash
cd backend
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY
uv sync
uv run python -m app.main
```

The admin panel is at `http://localhost:8000/admin` and the API at `http://localhost:8000/api`.

### iOS App

```bash
cd ios/WrenchAI
xcodegen generate
open WrenchAI.xcodeproj
```

Build and run on a physical device (microphone access required).

## Tech Stack Summary

| Component | Technology | Why |
|-----------|-----------|-----|
| PDF Processing | Docling | Preserves tables, images, and document structure from car manuals |
| Vector Search | ChromaDB + all-MiniLM-L6-v2 | Lightweight, file-based, zero-config for fast setup |
| AI Conversations | Claude (Anthropic) | Strong reasoning for multi-step repair instructions |
| Speech-to-Text | WhisperKit | On-device, private, low-latency transcription |
| Text-to-Speech | Kokoro via Sherpa-ONNX | Open-source, 82M params, natural voice quality |
| Voice Detection | Silero VAD via Sherpa-ONNX | Accurate, <1ms per frame, bundled with TTS runtime |
| Admin UI | NiceGUI | Python-native web UI, no frontend code needed |
| Auth | Firebase Auth | Google + Apple sign-in with minimal setup |

## License

MIT
