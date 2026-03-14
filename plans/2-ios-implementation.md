# Plan: WrenchAI iOS App

## Context

Build an iOS app for an AI-powered car repair assistant that enables hands-free voice conversations. The app uses on-device AI for the audio pipeline (WhisperKit STT, Silero VAD, Kokoro TTS via sherpa-onnx) and communicates with the Python backend for RAG-augmented Claude responses.

Key constraints:
- Hackathon project — ship fast, keep it simple
- Swift 5.9+, iOS 17.0 minimum, SwiftUI, MVVM architecture
- XcodeGen for project management (no `.xcodeproj` in source control)
- On-device audio pipeline: WhisperKit (~140MB), Sherpa-ONNX for Kokoro TTS + Silero VAD (~88MB)
- Firebase Auth (Google + Apple sign-in) for user identity
- Sherpa-ONNX integrated via pre-built xcframework (no official SPM package)
- Voice pipeline is a state machine: idle → listening → recording → transcribing → waitingForAPI → speaking → loop

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        iOS App (WrenchAI)                        │
│                                                                  │
│  ┌──────────────────┐   ┌─────────────────────────────────────┐  │
│  │  Views (SwiftUI) │   │  ViewModels (@Observable)           │  │
│  │                  │   │                                     │  │
│  │  LoginView       │──►│  AuthViewModel                      │  │
│  │  HomeView        │──►│  HomeViewModel                      │  │
│  │  NewSessionView  │   │  ConversationViewModel              │  │
│  │  ConversationView│──►│    ├─ VoicePipelineCoordinator      │  │
│  │  SessionDetail   │   │    └─ APIClient                     │  │
│  │  Components/     │   └──────────────┬──────────────────────┘  │
│  │   PulsingMic     │                  │                         │
│  │   StatusIndicator│                  ▼                         │
│  └──────────────────┘   ┌─────────────────────────────────────┐  │
│                         │  Services                           │  │
│                         │                                     │  │
│                         │  AuthService (Firebase)             │  │
│                         │  APIClient (URLSession + Bearer)    │  │
│                         │                                     │  │
│                         │  ┌───────────────────────────────┐  │  │
│                         │  │  Audio Pipeline                │  │  │
│                         │  │                               │  │  │
│                         │  │  AudioSessionManager          │  │  │
│                         │  │       ▼                       │  │  │
│                         │  │  AudioCaptureService          │  │  │
│                         │  │  (AVAudioEngine 16kHz mono)   │  │  │
│                         │  │       ▼                       │  │  │
│                         │  │  VADService (Silero/sherpa)   │  │  │
│                         │  │       ▼                       │  │  │
│                         │  │  TranscriptionService         │  │  │
│                         │  │  (WhisperKit)                 │  │  │
│                         │  │       ▼                       │  │  │
│                         │  │  TTSService (Kokoro/sherpa)   │  │  │
│                         │  │       ▼                       │  │  │
│                         │  │  VoicePipelineCoordinator     │  │  │
│                         │  │  (state machine orchestrator) │  │  │
│                         │  └───────────────────────────────┘  │  │
│                         └─────────────────────────────────────┘  │
└──────────────────────┬───────────────────────────────────────────┘
                       │ HTTPS
                       ▼
              ┌─────────────────┐
              │ Python Backend  │ (existing, see plan 3)
              │ /api/sessions   │
              │ /api/auth       │
              └─────────────────┘
