"""Slack E2E tests — mock-based comprehensive Slack adapter testing.

Tests the full Slack event handling pipeline with mocked dependencies.
No real Slack API calls — runs in CI.

Covers: AC-09 (Socket Mode), AC-10 (mention → thread), AC-11 (DM),
AC-12 (session persistence), AC-13 (compaction), AC-14 (context preservation),
plus dedup (#17), concurrency (#11), error handling.
"""

import threading
import time
from unittest.mock import MagicMock, call, patch

import pytest

from yui.session import SessionManager
from yui.slack_adapter import SlackHandler, _load_tokens, _summarize_messages

pytestmark = pytest.mark.e2e



@pytest.fixture
def mock_agent():
    """Mock agent that returns predictable responses."""
    agent = MagicMock()
    agent.return_value = "Hello! I'm Yui."
    return agent


@pytest.fixture
def mock_session_manager():
    """Mock session manager."""
    sm = MagicMock()
    sm.get_message_count.return_value = 5  # Below compaction threshold
    return sm


@pytest.fixture
def mock_client():
    """Mock Slack client."""
    return MagicMock()


@pytest.fixture
def handler(mock_agent, mock_session_manager, mock_client):
    """SlackHandler with all mocked dependencies."""
    return SlackHandler(
        agent=mock_agent,
        session_manager=mock_session_manager,
        slack_client=mock_client,
        compaction_threshold=50,
        bot_user_id="U_BOT_123",
    )


# --- SE-01: Mention triggers response ---

class TestMentionResponse:
    """SE-01: @mention → agent call → thread reply."""

    def test_mention_triggers_response(self, handler, mock_agent):
        """AC-10: @Yui mention triggers agent response in thread."""
        event = {
            "channel": "C_TEST",
            "user": "U_USER",
            "text": "<@U_BOT_123> hello",
            "ts": "1234567890.123456",
        }
        say = MagicMock()

        handler.handle_mention(event, say)

        mock_agent.assert_called_once_with("<@U_BOT_123> hello")
        say.assert_called_once_with(text="Hello! I'm Yui.", thread_ts="1234567890.123456")

    def test_mention_in_thread_replies_to_thread(self, handler):
        """SE-03: Message in thread → reply in same thread."""
        event = {
            "channel": "C_TEST",
            "user": "U_USER",
            "text": "<@U_BOT_123> follow up",
            "ts": "1234567890.999999",
            "thread_ts": "1234567890.000001",  # Existing thread
        }
        say = MagicMock()

        handler.handle_mention(event, say)

        # Should reply to the thread, not the individual message
        say.assert_called_once_with(text="Hello! I'm Yui.", thread_ts="1234567890.000001")


# --- SE-02: DM triggers response ---

class TestDMResponse:
    """SE-02: DM → agent call → reply."""

    def test_dm_triggers_response(self, handler, mock_agent):
        """AC-11: DM to bot triggers agent response."""
        event = {
            "channel": "D_DM_CHANNEL",
            "user": "U_USER",
            "text": "hello from DM",
            "ts": "1234567890.111111",
        }
        say = MagicMock()

        handler.handle_dm(event, say)

        mock_agent.assert_called_once_with("hello from DM")
        say.assert_called_once_with(text="Hello! I'm Yui.")


# --- SE-04: Reaction lifecycle ---

class TestReactionLifecycle:
    """SE-04: eyes → process → white_check_mark."""

    def test_reaction_lifecycle(self, handler, mock_client):
        """Mention adds eyes first, then white_check_mark after response."""
        event = {
            "channel": "C_TEST",
            "user": "U_USER",
            "text": "test",
            "ts": "1234567890.123456",
        }
        say = MagicMock()

        handler.handle_mention(event, say)

        # Verify reaction order: eyes first, then white_check_mark
        calls = mock_client.reactions_add.call_args_list
        assert len(calls) == 2
        assert calls[0] == call(channel="C_TEST", timestamp="1234567890.123456", name="eyes")
        assert calls[1] == call(
            channel="C_TEST", timestamp="1234567890.123456", name="white_check_mark"
        )


# --- SE-05: Already reacted ignored ---

