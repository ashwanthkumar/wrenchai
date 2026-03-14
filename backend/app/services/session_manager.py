"""Claude Agent SDK session manager — one SDK client per conversation session."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    create_sdk_mcp_server,
    tool,
)

from app.services.rag import RAGService

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are WrenchAI, an expert car repair and maintenance assistant.
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
        if not results:
            return {"content": [{"type": "text", "text": "No relevant sections found in the manual."}]}

        text_parts = []
        for r in results:
            text_parts.append(f"[distance={r['distance']:.3f}] {r['text']}")
        combined = "\n\n---\n\n".join(text_parts)
        return {"content": [{"type": "text", "text": combined}]}

    return search_manual


@dataclass
class SessionState:
    """Holds the SDK client and metadata for one conversation session."""

    client: ClaudeSDKClient
    last_activity: datetime
    manual_id: str
    session_dir: Path


class SessionManager:
    """Manages per-conversation Claude Agent SDK sessions with idle cleanup."""

    def __init__(
        self,
        rag_service: RAGService,
        sessions_dir: str,
        model: str,
        idle_timeout_minutes: int,
        cleanup_interval_minutes: int,
    ) -> None:
        self._rag_service = rag_service
        self._sessions_dir = sessions_dir
        self._model = model
        self._idle_timeout = timedelta(minutes=idle_timeout_minutes)
        self._cleanup_interval = cleanup_interval_minutes
        self._sessions: dict[str, SessionState] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task | None = None

    async def start_cleanup_task(self) -> None:
        """Launch background asyncio task that closes idle sessions periodically."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        """Periodically close idle sessions."""
        while True:
            await asyncio.sleep(self._cleanup_interval * 60)
            await self._close_idle_sessions()

    async def _close_idle_sessions(self) -> None:
        """Close sessions that have been idle longer than the timeout."""
        now = datetime.now(timezone.utc)
        to_close: list[str] = []

        async with self._lock:
            for sid, state in self._sessions.items():
                if now - state.last_activity > self._idle_timeout:
                    to_close.append(sid)

        for sid in to_close:
            logger.info("Closing idle session %s", sid)
            await self.close_session(sid)

    async def get_or_create_session(self, session_id: str, manual_id: str) -> SessionState:
        """Get existing session or create a new one with Claude SDK client."""
        async with self._lock:
            if session_id in self._sessions:
                return self._sessions[session_id]

            # Create session directory
            session_dir = Path(self._sessions_dir) / session_id
            session_dir.mkdir(parents=True, exist_ok=True)

            # Build MCP server with search tool bound to this manual
            search_tool = _build_search_manual_tool(self._rag_service, manual_id)
            mcp_server = create_sdk_mcp_server(
                name="wrenchai_tools",
                version="1.0.0",
                tools=[search_tool],
            )

            # Create and connect SDK client
            client = ClaudeSDKClient(
                options=ClaudeAgentOptions(
                    model=self._model,
                    system_prompt=SYSTEM_PROMPT,
                    mcp_servers={"wrenchai_tools": mcp_server},
                    cwd=str(session_dir),
                    permission_mode="bypassPermissions",
                    allowed_tools=["mcp__wrenchai_tools__search_manual"],
                )
            )
            await client.connect()

            state = SessionState(
                client=client,
                last_activity=datetime.now(timezone.utc),
                manual_id=manual_id,
                session_dir=session_dir,
            )
            self._sessions[session_id] = state
            return state

    async def send_message(self, session_id: str, user_message: str, manual_id: str) -> str:
        """Send a message to the session's Claude agent and return the response text."""
        state = await self.get_or_create_session(session_id, manual_id)

        await state.client.query(user_message)

        # Collect response text
        text_parts: list[str] = []
        async for msg in state.client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        text_parts.append(block.text)
            elif isinstance(msg, ResultMessage):
                if msg.result:
                    text_parts.append(msg.result)

        # Update last activity
        state.last_activity = datetime.now(timezone.utc)

        response = "".join(text_parts)
        return response if response else "I wasn't able to generate a response. Please try again."

    async def close_session(self, session_id: str) -> None:
        """Close a session and remove it from the manager."""
        async with self._lock:
            state = self._sessions.pop(session_id, None)
        if state:
            await state.client.disconnect()

    async def close_all(self) -> None:
        """Close all sessions and cancel the cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            sessions = list(self._sessions.items())
            self._sessions.clear()

        for _sid, state in sessions:
            try:
                await state.client.disconnect()
            except Exception:
                logger.exception("Error disconnecting session")
