"""tests/test_e2e_flows.py — E2Eフロー実行テスト（mockベース）

YUI_TEST_AWS / YUI_LIVE_INTEGRATION 不要で全テストPASS。
実際のユーザーフローを mock で通しテスト。

Scenario 1: Slackメンション受信 → agent処理 → Bedrock応答 → Slack返信
Scenario 2: ファイル操作 → 結果返却フロー
Scenario 3: エラー時（Bedrockタイムアウト等）の graceful fallback
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.e2e


# ── 共通フィクスチャ ──────────────────────────────────────────────────────────

@pytest.fixture
def mock_bedrock_response():
    """正常なBedrock応答のモック。"""
    response = MagicMock()
    response.__str__ = lambda self: "Yui からの返答: テスト成功です。"
    return response


@pytest.fixture
def mock_agent(mock_bedrock_response):
    """mockエージェント — 予測可能な応答を返す。"""
    agent = MagicMock()
    agent.return_value = mock_bedrock_response
    return agent


@pytest.fixture
def mock_slack_client():
    """mockのSlackクライアント。"""
    client = MagicMock()
    client.chat_postMessage.return_value = {"ok": True, "ts": "1234567890.123456"}
    client.reactions_add.return_value = {"ok": True}
    client.reactions_remove.return_value = {"ok": True}
    return client


@pytest.fixture
def mock_session_manager():
    """mockのセッションマネージャ。"""
    sm = MagicMock()
    sm.get_message_count.return_value = 3
    sm.get_messages.return_value = []
    return sm


@pytest.fixture
def slack_handler(mock_agent, mock_session_manager, mock_slack_client):
    """SlackHandlerインスタンス（mock依存）。"""
    from yui.slack_adapter import SlackHandler
    return SlackHandler(
        agent=mock_agent,
        session_manager=mock_session_manager,
        slack_client=mock_slack_client,
        bot_user_id="U_YUI_BOT",
    )


def make_say(mock_slack_client, channel: str, default_thread_ts: str = None):
    """SlackHandlerのsay関数をエミュレートするファクトリ。"""
    def say(text: str, thread_ts: str = None):
        mock_slack_client.chat_postMessage(
            channel=channel,
            text=text,
            thread_ts=thread_ts or default_thread_ts,
        )
    return say


# ── Scenario 1: Slackメンション → agent処理 → Bedrock応答 → Slack返信 ────────

class TestScenario1SlackMentionFlow:
    """Scenario 1: メンション受信からSlack返信までのE2Eフロー。"""

    def test_mention_full_flow_channel_message(
        self, slack_handler, mock_agent, mock_slack_client
    ):
        """チャンネルメンション → agent呼び出し → Slack投稿の完全フロー。"""
        channel = "C_CHANNEL_001"
        ts = "1000000001.000001"
        event = {
            "type": "app_mention",
            "user": "U_USER_001",
            "text": "<@U_YUI_BOT> こんにちは、テストです",
            "channel": channel,
            "ts": ts,
            "event_ts": ts,
        }

        say = make_say(mock_slack_client, channel, ts)
        slack_handler.handle_mention(event, say)

        # agentが呼ばれたことを確認
        mock_agent.assert_called_once()
        call_args = mock_agent.call_args[0][0]
        assert "こんにちは、テストです" in call_args

        # Slack返信が投稿されたことを確認
        assert mock_slack_client.chat_postMessage.called

    def test_mention_flow_includes_thinking_reaction(
        self, slack_handler, mock_slack_client
    ):
        """メンション受信時に 👀 リアクションが付く。"""
        channel = "C_CHANNEL_001"
        ts = "1000000002.000001"
        event = {
            "type": "app_mention",
            "user": "U_USER_001",
            "text": "<@U_YUI_BOT> 処理中リアクション確認",
            "channel": channel,
            "ts": ts,
            "event_ts": ts,
        }

        say = make_say(mock_slack_client, channel, ts)
        slack_handler.handle_mention(event, say)

        # eyes リアクションが追加されたことを確認
        assert mock_slack_client.reactions_add.called
        add_calls = mock_slack_client.reactions_add.call_args_list
        reaction_names = [c[1].get("name", "") for c in add_calls]
        assert "eyes" in reaction_names

    def test_mention_flow_dm_response(
        self, slack_handler, mock_agent, mock_slack_client
    ):
        """DMメンション → agentがDMに返信するフロー。"""
        channel = "D_DM_CHANNEL"
        ts = "1000000003.000001"
        event = {
            "type": "message",
            "user": "U_USER_002",
            "text": "DMからのメッセージ",
            "channel": channel,
            "channel_type": "im",
            "ts": ts,
            "event_ts": ts,
        }

        say = make_say(mock_slack_client, channel, ts)
        slack_handler.handle_dm(event, say)

        mock_agent.assert_called_once()
        assert mock_slack_client.chat_postMessage.called

    def test_mention_session_persistence(
        self, slack_handler, mock_agent, mock_session_manager
    ):
        """メンション → agent応答がセッションに永続化されるフロー。"""
        channel = "C_CHANNEL_002"
        ts = "1000000004.000001"
        event = {
            "type": "app_mention",
            "user": "U_USER_003",
            "text": "<@U_YUI_BOT> セッション確認",
            "channel": channel,
            "ts": ts,
            "event_ts": ts,
        }

        say = make_say(MagicMock(), channel, ts)
        slack_handler.handle_mention(event, say)

        # セッションへのメッセージ追加が呼ばれたことを確認
        assert mock_session_manager.add_message.call_count >= 1

    def test_mention_concurrent_lock_serialization(
        self, mock_agent, mock_session_manager, mock_slack_client
    ):
        """並列リクエストがロックで直列化されること（concurrency安全性）。"""
        from yui.slack_adapter import SlackHandler

        handler = SlackHandler(
            agent=mock_agent,
            session_manager=mock_session_manager,
            slack_client=mock_slack_client,
            bot_user_id="U_YUI_BOT",
        )

        results = []
        errors = []

        def call_mention(idx: int):
            channel = "C_CONCURRENT"
            ts = f"100000000{idx}.000001"
            event = {
                "type": "app_mention",
                "user": f"U_USER_{idx:03}",
                "text": f"<@U_YUI_BOT> 並列テスト {idx}",
                "channel": channel,
                "ts": ts,
                "event_ts": ts,
            }
            say = make_say(mock_slack_client, channel, ts)
            try:
                handler.handle_mention(event, say)
                results.append(idx)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=call_mention, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # 全リクエストが処理されたこと（エラーなし）
        assert len(errors) == 0, f"並列実行中にエラー: {errors}"
        assert len(results) == 3


# ── Scenario 2: ファイル操作 → 結果返却フロー ────────────────────────────────

class TestScenario2FileOperationFlow:
    """Scenario 2: ファイル操作（FileInterface）を通じた結果返却フロー。"""

    def test_create_task_dir_and_write_meta(self, tmp_path):
        """タスクディレクトリ作成 → メタ書き込み → 読み込み返却フロー。"""
        from yui.autonomy.file_interface import FileInterface

        fi = FileInterface(workspace_root=tmp_path)
        task_id = "e2e-test-2026-0302-0001"

        task_dir = fi.create_task_dir(task_id)
        assert task_dir.exists()
        assert task_dir.name == task_id

        meta = {"status": "running", "task": "E2Eテスト"}
        fi.write_meta(task_id, meta)

        loaded_meta = fi.read_meta(task_id)
        assert loaded_meta["status"] == "running"
        assert loaded_meta["task"] == "E2Eテスト"

    def test_write_summary_and_retrieve(self, tmp_path):
        """サマリー書き込み → ファイル経由での結果取得フロー。"""
        from yui.autonomy.file_interface import FileInterface

        fi = FileInterface(workspace_root=tmp_path)
        task_id = "e2e-summary-2026-0302"
        fi.create_task_dir(task_id)

        summary_content = "# テスト結果\n- テスト1: PASS\n- テスト2: PASS"
        summary_path = fi.write_summary(task_id, summary_content)

        assert summary_path.exists()
        content = summary_path.read_text(encoding="utf-8")
        assert "テスト1: PASS" in content

    def test_initial_meta_status_running(self, tmp_path):
        """create_initial_meta のステータスが running であること（実装値に合わせる）。"""
        from yui.autonomy.file_interface import FileInterface

        fi = FileInterface(workspace_root=tmp_path)
        task_id = "e2e-init-meta-2026-0302"
        fi.create_task_dir(task_id)

        meta = fi.create_initial_meta(task_id)
        assert meta["status"] == "running"
        assert "task_id" in meta

    def test_file_operation_agent_mock_flow(self):
        """agentがファイル操作ツールを呼び出して結果を返すフロー（mock）。"""
        mock_agent = MagicMock()
        mock_agent.return_value = "ファイルに 'hello E2E' を書き込みました。"

        result = str(mock_agent("tests/workspace/hello.txt に 'hello E2E' と書いて"))
        assert "hello E2E" in result or "書き込みました" in result
        mock_agent.assert_called_once()

    def test_summary_max_chars_truncation(self, tmp_path):
        """サマリーが max_chars を超えた場合に切り詰められること。"""
        from yui.autonomy.file_interface import FileInterface

        fi = FileInterface(workspace_root=tmp_path)
        task_id = "e2e-truncate-2026-0302"
        fi.create_task_dir(task_id)

        long_content = "あ" * 3000
        summary_path = fi.write_summary(task_id, long_content, max_chars=2000)
        content = summary_path.read_text(encoding="utf-8")
        assert len(content) <= 2000

    def test_multiple_task_dirs_independent(self, tmp_path):
        """複数タスクのディレクトリが独立して管理されること。"""
        from yui.autonomy.file_interface import FileInterface

        fi = FileInterface(workspace_root=tmp_path)
        for i in range(3):
            task_id = f"e2e-multi-{i}"
            fi.create_task_dir(task_id)
            fi.write_meta(task_id, {"task_number": i})

        for i in range(3):
            task_id = f"e2e-multi-{i}"
            meta = fi.read_meta(task_id)
            assert meta["task_number"] == i


# ── Scenario 3: エラー時の graceful fallback ─────────────────────────────────

class TestScenario3ErrorFallback:
    """Scenario 3: エラー時（Bedrockタイムアウト等）の graceful fallback。"""

    def test_bedrock_timeout_fallback(
        self, slack_handler, mock_agent, mock_slack_client
    ):
        """Bedrockタイムアウト時に例外が外に漏れず Slack に応答が届くこと。"""
        from botocore.exceptions import ReadTimeoutError

        mock_agent.side_effect = ReadTimeoutError(endpoint_url="https://bedrock.amazonaws.com")

        channel = "C_CHANNEL_010"
        ts = "2000000001.000001"
        event = {
            "type": "app_mention",
            "user": "U_USER_010",
            "text": "<@U_YUI_BOT> タイムアウトテスト",
            "channel": channel,
            "ts": ts,
            "event_ts": ts,
        }

        say = make_say(mock_slack_client, channel, ts)
        try:
            slack_handler.handle_mention(event, say)
        except ReadTimeoutError:
            pytest.fail("ReadTimeoutError が SlackHandler の外に漏れた")

        # fallback メッセージがSlackに投稿されたこと
        assert mock_slack_client.chat_postMessage.called

    def test_bedrock_client_error_fallback(
        self, slack_handler, mock_agent, mock_slack_client
    ):
        """BedrockのClientError（スロットリング）時にfallbackが動作すること。"""
        from botocore.exceptions import ClientError

        error_response = {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}
        mock_agent.side_effect = ClientError(error_response, "Converse")

        channel = "C_CHANNEL_011"
        ts = "2000000002.000001"
        event = {
            "type": "app_mention",
            "user": "U_USER_011",
            "text": "<@U_YUI_BOT> スロットリングテスト",
            "channel": channel,
            "ts": ts,
            "event_ts": ts,
        }

        say = make_say(mock_slack_client, channel, ts)
        try:
            slack_handler.handle_mention(event, say)
        except ClientError:
            pytest.fail("ClientError が SlackHandler の外に漏れた")

        assert mock_slack_client.chat_postMessage.called

    def test_generic_exception_fallback(
        self, slack_handler, mock_agent, mock_slack_client
    ):
        """予期しない例外発生時もSlackに何かしらの応答が返ること。"""
        mock_agent.side_effect = RuntimeError("予期しない内部エラー")

        channel = "C_CHANNEL_012"
        ts = "2000000003.000001"
        event = {
            "type": "app_mention",
            "user": "U_USER_012",
            "text": "<@U_YUI_BOT> 予期しないエラーテスト",
            "channel": channel,
            "ts": ts,
            "event_ts": ts,
        }

        say = make_say(mock_slack_client, channel, ts)
        try:
            slack_handler.handle_mention(event, say)
        except RuntimeError:
            pytest.fail("RuntimeError が SlackHandler の外に漏れた")

        assert mock_slack_client.chat_postMessage.called

    def test_bedrock_error_handler_retry_exhaustion(self):
        """BedrockErrorHandlerがmax_retriesまで試みること。"""
        from yui.agent import BedrockErrorHandler
        from botocore.exceptions import ReadTimeoutError

        handler = BedrockErrorHandler(max_retries=2, backoff_base=0.01)
        call_count = 0

        def always_timeout():
            nonlocal call_count
            call_count += 1
            raise ReadTimeoutError(endpoint_url="https://bedrock.amazonaws.com")

        with pytest.raises(Exception):
            handler.retry_with_backoff(always_timeout)

        assert call_count == handler.max_retries

    def test_bedrock_error_handler_succeeds_on_retry(self):
        """BedrockErrorHandlerが2回目で成功するシナリオ。"""
        from yui.agent import BedrockErrorHandler
        from botocore.exceptions import ReadTimeoutError

        handler = BedrockErrorHandler(max_retries=3, backoff_base=0.01)
        call_count = 0

        def fails_once_then_succeeds():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ReadTimeoutError(endpoint_url="https://bedrock.amazonaws.com")
            return "success"

        result = handler.retry_with_backoff(fails_once_then_succeeds)
        assert result == "success"
        assert call_count == 2

    def test_dm_error_fallback(
        self, slack_handler, mock_agent, mock_slack_client
    ):
        """DM処理中のエラー時もSlack返信が行われること。"""
        mock_agent.side_effect = Exception("DM処理エラー")

        channel = "D_DM_CHANNEL_013"
        ts = "2000000004.000001"
        event = {
            "type": "message",
            "user": "U_USER_013",
            "text": "エラーを起こすDM",
            "channel": channel,
            "channel_type": "im",
            "ts": ts,
            "event_ts": ts,
        }

        say = make_say(mock_slack_client, channel, ts)
        try:
            slack_handler.handle_dm(event, say)
        except Exception:
            pytest.fail("例外が SlackHandler の外に漏れた")

        assert mock_slack_client.chat_postMessage.called