```

---

## New File Structure

```
ios/WrenchAI/
├── project.yml                                # NEW — XcodeGen spec with app + test targets
├── Makefile                                   # NEW — generate, open, clean, test targets
├── GoogleService-Info.plist                   # NEW — Firebase config (user-provided)
├── WrenchAI/
│   ├── App/
│   │   ├── WrenchAIApp.swift                  # NEW — @main entry, auth-gated RootView
│   │   └── AppDelegate.swift                  # NEW — Firebase init, Google Sign-In URL handling
│   ├── Models/
│   │   ├── AppUser.swift                      # NEW — Firebase user model
│   │   ├── Session.swift                      # NEW — Chat session model (Codable)
│   │   └── Message.swift                      # NEW — Chat message model (Codable)
│   ├── Views/
│   │   ├── Auth/
│   │   │   └── LoginView.swift                # NEW — Google + Apple sign-in buttons
│   │   ├── Home/
│   │   │   ├── HomeView.swift                 # NEW — Session list + new session button
│   │   │   └── NewSessionView.swift           # NEW — Car make/model/year picker + start
│   │   ├── Conversation/
│   │   │   ├── ConversationView.swift         # NEW — Active voice session UI
│   │   │   ├── ConversationBubbleView.swift   # NEW — Single message bubble
│   │   │   └── SessionDetailView.swift        # NEW — Read-only past session viewer
│   │   └── Components/
│   │       ├── PulsingMicButton.swift         # NEW — Animated mic button (green/orange/blue)
│   │       └── StatusIndicatorView.swift      # NEW — Pipeline state text label
│   ├── ViewModels/
│   │   ├── AuthViewModel.swift                # NEW — Sign-in/out state management
│   │   ├── HomeViewModel.swift                # NEW — Session list CRUD
│   │   └── ConversationViewModel.swift        # NEW — Message list + pipeline bridge
│   ├── Services/
│   │   ├── Auth/
│   │   │   └── AuthService.swift              # NEW — Firebase Auth wrapper (protocol-based)
│   │   ├── API/
│   │   │   ├── APIClient.swift                # NEW — URLSession + Bearer auth + JSON coding
│   │   │   └── APIEndpoints.swift             # NEW — Endpoint URL builder
│   │   └── Audio/
│   │       ├── AudioSessionManager.swift      # NEW — AVAudioSession category + activation
│   │       ├── AudioCaptureService.swift      # NEW — AVAudioEngine mic → 16kHz mono Float32
│   │       ├── VADService.swift               # NEW — Silero VAD via sherpa-onnx
│   │       ├── TranscriptionService.swift     # NEW — WhisperKit STT wrapper
│   │       ├── TTSService.swift               # NEW — Kokoro TTS via sherpa-onnx
│   │       └── VoicePipelineCoordinator.swift # NEW — State machine orchestrating the loop
│   ├── Resources/
│   │   └── Assets.xcassets/                   # NEW — App icon + accent color
│   ├── Extensions/
│   │   └── Color+Theme.swift                  # NEW — App color palette
│   └── WrenchAI.entitlements                  # NEW — Apple Sign In capability
├── WrenchAITests/
│   ├── Models/
│   │   └── ModelTests.swift                   # NEW — Phase 1
│   ├── Services/
│   │   ├── APIClientTests.swift               # NEW — Phase 3
│   │   └── VoicePipelineTests.swift           # NEW — Phase 4
│   └── ViewModels/
│       ├── AuthViewModelTests.swift           # NEW — Phase 2
│       ├── HomeViewModelTests.swift           # NEW — Phase 6
│       └── ConversationViewModelTests.swift   # NEW — Phase 5
```

---

## Detailed Design

### 1. `ios/WrenchAI/project.yml` — XcodeGen project specification

Defines app target, test target, SPM dependencies, and build settings.

```yaml
name: WrenchAI
options:
  bundleIdPrefix: com.wrenchai
  deploymentTarget:
    iOS: "17.0"
  xcodeVersion: "16.0"

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
      # sherpa-onnx: added as binary xcframework
    settings:
      base:
        PRODUCT_BUNDLE_IDENTIFIER: com.wrenchai.app
    info:
      properties:
        NSMicrophoneUsageDescription: "WrenchAI needs microphone access for voice conversations"
        NSSpeechRecognitionUsageDescription: "WrenchAI uses speech recognition for hands-free operation"
    entitlements:
      properties:
        com.apple.developer.applesignin: [Default]

  WrenchAITests:
    type: bundle.unit-test
    platform: iOS
    sources: [WrenchAITests]
    dependencies:
      - target: WrenchAI
    settings:
      base:
        PRODUCT_BUNDLE_IDENTIFIER: com.wrenchai.app.tests
```

Note on sherpa-onnx: Integrated via pre-built xcframework downloaded from GitHub releases. Added as a binary framework in project.yml `dependencies` section.

### 2. `ios/WrenchAI/WrenchAI/Models/AppUser.swift` — User model

```swift
struct AppUser: Identifiable, Codable {
    let id: String          // Firebase UID
    let email: String?
    let displayName: String?
}
```

### 3. `ios/WrenchAI/WrenchAI/Models/Session.swift` — Session model

```swift
struct Session: Identifiable, Codable {
    let id: String
    let manualId: String
    let title: String
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, title
        case manualId = "manual_id"
        case createdAt = "created_at"
    }
}
```

### 4. `ios/WrenchAI/WrenchAI/Models/Message.swift` — Message model

```swift
struct Message: Identifiable, Codable {
    let id: String
    let role: String        // "user" or "assistant"
    let content: String
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, role, content
        case createdAt = "created_at"
    }

    var isUser: Bool { role == "user" }
}
```

### 5. `ios/WrenchAI/WrenchAI/Services/Auth/AuthService.swift` — Firebase auth wrapper

Protocol-based for testability.

```swift
protocol AuthServiceProtocol {
    var currentUser: AppUser? { get }
    func signInWithGoogle(presenting: UIViewController) async throws -> AppUser
    func signInWithApple(presenting: UIViewController) async throws -> AppUser
    func signOut() throws
    func getIdToken() async throws -> String
}

final class FirebaseAuthService: AuthServiceProtocol {
    var currentUser: AppUser? { ... }
    func signInWithGoogle(presenting: UIViewController) async throws -> AppUser { ... }
    func signInWithApple(presenting: UIViewController) async throws -> AppUser { ... }
    func signOut() throws { ... }
    func getIdToken() async throws -> String { ... }
}
```

### 6. `ios/WrenchAI/WrenchAI/Services/API/APIClient.swift` — HTTP client

```swift
final class APIClient {
    let baseURL: URL
    private let authService: AuthServiceProtocol
    private let session: URLSession
    private let decoder: JSONDecoder

    init(baseURL: URL, authService: AuthServiceProtocol, session: URLSession = .shared) { ... }

    func request<T: Decodable>(_ endpoint: APIEndpoint) async throws -> T { ... }
    func sendMessage(sessionId: String, content: String) async throws -> Message { ... }
    func createSession(manualId: String, title: String) async throws -> Session { ... }
    func listSessions() async throws -> [Session] { ... }
    func getMessages(sessionId: String) async throws -> [Message] { ... }
}
```

### 7. `ios/WrenchAI/WrenchAI/Services/API/APIEndpoints.swift` — Endpoint definitions

```swift
enum APIEndpoint {
    case verifyAuth
    case createSession(manualId: String, title: String)
    case listSessions
    case sendMessage(sessionId: String, content: String)
    case getMessages(sessionId: String)
    case searchManuals(query: String, manualId: String?)

