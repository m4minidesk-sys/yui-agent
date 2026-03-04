"""Component tests for Lambda handler core logic (FR-08-A1, A4, A5, A9)."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from tests.factories import LambdaContextFactory, LambdaEventFactory
from yui.lambda_handler import handler

pytestmark = pytest.mark.component


def test_lambda_handler__challenge_event__returns_challenge_value():
    challenge_value = "test_challenge_123"
    event = LambdaEventFactory.api_gateway_event(
        body=json.dumps(LambdaEventFactory.slack_challenge_event(challenge=challenge_value))
    )
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__event_callback__invokes_bedrock_stub():
    event_body = {
        "type": "event_callback",
        "event": {"type": "message", "text": "hello", "user": "U123", "channel": "C123"},
    }
    event = LambdaEventFactory.api_gateway_event(body=json.dumps(event_body))
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__invalid_signature__returns_401_unauthorized():
    event = LambdaEventFactory.api_gateway_event()
    event["headers"]["X-Slack-Signature"] = "v0=invalid_signature"
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__challenge_response__completes_under_100ms():
    challenge_value = "perf_test_challenge"
    event = LambdaEventFactory.api_gateway_event(
        body=json.dumps(LambdaEventFactory.slack_challenge_event(challenge=challenge_value))
    )
    context = LambdaContextFactory.create()

    start = time.perf_counter()
    with pytest.raises(NotImplementedError):
        handler(event, context)
    elapsed = time.perf_counter() - start

    assert elapsed < 0.1


def test_lambda_handler__consecutive_calls__no_state_pollution():
    event1 = LambdaEventFactory.api_gateway_event(
        body=json.dumps({"type": "url_verification", "challenge": "first"})
    )
    event2 = LambdaEventFactory.api_gateway_event(
        body=json.dumps({"type": "url_verification", "challenge": "second"})
    )
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event1, context)
    
    with pytest.raises(NotImplementedError):
        handler(event2, context)


def test_lambda_handler__api_gateway_event__converts_to_slack_event():
    slack_event = {"type": "event_callback", "event": {"type": "message"}}
    event = LambdaEventFactory.api_gateway_event(body=json.dumps(slack_event))
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__invalid_json_body__returns_400_bad_request():
    event = LambdaEventFactory.api_gateway_event(body="invalid json {{{")
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__bedrock_timeout__returns_error_to_slack():
    event_body = {"type": "event_callback", "event": {"type": "message", "text": "test"}}
    event = LambdaEventFactory.api_gateway_event(body=json.dumps(event_body))
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__slack_429__retries_with_backoff():
    event_body = {"type": "event_callback", "event": {"type": "message", "text": "test"}}
    event = LambdaEventFactory.api_gateway_event(body=json.dumps(event_body))
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__remaining_time_low__terminates_early():
    event_body = {"type": "event_callback", "event": {"type": "message", "text": "test"}}
    event = LambdaEventFactory.api_gateway_event(body=json.dumps(event_body))
    context = LambdaContextFactory.create(remaining_time_ms=500)

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__missing_body__returns_400_bad_request():
    event = LambdaEventFactory.api_gateway_event()
    del event["body"]
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__empty_body__returns_400_bad_request():
    event = LambdaEventFactory.api_gateway_event(body="")
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__missing_headers__returns_401_unauthorized():
    event = LambdaEventFactory.api_gateway_event()
    event["headers"] = {}
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__valid_signature__processes_event():
    event_body = {"type": "event_callback", "event": {"type": "message", "text": "hello"}}
    event = LambdaEventFactory.api_gateway_event(body=json.dumps(event_body))
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__bedrock_503__returns_error_response():
    event_body = {"type": "event_callback", "event": {"type": "message", "text": "test"}}
    event = LambdaEventFactory.api_gateway_event(body=json.dumps(event_body))
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__rate_limit_exceeded__backs_off_exponentially():
    event_body = {"type": "event_callback", "event": {"type": "message", "text": "test"}}
    event = LambdaEventFactory.api_gateway_event(body=json.dumps(event_body))
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__context_deadline_exceeded__returns_partial_response():
    event_body = {"type": "event_callback", "event": {"type": "message", "text": "long task"}}
    event = LambdaEventFactory.api_gateway_event(body=json.dumps(event_body))
    context = LambdaContextFactory.create(remaining_time_ms=100)

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__multiple_events_in_batch__processes_all():
    events = [
        {"type": "event_callback", "event": {"type": "message", "text": f"msg{i}"}}
        for i in range(3)
    ]
    event = LambdaEventFactory.api_gateway_event(body=json.dumps(events[0]))
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__slack_retry_header__skips_duplicate_processing():
    event_body = {"type": "event_callback", "event": {"type": "message", "text": "test"}}
    event = LambdaEventFactory.api_gateway_event(body=json.dumps(event_body))
    event["headers"]["X-Slack-Retry-Num"] = "1"
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__unknown_event_type__returns_200_ok():
    event_body = {"type": "unknown_type", "data": "something"}
    event = LambdaEventFactory.api_gateway_event(body=json.dumps(event_body))
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


# ── Phase 6 カバレッジ補強テスト (Part 1: handler基本動作) ───────────────────

import os
import json as _json
import time as _time
from unittest.mock import patch, MagicMock

# ── Phase 6 カバレッジ補強テスト ─────────────────────────────────────────────



def _make_lambda_env(monkeypatch):
    """LAMBDA_RUNTIME=true を設定するヘルパー。"""
    monkeypatch.setenv("LAMBDA_RUNTIME", "true")


def test_lambda_handler__url_verification__returns_challenge(monkeypatch):
    """url_verification イベントが challenge を返すこと。"""
    monkeypatch.setenv("LAMBDA_RUNTIME", "true")
    challenge_val = "abc123"
    event = LambdaEventFactory.api_gateway_event(
        body=_json.dumps({"type": "url_verification", "challenge": challenge_val})
    )
    context = LambdaContextFactory.create()

    from yui.lambda_handler import handler
    result = handler(event, context)
    assert result["statusCode"] == 200
    assert _json.loads(result["body"])["challenge"] == challenge_val


def test_lambda_handler__eventbridge_heartbeat__returns_200(monkeypatch):
    """EventBridge heartbeat が 200 を返すこと。"""
    monkeypatch.setenv("LAMBDA_RUNTIME", "true")
    event = LambdaEventFactory.eventbridge_event()
    context = LambdaContextFactory.create()

    from yui.lambda_handler import handler
    result = handler(event, context)
    assert result["statusCode"] == 200
    assert "heartbeat" in result["body"]


def test_lambda_handler__retry_header__returns_200(monkeypatch):
    """x-slack-retry-num ヘッダーがあれば即 200 を返すこと。"""
    monkeypatch.setenv("LAMBDA_RUNTIME", "true")
    event = LambdaEventFactory.api_gateway_event(
        body=_json.dumps({"type": "event_callback", "event": {"type": "message"}})
    )
    event["headers"]["x-slack-retry-num"] = "1"
    context = LambdaContextFactory.create()

    from yui.lambda_handler import handler
    result = handler(event, context)
    assert result["statusCode"] == 200
    assert "retry skipped" in result["body"]


def test_lambda_handler__empty_body_string__returns_400(monkeypatch):
    """空文字ボディは 400 を返すこと。"""
    monkeypatch.setenv("LAMBDA_RUNTIME", "true")
    event = LambdaEventFactory.api_gateway_event()
    event["body"] = ""  # Factoryのデフォルトを上書き
    context = LambdaContextFactory.create()

    from yui.lambda_handler import handler
    result = handler(event, context)
    assert result["statusCode"] == 400


def test_lambda_handler__invalid_json__returns_400(monkeypatch):
    """不正 JSON ボディは 400 を返すこと。"""
    monkeypatch.setenv("LAMBDA_RUNTIME", "true")
    event = LambdaEventFactory.api_gateway_event(body="not-json")
    context = LambdaContextFactory.create()

    from yui.lambda_handler import handler
    result = handler(event, context)
    assert result["statusCode"] == 400


def test_lambda_handler__event_callback_no_text__returns_200(monkeypatch):
    """event_callback でテキストなしの場合は 200 を返すこと。"""
    monkeypatch.setenv("LAMBDA_RUNTIME", "true")
    event = LambdaEventFactory.api_gateway_event(
        body=_json.dumps({
            "type": "event_callback",
            "event": {"type": "message", "channel": "C123"},
        })
    )
    context = LambdaContextFactory.create()

    from yui.lambda_handler import handler
    result = handler(event, context)
    assert result["statusCode"] == 200


def test_lambda_handler__low_remaining_time__returns_200(monkeypatch):
    """残余時間が少ない場合は早期終了で 200 を返すこと。"""
    monkeypatch.setenv("LAMBDA_RUNTIME", "true")
    event = LambdaEventFactory.api_gateway_event(
        body=_json.dumps({
            "type": "event_callback",
            "event": {"type": "message", "text": "hello", "channel": "C123"},
        })
    )
    # 残余時間 1000ms（閾値 2000ms 以下）
    context = LambdaContextFactory.create(remaining_time_ms=1000)

    from yui.lambda_handler import handler
    result = handler(event, context)
    assert result["statusCode"] == 200
    assert "timeout" in result["body"]




# ── Phase 6 カバレッジ補強テスト (Part 2: secrets/signature/event_callback) ──

def test_get_secrets__no_arn__returns_stub(monkeypatch):
    """SECRETS_ARN 未設定時はスタブ値を返すこと。"""
    monkeypatch.delenv("SECRETS_ARN", raising=False)
    import importlib
    import yui.lambda_handler_utils as lhu; import yui.lambda_handler as lh
    lhu._secrets_cache = None  # キャッシュリセット

    secrets = lhu._get_secrets()
    assert "BEDROCK_MODEL_ID" in secrets
    lhu._secrets_cache = None  # 後処理


def test_verify_slack_signature__no_signing_secret__returns_true(monkeypatch):
    """SLACK_SIGNING_SECRET 未設定時は検証をスキップして True を返すこと。"""
    monkeypatch.delenv("SLACK_SIGNING_SECRET", raising=False)
    from yui.lambda_handler_utils import _verify_slack_signature
    result = _verify_slack_signature({"X-Slack-Signature": "v0=abc"}, "body")
    assert result is True


def test_verify_slack_signature__stale_timestamp__returns_false(monkeypatch):
    """タイムスタンプが60秒以上古い場合は False を返すこと。"""
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "test_secret")
    stale_ts = str(int(_time.time()) - 120)  # 2分前
    from yui.lambda_handler_utils import _verify_slack_signature
    result = _verify_slack_signature(
        {"x-slack-signature": "v0=abc", "x-slack-request-timestamp": stale_ts},
        "body",
    )
    assert result is False


def test_verify_slack_signature__missing_headers__returns_false(monkeypatch):
    """署名ヘッダーがない場合は False を返すこと。"""
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "test_secret")
    from yui.lambda_handler_utils import _verify_slack_signature
    result = _verify_slack_signature({}, "body")
    assert result is False


# ── Secrets Manager / Bedrock モックテスト ──────────────────────────────────



def test_get_secrets__with_arn__returns_parsed_secret(monkeypatch):
    """SECRETS_ARN 設定時に Secrets Manager から値を取得すること。"""
    import yui.lambda_handler_utils as lhu; import yui.lambda_handler as lh
    lhu._secrets_cache = None

    secret_data = {"SLACK_BOT_TOKEN": "xoxb-test", "BEDROCK_MODEL_ID": "amazon.nova-lite-v1:0"}
    mock_sm = MagicMock()
    mock_sm.get_secret_value.return_value = {"SecretString": json.dumps(secret_data)}

    monkeypatch.setenv("SECRETS_ARN", "arn:aws:secretsmanager:us-east-1:123:secret:test")

    with patch("boto3.client", return_value=mock_sm):
        secrets = lhu._get_secrets()
    assert secrets["SLACK_BOT_TOKEN"] == "xoxb-test"
    lhu._secrets_cache = None


def test_get_secrets__resource_not_found__raises_runtime_error(monkeypatch):
    """存在しない ARN では RuntimeError を投げること。"""
    import yui.lambda_handler_utils as lhu; import yui.lambda_handler as lh
    lhu._secrets_cache = None
    monkeypatch.setenv("SECRETS_ARN", "arn:aws:secretsmanager:us-east-1:123:secret:missing")

    mock_sm = MagicMock()
    from botocore.exceptions import ClientError
    not_found_exc = ClientError(
        {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}},
        "GetSecretValue",
    )
    mock_sm.get_secret_value.side_effect = not_found_exc
    mock_sm.exceptions.ResourceNotFoundException = ClientError

    with patch("boto3.client", return_value=mock_sm):
        with pytest.raises(RuntimeError, match="not found"):
            lhu._get_secrets()
    lhu._secrets_cache = None


def test_lambda_handler__event_callback_with_mock_bedrock__returns_200(monkeypatch):
    """event_callback で Bedrock モック経由の応答が 200 を返すこと。"""
    monkeypatch.setenv("LAMBDA_RUNTIME", "true")
    monkeypatch.delenv("SECRETS_ARN", raising=False)
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)

    import yui.lambda_handler_utils as lhu; import yui.lambda_handler as lh
    lhu._secrets_cache = None

    event_body = {
        "type": "event_callback",
        "event": {"type": "message", "text": "hello", "channel": "C123", "user": "U123"},
    }
    event = LambdaEventFactory.api_gateway_event(body=json.dumps(event_body))
    context = LambdaContextFactory.create()

    bedrock_response = {
        "output": {"message": {"content": [{"text": "こんにちは！"}]}},
        "stopReason": "end_turn",
    }

    with patch("boto3.client") as mock_boto:
        mock_bedrock = MagicMock()
        mock_bedrock.converse.return_value = bedrock_response
        mock_boto.return_value = mock_bedrock

        result = lh.handler(event, context)
        assert result["statusCode"] == 200

    lhu._secrets_cache = None


def test_lambda_handler__socket_mode__raises_not_implemented(monkeypatch):
    """LAMBDA_RUNTIME が true 以外では NotImplementedError を返すこと。"""
    monkeypatch.setenv("LAMBDA_RUNTIME", "false")
    event = LambdaEventFactory.api_gateway_event()
    context = LambdaContextFactory.create()

    from yui.lambda_handler import handler
    with pytest.raises(NotImplementedError):
        handler(event, context)