class TestSafeReact:
    """SE-05: already_reacted error → silently ignored."""

    def test_already_reacted_ignored(self, handler, mock_client):
        """already_reacted error does not raise."""
        mock_client.reactions_add.side_effect = Exception("already_reacted")

        # Should not raise
        handler.safe_react("C_TEST", "123.456", "eyes")

    def test_other_reaction_error_logged(self, handler, mock_client):
        """Other reaction errors are logged but don't raise."""
        mock_client.reactions_add.side_effect = Exception("channel_not_found")

        # Should not raise
        handler.safe_react("C_TEST", "123.456", "eyes")


# --- SE-06: Concurrent requests lock ---

class TestConcurrencyLock:
    """SE-06: Two concurrent requests → serialized via Lock."""

    def test_concurrent_requests_serialized(self, mock_session_manager, mock_client):
        """AC-09: Concurrent agent calls are serialized."""
        call_order = []

        def slow_agent(text):
            call_order.append(f"start:{text}")
            time.sleep(0.1)
            call_order.append(f"end:{text}")
            return f"response to {text}"

        handler = SlackHandler(
            agent=slow_agent,
            session_manager=mock_session_manager,
            slack_client=mock_client,
            bot_user_id="U_BOT",
        )

        event1 = {"channel": "C", "user": "U1", "text": "first", "ts": "1.0"}
        event2 = {"channel": "C", "user": "U2", "text": "second", "ts": "2.0"}
        say1 = MagicMock()
        say2 = MagicMock()

        t1 = threading.Thread(target=handler.handle_mention, args=(event1, say1))
        t2 = threading.Thread(target=handler.handle_mention, args=(event2, say2))

        t1.start()
        time.sleep(0.01)  # Ensure t1 acquires lock first
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        # Both should complete (serialized)
        say1.assert_called_once()
        say2.assert_called_once()

        # Verify serialization: first must complete before second starts
        assert call_order.index("end:first") < call_order.index("start:second")


# --- SE-07: Lock timeout → processing message ---

class TestLockTimeout:
    """SE-07: Lock acquisition timeout → processing message."""

    def test_lock_timeout_sends_processing_message(self, mock_session_manager, mock_client):
        """When lock times out, user gets 'processing' message."""
        agent = MagicMock(return_value="ok")

        handler = SlackHandler(
            agent=agent,
            session_manager=mock_session_manager,
            slack_client=mock_client,
            bot_user_id="U_BOT",
        )

        # Manually acquire lock to simulate busy agent
        handler.agent_lock.acquire()

        event = {"channel": "C", "user": "U", "text": "test", "ts": "1.0"}
        say = MagicMock()

        # Patch timeout to be very short
        original_acquire = handler.agent_lock.acquire
        handler.agent_lock = MagicMock()
        handler.agent_lock.acquire.return_value = False  # Simulate timeout

        handler.handle_mention(event, say)

        # Should send processing message
        say.assert_called_once()
        assert "処理中" in say.call_args[1]["text"]


# --- SE-08: Session persistence ---

class TestSessionPersistence:
    """SE-08: Messages saved to SessionManager."""

    def test_mention_saves_to_session(self, handler, mock_session_manager):
        """AC-12: User and assistant messages persisted."""
        event = {
            "channel": "C_TEST",
            "user": "U_USER",
            "text": "hello",
            "ts": "1.0",
        }
        say = MagicMock()

        handler.handle_mention(event, say)

        # User message saved (session_id uses thread_ts = ts when no thread_ts in event)
        mock_session_manager.add_message.assert_any_call("slack:C_TEST:1.0", "user", "hello")
        # Assistant message saved
        mock_session_manager.add_message.assert_any_call(
            "slack:C_TEST:1.0", "assistant", "Hello! I'm Yui."
        )

    def test_dm_saves_to_session(self, handler, mock_session_manager):
        """DM messages use dm: session prefix."""
        event = {"channel": "D_DM", "user": "U_USER", "text": "hi", "ts": "1.0"}
        say = MagicMock()

        handler.handle_dm(event, say)

        mock_session_manager.add_message.assert_any_call("slack:dm:U_USER", "user", "hi")


# --- SE-09: Session compaction trigger ---