    var path: String { ... }
    var method: String { ... }
    var body: Data? { ... }
}
```

### 8. `ios/WrenchAI/WrenchAI/Services/Audio/AudioSessionManager.swift` — Audio session config

```swift
final class AudioSessionManager {
    func configureForRecording() throws { ... }
    func configureForPlayback() throws { ... }
    func deactivate() throws { ... }
}
```

Sets `.playAndRecord` category with `.defaultToSpeaker` and `.allowBluetooth` options.

### 9. `ios/WrenchAI/WrenchAI/Services/Audio/AudioCaptureService.swift` — Mic capture

```swift
final class AudioCaptureService {
    private let engine = AVAudioEngine()
    private var converter: AVAudioConverter?

    var onAudioBuffer: (([Float]) -> Void)?

    func startCapture() throws { ... }
    func stopCapture() { ... }
}
```

Installs tap on `engine.inputNode`, converts hardware format (typically 48kHz stereo) to 16kHz mono Float32 via `AVAudioConverter`, calls `onAudioBuffer` with each converted buffer.

### 10. `ios/WrenchAI/WrenchAI/Services/Audio/VADService.swift` — Voice activity detection

```swift
final class VADService {
    var onSpeechStart: (() -> Void)?
    var onSpeechEnd: (([Float]) -> Void)?

    init(modelPath: String) { ... }  // sherpa-onnx Silero VAD model
    func feedAudio(_ samples: [Float]) { ... }
    func reset() { ... }
}
```

Wraps sherpa-onnx's Silero VAD. Accumulates audio during speech, delivers full utterance on `onSpeechEnd`.

### 11. `ios/WrenchAI/WrenchAI/Services/Audio/TranscriptionService.swift` — WhisperKit STT

```swift
final class TranscriptionService {
    private var whisperKit: WhisperKit?

    func loadModel() async throws { ... }  // downloads "base" model on first launch
    func transcribe(audioArray: [Float]) async throws -> String { ... }
}
```

### 12. `ios/WrenchAI/WrenchAI/Services/Audio/TTSService.swift` — Kokoro TTS

```swift
final class TTSService {
    var onFinished: (() -> Void)?

    init(modelPath: String) { ... }  // sherpa-onnx Kokoro model
    func speak(text: String) { ... }
    func stop() { ... }
}
```

Generates audio via sherpa-onnx, plays via `AVAudioPlayer`. Calls `onFinished` when playback completes.

### 13. `ios/WrenchAI/WrenchAI/Services/Audio/VoicePipelineCoordinator.swift` — State machine

```swift
enum PipelineState: Equatable {
    case idle
    case listening
    case recording
    case transcribing
    case waitingForAPI
    case speaking
    case error(String)
}

@Observable
final class VoicePipelineCoordinator {
    private(set) var state: PipelineState = .idle
    private(set) var lastTranscription: String = ""

    private let audioCapture: AudioCaptureService
    private let vad: VADService
    private let transcription: TranscriptionService
    private let tts: TTSService
    private let apiClient: APIClient
    private let sessionId: String

    init(audioCapture: AudioCaptureService, vad: VADService,
         transcription: TranscriptionService, tts: TTSService,
         apiClient: APIClient, sessionId: String) { ... }

    func start() throws { ... }       // → .listening
    func stop() { ... }               // → .idle
    func handleSpeechEnd(_ audio: [Float]) async { ... }  // recording → transcribing → waitingForAPI → speaking
}
```

State transitions:
- `.idle` → user calls `start()` → `.listening`
- `.listening` → VAD detects speech start → `.recording`
- `.recording` → VAD detects speech end → `.transcribing`
- `.transcribing` → WhisperKit returns text → `.waitingForAPI`
- `.waitingForAPI` → API returns response → `.speaking`
- `.speaking` → TTS finishes → `.listening` (loop)
- Any error → `.error(message)` → speak error → `.listening`

Key behaviors:
- Max recording: 30 seconds, auto-stop
- Pause mic during TTS playback
- Error recovery: speak fallback message, return to `.listening`

### 14. `ios/WrenchAI/WrenchAI/ViewModels/AuthViewModel.swift` — Auth state

```swift
@Observable
final class AuthViewModel {
    private(set) var currentUser: AppUser?
    private(set) var isLoading = false
    private(set) var errorMessage: String?
    var isSignedIn: Bool { currentUser != nil }

    private let authService: AuthServiceProtocol

    init(authService: AuthServiceProtocol) { ... }

    func signInWithGoogle(presenting: UIViewController) async { ... }
    func signInWithApple(presenting: UIViewController) async { ... }
    func signOut() { ... }
    func checkExistingSession() { ... }  // restore on app launch
}
```

### 15. `ios/WrenchAI/WrenchAI/ViewModels/HomeViewModel.swift` — Session management

```swift
@Observable
final class HomeViewModel {
    private(set) var sessions: [Session] = []
    private(set) var isLoading = false

    private let apiClient: APIClient

    init(apiClient: APIClient) { ... }

    func loadSessions() async { ... }
    func createSession(manualId: String, title: String) async throws -> Session { ... }
}
```

### 16. `ios/WrenchAI/WrenchAI/ViewModels/ConversationViewModel.swift` — Conversation bridge

```swift
@Observable
final class ConversationViewModel {
    private(set) var messages: [Message] = []
    let pipeline: VoicePipelineCoordinator

    private let apiClient: APIClient
    private let sessionId: String

    init(sessionId: String, apiClient: APIClient, pipeline: VoicePipelineCoordinator) { ... }

    func loadHistory() async { ... }
    func addMessage(_ message: Message) { ... }
}
```

---

## Phase-by-Phase Execution

> **Execution note:** Each phase below should be executed by a separate Agent invocation
> (subagent_type: "general-purpose", model: "claude-opus-4-6") to ensure a full context window per phase.
> The orchestrator launches one Agent per phase sequentially.

> **iOS testing note:** Tests use XCTest. Build and test commands use `xcodebuild`.
> Run command pattern: `cd ios/WrenchAI && xcodegen generate && xcodebuild test -scheme WrenchAI -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' -only-testing WrenchAITests`
> Some audio/hardware services cannot be fully unit-tested on simulator and will be verified manually on device.

