# AGENTS.md — 結（Yui） エージェント運用ガイド

> Version: 1.0.0 | Last updated: 2026-03-10 | Issue #39 han feedback ④

---

## 1. エージェント概要

**結（Yui）** は軽量・AWS最適化AIエージェント。  
Mac上でローカル動作し、Bedrock Converse APIを通じてLLMを利用する。

---

## 2. Kiro相互レビューフロー（han feedback ④）

YuiはAYAと同様の「エージェント・エコシステムフロー」を採用する。

```
┌─────────────────────────────────────────────────────┐
│  Yui (設計・実装) ──→ Kiro CLI (レビュー) ──→ Yui (修正) │
│                                                     │
│  1. Yui が設計/コードを draft                          │
│  2. Kiro CLI がレビュー（Critical / Warning 指摘）     │
│  3. Yui が指摘を修正                                  │
│  4. Critical 0 になるまでループ                        │
│  5. PR作成 → hanさんレビュー                           │
└─────────────────────────────────────────────────────┘
```

### 2.1 Kiro相互レビューの対象

| 対象 | 必須/任意 | 説明 |
|---|---|---|
| 新機能（feat:）PR | **必須** | 外部API連携・既存フロー変更・セキュリティ境界に触れる場合 |
| requirements.md 更新 | **必須** | Phase定義・ツール設計の変更時 |
| リファクタリング（refactor:） | 推奨 | 既存処理フロー変更を伴う場合 |
| ドキュメント（docs:）のみ | 任意 | 設計変更なし・誤記修正等 |
| テスト追加（test:）のみ | 任意 | 実装変更なし |

### 2.2 Kiro CLIの呼び出し方

```bash
# 標準的なKiroレビュー呼び出し
kiro-cli chat --no-interactive --trust-all-tools "
以下のコードをレビューして、Critical/Warningがあれば指摘してください。
[コードまたは設計内容]
"

# タイムアウト目安
# - 単純レビュー: 60秒
# - 複雑設計: 120秒
# - 大規模実装: 180秒
```

### 2.3 レビュー結果の扱い

| 指摘レベル | 対応 |
|---|---|
| **Critical** | 即修正必須。修正後に再レビュー実施 |
| **Warning** | 修正推奨。スキップする場合はコメント付きで理由を明記 |
| **Suggestion** | 判断任意。プロセス系は確認後クローズ可能 |

**PR作成条件**: Critical 0件になるまでPR作成しない。

---

## 3. 開発フロー

### 3.1 基本フロー

```
1. Issue確認（要件・ACを把握）
2. Feature branch作成（feat/issue-{N}-{description}）
3. 実装
4. テスト実行（pytest）
5. Kiro CLIレビュー（対象の場合）
6. Critical指摘修正 → 再レビュー（必要なら）
7. PR作成（closes #{N} を含める）
8. hanさんレビュー → マージ
```

### 3.2 ブランチ命名規則

| タイプ | パターン | 例 |
|---|---|---|
| 機能追加 | `feat/issue-{N}-{description}` | `feat/issue-42-slack-adapter` |
| バグ修正 | `fix/issue-{N}-{description}` | `fix/issue-55-token-refresh` |
| ドキュメント | `docs/issue-{N}-{description}` | `docs/issue-39-agents-md` |
| リファクタリング | `refactor/issue-{N}-{description}` | `refactor/issue-60-agent-core` |

### 3.3 コミットメッセージ規則

```
<type>: <概要>

<変更理由・背景>（任意）
```

type: `feat` / `fix` / `docs` / `test` / `refactor` / `chore`

---

## 4. テスト方針

```bash
# 全テスト実行
python3 -m pytest -q

# カバレッジ確認
python3 -m pytest --cov=src/yui --cov-report=term-missing

# 目標: コアモジュール 80%以上
```

- **モック優先**: 外部APIは必ずモック化
- **E2Eテストは最小限**: 実AWS接続は smoke test のみ
- スキップ率上限: 10%（`pytest-skip-ratio` で管理）

---

## 5. Yui固有ルール

### 5.1 ツール使用

- `kiro_delegate` ツール: Kiro CLIへの委任（コーディングタスク）
- `shell` ツール: allowlist制御（config.yamlで定義）
- `use_browser` ツール: AgentCore Browser経由（ローカル実行）

### 5.2 セキュリティ

- 外部API呼び出し前に必ず確認
- シークレット（APIキー等）はAWS SSM Parameter Store経由
- `dangerouslySetInnerHTML` / `eval` 使用禁止

### 5.3 Macローカル固有

- `launchd` デーモン管理（Phase 3実装済み）
- ヘルスチェック: `~/Library/Logs/yui-agent/` を確認
- 設定ファイル: `config.yaml`（AGENTS.md/SOUL.md読み込み）

---

## 6. フェーズ進捗

| Phase | 内容 | 状態 |
|---|---|---|
| Phase 0 | CLI REPL + Bedrock Converse + exec/file tools | ✅ 完了 |
| Phase 1 | Slack Socket Mode + SQLite session管理 | ✅ 完了 |
| Phase 2 | Kiro CLI委任 + AgentCore Browser/Memory | ✅ 完了 |
| Phase 2.5 | Meeting Transcription（Whisper + Bedrock） | 📋 計画中 |
| Phase 3 | Bedrock Guardrails + Heartbeat + launchd | ✅ 完了 |
| Phase 4+ | Lambda + EventBridge, MCP server, Reflexion | 📋 計画中 |

---

## 参考

- `requirements.md`: 詳細要件・設計仕様
- `docs/testing-philosophy.md`: テスト設計方針
- `docs/deploy-guide.md`: セットアップ手順