class TestSessionCompaction:
    """SE-09: Compaction triggered when threshold exceeded."""

    def test_compaction_triggered(self, mock_agent, mock_client):
        """AC-13: Session compaction triggered at threshold."""
        sm = MagicMock()
        sm.get_message_count.return_value = 51  # Above threshold of 50

        handler = SlackHandler(
            agent=mock_agent,
            session_manager=sm,
            slack_client=mock_client,
            compaction_threshold=50,
            bot_user_id="U_BOT",
        )

        event = {"channel": "C", "user": "U", "text": "test", "ts": "1.0"}
        say = MagicMock()

        handler.handle_mention(event, say)

        sm.compact_session.assert_called_once()

    def test_no_compaction_below_threshold(self, handler, mock_session_manager):
        """No compaction when below threshold."""
        mock_session_manager.get_message_count.return_value = 10

        event = {"channel": "C", "user": "U", "text": "test", "ts": "1.0"}
        say = MagicMock()

        handler.handle_mention(event, say)

        mock_session_manager.compact_session.assert_not_called()


# --- SE-10: Bot message skip ---

class TestBotMessageSkip:
    """SE-10: Bot/subtype messages are ignored."""

    def test_subtype_message_skipped(self, handler, mock_agent):
        """Messages with subtype (e.g., bot_message) are skipped."""
        event = {
            "channel": "D_DM",
            "user": "U_USER",
            "text": "bot text",
            "ts": "1.0",
            "subtype": "bot_message",
        }
        say = MagicMock()

        handler.handle_dm(event, say)

        mock_agent.assert_not_called()
        say.assert_not_called()

    def test_threaded_dm_skipped(self, handler, mock_agent):
        """Threaded DM messages are skipped (handled by mention handler)."""
        event = {
            "channel": "D_DM",
            "user": "U_USER",
            "text": "thread reply",
            "ts": "1.0",
            "thread_ts": "0.9",
        }
        say = MagicMock()

        handler.handle_dm(event, say)

        mock_agent.assert_not_called()


# --- SE-11: Dedup mention in DM ---

class TestDedupMention:
    """SE-11: DM with bot mention → skipped by handle_dm."""

    def test_mention_in_dm_skipped(self, handler, mock_agent):
        """#17 fix: Message containing <@bot_user_id> skipped by handle_dm."""
        event = {
            "channel": "D_MPIM",
            "user": "U_USER",
            "text": "<@U_BOT_123> hello yui",
            "ts": "1.0",
        }
        say = MagicMock()

        handler.handle_dm(event, say)

        mock_agent.assert_not_called()

    def test_no_bot_user_id_no_dedup(self, mock_agent, mock_session_manager, mock_client):
        """When bot_user_id is None, no dedup filtering."""
        handler = SlackHandler(
            agent=mock_agent,
            session_manager=mock_session_manager,
            slack_client=mock_client,
            bot_user_id=None,  # Could not detect
        )

        event = {
            "channel": "D_DM",
            "user": "U_USER",
            "text": "<@U_SOMEONE> hello",
            "ts": "1.0",
        }
        say = MagicMock()

        handler.handle_dm(event, say)

        mock_agent.assert_called_once()


# --- SE-12: Agent error handling ---

class TestAgentErrorHandling:
    """SE-12: Agent exception → error message posted."""

    def test_mention_agent_error(self, mock_session_manager, mock_client):
        """Agent exception results in error message to user."""
        agent = MagicMock(side_effect=RuntimeError("LLM timeout"))

        handler = SlackHandler(
            agent=agent,
            session_manager=mock_session_manager,
            slack_client=mock_client,
            bot_user_id="U_BOT",
        )

        event = {"channel": "C", "user": "U", "text": "test", "ts": "1.0"}
        say = MagicMock()

        handler.handle_mention(event, say)

        # Error message posted
        say.assert_called_once()
        assert "Error" in say.call_args[1]["text"]
        assert "LLM timeout" in say.call_args[1]["text"]

    def test_dm_agent_error(self, mock_session_manager, mock_client):
        """DM agent exception results in error message."""
        agent = MagicMock(side_effect=ValueError("bad input"))

        handler = SlackHandler(
            agent=agent,
            session_manager=mock_session_manager,
            slack_client=mock_client,
            bot_user_id="U_BOT",
        )

        event = {"channel": "D", "user": "U", "text": "bad", "ts": "1.0"}
        say = MagicMock()

        handler.handle_dm(event, say)

        say.assert_called_once()
        assert "Error" in say.call_args[1]["text"]


# --- SE-13: AgentResult to string ---

