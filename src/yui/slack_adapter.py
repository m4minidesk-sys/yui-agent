"""Slack Socket Mode adapter.

Provides SlackHandler class for testable event handling,
and run_slack() entry point for Socket Mode connection.
"""

import logging
import os
import threading
import traceback
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from yui.config import load_config
from yui.session import SessionManager

logger = logging.getLogger(__name__)


def _load_tokens(config: dict) -> tuple[str, str]:
    """Load Slack tokens from env vars, .env file, or config.

    Priority: env vars > ~/.yui/.env > config.yaml

    Returns:
        Tuple of (bot_token, app_token).

    Raises:
        ValueError: If tokens are missing.
    """
    # Load from ~/.yui/.env if exists
    env_file = Path("~/.yui/.env").expanduser()
    if env_file.exists():
        load_dotenv(env_file)

    bot_token = os.getenv("SLACK_BOT_TOKEN") or config.get("slack", {}).get("bot_token")
    app_token = os.getenv("SLACK_APP_TOKEN") or config.get("slack", {}).get("app_token")

    if not bot_token or not app_token:
        raise ValueError(
            "Missing Slack tokens. Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN in env or ~/.yui/.env"
        )

    return bot_token, app_token


class SlackHandler:
    """Testable Slack event handler.

    Separates event handling logic from Slack Bolt wiring
    so each handler can be tested with mock dependencies.
    """

    def __init__(
        self,
        agent: callable,
        session_manager: "SessionManager",
        slack_client: object,
        compaction_threshold: int = 50,
        bot_user_id: Optional[str] = None,
    ):
        self.agent = agent
        self.session_manager = session_manager
        self.client = slack_client
        self.compaction_threshold = compaction_threshold
        self.bot_user_id = bot_user_id
        self.agent_lock = threading.Lock()

    def safe_react(self, channel: str, timestamp: str, name: str) -> None:
        """Add reaction, ignoring already_reacted errors."""
        try:
            self.client.reactions_add(channel=channel, timestamp=timestamp, name=name)
        except Exception as e:
            if "already_reacted" not in str(e):
                logger.warning("Failed to add reaction %s: %s", name, e)

    def handle_mention(self, event: dict, say: callable) -> None:
        """Handle @Yui mentions in channels."""
        try:
            channel = event["channel"]
            user = event["user"]
            text = event["text"]
            # event["ts"] は Slack app_mention で必須フィールドだが防御的に .get() を使用
            msg_ts = event.get("ts", "")
            thread_ts = event.get("thread_ts") or msg_ts

            # Acknowledge
            if msg_ts:
                self.safe_react(channel, msg_ts, "eyes")

            # Session ID: thread_ts でスレッドごとに分離（Issue #116）
            # 同一スレッド内のメッセージは同じ thread_ts → 同一セッション
            # 新規スレッドは event["ts"] がスレッド起点 → 独立セッション
            session_id = f"slack:{channel}:{thread_ts}"
            self.session_manager.get_or_create_session(
                session_id, {"channel": channel, "user": user, "thread_ts": thread_ts}
            )

            # Add user message
            self.session_manager.add_message(session_id, "user", text)

            # Get response (serialized — Strands Agent is not thread-safe)
            acquired = self.agent_lock.acquire(timeout=120)
            if not acquired:
                say(text="⏳ 他のリクエストを処理中です。少々お待ちください…", thread_ts=thread_ts)
                return
            try:
                result = self.agent(text)
                response = str(result)
            finally:
                self.agent_lock.release()

            # Add assistant message
            self.session_manager.add_message(session_id, "assistant", response)

            # Post response in thread
            say(text=response, thread_ts=thread_ts)

            # Mark done
            self.safe_react(channel, event["ts"], "white_check_mark")

            # Check compaction
            if self.session_manager.get_message_count(session_id) > self.compaction_threshold:
                self.session_manager.compact_session(session_id, _summarize_messages)

        except Exception as e:
            logger.error("Error handling mention: %s", traceback.format_exc())
            thread_ts = event.get("thread_ts") or event.get("ts", "")
            say(text=f"Error: {e}", thread_ts=thread_ts)

    def handle_dm(self, event: dict, say: callable) -> None:
        """Handle DMs and mpim messages (non-mention)."""
        # Skip bot messages and threaded replies
        if event.get("subtype") or event.get("thread_ts"):
            return

        # Skip messages that contain @mention of this bot — those are
        # handled by handle_mention to avoid duplicate responses (#17)
        text = event.get("text", "")
        if self.bot_user_id and f"<@{self.bot_user_id}>" in text:
            return

        try:
            channel = event["channel"]
            user = event["user"]
            text = event["text"]

            # Acknowledge
            self.safe_react(channel, event["ts"], "eyes")

            # Session ID
            session_id = f"slack:dm:{user}"
            self.session_manager.get_or_create_session(session_id, {"user": user})

            # Add user message
            self.session_manager.add_message(session_id, "user", text)

            # Get response (serialized — Strands Agent is not thread-safe)
            acquired = self.agent_lock.acquire(timeout=120)
            if not acquired:
                say(text="⏳ 他のリクエストを処理中です。少々お待ちください…")
                return
            try:
                result = self.agent(text)
                response = str(result)
            finally:
                self.agent_lock.release()

            # Add assistant message
            self.session_manager.add_message(session_id, "assistant", response)

            # Post response
            say(text=response)

            # Mark done
            self.safe_react(channel, event["ts"], "white_check_mark")

            # Check compaction
            if self.session_manager.get_message_count(session_id) > self.compaction_threshold:
                self.session_manager.compact_session(session_id, _summarize_messages)

        except Exception as e:
            logger.error("Error handling DM: %s", traceback.format_exc())
            say(text=f"Error: {e}")


def run_slack(config: Optional[dict] = None) -> None:
    """Start Slack Socket Mode handler.

    Args:
        config: Pre-loaded config dict. If None, loads from default path.
    """
    if config is None:
        config = load_config()
    bot_token, app_token = _load_tokens(config)

    app = App(token=bot_token)

    # Create agent
    from yui.agent import create_agent
    agent = create_agent(config)

    # Session manager
    session_config = config.get("runtime", {}).get("session", {})
    db_path = session_config.get("db_path", "~/.yui/sessions.db")
    compaction_threshold = session_config.get("compaction_threshold", 50)
    keep_recent = session_config.get("keep_recent_messages", 5)
    session_manager = SessionManager(db_path, compaction_threshold, keep_recent)

    # Get bot user ID for dedup filtering
    try:
        _auth = app.client.auth_test()
        bot_user_id = _auth["user_id"]
        logger.info("Bot user ID: %s", bot_user_id)
    except Exception:
        bot_user_id = None
        logger.warning("Could not determine bot user ID for dedup")

    # Create handler
    handler = SlackHandler(
        agent=agent,
        session_manager=session_manager,
        slack_client=app.client,
        compaction_threshold=compaction_threshold,
        bot_user_id=bot_user_id,
    )

    # Wire events
    @app.event("app_mention")
    def on_mention(event: dict, say: callable) -> None:
        handler.handle_mention(event, say)

    @app.event("message")
    def on_message(event: dict, say: callable) -> None:
        handler.handle_dm(event, say)

    logger.info("Starting Slack Socket Mode...")
    socket_handler = SocketModeHandler(app, app_token)
    socket_handler.start()


def _summarize_messages(messages: list) -> str:
    """Summarize old messages into a system message."""
    summary_parts = ["[Conversation summary]"]
    for msg in messages:
        summary_parts.append(f"{msg.role}: {msg.content[:100]}")
    return "\n".join(summary_parts)
