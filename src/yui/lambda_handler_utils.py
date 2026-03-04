"""Lambda handler utilities for AWS deployment.

Helper functions extracted from lambda_handler.py:
- _get_secrets: Secrets Manager lazy init + cache
- _verify_slack_signature: HMAC-SHA256 signature verification
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time

import boto3

logger = logging.getLogger(__name__)

# ── Secrets キャッシュ（Lambda コールド→ウォーム間で再利用） ─────────────────
_secrets_cache: dict[str, str] | None = None


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
    except client.exceptions.ResourceNotFoundException:
        logger.error("Secrets retrieval failed: secret not found")
        raise RuntimeError("Secrets retrieval failed: secret not found") from None
    except client.exceptions.AccessDeniedException:
        logger.error("Secrets retrieval failed: access denied")
        raise RuntimeError("Secrets retrieval failed: access denied") from None
    except json.JSONDecodeError:
        logger.error("Secrets retrieval failed: malformed secret JSON")
        raise RuntimeError("Secrets retrieval failed: malformed JSON") from None
    except Exception:
        logger.exception("Secrets retrieval failed: unexpected error")
        raise RuntimeError("Secrets retrieval failed: internal error") from None


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
        logger.warning("SLACK_SIGNING_SECRET not set; skipping signature verification")
        return True

    lower_headers = {k.lower(): v for k, v in headers.items()}
    sig = lower_headers.get("x-slack-signature", "")
    ts = lower_headers.get("x-slack-request-timestamp", "")

    if not sig or not ts:
        return False

    # リプレイアタック防止: タイムスタンプが60秒以上古い場合は拒否
    try:
        ts_int = int(ts)
        delta = abs(time.time() - ts_int)
        if delta > 60:
            logger.warning("Stale or future timestamp rejected (delta=%.1fs)", delta)
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