class TestAgentResultConversion:
    """SE-13: AgentResult object → str() for Slack posting."""

    def test_agent_result_stringified(self, mock_session_manager, mock_client):
        """AgentResult with custom __str__ is properly converted."""

        class FakeAgentResult:
            def __str__(self):
                return "Formatted response from agent"

        agent = MagicMock(return_value=FakeAgentResult())

        handler = SlackHandler(
            agent=agent,
            session_manager=mock_session_manager,
            slack_client=mock_client,
            bot_user_id="U_BOT",
        )

        event = {"channel": "C", "user": "U", "text": "test", "ts": "1.0"}
        say = MagicMock()

        handler.handle_mention(event, say)

        say.assert_called_once_with(text="Formatted response from agent", thread_ts="1.0")


# --- SE-14: Token load priority ---

class TestTokenPriority:
    """SE-14: Token loading priority: env > .env > config."""

    def test_env_over_config(self):
        """Environment variables take priority over config."""
        config = {"slack": {"bot_token": "xoxb-config", "app_token": "xapp-config"}}
        with patch.dict("os.environ", {"SLACK_BOT_TOKEN": "xoxb-env", "SLACK_APP_TOKEN": "xapp-env"}):
            bot, app = _load_tokens(config)
            assert bot == "xoxb-env"
            assert app == "xapp-env"


# --- SE-15: Missing tokens error ---

class TestMissingTokens:
    """SE-15: Missing tokens → ValueError."""

    def test_missing_tokens_raises(self):
        """ValueError when no tokens available."""
        with patch.dict("os.environ", {}, clear=True), \
             patch("yui.slack_adapter.load_dotenv"):
            with pytest.raises(ValueError, match="Missing Slack tokens"):
                _load_tokens({})


# --- SE-16: MPIM single response ---

class TestMPIMSingleResponse:
    """SE-16: Group DM mention → exactly one response (not two)."""

    def test_mpim_mention_handled_once(self, handler, mock_agent):
        """In group DM, mention is handled by handle_mention, skipped by handle_dm."""
        event = {
            "channel": "G_MPIM",
            "user": "U_USER",
            "text": "<@U_BOT_123> what's up",
            "ts": "1.0",
        }
        say = MagicMock()

        # handle_dm should skip (dedup)
        handler.handle_dm(event, say)
        assert mock_agent.call_count == 0

        # handle_mention should process
        handler.handle_mention(event, say)
        assert mock_agent.call_count == 1


# --- SE-18: Compaction summary format ---

class TestCompactionSummary:
    """SE-18: Compaction summary format."""

    def test_summarize_messages_format(self):
        """AC-14: Summary includes role and truncated content."""

        class FakeMsg:
            def __init__(self, role, content):
                self.role = role
                self.content = content

        messages = [
            FakeMsg("user", "Hello, how are you?"),
            FakeMsg("assistant", "I'm fine! " + "x" * 200),
        ]

        summary = _summarize_messages(messages)

        assert "[Conversation summary]" in summary
        assert "user: Hello, how are you?" in summary
        assert "assistant: I'm fine!" in summary
        # Content truncated to 100 chars
        assert len(summary.split("\n")[2]) <= 120


# --- S-03: Thread Reply (deep verification) ---

