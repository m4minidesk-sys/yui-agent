"""Lambda handler for AWS deployment (Phase 6 implementation).

Supports:
- API Gateway proxy event (Slack Events API)
- EventBridge scheduled event (heartbeat)

Environment variables:
- LAMBDA_RUNTIME: "true" to enable Events API mode (required)
- SECRETS_ARN: Secrets Manager ARN containing SLACK_BOT_TOKEN / BEDROCK_MODEL_ID
- BEDROCK_GUARDRAIL_ID: (optional) Bedrock Guardrail ID
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ── Secrets キャッシュ（Lambda コールド→ウォーム間で再利用） ─────────────────
_secrets_cache: dict[str, str] | None = None

_TIMEOUT_THRESHOLD_MS = 2000  # 残余時間がこれ以下なら早期終了

# ── Secrets Manager ─────────────────────────────────────────────────────────


def _get_secrets() -> dict[str, str]:
    """Secrets Manager から認証情報を取得する（lazy init + キャッシュ）。

    Returns:
        {"SLACK_BOT_TOKEN": str, "BEDROCK_MODEL_ID": str}

    Raises:
        RuntimeError: Secrets Manager 呼び出しに失敗した場合
    """
    global _secrets_cache
    if _secrets_cache is not None:
        return _secrets_cache

    secrets_arn = os.environ.get("SECRETS_ARN", "")
    if not secrets_arn:
        # 環境変数が未設定の場合はスタブ値を返す（ローカルテスト用）
        logger.warning("SECRETS_ARN not set; using stub secrets")
        _secrets_cache = {
            "SLACK_BOT_TOKEN": os.environ.get("SLACK_BOT_TOKEN", ""),
            "BEDROCK_MODEL_ID": os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"),
        }
        return _secrets_cache

    try:
        client = boto3.client("secretsmanager")
        response = client.get_secret_value(SecretId=secrets_arn)
        raw = response["SecretString"]
        _secrets_cache = json.loads(raw)
        return _secrets_cache
    except client.exceptions.ResourceNotFoundException as e:
        logger.error("Secrets not found: %s", e)
        raise RuntimeError(f"Secret not found: {secrets_arn}") from e
    except client.exceptions.AccessDeniedException as e:
        logger.error("Secrets access denied: %s", e)
        raise RuntimeError(f"Access denied to secret: {secrets_arn}") from e
    except json.JSONDecodeError as e:
        logger.error("Malformed secret JSON: %s", e)
        raise
    except Exception as e:  # network timeout etc.
        logger.error("Failed to get secrets: %s", e)
        raise RuntimeError(f"Secrets retrieval error: {e}") from e


# ── Slack 署名検証 ────────────────────────────────────────────────────────────


def _verify_slack_signature(headers: dict[str, str], body: str) -> bool:
    """Slack の X-Slack-Signature を検証する。

    Args:
        headers: HTTP ヘッダー（大文字小文字を問わず）
        body: リクエストボディの生文字列

    Returns:
        True なら検証通過、False なら失敗
    """
    signing_secret = os.environ.get("SLACK_SIGNING_SECRET", "")
    if not signing_secret:
        # テスト環境ではスキップ
        logger.warning("SLACK_SIGNING_SECRET not set; skipping signature verification")
        return True

    # ヘッダーはケース非依存で取得
    lower_headers = {k.lower(): v for k, v in headers.items()}
    sig = lower_headers.get("x-slack-signature", "")
    ts = lower_headers.get("x-slack-request-timestamp", "")

    if not sig or not ts:
        return False

    # リプレイアタック防止: タイムスタンプが5分以上古い場合は拒否
    try:
        if abs(time.time() - int(ts)) > 300:
            logger.warning("Stale timestamp: %s", ts)
            return False
    except ValueError:
        return False

    basestring = f"v0:{ts}:{body}"
    computed = "v0=" + hmac.new(
        signing_secret.encode("utf-8"),
        basestring.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed, sig)


# ── イベントハンドラー ────────────────────────────────────────────────────────


def _handle_url_verification(body: dict[str, Any]) -> dict[str, Any]:
    """Slack URL verification (challenge) に応答する。"""
    challenge = body.get("challenge", "")
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"challenge": challenge}),
    }


def _handle_event_callback(body: dict[str, Any], context: Any) -> dict[str, Any]:
    """Slack event_callback を処理し、Bedrock 経由で応答を生成する。

    Args:
        body: Slack イベントのボディ
        context: Lambda context オブジェクト

    Returns:
        API Gateway proxy response
    """
    # 残余時間チェック
    if hasattr(context, "get_remaining_time_in_millis"):
        remaining = context.get_remaining_time_in_millis()
        if remaining < _TIMEOUT_THRESHOLD_MS:
            logger.warning("Remaining time low (%dms), returning early", remaining)
            return {
                "statusCode": 200,
                "body": json.dumps({"message": "timeout approaching, skipped"}),
            }

    event = body.get("event", {})
    text = event.get("text", "")
    channel = event.get("channel", "")

    if not text or not channel:
        return {"statusCode": 200, "body": json.dumps({"message": "no text or channel"})}

    try:
        secrets = _get_secrets()
        model_id = secrets.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

        bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        response = bedrock.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": text}]}],
        )
        reply_text = response["output"]["message"]["content"][0]["text"]

        # Slack に投稿
        import urllib.request
        slack_token = secrets.get("SLACK_BOT_TOKEN", "")
        if slack_token:
            payload = json.dumps({"channel": channel, "text": reply_text}).encode("utf-8")
            req = urllib.request.Request(
                "https://slack.com/api/chat.postMessage",
                data=payload,
                headers={
                    "Authorization": f"Bearer {slack_token}",
                    "Content-Type": "application/json",
                },
            )
            urllib.request.urlopen(req, timeout=10)

        return {"statusCode": 200, "body": json.dumps({"message": "ok"})}

    except Exception as e:
        logger.error("event_callback error: %s", e)
        return {"statusCode": 500, "body": json.dumps({"message": "internal error"})}


def _handle_heartbeat() -> dict[str, Any]:
    """EventBridge scheduled event によるハートビート処理。"""
    logger.info("heartbeat: %s", time.strftime("%Y-%m-%dT%H:%M:%SZ"))
    return {
        "statusCode": 200,
        "body": json.dumps({"message": "heartbeat ok", "ts": int(time.time())}),
    }


# ── Lambda エントリーポイント ────────────────────────────────────────────────


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler entry point.

    Routing:
        EventBridge Scheduled Event  → _handle_heartbeat()
        API Gateway POST             → Slack Events API 処理
            url_verification         → _handle_url_verification()
            event_callback           → _handle_event_callback()

    Args:
        event: API Gateway proxy event or EventBridge schedule event
        context: Lambda context object

    Returns:
        dict: API Gateway proxy response format

    Raises:
        NotImplementedError: LAMBDA_RUNTIME が "true" 以外の場合（Socket Mode）
    """
    # Socket Mode / Events API 切り替え
    if os.environ.get("LAMBDA_RUNTIME") != "true":
        raise NotImplementedError(
            "Socket Mode is not supported in this handler. "
            "Set LAMBDA_RUNTIME=true to enable Events API mode."
        )

    # EventBridge scheduled event
    if event.get("detail-type") == "Scheduled Event":
        return _handle_heartbeat()

    # API Gateway proxy event
    headers = event.get("headers") or {}
    lower_headers = {k.lower(): v for k, v in headers.items()}

    # リトライスキップ（Slack の重複送信防止）
    if lower_headers.get("x-slack-retry-num"):
        logger.info("Skipping retry: x-slack-retry-num=%s", lower_headers["x-slack-retry-num"])
        return {"statusCode": 200, "body": json.dumps({"message": "retry skipped"})}

    # リクエストボディ取得
    raw_body = event.get("body") or ""
    if not raw_body:
        return {"statusCode": 400, "body": json.dumps({"error": "empty body"})}

    # JSON パース
    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        return {"statusCode": 400, "body": json.dumps({"error": "invalid json"})}

    # Slack 署名検証
    if not _verify_slack_signature(headers, raw_body):
        return {"statusCode": 401, "body": json.dumps({"error": "invalid signature"})}

    # イベントタイプ別処理
    event_type = body.get("type", "")
    if event_type == "url_verification":
        return _handle_url_verification(body)
    elif event_type == "event_callback":
        return _handle_event_callback(body, context)
    else:
        logger.info("Unknown event type: %s", event_type)
        return {"statusCode": 200, "body": json.dumps({"message": "unhandled event"})}