---

### Phase 1: Project Scaffold + Models

**Goal**: Set up XcodeGen project with app and test targets, create data models, theme colors, and verify the project builds.

**RED — Write failing tests**

Test file: `ios/WrenchAI/WrenchAITests/Models/ModelTests.swift`

| Test | What it checks |
|------|----------------|
| `test_appUser_codable_roundtrip` | `AppUser` encodes to JSON and decodes back with matching fields |
| `test_session_codable_from_snake_case_json` | `Session` decodes from `{"manual_id": ..., "created_at": ...}` correctly |
| `test_session_identifiable_uses_id` | `Session.id` serves as the `Identifiable` id |
| `test_message_codable_from_snake_case_json` | `Message` decodes from snake_case backend JSON |
| `test_message_isUser_returns_true_for_user_role` | `Message(role: "user").isUser` is `true` |
| `test_message_isUser_returns_false_for_assistant_role` | `Message(role: "assistant").isUser` is `false` |

Run: `cd ios/WrenchAI && xcodegen generate && xcodebuild test -scheme WrenchAI -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' -only-testing WrenchAITests` — expect FAIL (compilation error).

**GREEN — Implement**

1. Create `ios/WrenchAI/project.yml` with `WrenchAI` app target + `WrenchAITests` unit test target, all SPM packages
2. Create `ios/WrenchAI/Makefile` with targets: `generate`, `open`, `test`, `clean`
3. Create `ios/WrenchAI/WrenchAI/App/WrenchAIApp.swift` — minimal `@main` struct with `ContentView` placeholder
4. Create `ios/WrenchAI/WrenchAI/App/AppDelegate.swift` — `FirebaseApp.configure()`, Google Sign-In URL handling
5. Create `ios/WrenchAI/WrenchAI/Models/AppUser.swift`
6. Create `ios/WrenchAI/WrenchAI/Models/Session.swift` — with `CodingKeys` for snake_case mapping
7. Create `ios/WrenchAI/WrenchAI/Models/Message.swift` — with `CodingKeys` and `isUser` computed property
8. Create `ios/WrenchAI/WrenchAI/Extensions/Color+Theme.swift` — app color constants
9. Create `ios/WrenchAI/WrenchAI/Resources/Assets.xcassets/` with `Contents.json`
10. Create `ios/WrenchAI/WrenchAI/WrenchAI.entitlements` with Apple Sign In capability
11. Create `ios/WrenchAI/WrenchAITests/Models/ModelTests.swift`

Run: `cd ios/WrenchAI && xcodegen generate && xcodebuild test -scheme WrenchAI -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' -only-testing WrenchAITests` — expect PASS.

**REVIEW+FIX CYCLE**

```
Launch Agent (subagent_type: "general-purpose", model: "claude-opus-4-6"):
  "Review Phase 1 of plans/4-ios.md: Project scaffold and models.
   Files to review: ios/WrenchAI/project.yml, ios/WrenchAI/Makefile,
   ios/WrenchAI/WrenchAI/App/WrenchAIApp.swift, ios/WrenchAI/WrenchAI/App/AppDelegate.swift,
   ios/WrenchAI/WrenchAI/Models/AppUser.swift, ios/WrenchAI/WrenchAI/Models/Session.swift,
   ios/WrenchAI/WrenchAI/Models/Message.swift, ios/WrenchAI/WrenchAI/Extensions/Color+Theme.swift,
   ios/WrenchAI/WrenchAITests/Models/ModelTests.swift.
   Check: project generates (xcodegen generate), all tests pass
   (xcodebuild test -scheme WrenchAI -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' -only-testing WrenchAITests),
   code matches plan spec.
   Phase-specific: Do CodingKeys correctly map snake_case backend JSON? Is the project.yml valid with both
   app and test targets? Does AppDelegate configure Firebase? Are all SPM packages declared?
   If issues found: fix them, re-run tests, and review again. Repeat until review is clean.
   When review is clean and all tests pass, report DONE with a summary of changes made."
```

**FULL SUITE**: `cd ios/WrenchAI && xcodegen generate && xcodebuild test -scheme WrenchAI -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' -only-testing WrenchAITests` — no regressions.

**COMMIT**: `/commit` with message `"Phase 1: iOS project scaffold, models, and theme"`

**Files Created**:
- `ios/WrenchAI/project.yml`
- `ios/WrenchAI/Makefile`
- `ios/WrenchAI/WrenchAI/App/WrenchAIApp.swift`
- `ios/WrenchAI/WrenchAI/App/AppDelegate.swift`
- `ios/WrenchAI/WrenchAI/Models/AppUser.swift`
- `ios/WrenchAI/WrenchAI/Models/Session.swift`
- `ios/WrenchAI/WrenchAI/Models/Message.swift`
- `ios/WrenchAI/WrenchAI/Extensions/Color+Theme.swift`
- `ios/WrenchAI/WrenchAI/Resources/Assets.xcassets/Contents.json`
- `ios/WrenchAI/WrenchAI/WrenchAI.entitlements`
- `ios/WrenchAI/WrenchAITests/Models/ModelTests.swift`

---

### Phase 2: Auth Service + ViewModel

**Goal**: Implement Firebase Auth wrapper (protocol-based for testability) and AuthViewModel with sign-in/out state management.

**RED — Write failing tests**

Test file: `ios/WrenchAI/WrenchAITests/ViewModels/AuthViewModelTests.swift`

