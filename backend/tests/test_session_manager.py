"""Tests for the Claude Agent SDK session manager."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.session_manager import (
    SYSTEM_PROMPT,
    SessionManager,
    SessionState,
    _build_search_manual_tool,
)


@pytest.fixture
def mock_rag_service():
    """Provide a mock RAGService."""
    rag = MagicMock()
    rag.search = MagicMock(return_value=[
        {"text": "Check oil level on dipstick.", "metadata": {"manual_id": "m1", "chunk_index": 0}, "distance": 0.1},
        {"text": "Oil change every 5000 miles.", "metadata": {"manual_id": "m1", "chunk_index": 1}, "distance": 0.2},
    ])
    return rag


@pytest.fixture
def session_manager(mock_rag_service, tmp_path):
    """Provide a SessionManager with mocked dependencies."""
    return SessionManager(
        rag_service=mock_rag_service,
        sessions_dir=str(tmp_path / "sessions"),
        model="claude-sonnet-4-20250514",
        idle_timeout_minutes=30,
        cleanup_interval_minutes=5,
    )


class TestSessionState:
    def test_session_state_fields(self):
        """SessionState has client, last_activity, manual_id, session_dir."""
        state = SessionState(
            client=MagicMock(),
            last_activity=datetime.now(timezone.utc),
            manual_id="m1",
            session_dir=Path("/tmp/test"),
        )
        assert state.manual_id == "m1"
        assert state.session_dir == Path("/tmp/test")
        assert state.client is not None
        assert state.last_activity is not None


class TestSystemPrompt:
    def test_system_prompt_contains_persona(self):
        """SYSTEM_PROMPT contains WrenchAI and car repair guidance."""
        assert "WrenchAI" in SYSTEM_PROMPT
        assert "car" in SYSTEM_PROMPT.lower()
        assert "repair" in SYSTEM_PROMPT.lower()

    def test_system_prompt_mentions_search_tool(self):
        """SYSTEM_PROMPT mentions the search_manual tool."""
        assert "search_manual" in SYSTEM_PROMPT


class TestSearchManualTool:
    @pytest.mark.asyncio
    async def test_search_manual_tool_returns_results(self, mock_rag_service):
        """The search_manual MCP tool returns formatted RAG results."""
        tool_fn = _build_search_manual_tool(mock_rag_service, "m1")
        result = await tool_fn.handler({"query": "how to check oil"})

        mock_rag_service.search.assert_called_once_with(query="how to check oil", manual_id="m1", top_k=5)
        assert "content" in result
        assert len(result["content"]) > 0
        assert result["content"][0]["type"] == "text"
        assert "Check oil level" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_search_manual_tool_no_results(self, mock_rag_service):
        """The tool returns 'No relevant sections found' when RAG returns empty."""
        mock_rag_service.search.return_value = []
        tool_fn = _build_search_manual_tool(mock_rag_service, "m1")
        result = await tool_fn.handler({"query": "something obscure"})

        assert "content" in result
        assert "No relevant sections found" in result["content"][0]["text"]


class TestGetOrCreateSession:
    @pytest.mark.asyncio
    async def test_creates_new(self, session_manager, tmp_path):
        """First call creates a SessionState and adds to _sessions dict."""
        with patch("app.services.session_manager.ClaudeSDKClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value = mock_client

            state = await session_manager.get_or_create_session("s1", "m1")

            assert "s1" in session_manager._sessions
            assert isinstance(state, SessionState)
            assert state.manual_id == "m1"
            mock_client.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_existing(self, session_manager, tmp_path):
        """Second call with same session_id returns the same SessionState."""
        with patch("app.services.session_manager.ClaudeSDKClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value = mock_client

            state1 = await session_manager.get_or_create_session("s1", "m1")
            state2 = await session_manager.get_or_create_session("s1", "m1")

            assert state1 is state2
            # connect should only be called once (for creation)
            assert mock_client.connect.call_count == 1

    @pytest.mark.asyncio
    async def test_creates_directory(self, session_manager, tmp_path):
        """Session directory data/sessions/{session_id}/ is created."""
        with patch("app.services.session_manager.ClaudeSDKClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value = mock_client

            await session_manager.get_or_create_session("s1", "m1")

            session_dir = Path(session_manager._sessions_dir) / "s1"
            assert session_dir.exists()
            assert session_dir.is_dir()


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_returns_string(self, session_manager):
        """send_message() returns a non-empty string response."""
        with patch("app.services.session_manager.ClaudeSDKClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value = mock_client

            # Mock ResultMessage
            from claude_agent_sdk import ResultMessage
            mock_result = ResultMessage(
                subtype="result",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="s1",
                result="The oil filter is located under the engine.",
            )
            mock_client.receive_response = MagicMock(return_value=_async_iter([mock_result]))

            response = await session_manager.send_message("s1", "Where is the oil filter?", "m1")

            assert isinstance(response, str)
            assert len(response) > 0
            assert "oil filter" in response

    @pytest.mark.asyncio
    async def test_updates_last_activity(self, session_manager):
        """last_activity is updated after send_message()."""
        with patch("app.services.session_manager.ClaudeSDKClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value = mock_client

            from claude_agent_sdk import ResultMessage
            mock_result = ResultMessage(
                subtype="result",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="s1",
                result="Answer here.",
            )
            mock_client.receive_response = MagicMock(
                side_effect=lambda: _async_iter([mock_result])
            )

            await session_manager.get_or_create_session("s1", "m1")
            before = session_manager._sessions["s1"].last_activity

            # Small delay to ensure time difference
            await asyncio.sleep(0.01)
            await session_manager.send_message("s1", "test", "m1")

            after = session_manager._sessions["s1"].last_activity
            assert after > before

    @pytest.mark.asyncio
    async def test_calls_query_and_receive(self, session_manager):
        """Client's query() is called with user message, then receive_response() is iterated."""
        with patch("app.services.session_manager.ClaudeSDKClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value = mock_client

            from claude_agent_sdk import ResultMessage
            mock_result = ResultMessage(
                subtype="result",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="s1",
                result="Response text.",
            )
            mock_client.receive_response = MagicMock(return_value=_async_iter([mock_result]))

            await session_manager.send_message("s1", "my question", "m1")

            mock_client.query.assert_called_once_with("my question")
            mock_client.receive_response.assert_called_once()

    @pytest.mark.asyncio
    async def test_collects_assistant_text_blocks(self, session_manager):
        """send_message collects TextBlock content from AssistantMessage when ResultMessage.result is None."""
        with patch("app.services.session_manager.ClaudeSDKClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value = mock_client

            from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
            assistant_msg = AssistantMessage(
                content=[TextBlock(text="Part 1. "), TextBlock(text="Part 2.")],
                model="claude-sonnet-4-20250514",
            )
            result_msg = ResultMessage(
                subtype="result",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="s1",
                result=None,
            )
            mock_client.receive_response = MagicMock(
                return_value=_async_iter([assistant_msg, result_msg])
            )

            response = await session_manager.send_message("s1", "question", "m1")
            assert "Part 1." in response
            assert "Part 2." in response


class TestCloseSession:
    @pytest.mark.asyncio
    async def test_removes_from_dict(self, session_manager):
        """After close_session(), session is no longer in _sessions."""
        with patch("app.services.session_manager.ClaudeSDKClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value = mock_client

            await session_manager.get_or_create_session("s1", "m1")
            assert "s1" in session_manager._sessions

            await session_manager.close_session("s1")
            assert "s1" not in session_manager._sessions

    @pytest.mark.asyncio
    async def test_calls_disconnect(self, session_manager):
        """close_session() calls disconnect() on the client."""
        with patch("app.services.session_manager.ClaudeSDKClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value = mock_client

            await session_manager.get_or_create_session("s1", "m1")
            await session_manager.close_session("s1")

            mock_client.disconnect.assert_called_once()


class TestIdleCleanup:
    @pytest.mark.asyncio
    async def test_close_idle_sessions(self, session_manager):
        """Sessions idle longer than timeout are closed automatically."""
        with patch("app.services.session_manager.ClaudeSDKClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value = mock_client

            await session_manager.get_or_create_session("s1", "m1")
            # Set last_activity to well past the timeout
            session_manager._sessions["s1"].last_activity = (
                datetime.now(timezone.utc) - timedelta(minutes=60)
            )

            await session_manager._close_idle_sessions()

            assert "s1" not in session_manager._sessions
            mock_client.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_active_sessions_not_closed(self, session_manager):
        """Sessions with recent activity survive the cleanup sweep."""
        with patch("app.services.session_manager.ClaudeSDKClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value = mock_client

            await session_manager.get_or_create_session("s1", "m1")
            # last_activity is recent (just created)

            await session_manager._close_idle_sessions()

            assert "s1" in session_manager._sessions
            mock_client.disconnect.assert_not_called()


class TestCloseAll:
    @pytest.mark.asyncio
    async def test_closes_everything(self, session_manager):
        """close_all() closes all sessions and cancels the cleanup task."""
        with patch("app.services.session_manager.ClaudeSDKClient") as MockClient:
            mock_clients = []

            def make_client(*args, **kwargs):
                c = AsyncMock()
                mock_clients.append(c)
                return c

            MockClient.side_effect = make_client

            await session_manager.get_or_create_session("s1", "m1")
            await session_manager.get_or_create_session("s2", "m1")

            # Start cleanup task
            await session_manager.start_cleanup_task()
            assert session_manager._cleanup_task is not None

            await session_manager.close_all()

            assert len(session_manager._sessions) == 0
            assert session_manager._cleanup_task.cancelled()
            for c in mock_clients:
                c.disconnect.assert_called_once()


# Helper to create an async iterator from a list
async def _async_iter(items):
    for item in items:
        yield item