class TestThreadReplyDeep:
    """S-03: Thread reply — thread_ts propagation verified via chat_postMessage."""

    def test_thread_mention_uses_parent_thread_ts(self, handler, mock_agent):
        """Mention inside an existing thread replies to the parent thread, not the child message."""
        parent_ts = "1700000000.000001"
        child_ts = "1700000000.999999"

        event = {
            "channel": "C_TEST",
            "user": "U_USER",
            "text": "<@U_BOT_123> follow up question",
            "ts": child_ts,
            "thread_ts": parent_ts,  # Key: this is the parent thread
        }
        say = MagicMock()

        handler.handle_mention(event, say)

        # say() must use parent thread_ts, not the child message ts
        say.assert_called_once_with(text="Hello! I'm Yui.", thread_ts=parent_ts)
        assert say.call_args[1]["thread_ts"] == parent_ts
        assert say.call_args[1]["thread_ts"] != child_ts

    def test_top_level_mention_uses_own_ts_as_thread(self, handler, mock_agent):
        """Top-level mention (no thread_ts) creates new thread from its own ts."""
        message_ts = "1700000001.000001"

        event = {
            "channel": "C_TEST",
            "user": "U_USER",
            "text": "<@U_BOT_123> new question",
            "ts": message_ts,
            # No thread_ts — this is a top-level message
        }
        say = MagicMock()

        handler.handle_mention(event, say)

        # Should use message's own ts as thread_ts (start new thread)
        say.assert_called_once_with(text="Hello! I'm Yui.", thread_ts=message_ts)

    def test_thread_reply_session_id_uses_channel(self, handler, mock_session_manager):
        """Thread reply uses channel-based session ID (not thread-based)."""
        event = {
            "channel": "C_THREAD_TEST",
            "user": "U_THREAD_USER",
            "text": "<@U_BOT_123> in thread",
            "ts": "1700000002.999999",
            "thread_ts": "1700000002.000001",
        }
        say = MagicMock()

        handler.handle_mention(event, say)

        # Session ID should be channel:thread_ts based (Issue #116)
        expected_sid = "slack:C_THREAD_TEST:1700000002.000001"
        mock_session_manager.add_message.assert_any_call(expected_sid, "user", "<@U_BOT_123> in thread")

    def test_multiple_thread_replies_maintain_thread(self, handler, mock_agent):
        """Multiple mentions in same thread all reply to the same parent thread."""
        parent_ts = "1700000003.000001"

        for i in range(3):
            event = {
                "channel": "C_TEST",
                "user": "U_USER",
                "text": f"<@U_BOT_123> message {i}",
                "ts": f"1700000003.{i:06d}",
                "thread_ts": parent_ts,
            }
            say = MagicMock()
            handler.handle_mention(event, say)

            # Each reply should go to the same parent thread
            say.assert_called_once()
            assert say.call_args[1]["thread_ts"] == parent_ts


# --- S-10: Agent Timeout ---

class TestAgentTimeout:
    """S-10: Agent processing timeout → error message, session intact."""

    def test_agent_timeout_sends_error_message(self, mock_session_manager, mock_client):
        """When agent raises TimeoutError, user receives an error message."""
        agent = MagicMock(side_effect=TimeoutError("Agent processing timed out after 120s"))

        handler = SlackHandler(
            agent=agent,
            session_manager=mock_session_manager,
            slack_client=mock_client,
            bot_user_id="U_BOT",
        )

        event = {"channel": "C_TEST", "user": "U_USER", "text": "test", "ts": "1.0"}
        say = MagicMock()

        handler.handle_mention(event, say)

        # Error message should be sent to user
        say.assert_called_once()
        assert "Error" in say.call_args[1]["text"]
        assert "timed out" in say.call_args[1]["text"]

    def test_agent_timeout_preserves_user_message_in_session(self, mock_client):
        """After timeout, the user message is still saved in session (not lost)."""
        sm = MagicMock()
        sm.get_message_count.return_value = 5
        agent = MagicMock(side_effect=TimeoutError("timeout"))

        handler = SlackHandler(
            agent=agent,
            session_manager=sm,
            slack_client=mock_client,
            bot_user_id="U_BOT",
        )

        event = {"channel": "C_TIMEOUT", "user": "U_TIMEOUT", "text": "my question", "ts": "1.0"}
        say = MagicMock()

        handler.handle_mention(event, say)

        # User message should have been saved before agent call (session_id uses thread_ts = ts)
        sm.add_message.assert_called_with("slack:C_TIMEOUT:1.0", "user", "my question")

    def test_agent_timeout_session_not_corrupted(self, mock_client):
        """After timeout, subsequent requests still work normally."""
        call_count = 0

        def flaky_agent(text):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("Agent processing timed out")
            return "recovered response"

        sm = MagicMock()
        sm.get_message_count.return_value = 5

        handler = SlackHandler(
            agent=flaky_agent,
            session_manager=sm,
            slack_client=mock_client,
            bot_user_id="U_BOT",
        )

        # First request: timeout
        event1 = {"channel": "C_TEST", "user": "U_USER", "text": "first", "ts": "1.0"}
        say1 = MagicMock()
        handler.handle_mention(event1, say1)

        assert "Error" in say1.call_args[1]["text"]

        # Second request: should succeed (session not corrupted)
        event2 = {"channel": "C_TEST", "user": "U_USER", "text": "second", "ts": "2.0"}
        say2 = MagicMock()
        handler.handle_mention(event2, say2)

        say2.assert_called_once_with(text="recovered response", thread_ts="2.0")

    def test_agent_timeout_lock_released(self, mock_client):
        """After timeout, the agent lock is properly released."""
        agent = MagicMock(side_effect=TimeoutError("timeout"))
        sm = MagicMock()
        sm.get_message_count.return_value = 5

        handler = SlackHandler(
            agent=agent,
            session_manager=sm,
            slack_client=mock_client,
            bot_user_id="U_BOT",
        )

        event = {"channel": "C", "user": "U", "text": "test", "ts": "1.0"}
        say = MagicMock()
        handler.handle_mention(event, say)

        # Lock should be released — can be acquired immediately
        assert handler.agent_lock.acquire(timeout=0.1)
        handler.agent_lock.release()

    def test_dm_agent_timeout(self, mock_client):
        """DM agent timeout also sends error message."""
        agent = MagicMock(side_effect=TimeoutError("DM agent timed out"))
        sm = MagicMock()
        sm.get_message_count.return_value = 5

        handler = SlackHandler(
            agent=agent,
            session_manager=sm,
            slack_client=mock_client,
            bot_user_id="U_BOT",
        )

        event = {"channel": "D_DM", "user": "U_USER", "text": "hello", "ts": "1.0"}
        say = MagicMock()

        handler.handle_dm(event, say)

        say.assert_called_once()
        assert "Error" in say.call_args[1]["text"]