| Test | What it checks |
|------|----------------|
| `test_initial_state_not_signed_in` | `AuthViewModel` starts with `currentUser == nil`, `isSignedIn == false` |
| `test_signIn_sets_current_user` | After successful sign-in, `currentUser` is populated and `isSignedIn == true` |
| `test_signIn_sets_loading_during_call` | `isLoading` is `true` while sign-in is in progress |
| `test_signIn_error_sets_error_message` | On auth failure, `errorMessage` is set and `currentUser` remains nil |
| `test_signOut_clears_user` | After `signOut()`, `currentUser` is nil and `isSignedIn` is false |
| `test_checkExistingSession_restores_user` | If Firebase has a cached session, `checkExistingSession()` populates `currentUser` |

Use a `MockAuthService` conforming to `AuthServiceProtocol` for all tests.

Run: `cd ios/WrenchAI && xcodegen generate && xcodebuild test -scheme WrenchAI -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' -only-testing WrenchAITests` — expect FAIL.

**GREEN — Implement**

1. Create `ios/WrenchAI/WrenchAI/Services/Auth/AuthService.swift` — `AuthServiceProtocol` protocol + `FirebaseAuthService` implementation
2. Create `ios/WrenchAI/WrenchAI/ViewModels/AuthViewModel.swift` — `@Observable` class with sign-in/out/check methods
3. Create `ios/WrenchAI/WrenchAI/Views/Auth/LoginView.swift` — Google + Apple sign-in buttons, error display
4. Update `ios/WrenchAI/WrenchAI/App/WrenchAIApp.swift` — inject `AuthViewModel`, show `LoginView` or `HomeView` based on `isSignedIn`
5. Create `ios/WrenchAI/WrenchAITests/ViewModels/AuthViewModelTests.swift` with `MockAuthService`

Run: `cd ios/WrenchAI && xcodegen generate && xcodebuild test -scheme WrenchAI -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' -only-testing WrenchAITests` — expect PASS.

**REVIEW+FIX CYCLE**

```
Launch Agent (subagent_type: "general-purpose", model: "claude-opus-4-6"):
  "Review Phase 2 of plans/4-ios.md: Auth service and view model.
   Files to review: ios/WrenchAI/WrenchAI/Services/Auth/AuthService.swift,
   ios/WrenchAI/WrenchAI/ViewModels/AuthViewModel.swift,
   ios/WrenchAI/WrenchAI/Views/Auth/LoginView.swift,
   ios/WrenchAI/WrenchAI/App/WrenchAIApp.swift,
   ios/WrenchAI/WrenchAITests/ViewModels/AuthViewModelTests.swift.
   Check: all tests pass (xcodebuild test ...), code matches plan spec, no regressions.
   Phase-specific: Does AuthServiceProtocol have all required methods? Does MockAuthService properly simulate
   success and failure? Is the AuthViewModel properly @Observable? Does LoginView handle both Google and Apple
   sign-in? Is the root view properly gated on isSignedIn?
   If issues found: fix them, re-run tests, and review again. Repeat until review is clean.
   When review is clean and all tests pass, report DONE with a summary of changes made."
```

**FULL SUITE**: `cd ios/WrenchAI && xcodegen generate && xcodebuild test -scheme WrenchAI -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' -only-testing WrenchAITests` — no regressions from Phase 1.

**COMMIT**: `/commit` with message `"Phase 2: Firebase auth service and AuthViewModel"`

**Files Created**:
- `ios/WrenchAI/WrenchAI/Services/Auth/AuthService.swift`
- `ios/WrenchAI/WrenchAI/ViewModels/AuthViewModel.swift`
- `ios/WrenchAI/WrenchAI/Views/Auth/LoginView.swift`
- `ios/WrenchAI/WrenchAITests/ViewModels/AuthViewModelTests.swift`

**Files Modified**:
- `ios/WrenchAI/WrenchAI/App/WrenchAIApp.swift`

---

### Phase 3: API Client

**Goal**: Implement the HTTP client for communicating with the Python backend, with endpoint definitions and JSON handling.

**RED — Write failing tests**

Test file: `ios/WrenchAI/WrenchAITests/Services/APIClientTests.swift`

| Test | What it checks |
|------|----------------|
| `test_endpoint_paths_correct` | Each `APIEndpoint` case produces the expected URL path |
| `test_endpoint_methods_correct` | `.createSession` is POST, `.listSessions` is GET, etc. |
| `test_endpoint_body_encodes_json` | `.sendMessage(sessionId:content:)` produces valid JSON body |
| `test_request_includes_bearer_token` | `APIClient` adds `Authorization: Bearer <token>` header |
| `test_request_decodes_session_response` | Given mock response JSON, `createSession()` returns valid `Session` |
| `test_request_decodes_message_response` | Given mock response JSON, `sendMessage()` returns valid `Message` |
| `test_request_throws_on_http_error` | 4xx/5xx response throws appropriate error |
| `test_list_sessions_decodes_array` | `listSessions()` correctly decodes `[Session]` from JSON array |

Use `URLProtocol` subclass to mock HTTP responses. Use `MockAuthService` for token provision.

Run: `cd ios/WrenchAI && xcodegen generate && xcodebuild test -scheme WrenchAI -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' -only-testing WrenchAITests` — expect FAIL.

**GREEN — Implement**

1. Create `ios/WrenchAI/WrenchAI/Services/API/APIEndpoints.swift` — `APIEndpoint` enum with path, method, body
2. Create `ios/WrenchAI/WrenchAI/Services/API/APIClient.swift` — `APIClient` with `request<T>()`, convenience methods for sessions/messages
3. Configure `JSONDecoder` with `.iso8601` date strategy (or custom for backend format)
4. Create `ios/WrenchAI/WrenchAITests/Services/APIClientTests.swift` with `MockURLProtocol` and `MockAuthService`

