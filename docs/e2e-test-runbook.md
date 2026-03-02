# YUI E2E テスト実行手順書（OCA委譲フロー）

OCA（EC2上のOpenClaw AWS Agent）が yui-agent のE2Eテストを実行するための手順書。

---

## 前提条件

- **実行環境**: EC2インスタンス `i-058018cdc46bf4eaa`（ap-northeast-1）
- **リポジトリ**: `/home/ubuntu/yui-agent/`
- **Python**: 3.12.3（システムグローバル）
- **必要な権限**: AWS Bedrock（ap-northeast-1）へのアクセス権

---

## 1. 環境変数設定

### 1-1. .env ファイルの確認・作成

```bash
cd /home/ubuntu/yui-agent
cat .env | grep -v TOKEN  # 現在の設定確認（トークン非表示）
```

### 1-2. 必要な環境変数

| 変数名 | 用途 | 設定方法 |
|---|---|---|
| `YUI_AWS_E2E` | AgentCore E2Eテスト有効化 | `1` を設定 |
| `YUI_TEST_AWS` | AWS接続テスト有効化 | `1` を設定 |
| `YUI_TEST_SLACK` | Slack liveテスト有効化 | `1` を設定 |
| `YUI_LIVE_INTEGRATION` | AYA↔Yui統合テスト有効化 | `1` を設定 |
| `YUI_TEST_SLACK_CHANNEL` | テスト用Slackチャンネル | `C0AH55CBKGW`（#yui-test） |
| `SLACK_BOT_TOKEN` | Yui Bot Token | OpenClawの設定から取得 |
| `SLACK_APP_TOKEN` | Yui Socket Mode Token | xapp-1-... 形式 |
| `SLACK_BOT_TOKEN_AYA` | AYA Bot Token（メンション送信用） | xoxb-... 形式 |
| `YUI_TEST_GUARDRAIL_ID` | Guardrails E2Eテスト用ID | `ri5j1ct19c68` |
| `YUI_TEST_GUARDRAIL_VERSION` | Guardrails バージョン | `DRAFT` |

### 1-3. .env ファイルの作成例

```bash
cat > /home/ubuntu/yui-agent/.env << 'EOF'
YUI_AWS_E2E=1
YUI_TEST_AWS=1
YUI_TEST_SLACK=1
YUI_LIVE_INTEGRATION=1
YUI_TEST_SLACK_CHANNEL=C0AH55CBKGW
SLACK_BOT_TOKEN=<YUI_BOT_TOKEN>
SLACK_APP_TOKEN=<YUI_APP_TOKEN>
SLACK_BOT_TOKEN_AYA=<AYA_BOT_TOKEN>
YUI_TEST_GUARDRAIL_ID=ri5j1ct19c68
YUI_TEST_GUARDRAIL_VERSION=DRAFT
EOF
chmod 600 /home/ubuntu/yui-agent/.env
```

> **注意**: トークンはhanさん経由で取得すること。EC2のSSM Parameter Storeには現在保存されていない。

---

## 2. テスト種別と実行コマンド

### 2-1. E2Eテスト（mockベース）— 常時実行可能

```bash
cd /home/ubuntu/yui-agent
export $(cat .env | grep -v '^#' | xargs)

# E2Eテストのみ
python3 -m pytest tests/ -m e2e -v --tb=short --timeout=30 -q
```

**期待結果**: 70 passed / 42 skipped（実API系は正常スキップ）

### 2-2. Slack liveテスト

```bash
cd /home/ubuntu/yui-agent
export $(cat .env | grep -v '^#' | xargs)

python3 -m pytest tests/test_slack_live.py -v --tb=short
```

**期待結果**: 6 passed / 1 skipped（`test_mention_gets_response`はYui起動必要）

### 2-3. AYA↔Yui 統合テスト（Yui起動必要）

**Step 1: Yuiをバックグラウンドで起動**