# --- S-12: 50-Message Compaction ---

class TestFiftyMessageCompaction:
    """S-12: Session compaction at 50+ messages with context preservation."""

    def test_compaction_at_threshold_boundary(self, mock_agent, mock_client):
        """Compaction triggers only when message count exceeds threshold."""
        sm = MagicMock()

        # Exactly at threshold — should NOT compact
        sm.get_message_count.return_value = 50
        handler = SlackHandler(
            agent=mock_agent, session_manager=sm,
            slack_client=mock_client, compaction_threshold=50, bot_user_id="U_BOT",
        )
        event = {"channel": "C", "user": "U", "text": "test", "ts": "1.0"}
        say = MagicMock()
        handler.handle_mention(event, say)
        sm.compact_session.assert_not_called()

        # Above threshold — should compact
        sm.reset_mock()
        sm.get_message_count.return_value = 51
        handler.handle_mention(event, say)
        sm.compact_session.assert_called_once()

    def test_compaction_uses_summarize_function(self, mock_agent, mock_client):
        """compact_session is called with _summarize_messages as summarizer."""
        sm = MagicMock()
        sm.get_message_count.return_value = 55

        handler = SlackHandler(
            agent=mock_agent, session_manager=sm,
            slack_client=mock_client, compaction_threshold=50, bot_user_id="U_BOT",
        )

        event = {"channel": "C_COMP", "user": "U_COMP", "text": "test", "ts": "1.0"}
        say = MagicMock()
        handler.handle_mention(event, say)

        # Verify compact_session called with session_id (channel:thread_ts) and summarizer function
        sm.compact_session.assert_called_once()
        call_args = sm.compact_session.call_args
        assert call_args[0][0] == "slack:C_COMP:1.0"
        assert call_args[0][1] is _summarize_messages

    def test_custom_compaction_threshold(self, mock_agent, mock_client):
        """Custom compaction_threshold is respected."""
        sm = MagicMock()
        sm.get_message_count.return_value = 25

        # Lower threshold of 20
        handler = SlackHandler(
            agent=mock_agent, session_manager=sm,
            slack_client=mock_client, compaction_threshold=20, bot_user_id="U_BOT",
        )

        event = {"channel": "C", "user": "U", "text": "test", "ts": "1.0"}
        say = MagicMock()
        handler.handle_mention(event, say)

        # 25 > 20 → should compact
        sm.compact_session.assert_called_once()

    def test_high_threshold_prevents_compaction(self, mock_agent, mock_client):
        """High threshold prevents compaction for moderate message counts."""
        sm = MagicMock()
        sm.get_message_count.return_value = 80

        handler = SlackHandler(
            agent=mock_agent, session_manager=sm,
            slack_client=mock_client, compaction_threshold=100, bot_user_id="U_BOT",
        )

        event = {"channel": "C", "user": "U", "text": "test", "ts": "1.0"}
        say = MagicMock()
        handler.handle_mention(event, say)

        # 80 ≤ 100 → should NOT compact
        sm.compact_session.assert_not_called()

    def test_compaction_preserves_context_integration(self, tmp_path):
        """Integration: real SessionManager compaction preserves recent messages and summary."""
        db_path = tmp_path / "test.db"
        sm = SessionManager(str(db_path), compaction_threshold=10, keep_recent=3)

        session_id = "slack:C_INT:U_INT"
        sm.get_or_create_session(session_id, {"channel": "C_INT", "user": "U_INT"})

        # Add 15 messages (above threshold of 10)
        for i in range(15):
            role = "user" if i % 2 == 0 else "assistant"
            sm.add_message(session_id, role, f"Message {i}")

        assert sm.get_message_count(session_id) == 15

        # Compact
        sm.compact_session(session_id, _summarize_messages)

        # After compaction: 1 summary + 3 recent = 4 messages
        messages = sm.get_messages(session_id)
        assert len(messages) == 4

        # First message is the summary
        assert messages[0].role == "system"
        assert "[Conversation summary]" in messages[0].content

        # Last 3 messages are the recent ones (messages 12, 13, 14)
        assert messages[1].content == "Message 12"
        assert messages[2].content == "Message 13"
        assert messages[3].content == "Message 14"

    def test_compaction_summary_contains_old_messages(self, tmp_path):
        """Integration: summary text contains content from compacted (old) messages."""
        db_path = tmp_path / "test_summary.db"
        sm = SessionManager(str(db_path), compaction_threshold=5, keep_recent=2)

        session_id = "slack:C_SUM:U_SUM"
        sm.get_or_create_session(session_id, {"channel": "C_SUM"})

        # Add distinctive messages
        sm.add_message(session_id, "user", "What is the capital of France?")
        sm.add_message(session_id, "assistant", "The capital of France is Paris.")
        sm.add_message(session_id, "user", "And what about Japan?")
        sm.add_message(session_id, "assistant", "The capital of Japan is Tokyo.")
        sm.add_message(session_id, "user", "Thanks!")
        sm.add_message(session_id, "assistant", "You're welcome!")

        sm.compact_session(session_id, _summarize_messages)

        messages = sm.get_messages(session_id)
        summary = messages[0].content

        # Old messages should be in summary
        assert "capital of France" in summary
        assert "Paris" in summary
        assert "Japan" in summary
        assert "Tokyo" in summary

        # Recent messages should NOT be in summary (they're kept separate)
        recent_contents = [m.content for m in messages[1:]]
        assert "Thanks!" in recent_contents
        assert "You're welcome!" in recent_contents

    def test_dm_compaction_also_works(self, mock_agent, mock_client):
        """DM handler also triggers compaction above threshold."""
        sm = MagicMock()
        sm.get_message_count.return_value = 60

        handler = SlackHandler(
            agent=mock_agent, session_manager=sm,
            slack_client=mock_client, compaction_threshold=50, bot_user_id="U_BOT",
        )

        event = {"channel": "D_DM", "user": "U_DM", "text": "dm message", "ts": "1.0"}
        say = MagicMock()

        handler.handle_dm(event, say)

        sm.compact_session.assert_called_once()
        assert sm.compact_session.call_args[0][0] == "slack:dm:U_DM"


# --- SE-17: Socket Mode startup (smoke test) ---

class TestSocketModeStartup:
    """SE-17: run_slack creates SocketModeHandler and starts."""

    @patch("yui.slack_adapter.SocketModeHandler")
    @patch("yui.slack_adapter.App")
    @patch("yui.agent.create_agent")
    @patch("yui.slack_adapter.SessionManager")
    @patch("yui.slack_adapter._load_tokens", return_value=("xoxb-t", "xapp-t"))
    def test_run_slack_starts_handler(self, mock_tokens, mock_sm, mock_agent, mock_app, mock_smh):
        """AC-09: Socket Mode handler created and started."""
        mock_app_instance = MagicMock()
        mock_app_instance.client.auth_test.return_value = {"user_id": "U_BOT"}
        mock_app.return_value = mock_app_instance
        mock_agent.return_value = MagicMock()

        from yui.slack_adapter import run_slack
        run_slack(config={"runtime": {"session": {}}})

        mock_smh.assert_called_once()
        mock_smh.return_value.start.assert_called_once()