Run: `cd ios/WrenchAI && xcodegen generate && xcodebuild test -scheme WrenchAI -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' -only-testing WrenchAITests` — expect PASS.

**REVIEW+FIX CYCLE**

```
Launch Agent (subagent_type: "general-purpose", model: "claude-opus-4-6"):
  "Review Phase 3 of plans/4-ios.md: API client.
   Files to review: ios/WrenchAI/WrenchAI/Services/API/APIEndpoints.swift,
   ios/WrenchAI/WrenchAI/Services/API/APIClient.swift,
   ios/WrenchAI/WrenchAITests/Services/APIClientTests.swift.
   Check: all tests pass (xcodebuild test ...), code matches plan spec, no regressions.
   Phase-specific: Do endpoint paths match the backend API exactly (/api/auth/verify, /api/sessions, etc.)?
   Does the Bearer token get refreshed on each request via authService.getIdToken()? Is JSON snake_case
   decoding handled correctly to match the backend? Does error handling cover network failures and HTTP errors?
   If issues found: fix them, re-run tests, and review again. Repeat until review is clean.
   When review is clean and all tests pass, report DONE with a summary of changes made."
```

**FULL SUITE**: `cd ios/WrenchAI && xcodegen generate && xcodebuild test -scheme WrenchAI -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' -only-testing WrenchAITests` — no regressions from Phase 1-2.

**COMMIT**: `/commit` with message `"Phase 3: API client with endpoint definitions and JSON handling"`

**Files Created**:
- `ios/WrenchAI/WrenchAI/Services/API/APIEndpoints.swift`
- `ios/WrenchAI/WrenchAI/Services/API/APIClient.swift`
- `ios/WrenchAI/WrenchAITests/Services/APIClientTests.swift`

---

### Phase 4: Audio Pipeline + Voice Pipeline Coordinator

**Goal**: Implement all audio services (capture, VAD, STT, TTS) and the state machine coordinator that orchestrates them.

Audio hardware services (`AudioCaptureService`, `VADService`, `TranscriptionService`, `TTSService`) require device access and cannot be fully unit-tested on simulator. This phase tests the **state machine logic** of `VoicePipelineCoordinator` using mock services, and verifies audio services compile correctly.

**RED — Write failing tests**

Test file: `ios/WrenchAI/WrenchAITests/Services/VoicePipelineTests.swift`

| Test | What it checks |
|------|----------------|
| `test_initial_state_is_idle` | Coordinator starts in `.idle` state |
| `test_start_transitions_to_listening` | Calling `start()` changes state to `.listening` |
| `test_stop_transitions_to_idle` | Calling `stop()` from any state returns to `.idle` |
| `test_speech_start_transitions_to_recording` | VAD speech start callback moves from `.listening` to `.recording` |
| `test_speech_end_transitions_to_transcribing` | VAD speech end moves from `.recording` to `.transcribing` |
| `test_transcription_done_transitions_to_waiting` | After transcription completes, state becomes `.waitingForAPI` |
| `test_api_response_transitions_to_speaking` | After API response, state becomes `.speaking` |
| `test_tts_done_transitions_to_listening` | After TTS finishes, state returns to `.listening` (loop) |
| `test_api_error_transitions_to_error_then_listening` | On API failure, state goes to `.error` then back to `.listening` |
| `test_last_transcription_updated` | After transcription, `lastTranscription` contains the text |

Use mock/stub implementations of all audio services (they are protocol-based or injectable).

Run: `cd ios/WrenchAI && xcodegen generate && xcodebuild test -scheme WrenchAI -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' -only-testing WrenchAITests` — expect FAIL.

**GREEN — Implement**

1. Create `ios/WrenchAI/WrenchAI/Services/Audio/AudioSessionManager.swift` — AVAudioSession configuration
2. Create `ios/WrenchAI/WrenchAI/Services/Audio/AudioCaptureService.swift` — AVAudioEngine mic capture + format conversion
3. Create `ios/WrenchAI/WrenchAI/Services/Audio/VADService.swift` — Silero VAD via sherpa-onnx (with protocol for mocking)
4. Create `ios/WrenchAI/WrenchAI/Services/Audio/TranscriptionService.swift` — WhisperKit wrapper (with protocol for mocking)
5. Create `ios/WrenchAI/WrenchAI/Services/Audio/TTSService.swift` — Kokoro TTS via sherpa-onnx (with protocol for mocking)
6. Create `ios/WrenchAI/WrenchAI/Services/Audio/VoicePipelineCoordinator.swift` — `PipelineState` enum + `@Observable` coordinator with full state machine
7. Create `ios/WrenchAI/WrenchAITests/Services/VoicePipelineTests.swift` with mock audio services

Run: `cd ios/WrenchAI && xcodegen generate && xcodebuild test -scheme WrenchAI -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' -only-testing WrenchAITests` — expect PASS.

**REVIEW+FIX CYCLE**

