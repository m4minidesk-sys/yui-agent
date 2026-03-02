# 結（Yui） — Your Unified Intelligence

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![AWS](https://img.shields.io/badge/AWS-Bedrock-orange.svg)](https://aws.amazon.com/bedrock/)

**Lightweight, secure, AWS-optimized AI agent orchestrator** — an OpenClaw alternative built on the Strands Agent SDK.

> 結（ゆい / Yui） — "to tie, to bind, to connect"

## Features

- 🧠 **Strands Agent SDK** — Modern agent framework with built-in tool orchestration
- ☁️ **AWS-Native** — Bedrock Converse API, AgentCore Browser/Memory, Guardrails
- 🛠️ **Rich Tool Suite** — exec, file ops, git, Kiro delegation, Slack
- 💬 **Multi-Channel** — CLI REPL + Slack Socket Mode
- 💾 **Persistent Sessions** — SQLite local + S3 sync
- 🔒 **Security First** — Command allowlists, Bedrock Guardrails, scoped file access
- 🍎 **macOS-Optimized** — Designed for Mac (arm64) with launchd daemon
- ⏰ **Heartbeat** — Periodic autonomous actions with configurable schedules
- 😈 **Daemon Mode** — launchd background service
- 🎤 **Meeting Transcription** — Whisper-based STT + auto-minutes via Bedrock
- 🖥️ **Menu Bar App** — One-click recording trigger from macOS status bar

## Architecture

```
LOCAL TIER (macOS)                    CLOUD TIER (AWS)
┌────────────────────────────┐    ┌─────────────────────────────┐
│  Strands Agent (Core)      │←──→│  Bedrock Converse API       │
│  ├── Local Tools           │    │  ├── Claude / Nova models   │
│  │   ├── exec              │    │  └── Bedrock Guardrails     │
│  │   ├── file ops          │    │                             │
│  │   ├── git               │    │  AgentCore Services         │
│  │   ├── kiro delegate     │    │  ├── Browser Tool           │
│  │   └── outlook           │    │  ├── Memory                 │
│  │                         │    │  └── Web Search             │
│  ├── Channels              │    │                             │
│  │   ├── CLI REPL          │    │  Storage & Logging          │
│  │   └── Slack             │    │  ├── S3 (session sync)      │
│  │                         │    │  └── CloudWatch Logs        │
│  └── Runtime               │    └─────────────────────────────┘
│      ├── Session (SQLite)  │
│      ├── Config Loader     │
│      ├── Heartbeat         │
│      └── Daemon            │
└────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.12+
- AWS credentials configured (`~/.aws/credentials` or environment variables)
- Bedrock model access enabled in your AWS account

### Installation

```bash
# Clone
git clone https://github.com/m4minidesk-sys/yui-agent.git
cd yui-agent

# Install
pip install -e .

# Copy config
cp config.yaml.example ~/.yui/config.yaml
cp .env.example .env

# Run
python -m yui
```

### Usage

```bash
# Interactive REPL
python -m yui

# Single command
python -m yui --prompt "List files in the current directory"

# With custom config
python -m yui --config /path/to/config.yaml

# Slack mode
python -m yui --slack

# Daemon mode
python -m yui --daemon
```

## Configuration

Edit `~/.yui/config.yaml`:

```yaml
agent:
  model_id: "us.anthropic.claude-sonnet-4-20250514"
  region: "us-east-1"

workspace:
  root: "~/.yui/workspace"
```

See [config.yaml.example](config.yaml.example) for full options.

## Workspace

Yui uses markdown files for agent behavior and personality:

- **AGENTS.md** — Agent behavior rules and conventions
- **SOUL.md** — Agent personality and tone

Place these in your workspace directory (`~/.yui/workspace/` by default).

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check .

# Type check
mypy yui/
```

## Testing

### Unit/Component Tests
```bash
pytest tests/ -m 'not integration and not e2e'
```

### Contract Tests (requires AWS credentials)
```bash
pytest tests/contracts/ -m integration
```

### Mock Drift Detection
```bash
# Dry-run mode
python scripts/check_mock_drift.py --dry-run

# Check specific API
python scripts/check_mock_drift.py --api bedrock --dry-run

# Create GitHub Issue (CI only)
python scripts/check_mock_drift.py --create-issue
```


## Testing

See [docs/testing-philosophy.md](docs/testing-philosophy.md) for the full testing strategy:
mock vs real API の判断基準、テスト種別定義（unit/component/integration/e2e/live）、
既存テストのカテゴリ対応表。

## Phase Roadmap

| Phase | Scope | Timeline |
|---|---|---|
| **Phase 0** | CLI + Bedrock + exec/file tools | 3 days |
| **Phase 1** | Slack + Session management | 1 week |
| **Phase 2** | Kiro/git/AgentCore Browser/Memory | 1 week |
| **Phase 2.5** | Meeting Transcription + Menu Bar UI | 1 week |
| **Phase 3** | Guardrails + Heartbeat + Daemon (launchd) | 1 week |

## License

MIT License — see [LICENSE](LICENSE) for details.

## Acknowledgments

- [Strands Agent SDK](https://github.com/strands-agents/sdk-python) — The agent framework
- [Amazon Bedrock](https://aws.amazon.com/bedrock/) — LLM backbone
- [OpenClaw](https://github.com/nichochar/openclaw) — Inspiration and reference architecture