```bash
cd /home/ubuntu/yui-agent
export $(cat .env | grep -v '^#' | xargs)

# バックグラウンド起動（ログは /tmp/yui-slack.log に記録）
nohup python3 -c "
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', filename='/tmp/yui-slack.log')
from yui.config import load_config
from yui.slack_adapter import run_slack
run_slack(load_config())
" > /tmp/yui-slack-stdout.log 2>&1 &
echo "Yui PID: $!"

# 起動確認（Socket Mode接続まで待つ）
sleep 8 && tail -5 /tmp/yui-slack.log
```

**Step 2: 統合テスト実行**

```bash
cd /home/ubuntu/yui-agent
export $(cat .env | grep -v '^#' | xargs)

# タイムアウト120秒で実行（Bedrock応答に時間がかかるため）
python3 -m pytest tests/test_aya_yui_integration.py -v --tb=short --timeout=120
```

**期待結果**: 9 passed（実行時間 約2〜3分）

**Step 3: テスト終了後にYuiをkill**

```bash
kill $(ps aux | grep "python3 -c.*run_slack\|python3 -m yui" | grep -v grep | awk '{print $2}') 2>/dev/null
echo "Yui stopped"
```

### 2-4. Guardrails E2Eテスト

```bash
cd /home/ubuntu/yui-agent
export $(cat .env | grep -v '^#' | xargs)

python3 -m pytest tests/test_guardrails_e2e.py -v --tb=short --timeout=60
```

**期待結果**: 11 passed / 4 failed（Guardrailsブロック系はStrands SDKバージョン変更により要修正 → Issue #108）

### 2-5. 全テスト合算確認

```bash
cd /home/ubuntu/yui-agent
export $(cat .env | grep -v '^#' | xargs)

# E2E + Slack liveの合算（Yui起動不要テストのみ）
python3 -m pytest tests/test_slack_e2e.py tests/test_slack_live.py -v --tb=short --timeout=30 -q
```

---

## 3. テスト結果の報告

テスト実行後、`#aya-aws-lab`（C0AHLSWJHSR）に以下フォーマットで報告する:

```
✅ yui-agent E2Eテスト完了 [日時]
Pass: N / Fail: N / Skip: N
Critical Issues: なし / あり（#N #N）
実行コマンド: python3 -m pytest tests/ -m e2e ...
```

---

## 4. トラブルシューティング

### Yui起動失敗

```bash
# ログ確認
cat /tmp/yui-slack.log
cat /tmp/yui-slack-stdout.log

# トークン確認（値は出力しない）
python3 -c "
import json, os
data = json.load(open('/home/ubuntu/.openclaw/openclaw.json'))
token = data.get('channels', {}).get('slack', {}).get('bot_token', '')
print('token length:', len(token))
"
```

### テストタイムアウト

統合テストはBedrock APIの応答待ちで時間がかかる。デフォルト60秒では不足するため `--timeout=120` を使用する。

### SLACK_APP_TOKEN 未設定

Socket Modeには `xapp-1-...` 形式のApp-Level Tokenが必要。

```bash
grep SLACK_APP_TOKEN /home/ubuntu/yui-agent/.env
```

未設定の場合はhanさんにSlack App設定画面から取得を依頼する。

### Guardrails テスト失敗（Issue #108）

`TestGuardrailsE2E` の4件はStrands SDK変更によりテスト側の修正が必要（コード本体のバグではない）。
修正PRを作成して対応予定。

---

## 5. 既知の制約

| 制約 | 詳細 |
|---|---|
| `test_mention_gets_response` (1 Skip) | Yui Socket Mode起動 + `--timeout=120` が必要 |
| Guardrails 4件 (Fail) | Strands SDKのAgentResult対応が必要（Issue #108） |
| AgentCore E2E (24 Skip) | `YUI_AWS_E2E=1` でもAgentCoreのエンドポイントが必要 |
| `test_aya_yui_integration.py` | Yui起動必須・実行時間2〜3分 |

---

## 6. 参照

- `docs/testing-philosophy.md` — テスト戦略・種別定義
- `tests/test_aya_yui_integration.py` — AYA↔Yui統合テスト
- `tests/test_slack_live.py` — Slack liveテスト
- Issue #108 — Guardrails TestのStrands SDK対応