```
Launch Agent (subagent_type: "general-purpose", model: "claude-opus-4-6"):
  "Review Phase 4 of plans/4-ios.md: Audio pipeline and voice pipeline coordinator.
   Files to review: ios/WrenchAI/WrenchAI/Services/Audio/AudioSessionManager.swift,
   ios/WrenchAI/WrenchAI/Services/Audio/AudioCaptureService.swift,
   ios/WrenchAI/WrenchAI/Services/Audio/VADService.swift,
   ios/WrenchAI/WrenchAI/Services/Audio/TranscriptionService.swift,
   ios/WrenchAI/WrenchAI/Services/Audio/TTSService.swift,
   ios/WrenchAI/WrenchAI/Services/Audio/VoicePipelineCoordinator.swift,
   ios/WrenchAI/WrenchAITests/Services/VoicePipelineTests.swift.
   Check: all tests pass (xcodebuild test ...), code matches plan spec, no regressions.
   Phase-specific: Does the state machine correctly handle ALL transitions including error recovery?
   Is mic paused during TTS playback? Is there a 30-second max recording timeout? Are audio services
   protocol-based so the coordinator can be tested with mocks? Does AudioCaptureService convert to
   16kHz mono Float32? Does the coordinator properly wire VAD callbacks to state transitions?
   If issues found: fix them, re-run tests, and review again. Repeat until review is clean.
   When review is clean and all tests pass, report DONE with a summary of changes made."
```

**FULL SUITE**: `cd ios/WrenchAI && xcodegen generate && xcodebuild test -scheme WrenchAI -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' -only-testing WrenchAITests` — no regressions from Phase 1-3.

**COMMIT**: `/commit` with message `"Phase 4: Audio pipeline services and voice pipeline state machine"`

**Files Created**:
- `ios/WrenchAI/WrenchAI/Services/Audio/AudioSessionManager.swift`
- `ios/WrenchAI/WrenchAI/Services/Audio/AudioCaptureService.swift`
- `ios/WrenchAI/WrenchAI/Services/Audio/VADService.swift`
- `ios/WrenchAI/WrenchAI/Services/Audio/TranscriptionService.swift`
- `ios/WrenchAI/WrenchAI/Services/Audio/TTSService.swift`
- `ios/WrenchAI/WrenchAI/Services/Audio/VoicePipelineCoordinator.swift`
- `ios/WrenchAI/WrenchAITests/Services/VoicePipelineTests.swift`

---

### Phase 5: Conversation UI + ViewModel

**Goal**: Build the active conversation view with message bubbles, pulsing mic button, status indicator, and ConversationViewModel bridging the pipeline.

**RED — Write failing tests**

Test file: `ios/WrenchAI/WrenchAITests/ViewModels/ConversationViewModelTests.swift`

| Test | What it checks |
|------|----------------|
| `test_initial_messages_empty` | `ConversationViewModel` starts with empty `messages` array |
| `test_loadHistory_populates_messages` | After `loadHistory()`, messages array matches API response |
| `test_addMessage_appends_to_list` | `addMessage()` adds message to end of array |
| `test_messages_sorted_by_date` | Messages maintain chronological order |
| `test_pipeline_state_exposed` | ViewModel exposes `pipeline.state` for the view to observe |

Use mock `APIClient` (via `URLProtocol`).

Run: `cd ios/WrenchAI && xcodegen generate && xcodebuild test -scheme WrenchAI -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' -only-testing WrenchAITests` — expect FAIL.

**GREEN — Implement**

1. Create `ios/WrenchAI/WrenchAI/ViewModels/ConversationViewModel.swift` — manages messages list, bridges pipeline state
2. Create `ios/WrenchAI/WrenchAI/Views/Components/PulsingMicButton.swift` — animated circle: green=listening, orange=processing, blue=speaking
3. Create `ios/WrenchAI/WrenchAI/Views/Components/StatusIndicatorView.swift` — text label showing current `PipelineState`
4. Create `ios/WrenchAI/WrenchAI/Views/Conversation/ConversationBubbleView.swift` — single message bubble (user=right/blue, assistant=left/gray)
5. Create `ios/WrenchAI/WrenchAI/Views/Conversation/ConversationView.swift` — ScrollView of bubbles + mic button + status + live transcription overlay
6. Create `ios/WrenchAI/WrenchAI/Views/Conversation/SessionDetailView.swift` — read-only view of past session messages
7. Create `ios/WrenchAI/WrenchAITests/ViewModels/ConversationViewModelTests.swift`

Run: `cd ios/WrenchAI && xcodegen generate && xcodebuild test -scheme WrenchAI -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' -only-testing WrenchAITests` — expect PASS.

**REVIEW+FIX CYCLE**

```
Launch Agent (subagent_type: "general-purpose", model: "claude-opus-4-6"):
  "Review Phase 5 of plans/4-ios.md: Conversation UI and view model.
   Files to review: ios/WrenchAI/WrenchAI/ViewModels/ConversationViewModel.swift,
   ios/WrenchAI/WrenchAI/Views/Components/PulsingMicButton.swift,
   ios/WrenchAI/WrenchAI/Views/Components/StatusIndicatorView.swift,
   ios/WrenchAI/WrenchAI/Views/Conversation/ConversationBubbleView.swift,
   ios/WrenchAI/WrenchAI/Views/Conversation/ConversationView.swift,
   ios/WrenchAI/WrenchAI/Views/Conversation/SessionDetailView.swift,
   ios/WrenchAI/WrenchAITests/ViewModels/ConversationViewModelTests.swift.
   Check: all tests pass (xcodebuild test ...), code matches plan spec, no regressions.
   Phase-specific: Does PulsingMicButton animate with correct colors per state? Does ConversationView
   auto-scroll to bottom on new messages? Does the live transcription overlay update from pipeline.lastTranscription?
   Is SessionDetailView properly read-only (no mic button)? Does the bubble layout match the wireframe?
   If issues found: fix them, re-run tests, and review again. Repeat until review is clean.
   When review is clean and all tests pass, report DONE with a summary of changes made."
```

**FULL SUITE**: `cd ios/WrenchAI && xcodegen generate && xcodebuild test -scheme WrenchAI -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' -only-testing WrenchAITests` — no regressions from Phase 1-4.

**COMMIT**: `/commit` with message `"Phase 5: Conversation UI with message bubbles and voice controls"`

**Files Created**:
- `ios/WrenchAI/WrenchAI/ViewModels/ConversationViewModel.swift`
- `ios/WrenchAI/WrenchAI/Views/Components/PulsingMicButton.swift`
- `ios/WrenchAI/WrenchAI/Views/Components/StatusIndicatorView.swift`
- `ios/WrenchAI/WrenchAI/Views/Conversation/ConversationBubbleView.swift`
- `ios/WrenchAI/WrenchAI/Views/Conversation/ConversationView.swift`
- `ios/WrenchAI/WrenchAI/Views/Conversation/SessionDetailView.swift`
- `ios/WrenchAI/WrenchAITests/ViewModels/ConversationViewModelTests.swift`

---

### Phase 6: Home + Session Management

**Goal**: Build the home screen with session list, new session creation, and wire up the full navigation flow.

**RED — Write failing tests**

Test file: `ios/WrenchAI/WrenchAITests/ViewModels/HomeViewModelTests.swift`

| Test | What it checks |
|------|----------------|
| `test_initial_sessions_empty` | `HomeViewModel` starts with empty `sessions` array |
| `test_loadSessions_populates_list` | After `loadSessions()`, sessions array matches API response |
| `test_loadSessions_sets_loading` | `isLoading` is true during API call |
| `test_createSession_returns_session` | `createSession()` returns new `Session` with correct fields |
| `test_createSession_appends_to_list` | After creating, new session appears in `sessions` array |

Use mock `APIClient`.

Run: `cd ios/WrenchAI && xcodegen generate && xcodebuild test -scheme WrenchAI -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' -only-testing WrenchAITests` — expect FAIL.

**GREEN — Implement**

1. Create `ios/WrenchAI/WrenchAI/ViewModels/HomeViewModel.swift` — session list management, CRUD via APIClient
2. Create `ios/WrenchAI/WrenchAI/Views/Home/HomeView.swift` — `NavigationStack` with session list, "New Session" button, pull-to-refresh
3. Create `ios/WrenchAI/WrenchAI/Views/Home/NewSessionView.swift` — car make/model/year pickers, "Start" button that creates session and navigates to `ConversationView`
4. Update `ios/WrenchAI/WrenchAI/App/WrenchAIApp.swift` — wire full navigation: `LoginView` → `HomeView` → `ConversationView`
5. Create `ios/WrenchAI/WrenchAITests/ViewModels/HomeViewModelTests.swift`

Run: `cd ios/WrenchAI && xcodegen generate && xcodebuild test -scheme WrenchAI -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' -only-testing WrenchAITests` — expect PASS.

**REVIEW+FIX CYCLE**

```
Launch Agent (subagent_type: "general-purpose", model: "claude-opus-4-6"):
  "Review Phase 6 of plans/4-ios.md: Home screen and session management.
   Files to review: ios/WrenchAI/WrenchAI/ViewModels/HomeViewModel.swift,
   ios/WrenchAI/WrenchAI/Views/Home/HomeView.swift,
   ios/WrenchAI/WrenchAI/Views/Home/NewSessionView.swift,
   ios/WrenchAI/WrenchAI/App/WrenchAIApp.swift,
   ios/WrenchAI/WrenchAITests/ViewModels/HomeViewModelTests.swift.
   Check: all tests pass (xcodebuild test ...), code matches plan spec, no regressions.
   Phase-specific: Does HomeView show sessions sorted by date? Does NewSessionView properly
   create a session via API before navigating? Is the full navigation stack correct
   (Login → Home → NewSession/Conversation → SessionDetail)? Does pull-to-refresh work?
   Does tapping a past session navigate to SessionDetailView (read-only)?
   If issues found: fix them, re-run tests, and review again. Repeat until review is clean.
   When review is clean and all tests pass, report DONE with a summary of changes made."
```

**FULL SUITE**: `cd ios/WrenchAI && xcodegen generate && xcodebuild test -scheme WrenchAI -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' -only-testing WrenchAITests` — no regressions from Phase 1-5.

**COMMIT**: `/commit` with message `"Phase 6: Home screen, session management, and navigation flow"`

**Files Created**:
- `ios/WrenchAI/WrenchAI/ViewModels/HomeViewModel.swift`
- `ios/WrenchAI/WrenchAI/Views/Home/HomeView.swift`
- `ios/WrenchAI/WrenchAI/Views/Home/NewSessionView.swift`
- `ios/WrenchAI/WrenchAITests/ViewModels/HomeViewModelTests.swift`

**Files Modified**:
- `ios/WrenchAI/WrenchAI/App/WrenchAIApp.swift`

---

## Verification

After all phases are complete, run the following checks:

```bash
# 1. Generate Xcode project and run all tests
cd ios/WrenchAI && xcodegen generate && xcodebuild test \
  -scheme WrenchAI \
  -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' \
  -only-testing WrenchAITests

# 2. Build for device (verify no simulator-only issues)
cd ios/WrenchAI && xcodebuild build \
  -scheme WrenchAI \
  -destination 'generic/platform=iOS'

# 3. Manual on-device verification (requires physical iPhone):
#    a. Launch app → see login screen
#    b. Sign in with Google → see home screen
#    c. Tap "New Session" → select car → tap "Start"
#    d. In conversation view: tap Start → speak → see transcription
#    e. Verify API call to backend → verify TTS plays response
#    f. End session → verify it appears in session list
#    g. Tap past session → see read-only message history

# 4. End-to-end with backend running:
#    a. Upload a car manual via backend admin UI
#    b. Create session in iOS app for that car
#    c. Ask "How do I check the tire pressure?" via voice
#    d. AI should respond with relevant manual content via voice
```
