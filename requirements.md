# 結（Yui） — Requirements Document

> Lightweight, AWS-optimized AI agent orchestrator inspired by OpenClaw.
> Name: 結（ゆい / Yui） — meaning "to tie, to bind, to connect"
> Version: 0.10.0-draft | Last updated: 2026-02-26 | Reviewed by: Kiro CLI (v1.26.2, 4 rounds) + han feedback

---

## 1. Background & Problem Statement

### 1.1 Why build this?

OpenClaw is a powerful AI agent orchestrator (400K+ lines TypeScript, 54 npm deps, 300MB+ install) but has critical constraints for AWS corporate environments:

- **License**: ELv2 (Elastic License v2) — restricts providing as a managed service
- **External API dependency**: Default model calls go through Anthropic/OpenAI APIs — violates corporate data governance policies that require data to stay within AWS VPC
- **Size/complexity**: 300MB+ install with Node.js runtime — excessive for a corporate laptop tool
- **No Bedrock-native support**: Requires additional configuration to use AWS Bedrock; not designed for it

### 1.2 Target users

AWS corporate engineers who need a local AI coding assistant that:
- Integrates with Slack for daily communication
- Uses Bedrock API for LLM calls (data stays in AWS)
- Runs local tools (Kiro CLI, git, Outlook, shell commands)
- Can be set up in <10 minutes on a Mac

### 1.3 Success criteria

| Criteria | Target |
|---|---|
| Install size | <50MB (vs OpenClaw's 300MB+) |
| Python dependencies | ≤10 packages (core), ≤15 with all optional features (meeting + ui + hotkey) |
| Time to first working agent | <10 minutes |
| Bedrock Converse API latency overhead | <100ms over raw API call |
| Test coverage | >80% for core modules |

---

## 2. Scope

### 2.1 In scope (Phase 0–3)

| Phase | Deliverables |
|---|---|
| Phase 0 | CLI REPL + Bedrock Converse + exec/file tools + AGENTS.md/SOUL.md config loading |
| Phase 1 | Slack Socket Mode adapter + SQLite session management + session compaction |
| Phase 2 | Kiro CLI delegation tool + git tool + AgentCore Browser Tool + AgentCore Memory |
| Phase 2.5 | **Meeting Transcription & Minutes** (Whisper + Bedrock) — standalone feature, does not block Phase 3 |
| Phase 3 | Bedrock Guardrails integration + Heartbeat scheduler + launchd daemon (macOS) |

### 2.2 Out of scope (explicit exclusions)

- **Windows support** — Mac-only for initial release
- **mwinit/Midway authentication caching** — users handle AWS auth externally
- **Docker sandbox** — uses command allowlist/blocklist instead
- **Multi-channel support** — Slack + CLI only (no Telegram, Discord, etc.)
- **Plugin/Hook system** — tools are registered in code or via MCP, not via plugin hooks
- **MCP server hosting** — Yui consumes MCP tools but does not expose MCP endpoints
- **24/7 Slack Bot (Lambda deployment)** — Phase 0-3 uses local Socket Mode only; cloud Slack adapter deferred to Phase 4+
- **Flexible cron scheduling (EventBridge)** — Phase 0-3 uses fixed-interval Heartbeat only; EventBridge deferred to Phase 4+
- **External search APIs as default** — Tavily/Exa are opt-in only; default web search uses Bedrock Knowledge Base (VPC-internal)

### 2.3 Pre-Phase 0: SDK Verification Gate (Kiro review C-01)

Before any implementation begins, verify all SDK assumptions:

- [ ] Confirm `strands-agents` package name and import path (`from strands import Agent`)
- [ ] List available tools in `strands-agents-tools` and verify exact function signatures
- [ ] Verify `BedrockModel` constructor parameters for Guardrails integration
- [ ] Verify `BedrockModel` `guardrail_latest_message` parameter exists and works as documented (Kiro R4 C-03)
- [ ] Confirm `shell` tool's built-in allowlist/blocklist capability and configuration API
- [ ] Verify `GraphBuilder` supports cyclic graphs with conditional edges (`add_edge(condition=callable)`) (Kiro R4 C-01)
- [ ] Test minimal reflexion loop: node A → node B → [condition] → node A with `max_node_executions` (Kiro R4 C-01)
- [ ] Verify `@tool` decorator works with subprocess-based tools (timeout handling, stderr capture) (Kiro R4 C-02)
- [ ] Test tool timeout handling with long-running subprocess (>60s) (Kiro R4 C-02)
- [ ] Document any API differences from assumptions in this spec
- [ ] Test minimal "hello world" agent with Bedrock in target AWS region

**Gate**: Phase 0 cannot begin until all items are verified and documented.

---

## 3. Architecture Overview

### 3.1 Layer diagram

```
┌─────────────────────────────────────────────────────┐
│                    Yui Runtime                      │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │          Strands Agent (core loop)            │  │
│  │  model: BedrockModel (Claude Sonnet/Opus)     │  │
│  │  tools: [local + cloud + mcp]                 │  │
│  └──────────┬──────────────────┬─────────────────┘  │
│             ↓                  ↓                    │
│  ┌──────────────────┐  ┌─────────────────────────┐  │
│  │  Local Tools      │  │  Cloud Tools (AWS)      │  │
│  │  • exec (shell)   │  │  • Bedrock Converse     │  │
│  │  • file r/w/edit  │  │  • AgentCore Browser    │  │
│  │  • kiro delegate  │  │  • AgentCore Memory     │  │
│  │  • git            │  │  • Bedrock Guardrails   │  │
│  │  • outlook (Mac)  │  │                         │  │
│  └──────────────────┘  └─────────────────────────┘  │
│             ↕                                       │
│  ┌───────────────────────────────────────────────┐  │
│  │  Channel Adapters                             │  │
│  │  • CLI (terminal REPL)                        │  │
│  │  • Slack (Socket Mode, no public URL needed)  │  │
│  └───────────────────────────────────────────────┘  │
│             ↕                                       │
│  ┌───────────────────────────────────────────────┐  │
│  │  Runtime Services                             │  │
│  │  • Session Manager (SQLite)                   │  │
│  │  • Config Loader (YAML + AGENTS.md/SOUL.md)   │  │
│  │  • Heartbeat Scheduler                        │  │
│  │  • Daemon (launchd plist)                     │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### 3.2 Key design decisions

| Decision | Rationale |
|---|---|
| **Strands Agent SDK as base** | AWS-official, Bedrock-native, MCP support, Apache 2.0. Provides the agent loop, tool registration, and model abstraction — avoids reimplementing OpenClaw's 1,165-line `run.ts` |
| **Strands built-in tools where possible** | `shell`, `file_read`, `file_write`, `editor`, `slack_client`, `use_aws` already exist in `strands-agents-tools`. Use them instead of writing custom implementations |
| **Custom tools only for Yui-specific needs** | Kiro CLI delegation, Outlook AppleScript, Heartbeat — things not covered by strands-agents-tools |
| **SQLite for sessions (not S3)** | Phase 0-3 is single-device. S3 sync is a future optimization |
| **Bedrock Guardrails via SDK parameter** | `BedrockModel(guardrail_id=..., guardrail_latest_message=True)` — zero custom code needed |
| **No Docker sandbox** | Command allowlist + blocklist on exec tool. Lighter than Docker for corporate laptop use case |

### 3.3 Data flow: user message → response

```
1. User types in CLI or sends Slack message
2. Channel adapter extracts text, routes to Agent
3. Agent builds system prompt: config.yaml base + AGENTS.md + SOUL.md content
4. Agent calls BedrockModel.converse() with conversation history + tools
5. If model returns tool_use → execute tool → feed result back → loop to step 4
6. If model returns end_turn → extract text → send to channel adapter → display to user
7. Session manager persists conversation history to SQLite
```

---

## 4. Tool Inventory & Local/Cloud Boundary Design

### 4.0 Boundary Design Principles (Kiro review round 2)

Every tool must be explicitly assigned to a tier based on these criteria:

| Criteria | → Local | → Cloud (AWS) |
|---|---|---|
| Needs local filesystem | ✅ Must be local | — |
| Needs local CLI (Kiro, git, osascript) | ✅ Must be local | — |
| Low latency required (<100ms) | ✅ Prefer local | — |
| Must work offline | ✅ Must be local | — |
| Handles sensitive local data (keys, config) | ✅ Must be local | — |
| Heavy compute / memory (browser, ML) | — | ✅ Prefer cloud |
| AWS VPC data governance requirement | — | ✅ Must be cloud |
| 24/7 availability needed | — | ✅ Prefer cloud |
| Sandboxed execution required | — | ✅ Prefer cloud |

### 4.1 Local Tools (run on user's Mac)

These tools MUST run locally because they access local filesystem, CLIs, or macOS APIs.

| Tool | Source | Purpose | Why local |
|---|---|---|---|
| `shell` | strands-agents-tools | Shell command execution with allowlist | Local CLI access |
| `file_read` | strands-agents-tools | Read file contents | Local filesystem |
| `file_write` | strands-agents-tools | Write/create files | Local filesystem |
| `editor` | strands-agents-tools | View, replace, insert, undo edits | Local filesystem |
| `kiro_delegate` | Custom | Delegate coding tasks to Kiro CLI | Local CLI + workspace access. **Kiro CLI is a required dependency** (han review item ④) |
| `git_tool` | Custom | Git operations (status, add, commit, push, log, diff) | Local repo access |
| `http_request` | strands-agents-tools | HTTP GET/POST to public URLs | Low latency, simple HTTP |
| `meeting_recorder` | Custom | Capture system audio + mic for meeting transcription | macOS audio APIs (ScreenCaptureKit / BlackHole), local audio processing |
| `whisper_transcribe` | Custom | Real-time speech-to-text using Whisper | Local ML inference on Apple Silicon (mlx-whisper / whisper.cpp) |

**Note**: `outlook_calendar` and `outlook_mail` are no longer custom local tools. They are provided via the `aws-outlook-mcp` corporate MCP server (see Section 4.4).

### 4.2 Cloud Tools (run on AWS)

These tools run in AWS because they require managed infrastructure, sandboxing, or VPC-internal data processing.

| Tool | Source | Purpose | Why cloud |
|---|---|---|---|
| Bedrock Converse | Strands SDK core | LLM inference | VPC data governance, IAM auth |
| AgentCore Browser | strands-agents-tools `AgentCoreBrowser` | Web browsing automation (managed Chrome) | Memory savings (~2GB), sandboxed, VPC-internal |
| AgentCore Memory | strands-agents-tools `agent_core_memory` | Long-term memory (facts, preferences) | Cross-device sync, managed persistence |
| AgentCore Code Interpreter | strands-agents-tools `code_interpreter` | Python code execution in sandbox | Sandboxed, safe arbitrary code execution |
| Bedrock Knowledge Base | strands-agents-tools `retrieve` | Semantic search over indexed documents | VPC-internal, replaces external search APIs |

### 4.3 Hybrid Tools (local initiation, cloud component)

| Tool | Local component | Cloud component | Rationale |
|---|---|---|---|
| `slack_client` | Socket Mode WebSocket from local machine | Slack API (external SaaS) | Must be local for Socket Mode; Slack API is external but authorized via bot tokens |

### 4.4 MCP Server Integration (han review — items ⑤⑥)

Yui uses Strands SDK's native MCP support (`MCPClient` / `mcp_client` tool) to extend capabilities via MCP servers. This replaces custom tool implementations for Outlook and media/diagram generation.

**Strands MCP integration patterns:**
- **Static (pre-configured)**: `MCPClient` from `strands.tools.mcp` — loaded at startup from config.yaml
- **Dynamic (runtime)**: `mcp_client` tool from `strands-agents-tools` — agent can connect to new MCP servers on demand

```yaml
# config.yaml — MCP server configuration
mcp:
  servers:
    # Corporate MCP servers (pre-configured, loaded at startup)
    outlook:
      transport: stdio
      command: "aws-outlook-mcp"    # Corporate Outlook MCP server
      args: []
      enabled: true
    # Additional MCP servers can be added here
  dynamic:
    enabled: true                   # Allow agent to connect to new MCP servers at runtime
    allowlist: []                   # Optional: restrict to specific server commands
```

**MCP replaces these previously custom/excluded tools:**

| Previously | Now via MCP | MCP Server |
|---|---|---|
| `outlook_calendar` (custom AppleScript) | MCP tool call | `aws-outlook-mcp` (corporate) |
| `outlook_mail` (custom AppleScript) | MCP tool call | `aws-outlook-mcp` (corporate) |
| `diagram` (excluded) | MCP tool call | Corporate/community MCP server |
| `nova_reels` / image / video (excluded) | MCP tool call (opt-in) | Corporate/community MCP server |

### 4.5 Explicitly NOT included as builtin (with rationale + alternative)

| Tool | Why not builtin | Alternative | Status |
|---|---|---|---|
| `tavily_search` / `tavily_extract` / `tavily_crawl` | Sends queries to external SaaS outside AWS VPC | **AgentCore Browser** (cloud-managed Chrome for web browsing + search) | Bedrock feature: AgentCore Browser (`bedrock-agentcore:CreateBrowser`, `StartBrowserSession`) |
| `exa_search` / `exa_get_contents` | Same VPC concern as Tavily | **AgentCore Browser** | Same as above |
| `python_repl` (local) | Arbitrary local code execution without sandbox | **AgentCore Code Interpreter** (sandboxed, multi-language) | Bedrock feature: AgentCore Code Interpreter (`bedrock-agentcore:CreateCodeInterpreter`) |
| `use_browser` (local Chromium) | ~2GB memory overhead | **AgentCore Browser** (default). Local Chromium available as opt-in fallback for auth-required internal sites | Config: `tools.browser.provider: local` |
| `use_computer` | High security risk (arbitrary desktop control) | **MCP servers** for specific desktop integrations as needed | Deferred — no current use case beyond what Outlook MCP + Kiro CLI cover |
| `outlook_calendar` / `outlook_mail` (custom) | AppleScript is Mac-specific, brittle | **`aws-outlook-mcp`** corporate MCP server | MCP: cross-platform, maintained by corporate team |
| `nova_reels` / image / video / audio | Not core to coding assistant use case | **MCP servers** (corporate/community) for on-demand media generation | MCP: extensible without code changes |
| `diagram` | Not core enough for builtin | **MCP server** (community) for diagram generation when needed | MCP: available on-demand |

### 4.6 AWS Bedrock features used (explicit enumeration — han review items ①②③)

Yui depends on the following specific AWS Bedrock/AgentCore features. These must be available in the target AWS region.

| Feature | AWS Service | API/Resource | Purpose in Yui | Phase |
|---|---|---|---|---|
| **LLM Inference** | Bedrock | `bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream` | Core agent loop — Converse API | Phase 0 |
| **Guardrails** | Bedrock | `bedrock:ApplyGuardrail` + Guardrail resource | Input/output safety filtering | Phase 3 |
| **AgentCore Browser** | Bedrock AgentCore | `bedrock-agentcore:CreateBrowser`, `StartBrowserSession`, `ConnectBrowserAutomationStream`, `ConnectBrowserLiveViewStream` | Cloud-managed Chrome for web browsing, search, content extraction. **Replaces Tavily/Exa** | Phase 2 |
| **AgentCore Memory** | Bedrock AgentCore | AgentCore Memory API (create memory, store, retrieve) | Long-term memory (facts, preferences) with cross-device sync | Phase 2 |
| **AgentCore Code Interpreter** | Bedrock AgentCore | `bedrock-agentcore:CreateCodeInterpreter` + session management | Sandboxed Python/JS/TS execution. **Replaces local python_repl** | Phase 2 |
| **Knowledge Base** | Bedrock | `bedrock:Retrieve`, `bedrock:RetrieveAndGenerate` | Semantic search over indexed corporate documents (RAG) | Phase 2 |

### 4.5 Browser provider selection (Kiro review round 2, C-1)

```yaml
tools:
  browser:
    provider: agentcore       # Default: AWS-managed Chrome
    # provider: local         # Fallback: local Chromium (requires pip install strands-agents-tools[local-chromium-browser])
    region: us-east-1         # AgentCore Browser region
```

| Provider | When to use | Pros | Cons |
|---|---|---|---|
| `agentcore` (default) | Normal operation | No local memory cost, sandboxed, VPC-internal | Requires AWS credentials, network latency |
| `local` (fallback) | Offline, AgentCore unavailable | Low latency, works offline | ~2GB memory, local Chromium install required |

### 4.6 Web search strategy (Kiro review round 2, C-2)

**Problem**: Tavily/Exa send search queries to external SaaS → breaks VPC data governance requirement.

**Solution — phased approach**:

| Phase | Web search method | VPC compliance |
|---|---|---|
| Phase 0–1 | `http_request` (direct HTTP GET to public URLs) | ✅ No external API keys, local execution |
| Phase 2 | `retrieve` (Bedrock Knowledge Base) for indexed corporate docs | ✅ VPC-internal semantic search |
| Phase 3+ | `tavily_search` as **opt-in** with config warning | ⚠️ Explicit user choice, logged |

```yaml
tools:
  web_search:
    provider: bedrock_kb      # Default: VPC-internal (requires Knowledge Base setup)
    # provider: tavily        # Opt-in: external SaaS (WARNING: data leaves AWS VPC)
    # provider: http_only     # Minimal: plain HTTP requests only
    knowledge_base_id: ""     # Required for bedrock_kb provider
```

### 4.7 Python execution strategy (Kiro review round 2, C-3)

**Problem**: `python_repl` executes arbitrary code locally without sandbox.

**Solution**:

| Provider | Security | Use case |
|---|---|---|
| `agentcore_code_interpreter` (default) | ✅ AWS-managed sandbox, isolated | Data analysis, calculations, any untrusted code |
| `python_repl` (opt-in) | ⚠️ Local execution, import allowlist | Quick local scripts, requires explicit config flag |

```yaml
tools:
  python:
    provider: agentcore_code_interpreter  # Default: sandboxed
    # provider: local_repl                # Opt-in: local (WARNING: arbitrary code execution)
    region: us-east-1
```

### 4.8 Memory architecture (Kiro review round 2, M-2)

**Two-tier memory with clear separation of concerns:**

| Data type | Storage | Reason |
|---|---|---|
| **Conversation history** (short-term) | SQLite (local) | Low latency, offline-capable, single device |
| **Session metadata** (thread IDs, timestamps) | SQLite (local) | Local management sufficient |
| **Long-term memory** (facts, preferences, learned info) | AgentCore Memory (cloud) | Cross-device sync, managed persistence, semantic retrieval |

SQLite handles ephemeral session data. AgentCore Memory handles durable knowledge that should survive device changes. They are complementary, not redundant.

### 4.9 Scheduler design (Kiro review round 2, M-3)

| Phase | Scheduler | Limitation |
|---|---|---|
| Phase 0–3 | Heartbeat only (fixed-interval, in-process `threading.Timer`) | Machine must be awake; no cron expressions |
| Phase 4+ | EventBridge (cloud) for reliable cron scheduling | Requires AWS setup; machine sleep irrelevant |

**Out of scope for Phase 0–3**: Flexible cron scheduling (EventBridge). Heartbeat is fixed-interval only.

### 4.10 Custom tool implementation details

| Tool | Purpose | Implementation notes |
|---|---|---|
| `kiro_delegate` | Delegate coding tasks to Kiro CLI | `subprocess.run(["kiro-cli", "chat", "--no-interactive", ...])`, ANSI strip, timeout 300s, **output truncated at 50,000 chars** (≈12,500 tokens — fits within Claude's context window with room for conversation history). **Kiro CLI must be installed** — Yui checks at startup and provides install instructions if missing |
| `git_tool` | Git operations (status, add, commit, push, log, diff, branch, checkout) | Wrapper around `subprocess.run(["git", ...])` with allowlisted subcommands |

### 4.10.1 Meeting Tools (Phase 2)

| Tool | Input | Output | Notes |
|---|---|---|---|
| `meeting_recorder` | `action: "start"\|"stop"\|"status"`, `include_mic: bool`, `output_dir: str` | `{status: str, meeting_id: str, duration_seconds: float, word_count: int}` | Starts/stops audio capture + Whisper pipeline. Only one recording active at a time (E-18). |
| `whisper_transcribe` | `audio_path: str`, `language: str\|"auto"`, `model: str` | `{text: str, segments: [{start: float, end: float, text: str}], language_detected: str}` | Offline transcription of saved audio file. Used for re-transcription (`yui meeting transcribe <id>`). |
| `meeting_analyzer` | `transcript: str`, `analysis_type: "realtime"\|"minutes"` | `{summary: str, action_items: [{action, owner, due_date}], decisions: [str], open_questions: [str]}` | Calls Bedrock Converse API with meeting-specific prompt template. |

### 4.11 Tool security model

- **Shell execution**: strands-agents-tools `shell` tool has built-in user confirmation. Yui config adds an allowlist with subcommand granularity (e.g., `"git status"`, `"git log"`, `"git diff"` — not bare `"git"`) and a blocklist (e.g., `["rm -rf /", "sudo", "curl | bash", "git push --force", "git reset --hard", "git clean -f"]`). Remove bare `git` from shell allowlist; use dedicated `git_tool` for safe git operations.
- **File operations**: Restricted to configurable workspace directory by default
- **Outlook**: Provided via `aws-outlook-mcp` corporate MCP server. No local AppleScript — cross-platform, maintained by corporate team.
- **MCP servers**: Static servers loaded from config.yaml at startup. Dynamic server connections require `mcp.dynamic.enabled: true`. Optional allowlist restricts which servers can be connected at runtime.
- **Python execution**: AgentCore Code Interpreter by default (sandboxed). Local `python_repl` requires explicit opt-in + import allowlist.
- **Web search**: Bedrock Knowledge Base by default (VPC-internal). Tavily requires explicit opt-in with logged warning.
- **Browser**: AgentCore Browser by default (managed Chrome). Local Chromium requires explicit opt-in.

---

## 5. Channel Adapters

### 5.1 CLI Adapter (Phase 0)

- Terminal REPL with `readline` history support
- Rich-formatted output (code blocks, tables) via `rich` library
- Ctrl+C graceful exit, Ctrl+D for EOF
- System prompt displayed on startup

### 5.2 Slack Adapter (Phase 1)

- **Library**: `slack-bolt` with Socket Mode (no public URL/ngrok needed)
- **Tokens**: Bot Token (`xoxb-`) + App-Level Token (`xapp-`)
- **Events**: `app_mention`, `message.channels`, `message.im`
- **Threading**: Replies in thread when original message is threaded
- **Reactions**: 👀 on receipt, ✅ on completion. Batch status updates — do NOT react after every tool call (Kiro review M-03)
- **Rate limiting**: `slack-bolt` has built-in rate limit handling with automatic retry+backoff. If rate limited for >30s, send single message: "Response ready but Slack rate limited. Will retry shortly."

### 5.2.1 Slack App/Bot Setup Guide (Phase 1 prerequisite)

Yui communicates via Slack using **Socket Mode** — a WebSocket-based connection that requires no public URL, no ngrok, no firewall changes. This makes it ideal for local/corporate environments behind firewalls.

#### Step-by-step: Creating the Slack App

**Step 1: Create the Slack App**
1. Go to https://api.slack.com/apps → "Create New App"
2. Select "From an app manifest" (recommended — reproducible setup)
3. Select your workspace
4. Paste the manifest below → Create App

**Step 2: App Manifest (YAML)**

The following manifest configures 結(Yui) as a Socket Mode bot with all required scopes:

```yaml
_metadata:
  major_version: 1
display_information:
  name: "結 (Yui)"
  description: "AI secretary agent — lightweight, AWS-optimized"
  background_color: "#4A154B"
features:
  app_home:
    home_tab_enabled: false
    messages_tab_enabled: true
    messages_tab_read_only_enabled: false
  bot_user:
    display_name: "Yui"
    always_online: true
oauth_config:
  scopes:
    bot:
      # Core messaging
      - app_mentions:read        # Respond to @Yui mentions
      - chat:write               # Send messages
      - chat:write.customize     # Send with custom username/icon
      # Channel awareness
      - channels:history         # Read public channel messages
      - channels:read            # List channels
      - groups:history           # Read private channel messages
      - groups:read              # List private channels
      - im:history               # Read DM messages
      - im:read                  # List DMs
      - im:write                 # Open DMs
      - mpim:history             # Read group DM messages
      - mpim:read                # List group DMs
      # Reactions & threads
      - reactions:read           # Read reactions
      - reactions:write          # Add 👀/✅ reactions
      # File sharing (meeting minutes)
      - files:write              # Upload meeting minutes
      - files:read               # Read shared files
      # User info
      - users:read               # Resolve user names
settings:
  event_subscriptions:
    bot_events:
      - app_mention              # @Yui triggers
      - message.channels         # Public channel messages
      - message.groups           # Private channel messages
      - message.im               # Direct messages
      - message.mpim             # Group DMs
  org_deploy_enabled: false
  socket_mode_enabled: true      # ← Key setting: Socket Mode
  is_hosted: false
  token_rotation_enabled: false
```

**Step 3: Enable Socket Mode**
1. In app settings → "Socket Mode" (left sidebar) → Toggle ON
2. This confirms WebSocket connection instead of HTTP endpoint

**Step 4: Generate Tokens**

| Token | Where | Scope | Config Key |
|---|---|---|---|
| **Bot Token** (`xoxb-`) | OAuth & Permissions → Install to Workspace → Copy | (from manifest scopes) | `SLACK_BOT_TOKEN` |
| **App-Level Token** (`xapp-`) | Basic Information → App-Level Tokens → Generate | `connections:write` | `SLACK_APP_TOKEN` |

**Step 5: Install to Workspace**
1. OAuth & Permissions → "Install to Workspace"
2. Review permissions → "Allow"
3. Copy the Bot User OAuth Token (`xoxb-...`)

**Step 6: Configure Yui**

```yaml
# ~/.yui/config.yaml
slack:
  enabled: true
  bot_token: "${SLACK_BOT_TOKEN}"      # xoxb-...
  app_token: "${SLACK_APP_TOKEN}"      # xapp-...
  default_channel: "#yui-general"       # Optional: default channel for notifications
```

```bash
# ~/.yui/.env
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_APP_TOKEN=xapp-your-app-level-token-here
```

**Step 7: Invite Yui to Channels**
```
/invite @Yui
```
Yui only receives messages from channels it's been invited to (except DMs).

#### Architecture: Why Socket Mode?

```
┌─────────────────────────┐
│  Mac (behind firewall)  │
│                         │
│  ┌───────────────────┐  │       WebSocket (outbound only)
│  │  Yui Agent        │──│──────────────────────────────→ Slack API
│  │  (slack-bolt)     │  │  ← No inbound ports needed
│  │                   │  │  ← No public URL
│  │  Socket Mode      │  │  ← No ngrok/tunnel
│  └───────────────────┘  │
└─────────────────────────┘
```

| Feature | Socket Mode | HTTP (Events API) |
|---|---|---|
| Public URL needed | ❌ No | ✅ Yes |
| Firewall changes | ❌ None | ✅ Inbound port |
| SSL certificate | ❌ Not needed | ✅ Required |
| Latency | ~50ms (WebSocket) | ~100-200ms (HTTP) |
| Marketplace distribution | ❌ Not eligible | ✅ Eligible |
| Corporate firewall compatible | ✅ Perfect fit | ⚠️ Needs config |

**Trade-off**: Socket Mode apps cannot be published to the Slack Marketplace. This is acceptable for Yui — it's a personal/team agent, not a public product.

#### Slack App Capabilities

| Capability | How Yui Uses It |
|---|---|
| **@mention response** | `@Yui what's my schedule?` → Agent processes and replies in thread |
| **DM conversation** | Direct messages for private interactions |
| **Channel monitoring** | Listen to specific channels, respond when relevant |
| **Reactions** | 👀 on receipt, 🔥 on processing, ✅ on completion |
| **File upload** | Share meeting minutes, reports as Slack files |
| **Thread replies** | Keep conversations organized in threads |
| **Notifications** | Post meeting summaries, heartbeat alerts to channels |

#### Acceptance Criteria (Slack Setup)

- [ ] AC-62: `yui setup slack` CLI command validates tokens, tests connection, AND verifies all required OAuth scopes are granted (compares installed scopes against manifest)
- [ ] AC-63: App manifest YAML is shipped in repo as `slack-manifest.yaml` for one-click setup
- [ ] AC-64: Missing/invalid tokens at startup → clear error message with setup instructions
- [ ] AC-65: Yui responds to @mention within 3 seconds (👀 reaction) in any invited channel
- [ ] AC-66: DM messages processed without @mention prefix

#### Acceptance Criteria (Autonomy — Section 8)

- [ ] AC-67: `kiro_review` tool delegates file review to Kiro CLI and returns structured Critical/Major/Minor findings
- [ ] AC-68: `kiro_implement` tool delegates implementation to Kiro CLI with spec file as input
- [ ] AC-69: Yui ⇔ Kiro Reflexion Graph executes coding workflow: draft → review → [revise loop] → complete
- [ ] AC-70: Yui ⇔ Kiro Reflexion Graph executes requirements review workflow: Yui drafts → Kiro reviews → [revise loop] → approved
- [ ] AC-71: GraphBuilder `max_node_executions` prevents infinite review loops (max 4 cycles = 8 node executions)
- [ ] AC-72: GraphBuilder `execution_timeout` kills stalled review loops after 10 minutes
- [ ] AC-73: Task-level self-evaluation recorded to `memory/evaluations/` after each task completion
- [ ] AC-74: Weekly cron job analyzes evaluation patterns and proposes AGENTS.md improvements as a PR
- [ ] AC-75: AGENTS.md modifications are NEVER applied directly — always via PR requiring han review
- [ ] AC-76: Autonomy level (L0–L4) configurable in `config.yaml` with per-task override
- [ ] AC-77: Cost budget guard: `max_monthly_bedrock_usd` enforced; warning at 80%, hard stop at 100%
- [ ] AC-78: Kiro CLI availability check at startup — clear error message if not installed
- [ ] AC-79: Cross-review findings logged to `memory/reviews/` for retrospective analysis
- [ ] AC-80: Heartbeat OODA loop: Observe (env check) → Orient (analyze) → Decide (plan) → Act (execute) cycle completes within 60 seconds
- [ ] AC-81: `yui meeting start` performs 5-second audio quality test before recording — warns user if RMS amplitude below threshold or clipping detected
- [ ] AC-82: Conflict resolution protocol: Yui can CHALLENGE Kiro findings; unresolved Criticals escalate to han
- [ ] AC-83: Self-improvement rollback: auto-revert AGENTS.md PR if metrics degrade >20% within 24h shadow period
- [ ] AC-84: Failure recovery: partial work saved to `memory/incomplete/` when Reflexion loop hits execution limit

---

## 6. Session Management (Phase 1)

### 6.1 Storage

- **Backend**: SQLite database at `~/.yui/sessions.db`
- **WAL mode**: `PRAGMA journal_mode=WAL` for concurrent reads + single writer (Kiro review C-03)
- **Connection timeout**: `sqlite3.connect(timeout=5.0)` to handle lock contention
- **Single instance**: Only ONE Yui process per user. On startup, check PID file at `~/.yui/yui.pid`. If PID file exists and process is alive, exit with: "Another Yui instance is running (PID: X). Stop it first or use that instance."
- **Schema**: `sessions(id TEXT PK, channel TEXT, user TEXT, messages JSON, created_at INT, updated_at INT, token_count INT)`
- **Scope**: per-sender (one session per Slack user or CLI instance)

### 6.2 Compaction

- **Trigger**: When `token_count` exceeds configurable threshold (default: 80% of model context window)
- **Method**: Summarize conversation via LLM call, replace history with summary + recent N messages
- **Preservation**: Always keep system prompt + last 5 messages in full

---

## 7. Configuration (Phase 0)

### 7.1 File structure

```
~/.yui/
├── config.yaml          # Main configuration
├── sessions.db          # SQLite session store (auto-created)
├── workspace/
│   ├── AGENTS.md        # System prompt (what the agent does) — includes Kiro cross-review workflow
│   └── SOUL.md          # Persona definition (how the agent behaves)
└── .env                 # Secrets (SLACK_BOT_TOKEN, etc.)
```

### 7.1.1 Kiro CLI as required dependency (han review item ④)

Kiro CLI is a **required setup dependency**, not optional. Yui delegates all coding tasks to Kiro CLI, following the same pattern as AYA's ecosystem:

**Setup requirement:**
- `kiro-cli` must be installed and authenticated before Yui can start
- Yui checks for Kiro CLI at startup: if missing, displays install instructions and exits
- Kiro CLI path is configurable via `tools.kiro.binary_path`

**AGENTS.md cross-review workflow (built-in):**

The default `~/.yui/workspace/AGENTS.md` shipped with Yui includes a mandatory Kiro⇔Yui cross-review process, modeled on AYA's ecosystem:

```markdown
# Default AGENTS.md excerpt — Kiro Cross-Review Workflow

## Coding Workflow (mandatory)
1. Yui writes requirements.md (What/Why)
2. Kiro CLI generates design.md + tasks.md (How)
3. Kiro CLI implements code
4. Yui reviews Kiro's output against requirements (AC matching)
5. Kiro CLI reviews Yui's requirements for ambiguities
6. Iterate until both pass
7. Only then: PR creation

## Rules
- Yui MUST NOT write code directly — all code via Kiro CLI
- Requirements changes require re-review cycle
- Every PR must have been reviewed by both Yui and Kiro
```

### 7.2 config.yaml schema

```yaml
# Model configuration
model:
  provider: bedrock             # Only bedrock supported initially
  model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
  region: us-east-1
  guardrail_id: ""              # Optional Bedrock Guardrail ID
  guardrail_version: DRAFT
  guardrail_latest_message: false   # Default: full history for security. Set true for cost savings (see Section 8)
  max_tokens: 4096

# Tool configuration
tools:
  shell:
    allowlist:
      - "ls"
      - "cat"
      - "grep"
      - "find"
      - "python3"
      - "kiro-cli"
      - "brew"
      # Note: bare "git" is NOT in allowlist — use git_tool for safe git ops
    blocklist:
      - "rm -rf /"
      - "sudo"
      - "curl | bash"
      - "eval"
      - "git push --force"
      - "git reset --hard"
      - "git clean -f"
    timeout_seconds: 30
  file:
    workspace_root: "~/workspace"   # Restrict file ops to this directory
  kiro:
    binary_path: "~/.local/bin/kiro-cli"
    timeout_seconds: 300

# MCP server configuration (han review items ⑤⑥)
mcp:
  servers:
    outlook:
      transport: stdio
      command: "aws-outlook-mcp"
      args: []
      enabled: true
  dynamic:
    enabled: true
    allowlist: []                   # Empty = allow all. To restrict: ['aws-*', 'corporate-*']
  browser:
    provider: agentcore             # "agentcore" (default, cloud) or "local" (fallback)
    region: us-east-1
  web_search:
    provider: bedrock_kb            # "bedrock_kb" (default, VPC-internal) or "tavily" (opt-in, external)
    knowledge_base_id: ""           # Required for bedrock_kb
    # WARNING: tavily sends queries to external SaaS outside AWS VPC
  python:
    provider: agentcore_code_interpreter  # "agentcore_code_interpreter" (default, sandboxed) or "local_repl" (opt-in)
    region: us-east-1
  memory:
    provider: agentcore             # "agentcore" (default, cloud) or "local_only" (SQLite only)
    region: us-east-1

# Channel configuration  
channels:
  cli:
    enabled: true
  slack:
    enabled: false                  # Requires tokens in .env
    bot_token_env: SLACK_BOT_TOKEN
    app_token_env: SLACK_APP_TOKEN
    default_channel: ""

# Runtime configuration
runtime:
  session:
    compaction_threshold: 0.8       # Compact at 80% of context window
    keep_recent_messages: 5
  heartbeat:
    enabled: false
    interval_minutes: 15
    active_hours: "07:00-24:00"
    timezone: "Asia/Tokyo"          # IANA timezone (DST handled via stdlib zoneinfo)
  daemon:
    enabled: false
    launchd_label: "com.yui.agent"
```

---

## 8. Autonomy Architecture (Phase 2–3)

### 8.1 Problem: Single-Agent Ceiling

A single LLM agent (even Claude on Bedrock) has inherent limitations:

| Limitation | Description |
|---|---|
| **Self-bias** | Agent evaluating its own output tends to be lenient |
| **Knowledge closure** | Bounded by training data + tool outputs |
| **Quality ceiling** | Same model writing and reviewing → quality plateaus |
| **Blind spot fixation** | Same LLM has the same systematic blind spots |

**Conclusion**: A single agent cannot exceed its own capability boundary. Cross-LLM review (Yui's Claude ⇔ Kiro's independent LLM) breaks through this ceiling by introducing diverse reasoning perspectives and mutual error detection.

### 8.2 Autonomy Levels

| Level | Name | Description | Human Involvement |
|---|---|---|---|
| L0 | Manual | Han directs all actions. Yui executes only. | 100% |
| L1 | Assisted | Yui proposes, han approves, Yui executes. | ~70% |
| L2 | Supervised | Yui executes autonomously, reports results. Han intervenes on anomalies only. | ~30% |
| L3 | Autonomous | Yui + Kiro mutual review loop. AGENTS.md changes via PR (han review). | ~10% |
| L4 | Self-Evolving | L3 + periodic self-evaluation → automatic rule improvement proposals. Han weekly review only. | ~5% |

**Progression**: Phase 0–1: L1–L2 → Phase 2+: L2–L3 → Stable operation: L3–L4

### 8.3 Layer 1: Single-Agent Autonomy (Strands Agent Loop)

The Strands SDK `Agent` class handles the core autonomous loop:

```
Agent Loop (ReAct pattern):
  1. Receive task
  2. Reason about approach
  3. Select and call tools
  4. Observe results
  5. Reflect and decide: done? or iterate?
  6. Respond (or loop back to step 2)
```

**Built-in capabilities**:
- Tool selection and invocation (Strands toolbelt)
- Error recovery within agent loop (retry with reformulated approach)
- Streaming output for real-time feedback
- Session/conversation management

**Limitations addressed by Layer 2**: Self-review bias, quality ceiling, systematic blind spots.

### 8.4 Layer 2: Yui ⇔ Kiro Cross-Review (Reflexion Loop)

**Core principle**: Yui (Claude via Bedrock) handles *What/Why* (requirements, review, quality). Kiro CLI (independent LLM) handles *How* (design, implementation, code review). Each reviews the other's output.

#### 8.4.1 Architecture

```
┌─ Yui Agent (Claude via Bedrock) ─────────────────────┐
│ Roles:                                                │
│   • Requirements authoring (What/Why)                 │
│   • Acceptance criteria review                        │
│   • Quality gate enforcement                          │
│   • Self-evaluation and memory management             │
│ Strengths: Context retention, dialogue, judgment       │
└──────────────────┬────────────────────────────────────┘
                   │ ← Strands GraphBuilder Reflexion Loop →
┌─ Kiro CLI (Independent LLM) ─────────────────────────┐
│ Roles:                                                │
│   • Design document authoring (How)                   │
│   • Code implementation                               │
│   • Requirements review (technical feasibility)       │
│   • Code review                                       │
│ Strengths: Coding specialization, project structure   │
└───────────────────────────────────────────────────────┘
```

#### 8.4.2 Cross-Review Workflows

**Workflow A: Coding Task (fullspec)**
```
Yui: requirements.md → Kiro: design.md + tasks.md + implement
  → Yui: AC review (acceptance criteria check)
  → [needs_revision?] → Kiro: fix → Yui: re-review
  → [approved?] → PR → merge
```

**Workflow B: Requirements Review (NEW — han directive)**
```
Yui: draft requirements.md → Kiro: review (technical feasibility,
  missing edge cases, API assumptions, dependency risks)
  → Yui: address Kiro findings → Kiro: re-review
  → [approved?] → han final review → approved
```

**Workflow C: Design Review**
```
Kiro: design.md → Yui: review (alignment with requirements,
  security implications, cost analysis)
  → Kiro: revise → Yui: re-review → approved
```

#### 8.4.3 Implementation with Strands GraphBuilder

```python
from strands import Agent
from strands.multiagent import GraphBuilder

# Condition functions (implementation sketch):
# def has_critical_or_major(state): return any severity in ["critical","major"] in state results
# def is_approved(state): return not has_critical_or_major(state)

# Yui ⇔ Kiro Reflexion Graph
builder = GraphBuilder()

# Nodes
builder.add_node(yui_spec_agent, "yui_draft")      # Yui drafts spec
builder.add_node(kiro_review_node, "kiro_review")   # Kiro reviews spec
builder.add_node(yui_revise_agent, "yui_revise")    # Yui addresses findings
builder.add_node(kiro_recheck_node, "kiro_recheck") # Kiro re-reviews
builder.add_node(complete_node, "complete")         # Done

# Edges
builder.add_edge("yui_draft", "kiro_review")
builder.add_edge("kiro_review", "yui_revise",
    condition=has_critical_or_major)     # Issues found → revise
builder.add_edge("kiro_review", "complete",
    condition=is_approved)               # No issues → done
builder.add_edge("yui_revise", "kiro_recheck")
builder.add_edge("kiro_recheck", "yui_revise",
    condition=has_critical_or_major)     # Still issues → iterate
builder.add_edge("kiro_recheck", "complete",
    condition=is_approved)               # Clean → done

# Safety
builder.set_max_node_executions(8)       # Max 4 review cycles
builder.set_execution_timeout(600)       # 10 minute timeout
```

#### 8.4.4 Kiro CLI Integration as Strands Tool

```python
@tool
def kiro_review(file_path: str, review_focus: str) -> str:
    """Delegate review to Kiro CLI (independent LLM).

    Args:
        file_path: Path to file to review
        review_focus: What aspects to focus on (e.g. "technical feasibility",
                      "missing edge cases", "API assumptions")
    Returns:
        Structured review with Critical/Major/Minor findings
    """
    result = subprocess.run(
        ["kiro-cli", "chat", "--no-interactive", "--trust-all-tools",
         f"Review {file_path} focusing on: {review_focus}. "
         "Classify findings as Critical/Major/Minor."],
        capture_output=True, timeout=120
    )
    return result.stdout

@tool
def kiro_implement(spec_path: str, task_description: str) -> str:
    """Delegate implementation to Kiro CLI."""
    ...
```

### 8.5 Layer 3: Self-Evaluation & Self-Improvement

#### 8.5.1 Task-Level Self-Evaluation

After each task completion, Yui records:
```yaml
# memory/evaluations/YYYY-MM-DD_task_id.yaml
task_id: "yui-42"
timestamp: "2026-03-01T10:30:00+09:00"
outcome: "success"  # success | partial | failure
metrics:
  kiro_review_rounds: 2
  critical_findings: 1
  time_to_complete_minutes: 45
lessons:
  - "API endpoint assumptions need verification before spec finalization"
  - "Missing error handling for network timeout in initial draft"
improvements:
  - target: "AGENTS.md"
    suggestion: "Add 'verify API availability' to spec checklist"
```

**Schema validation** (Kiro R4 m-08): Evaluation files validated against JSON Schema (`schema/evaluation.schema.json`) before writing. Invalid evaluations logged to `memory/invalid/` for debugging, never silently dropped.

#### 8.5.2 Periodic Self-Improvement (Cron-driven)

| Frequency | Action | Output |
|---|---|---|
| Daily | Review today's task evaluations → extract patterns | `memory/YYYY-MM-DD.md` |
| Weekly | Analyze week's success/failure patterns → propose AGENTS.md improvements | PR to AGENTS.md |
| Monthly | Full retrospective → tool usage audit → dependency check | Report to han |

**Critical safety constraint**: All AGENTS.md modifications are proposed as PRs. Han must review and approve before merge. Yui never directly modifies its own behavioral rules.

#### 8.5.3 OODA Loop Integration

```
Observe  → Heartbeat: check environment state, unread messages, stalled tasks
Orient   → Analyze: compare current state with goals and past patterns
Decide   → Plan: select next action based on priority and autonomy level
Act      → Execute: run task via agent loop with Kiro cross-review
  ↓
Record   → Log outcome to memory/
Reflect  → Self-evaluate against acceptance criteria
Improve  → Propose rule changes if recurring failures detected
  ↓
[Loop back to Observe]
```

### 8.6 Guardrails & Safety (Autonomy Constraints)

| Constraint | Mechanism | Phase |
|---|---|---|
| **AGENTS.md changes** | PR only — han review required | Phase 2+ |
| **Destructive operations** | Maintenance window only (han-defined hours) | Phase 3 |
| **Cost budget** | `max_monthly_bedrock_usd` in config.yaml. Yui estimates cost locally by tracking token counts (input + output) per API call and applying Bedrock pricing. Resets monthly. Warning at 80%, hard stop at 100%. Override: `yui budget reset`. | Phase 0 |
| **Loop limits** | `max_node_executions`, `execution_timeout` in GraphBuilder | Phase 2 |
| **Content safety** | Bedrock Guardrails (Section 9) | Phase 3 |
| **Secret hygiene** | Never output API keys/tokens to chat or logs | Phase 0 |
| **External data send** | Requires han approval for new external endpoints | Phase 0 |

### 8.7 Why Yui + Kiro > Single Agent (Evidence)

Based on AYA ecosystem empirical data (2026-02):
- AYA(requirements) × Kiro(implementation) × IRIS(review) improved code quality from ~60% first-pass to ~95%
- Cross-LLM review caught issues that self-review missed in 100% of cases tested
- Reflexion loop (max 3 iterations) resolved all Critical findings before merge

**Applied to Yui**:
- Same pattern, but implemented programmatically via Strands GraphBuilder
- Kiro reviews Yui's requirements (not just code) — per han directive
- Cyclic graph with conditional edges enables automated revision loops
- `max_node_executions` prevents infinite loops while allowing sufficient iteration

### 8.8 Failure Modes & Recovery (Kiro R4 C-04)

| Failure | Detection | Recovery |
|---|---|---|
| **Kiro CLI crash mid-review** | Subprocess exit code ≠ 0 or timeout | Save partial review output to `memory/incomplete/<task_id>/`, notify user, mark task as `needs_manual_review` |
| **Reflexion loop hits max_node_executions** | GraphBuilder raises limit error | Save all intermediate outputs (each node's result) to `memory/incomplete/<task_id>/`, notify user with summary of findings so far |
| **Yui-Kiro deadlock** (both keep rejecting each other) | 3 consecutive cycles with same findings repeated (no delta between review rounds) | Escalate to han with both agents' perspectives attached, pause task pending human decision |
| **Bedrock API failure during eval recording** | boto3 ClientError | Log evaluation to local file only (`memory/evaluations/`), retry cloud upload on next heartbeat |
| **Kiro CLI not found at runtime** | `FileNotFoundError` on subprocess | E-20: Clear error message with install instructions, mark task as blocked |
| **Token budget exceeded mid-task** | Running token count > budget | Complete current agent loop iteration, save state, refuse new tool calls, notify user |

### 8.9 Level Transition Criteria (Kiro R4 M-01)

| From → To | Trigger Criteria | Who Decides |
|---|---|---|
| L0 → L1 | Initial setup complete, first successful task | Automatic |
| L1 → L2 | 20+ successful tasks with <10% han intervention rate | Han approval |
| L2 → L3 | 50+ tasks, Kiro cross-review catches 90%+ of issues before han review, 0 security incidents | Han approval |
| L3 → L4 | 100+ tasks, self-evaluation accuracy >85% (compared to han's post-review assessment), weekly retrospective quality validated | Han approval |
| Any → L0 | Security incident, repeated failures (3+ in 24h), han explicit request | Automatic or han |

**Note**: Level transitions are one-way upgrades (except emergency downgrade). Stored in `config.yaml` as `autonomy.level`.

### 8.10 Conflict Resolution Protocol (Kiro R4 M-04)

When Yui and Kiro disagree during cross-review:

1. **Challenge mechanism**: If Yui disagrees with Kiro's Critical/Major finding, Yui responds with `CHALLENGE: <reasoning>` in the graph state
2. **Re-evaluation**: Kiro must re-evaluate the challenged finding with additional context provided by Yui
3. **Escalation**: If finding remains Critical after re-evaluation, escalate to han for tie-breaking
4. **Minor dismissal**: Minor findings can be dismissed by Yui with logged justification (stored in `memory/reviews/` for retrospective analysis)
5. **Logging**: All challenges and resolutions logged for pattern analysis

### 8.11 Self-Improvement Validation & Rollback (Kiro R4 M-06)

After an AGENTS.md improvement PR is merged:

1. **Shadow mode** (24 hours): New rules applied, but outcomes compared against simulated old-rules behavior
2. **Metrics tracked**: Kiro review cycle count, han intervention rate, task completion time
3. **Auto-revert trigger**: If new rules cause >20% increase in review cycles OR >15% increase in han interventions compared to pre-merge baseline → auto-revert PR, log to `memory/rollbacks/`
4. **Manual revert**: Han can always `yui rules revert <pr_number>` to undo a specific change
5. **Cool-down**: After a rollback, no new AGENTS.md proposals for 7 days (to prevent thrashing)

---

## 9. Bedrock Guardrails (Phase 3)

- Integrated via `BedrockModel(guardrail_id=..., guardrail_version=..., guardrail_latest_message=...)`
- **Security trade-off** (Kiro review C-02):
  - `guardrail_latest_message=False` (default): Full conversation history sent to Guardrails — secure against multi-turn attacks but higher token cost
  - `guardrail_latest_message=True`: Only latest message evaluated — faster/cheaper but vulnerable to multi-turn jailbreak
  - **Yui default: `false`** (full history). Users can opt into `true` in config.yaml with explicit warning
  - **Compensating control**: When `guardrail_latest_message=true`, Yui performs a full-history guardrail check every 10 turns as a safety net
- No custom guardrail implementation needed — Strands SDK handles it
- Guardrail violations surface as error messages to the user

---

## 10. Heartbeat (Phase 3)

### 10.1 Behavior

- Reads `~/.yui/workspace/HEARTBEAT.md` (if exists) at configurable interval
- **File integrity** (Kiro review M-04, strengthened R4 M-05): On first load, compute SHA256 hash. On subsequent loads, verify hash. If changed externally (not by agent):
  1. **Stop** heartbeat execution immediately — do NOT process modified content
  2. **Notify** han via Slack (if configured) or log critical alert to `memory/security/`
  3. **Require** explicit user action: `yui heartbeat reset` to re-baseline hash and resume
  4. **Never** auto-accept a modified HEARTBEAT.md — treat as potential prompt injection
  - HEARTBEAT.md must be owned by current user with 600 permissions; reject if world-writable.
- **Content handling**: Heartbeat content is treated as **user input** (not system prompt) — goes through Bedrock Guardrails if enabled
- Sends content to agent as a system event
- Agent responds autonomously (e.g., check Slack for unread messages, run scheduled tasks)
- Active hours restriction prevents execution during sleep hours

### 10.2 Implementation

- Python `threading.Timer` or `schedule` library
- Runs in-process (not a separate process)
- Heartbeat results logged but not sent to any channel unless agent decides to
- **Fixed-interval only** — cron expressions (e.g., "every Monday at 9am") are NOT supported in Phase 0–3. Flexible scheduling via EventBridge is deferred to Phase 4+.

---

## 10.5 Meeting Transcription & Automatic Minutes (Phase 2)

### 10.5.1 Overview

Yui provides automatic meeting transcription, intelligent minute generation, and real-time meeting analysis using a **hybrid local/cloud architecture**: audio capture and speech-to-text run locally (privacy + low latency), while LLM-powered analysis runs via Bedrock (intelligence + quality).

### 10.5.2 Architecture: Local/Cloud Split

```
┌─ LOCAL (Mac) ─────────────────────────────────┐
│                                                │
│  [System Audio]──┐                             │
│                  ├─→ Audio Mixer → Whisper ──→ Transcript chunks
│  [Mic Audio]─────┘   (16kHz mono)  (local)     │
│                                                │
│  Whisper engine: mlx-whisper (Apple Silicon)    │
│  or whisper.cpp (CoreML/ANE acceleration)       │
│                                                │
└──────────────┬─────────────────────────────────┘
               │ transcript text (every ~5-10s)
               ▼
┌─ CLOUD (AWS Bedrock) ─────────────────────────┐
│                                                │
│  [Bedrock Converse API]                        │
│    ├─ Real-time analysis (sliding window)      │
│    ├─ Post-meeting summary & minutes           │
│    └─ Action item extraction                   │
│                                                │
└────────────────────────────────────────────────┘
```

**Why Whisper local (not Amazon Transcribe)?**

| Factor | Whisper Local (mlx-whisper) | Amazon Transcribe Streaming |
|---|---|---|
| **Privacy** | Audio never leaves device | Audio sent to AWS |
| **Cost** | Free (local compute) | $0.024/min (~$1.44/hr meeting) |
| **Latency** | ~0.5s on Apple Silicon | ~1-2s (network round-trip) |
| **Offline** | Works without internet | Requires internet |
| **Accuracy (WER)** | ~8-12% (large-v3-turbo, varies by domain/noise) | ~5-8% (English), ~10-15% (Japanese) |
| **Speaker diarization** | Requires pyannote (optional) | Built-in |
| **Japanese** | Excellent (trained on multilingual data) | Good |

**Decision: Whisper local is default.** Primary advantages: privacy (audio never leaves device), zero cost, and offline capability. Amazon Transcribe may have better accuracy in some enterprise scenarios but comes with per-minute cost and requires network. Available as opt-in fallback via `meeting.transcribe.provider: aws_transcribe`.

### 10.5.3 Audio Capture (macOS)

**Primary method: ScreenCaptureKit** (macOS 13+)
- Captures system audio directly via `SCStreamConfiguration.capturesAudio = true` (Apple WWDC22, confirmed API)
- No virtual audio driver needed
- Requires Screen Recording permission in System Preferences
- Can capture specific app audio (e.g., Zoom/Teams only) via `SCContentFilter`
- ⚠️ **Known issue**: PyObjC bridge on macOS 15 has reported stability issues with ScreenCaptureKit audio (GitHub pyobjc#647). Monitor and test.
- Implementation: Swift helper binary or PyObjC bridge

**Fallback: BlackHole virtual audio driver** (recommended if ScreenCaptureKit is unstable)
- For macOS <13, or if ScreenCaptureKit audio is unreliable
- Requires `brew install blackhole-2ch` + Audio MIDI Setup configuration
- Creates loopback device combining system audio + mic
- More mature, widely documented approach

**Audio mixing (mic + system audio):**
- `sounddevice` with multiple input streams combined via `numpy.add()`
- Resampling to 16kHz mono via `scipy.signal.resample` or `librosa`

**Audio pipeline:**
```
System Audio (meeting app) ─┐
                            ├─→ Audio Mixer → Resampler (16kHz mono) → Whisper
Microphone (user's voice) ──┘
```

**Config:**
```yaml
meeting:
  audio:
    capture_method: screencapturekit  # or "blackhole"
    include_mic: true                 # Mix microphone input
    sample_rate: 16000                # Whisper expects 16kHz
    channels: 1                       # Mono
  whisper:
    engine: mlx                       # "mlx" (default on Apple Silicon) or "cpp" (whisper.cpp)
    model: large-v3-turbo             # Best accuracy/speed balance
    language: auto                    # Auto-detect, or "ja", "en"
    chunk_seconds: 5                  # Transcribe every 5 seconds
    vad_enabled: true                 # Voice Activity Detection — skip silence
  analysis:
    provider: bedrock                 # Bedrock Converse for LLM analysis
    realtime_enabled: false            # ⚠️ Default OFF — enables real-time analysis during meeting (costs ~$0.90/hr)
    realtime_interval_seconds: 60     # Analyze every 60 seconds (when enabled)
    realtime_window_minutes: 5        # Sliding window: last N minutes of transcript sent to LLM
    max_cost_per_meeting_usd: 2.0     # Budget guard: stop real-time analysis if projected cost exceeds limit
    minutes_auto_generate: true       # Auto-generate minutes when meeting ends
  output:
    transcript_dir: ~/.yui/meetings/  # Save transcripts here
    format: markdown                  # "markdown" or "json"
    slack_notify: true                # Post minutes to Slack after meeting
```

### 10.5.4 Whisper Engine Options

| Engine | Package | Apple Silicon Optimization | Install |
|---|---|---|---|
| **mlx-whisper** (default) | `mlx-whisper` | MLX framework — 2-3x faster than CPU | `pip install mlx-whisper` |
| **whisper.cpp** | System binary | CoreML + ANE — 3x+ faster than CPU | `brew install whisper-cpp` |
| **faster-whisper** | `faster-whisper` | CTranslate2 (CPU optimized) | `pip install faster-whisper` |

**Default: mlx-whisper** — best Python integration, native Apple Silicon optimization, easy install via pip.

### 10.5.5 Real-time Meeting Analysis (Bedrock)

During a meeting, Yui performs live analysis by sending transcript chunks to Bedrock:

**Every ~60 seconds (configurable):**
```
System prompt: "You are a meeting analyst. Based on the following transcript excerpt,
identify: (1) key decisions being made, (2) action items mentioned, (3) questions
that were asked but not answered, (4) topics that may need follow-up."

[Sliding window: last 5 minutes of transcript]
```

**Output channels:**
- **CLI**: Real-time display in terminal sidebar (if CLI mode)
- **Slack**: Periodic updates to a designated thread (configurable)
- **File**: Appended to `~/.yui/meetings/<meeting_id>/analysis.md`

**Use cases during meeting:**
- 🎯 Track action items as they're assigned ("Bob will send the doc by Friday")
- ❓ Flag unanswered questions ("We didn't resolve the deployment timeline")
- 📊 Detect topic shifts ("We moved from budget to hiring")
- ⚠️ Alert on decisions ("Team decided to use Kafka instead of SQS")

### 10.5.6 Automatic Minutes Generation (Post-meeting)

When the meeting recording stops, Yui automatically generates structured minutes:

**Minutes template (Bedrock LLM prompt):**
```markdown
# Meeting Minutes — {date} {time}
## Participants
(Speaker identification requires diarization — see Phase 4+ roadmap. Until then, speakers are not individually identified.)

## Summary
(2-3 paragraph executive summary)

## Key Decisions
1. [Decision] — [Context]

## Action Items
| # | Action | Owner | Due Date | Status |
|---|---|---|---|---|
| 1 | ... | ... | ... | Open |

## Discussion Topics
### Topic 1: ...
- Key points discussed
- Outcome / Next steps

## Open Questions
- Questions raised but not resolved

## Raw Transcript
(Link to full transcript file)
```

**Post-processing pipeline:**
1. Meeting ends → `meeting_recorder` tool stops
2. Full transcript assembled from chunks
3. Bedrock Converse API: Generate structured minutes (using Claude)
4. Minutes saved to `~/.yui/meetings/<meeting_id>/minutes.md`
5. If `slack_notify: true` → Post summary to Slack channel (tables converted to plain text for Slack mrkdwn compatibility)
6. If `outlook_mcp` available → Create follow-up calendar events for action items

### 10.5.7 Speaker Diarization (optional)

**Option A: pyannote.audio (local, recommended)**
- Open-source, runs locally
- Requires HuggingFace token (model is gated)
- Can identify 2-10 speakers
- Package: `pyannote-audio`
- Integration: Run after Whisper transcription, align timestamps

**Option B: Amazon Transcribe (cloud fallback)**
- Built-in speaker diarization
- Better for >5 speakers
- Cost: $0.024/min
- Use via `meeting.transcribe.provider: aws_transcribe` config

**Default: No diarization** (Phase 2 MVP). Speaker labels are a Phase 4+ enhancement.

### 10.5.8 Meeting Lifecycle

```
yui meeting start                    # Start recording + transcription
  → Audio capture begins
  → Whisper chunked transcription starts
  → Real-time Bedrock analysis starts (if enabled)

yui meeting status                   # Show current meeting info
  → Duration, word count, current topic, action items so far

yui meeting stop                     # Stop recording
  → Transcription finalized
  → Bedrock generates minutes
  → Slack notification (if configured)
  → Files saved to ~/.yui/meetings/

yui meeting list                     # List past meetings
yui meeting show <id>                # Show transcript + minutes
yui meeting search "keyword"         # Search across meeting transcripts (SQLite FTS5 full-text index)
```

### 10.5.9 Privacy & Security

- **Audio stays local** (default): When using Whisper (default), raw audio is processed on-device and never uploaded. If using Amazon Transcribe (opt-in via `meeting.transcribe.provider: aws_transcribe`), audio is streamed to AWS.
- **Text to Bedrock**: Only text transcripts are sent to Bedrock for analysis (within AWS VPC).
- **Meeting files**: Stored locally at `~/.yui/meetings/` with permission 700.
- **Retention**: Configurable auto-delete after N days (`meeting.retention_days: 90`).
- **No recording without explicit start**: Yui NEVER records audio without explicit `yui meeting start` command.

### 10.5.10 Dependencies (meeting feature)

| Package | Purpose | License | Phase |
|---|---|---|---|
| `mlx-whisper` | Whisper inference on Apple Silicon | MIT | Phase 2.5 |
| `sounddevice` | Audio capture from system/mic (preferred over pyaudio — no C dependency issues on macOS) | MIT | Phase 2.5 |
| `numpy` | Audio buffer processing | BSD | Phase 2.5 |

### 10.5.11 Meeting App Compatibility

| App | Audio Capture | Known Issues |
|---|---|---|
| **Amazon Chime** | ✅ Supported | ⚠️ Disable "Mute system audio during screen share" in Chime settings — Chime mutes system audio output during screen sharing by default, which breaks audio capture |
| **Zoom** | ✅ Supported | May need "Share Computer Sound" enabled in Zoom settings for ScreenCaptureKit. BlackHole works without extra config. |
| **Microsoft Teams** | ✅ Supported | Standard audio routing |
| **Google Meet** (browser) | ✅ Supported | Captures browser audio output |
| **WebEx** | ⚠️ Untested | Expected to work via system audio capture |

**Note**: Audio capture quality depends on system audio output settings. Headphone users may need to configure BlackHole as a multi-output device to capture audio while still hearing it.

### 10.5.12 Meeting Trigger UI — Menu Bar App + Global Hotkey (Phase 2.5)

Meeting recording can be triggered via CLI (`yui meeting start/stop`), but for day-to-day use a **macOS menu bar icon** and **global keyboard shortcut** provide a much better UX.

#### Menu Bar Icon (rumps)

A persistent status bar icon shows recording state at a glance and provides one-click meeting control.

| State | Icon | Menu Items |
|---|---|---|
| Idle | 🎤 (grey microphone) | ▶️ Start Meeting (⌘⇧R), 📝 Last Minutes, ⚙️ Settings, Quit |
| Recording | 🔴 (red dot) | ⏹ Stop Meeting (⌘⇧S), 📊 Status: Recording 00:23:45, Quit |
| Generating minutes | ⏳ (hourglass) | Generating minutes…, Quit |
| Minutes ready | ✅ (green check, 5s) | Returns to Idle after 5 seconds |

**Behavior**:
- macOS notification on recording start/stop/minutes ready
- Recording timer displayed in menu dropdown
- "Last Minutes" opens most recent minutes file in default editor
- Menu bar app communicates with Yui daemon via local Unix domain socket (default: `~/.yui/yui.sock`, configurable via `runtime.socket_path` in config.yaml for multi-instance setups)

**Implementation**: `rumps` library (Ridiculously Uncomplicated macOS Python Statusbar apps)
- Pure Python, PyObjC-based, ~50 lines of code
- Runs as a separate lightweight process (`yui menubar`)
- Automatically launched via launchd: `~/Library/LaunchAgents/com.yui.menubar.plist`

#### Global Hotkey (pynput)

Keyboard shortcuts for hands-free control without leaving the current app.

| Shortcut | Action |
|---|---|
| `⌘⇧R` (Cmd+Shift+R) | Toggle recording (start if idle, stop if recording) |
| `⌘⇧S` (Cmd+Shift+S) | Stop recording + generate minutes |
| `⌘⇧M` (Cmd+Shift+M) | Open latest meeting minutes |

**Implementation**: `pynput.keyboard.GlobalHotKeys`
- Requires macOS Accessibility permission (System Settings → Privacy & Security → Accessibility)
- Cmd+Shift modifiers recommended (Ctrl/Alt have known issues on macOS with pynput)
- Shortcuts are configurable in `config.yaml`:

```yaml
meeting:
  hotkeys:
    toggle: "<cmd>+<shift>+r"
    stop: "<cmd>+<shift>+s"
    open_minutes: "<cmd>+<shift>+m"
    enabled: true  # set false to disable hotkeys
```

#### IPC: Menu Bar ↔ Yui Daemon

```
┌─────────────────┐     Unix Socket      ┌─────────────────┐
│  yui menubar    │ ←──────────────────→  │  yui daemon     │
│  (rumps + UI)   │   ~/.yui/yui.sock     │  (agent + STT)  │
│                 │                       │                 │
│  • Menu state   │   JSON messages:      │  • Recording    │
│  • Hotkeys      │   {cmd: "start"}      │  • Whisper      │
│  • Notifications│   {cmd: "stop"}       │  • Bedrock      │
│                 │   {status: "rec",     │                 │
│                 │    elapsed: 1425}     │                 │
└─────────────────┘                       └─────────────────┘
```

- Menu bar app sends commands: `{"cmd": "meeting_start"}`, `{"cmd": "meeting_stop"}`, `{"cmd": "meeting_status"}`
- Daemon responds with status: `{"status": "recording", "elapsed_seconds": 1425, "transcript_lines": 342}`
- Daemon pushes state changes to menu bar (recording started/stopped/minutes ready)

#### CLI Entry Points

```bash
yui menubar              # Launch menu bar app (foreground)
yui menubar --background # Launch as background process
yui menubar --install    # Install launchd plist for auto-start on login
yui menubar --uninstall  # Remove launchd plist
```

#### Dependencies (optional)

| Package | Version | Purpose | License | Phase |
|---|---|---|---|---|
| `rumps` | ≥0.4 | macOS menu bar app | MIT | Phase 2.5 |
| `pynput` | ≥1.7 | Global keyboard hotkeys | LGPL-3.0 | Phase 2.5 |

```toml
# pyproject.toml additions
[project.optional-dependencies]
meeting = ["mlx-whisper>=0.4", "sounddevice>=0.5", "numpy>=1.26"]
ui = ["rumps>=0.4"]
hotkey = ["pynput>=1.7"]
all = ["yui-agent[meeting,ui,hotkey]"]
```

#### macOS Permissions Required

| Permission | Required For | How to Grant |
|---|---|---|
| Screen Recording | ScreenCaptureKit audio capture | System Settings → Privacy → Screen Recording |
| Microphone | Mic input recording | System Settings → Privacy → Microphone |
| Accessibility | Global hotkeys (pynput) | System Settings → Privacy → Accessibility |
| Notifications | Recording start/stop alerts | System Settings → Notifications |

#### Acceptance Criteria

- [ ] AC-52: Menu bar icon visible in macOS status bar after `yui menubar`
- [ ] AC-53: Click "Start Meeting" → recording begins, icon changes to 🔴
- [ ] AC-54: Click "Stop Meeting" → recording stops, minutes generated, icon returns to 🎤
- [ ] AC-55: Global hotkey ⌘⇧R toggles recording on/off
- [ ] AC-56: Recording elapsed time visible in menu dropdown
- [ ] AC-57: macOS notification shown on recording start and minutes completion
- [ ] AC-58: Menu bar app communicates with daemon via Unix socket
- [ ] AC-59: `yui menubar --install` creates launchd plist for auto-start
- [ ] AC-60: Hotkeys configurable via config.yaml; `enabled: false` disables them
- [ ] AC-61: Menu bar app gracefully handles daemon not running (shows "Daemon offline" in menu)

**Note**: These are **optional dependencies** — installed only when meeting feature is enabled. Core Yui works without them.

```toml
# pyproject.toml
[project.scripts]
yui = "yui.__main__:main"

[project.optional-dependencies]
meeting = ["mlx-whisper>=0.4", "sounddevice>=0.5", "numpy>=1.26"]
ui = ["rumps>=0.4"]
hotkey = ["pynput>=1.7"]
all = ["yui-agent[meeting,ui,hotkey]"]
```

---

## 10.6 AWS Workshop Auto-Execution Testing (Phase 4)

### 10.6.1 Overview

Yui provides automated workshop testing: given a Workshop Studio URL, Yui scrapes the workshop content via browser automation, walks through each step by operating the AWS Console (Playwright), records the entire session as video, validates results with Bedrock Vision, and produces a test report with video recordings and screenshots. This enables workshop authors to verify their content works end-to-end before publishing, and supports regression testing when AWS services change.

**Key design decisions (confirmed by han 2026-02-26):**
- Primary content source is Workshop Studio (catalog.workshops.aws); GitHub support planned for future
- Environment provisioning is done via Console operations by Yui (not CLI/CFn)
- Console operations must be verified via browser automation (Playwright)
- Target workshops are not genre-limited; Cloud-based workshops that complete entirely in Console

### 10.6.2 Workflow

```
Workshop Studio URL (catalog.workshops.aws)
  ↓ Content Scraper (Playwright — SPA requires browser)
Page content (all modules/steps)
  ↓ Step Planner (Bedrock LLM)
Structured executable steps (JSON)
  ↓ Console Executor (Playwright + Bedrock Vision)
  ↓ + Video Recorder (Playwright record_video)
  ↓ + Screenshot Capture (per step + on failure)
Step Results (PASS / FAIL / SKIP / TIMEOUT)
  ↓ Reporter
Test Report (Markdown + video links + screenshots)
  ↓ Slack Notification
  ↓ Cleanup (tag-based resource deletion)
```

### 10.6.3 Step Types

| Type | Description | Executor | Video |
|---|---|---|---|
| `console_navigate` | AWS Console page navigation | Playwright | ✅ |
| `console_action` | Console CRUD operations (click, fill, select) | Playwright + Bedrock Vision | ✅ |
| `console_verify` | Console screen state validation | Playwright screenshot + Bedrock Vision | ✅ |
| `cli_command` | AWS CLI / shell command (when workshop has CLI steps) | subprocess (safe_shell) | ❌ |
| `cli_check` | CLI output validation | subprocess + Bedrock LLM | ❌ |
| `cfn_deploy` | CloudFormation stack ops (if in workshop) | boto3 | ❌ |
| `http_test` | HTTP endpoint test | requests | ❌ |
| `code_run` | Code execution (if in workshop) | subprocess | ❌ |
| `wait` | Resource readiness polling | timeout loop | ❌ |
| `manual_step` | Manual op — LLM skip or find alternative | — | — |

**Console operations are primary.** Most workshop steps are Console UI operations.

### 10.6.4 Content Sources

- **Workshop Studio URL** (`catalog.workshops.aws/...`) → Playwright browser scraping (SPA, web_fetch won't work)
- **GitHub repository** (future) → `git clone` or GitHub API

### 10.6.5 Console Authentication

Workshop testing requires AWS Console login. Supported methods:

| Method | Description | Config key |
|---|---|---|
| `iam_user` | IAM user + password Console login | `console_auth.method: iam_user` |
| `federation` | STS GetFederationToken → Console URL (temp credentials) | `console_auth.method: federation` |
| `sso` | IAM Identity Center SSO portal | `console_auth.method: sso` |

### 10.6.6 Video Recording

Playwright built-in video recording captures the entire Console operation:

- **Format**: WebM (VP8)
- **Resolution**: Configurable (default: 1920×1080)
- **Per-step videos**: Each step recorded as separate video file
- **Full walkthrough**: Continuous video of entire test run
- **Works in headless mode**: No display required
- **Output**: `~/.yui/workshop-tests/{test-id}/videos/`

### 10.6.7 Vision Validation

Each step result is validated using Bedrock Claude Vision:
- Screenshot captured after step execution
- Image sent to Bedrock with expected result description
- LLM responds PASS/FAIL/UNCLEAR with explanation
- Failed steps include screenshot + failure reason in report

### 10.6.8 Test Report

```markdown
# Workshop Test Report — {date}
## Workshop: {title}
## Source: {url}
### Summary
- Total Steps: N
- Passed: X ✅ | Failed: Y ❌ | Skipped: Z ⏭
- Duration: Xm Ys
- AWS Cost (estimated): $X.XX
### Video Recordings
- 📹 Full walkthrough: videos/full-walkthrough.webm
- 📹 Module 1: videos/module-1.webm
### Step Results
| # | Module | Step | Result | Screenshot | Video Timestamp |
|---|---|---|---|---|---|
### Failed Steps Detail
(screenshot + explanation + LLM-generated fix suggestions)
### AWS Resources Created (for cleanup)
```

### 10.6.9 Safety Controls

- **Cost guard**: Configurable max cost per test run (default: $10). Test aborts if projected cost exceeds limit.
- **Timeout**: Per-step timeout (default: 300s) and total test timeout (default: 120min).
- **Cleanup**: `--cleanup` auto-deletes all test-created resources via tag-based tracking (`yui:workshop-test={test-id}`).
- **Account isolation**: Test in dedicated AWS account recommended.
- **Command allowlist**: safe_shell restrictions apply to any CLI steps.

### 10.6.10 Config

```yaml
workshop:
  test:
    region: us-east-1
    cleanup_after_test: true
    timeout_per_step_seconds: 300
    max_total_duration_minutes: 120
    max_cost_usd: 10.0
    headed: false  # true=visible browser, false=headless
    console_auth:
      method: iam_user  # iam_user | federation | sso
      account_id: ""
      username: ""
      # password from .env: YUI_CONSOLE_PASSWORD
    video:
      enabled: true
      resolution: {width: 1920, height: 1080}
      per_step: true
      full_walkthrough: true
      output_dir: ~/.yui/workshop-tests/
    screenshot:
      enabled: true
      on_step_complete: true
      on_failure: true
      full_page: true
  report:
    format: markdown
    include_screenshots: true
    include_video_links: true
    slack_notify: true
    save_path: ~/.yui/workshop-tests/
```

### 10.6.11 CLI

```bash
yui workshop test <url>                    # Run workshop test
yui workshop test <url> --record           # Test + video recording (default: on)
yui workshop test <url> --cleanup          # Test + auto-cleanup resources
yui workshop test <url> --headed           # Show browser window
yui workshop test <url> --dry-run          # Parse only, no execution
yui workshop test <url> --steps 1-5        # Test specific steps
yui workshop list-tests                     # List past test runs
yui workshop show-report <test-id>         # Show specific report
```

### 10.6.12 Acceptance Criteria

- [ ] AC-70: Workshop Studio content scraped via Playwright (SPA navigation)
- [ ] AC-71: Bedrock LLM converts scraped content into structured executable steps
- [ ] AC-72: AWS Console login automated via Playwright (IAM user / federation / SSO)
- [ ] AC-73: Console page navigation automated (service switching, region selection)
- [ ] AC-74: Console CRUD operations executed (resource create/update/delete via UI)
- [ ] AC-75: Bedrock Vision validates step results from screenshots (PASS/FAIL/SKIP)
- [ ] AC-76: Playwright video records all Console operations (per-step + full walkthrough)
- [ ] AC-77: Screenshots captured at step completion and on failure
- [ ] AC-78: Structured test report with video links and screenshots generated
- [ ] AC-79: Slack notification with test summary posted
- [ ] AC-80: Tag-based resource cleanup (`yui:workshop-test` tag)
- [ ] AC-81: Cost guard aborts test when projected cost exceeds configured limit
- [ ] AC-82: `yui workshop test <url>` CLI with `--record`, `--cleanup`, `--headed`, `--dry-run`
- [ ] AC-83: Per-step and total timeout enforced
- [ ] AC-84: CLI command fallback for workshop steps that include CLI instructions
- [ ] AC-85: Regression mode for periodic automated testing (cron)
- [ ] AC-86: (Future) GitHub repository content source support

---

## 11. Daemon (Phase 3, macOS only)

- launchd plist at `~/Library/LaunchAgents/com.yui.agent.plist`
- Starts on login, restarts on crash (5s backoff)
- Environment variables loaded from `~/.yui/.env`
- **Logging**: `~/.yui/logs/yui.log` with `RotatingFileHandler(maxBytes=10MB, backupCount=5)` (Kiro review m-03)
- Control: `launchctl load/unload`, `yui daemon start/stop/status`
- **Daily cleanup job** (3am): Delete meeting recordings older than `meeting.retention_days` (default: 90)

---

## 12. Non-Functional Requirements

| Category | Requirement |
|---|---|
| **Language** | Python 3.12+ |
| **License** | Apache 2.0 |
| **Install size** | <50MB |
| **Dependencies** | strands-agents, strands-agents-tools, bedrock-agentcore, boto3, slack-bolt, pyyaml, rich, mcp |
| **Startup time** | <3 seconds to CLI REPL |
| **LLM latency** | No measurable overhead vs raw Bedrock API call |
| **Security** | No plaintext secrets in config; .env file with 600 permissions |
| **Logging** | Python `logging` module with `RotatingFileHandler`, configurable level |
| **Error handling** | Graceful degradation: Bedrock timeout → retry 3x with exponential backoff (1s, 2s, 4s) → user error message |
| **Testing** | pytest, >80% coverage for core modules, mocked AWS calls. **Must include negative tests for E-01 through E-12** (Kiro review m-05) |

---

## 13. Acceptance Criteria

### Phase 0 (CLI + Bedrock + Tools)

- [ ] AC-01: `python -m yui` starts a CLI REPL that accepts user input
- [ ] AC-02: User message is sent to Bedrock via Strands Agent SDK and response is displayed
- [ ] AC-03: Agent can execute shell commands via `shell` tool with allowlist enforcement
- [ ] AC-04: Agent can read, write, and edit files via strands-agents-tools
- [ ] AC-05: System prompt includes content from AGENTS.md and SOUL.md
- [ ] AC-06: `config.yaml` is loaded and validated on startup
- [ ] AC-07: Invalid config produces a clear error message and exits
- [ ] AC-08: CLI supports readline history (up arrow recalls previous input)

### Phase 1 (Slack + Sessions)

- [ ] AC-09: Slack Socket Mode connects successfully with bot + app tokens
- [ ] AC-10: @mention in a Slack channel triggers agent response in thread
- [ ] AC-11: DM to bot triggers agent response
- [ ] AC-12: Conversation history is persisted in SQLite across restarts
- [ ] AC-13: Session compaction triggers at configured threshold
- [ ] AC-14: Compacted session preserves context (agent still knows prior discussion)

### Phase 2 (Kiro + Git + Cloud Tools)

- [ ] AC-15: `kiro_delegate` tool invokes Kiro CLI and returns cleaned output
- [ ] AC-16: `git_tool` can run status, add, commit, push, log, diff
- [ ] AC-17: AgentCore Browser Tool can fetch and extract web page content
- [ ] AC-18: AgentCore Memory can store and retrieve memories across sessions
- [ ] AC-18a: AgentCore Code Interpreter can execute Python code and return results
- [ ] AC-19: Kiro CLI timeout (>300s) produces graceful error, not crash
- [ ] AC-19a: Kiro CLI missing at startup → clear error with install instructions, exit code 1

### Phase 2.5 — Meeting Transcription & Minutes

- [ ] AC-40: `yui meeting start` begins audio capture and Whisper transcription
- [ ] AC-41: `yui meeting stop` stops recording and triggers auto-minutes generation
- [ ] AC-42: Whisper transcribes audio chunks in near-real-time (<5s latency)
- [ ] AC-43: System audio from meeting apps (Zoom/Teams/Chime) is captured
- [ ] AC-44: Microphone audio is mixed with system audio when `include_mic: true`
- [ ] AC-45: Bedrock generates structured meeting minutes (summary, action items, decisions)
- [ ] AC-46: Minutes saved to `~/.yui/meetings/<meeting_id>/minutes.md`
- [ ] AC-47: Slack notification with meeting summary posted after meeting ends (if configured)
- [ ] AC-48: `yui meeting list` shows past meeting transcripts
- [ ] AC-49: `yui meeting search "keyword"` searches across meeting transcripts
- [ ] AC-50: Real-time analysis updates every 60s during active meeting (action items, decisions)
- [ ] AC-51: Meeting feature is opt-in — requires `pip install yui-agent[meeting]`
- [ ] AC-52: Menu bar icon visible in macOS status bar after `yui menubar`
- [ ] AC-53: Click "Start Meeting" → recording begins, icon changes to 🔴
- [ ] AC-54: Click "Stop Meeting" → recording stops, minutes generated, icon returns to 🎤
- [ ] AC-55: Global hotkey ⌘⇧R toggles recording on/off
- [ ] AC-56: Recording elapsed time visible in menu dropdown
- [ ] AC-57: macOS notification shown on recording start and minutes completion
- [ ] AC-58: Menu bar app communicates with daemon via Unix socket (`~/.yui/yui.sock`)
- [ ] AC-59: `yui menubar --install` creates launchd plist for auto-start on login
- [ ] AC-60: Hotkeys configurable via config.yaml; `enabled: false` disables them
- [ ] AC-61: Menu bar app gracefully handles daemon not running (shows "Daemon offline")

### Phase 3 (Guardrails + Heartbeat + Daemon)

- [ ] AC-20: Bedrock Guardrail blocks harmful content and surfaces error to user
- [ ] AC-21: Heartbeat reads HEARTBEAT.md and triggers agent at configured interval
- [ ] AC-22: Heartbeat respects active hours (no execution outside configured window)
- [ ] AC-23: `launchctl load` starts Yui as background daemon
- [ ] AC-24: Daemon auto-restarts on crash within 5 seconds
- [ ] AC-25: `yui daemon status` reports running/stopped state
- [ ] AC-25a: Static MCP servers from config.yaml are connected at startup
- [ ] AC-25b: `aws-outlook-mcp` server provides calendar and mail functionality
- [ ] AC-25c: Dynamic MCP server connection works at agent runtime

### Error Handling (negative tests — Kiro review m-05)

- [ ] AC-26: Missing AWS credentials → clear error message, exit code 1 (E-01)
- [ ] AC-27: Bedrock permission denied → actionable IAM error (E-02)
- [ ] AC-28: Bedrock timeout → 3 retries with backoff, then user error (E-03)
- [ ] AC-29: Invalid Slack tokens → startup error with guidance (E-04)
- [ ] AC-30: Shell blocklisted command → "blocked by security policy" (E-08)
- [ ] AC-31: File operation outside workspace → "access denied" (E-09)
- [ ] AC-32: Missing config.yaml → runs with defaults, logs info (E-10)
- [ ] AC-33: Kiro CLI not found → graceful error message (E-07)
- [ ] AC-34: SQLite database locked → retry with backoff, then clear error (E-06)
- [ ] AC-35: Context window exceeded → force compaction or archive session (E-12)
- [ ] AC-36: MCP server connection failure → graceful degradation, agent continues (E-13)
- [ ] AC-37: Kiro CLI missing at startup → exit with install instructions (E-07 revised)
- [ ] AC-38: Meeting feature handles E-15 through E-20 gracefully (permission, model, device, duplicate, crash, HF token)
- [ ] AC-39: Meeting app compatibility verified for Zoom, Teams, and Chime (AC from M-06)

---

## 14. Edge Cases & Error Handling

| # | Scenario | Expected behavior |
|---|---|---|
| E-01 | AWS credentials not configured | Clear error message: "AWS credentials not found. Run `aws configure` or set environment variables." Exit code 1 |
| E-02 | Bedrock model not accessible (permission denied) | Error: "Cannot access model X. Check IAM permissions for bedrock:InvokeModel." |
| E-03 | Bedrock API timeout (30s+) | Retry up to 3 times with exponential backoff (1s, 2s, 4s). Then: "Bedrock API timed out after 3 retries." |
| E-04 | Slack tokens invalid/expired | Error on startup: "Slack authentication failed. Check SLACK_BOT_TOKEN and SLACK_APP_TOKEN." |
| E-05 | Slack Socket Mode disconnects | Auto-reconnect (handled by slack-bolt). Log warning. |
| E-06 | SQLite database locked | Retry with 100ms backoff, max 5 attempts. If still locked: "Session database is locked. Another Yui instance may be running." |
| E-07 | Kiro CLI not found in PATH | **Startup error**: "Kiro CLI not found at configured path. Yui requires Kiro CLI for coding tasks. Install it from https://kiro.dev/docs/cli/ or update tools.kiro.binary_path." **Exit code 1** |
| E-08 | Shell command in blocklist attempted | Return: "Command blocked by security policy." Log the attempt. |
| E-09 | File operation outside workspace_root | Return: "Access denied: path is outside configured workspace." |
| E-10 | config.yaml missing | Use defaults. Log: "No config.yaml found at ~/.yui/config.yaml, using defaults." |
| E-11 | AGENTS.md / SOUL.md missing | Agent runs with base system prompt only. Log info. |
| E-12 | Context window exceeded before compaction | Force compaction. If compaction itself fails (summary too large), archive current session to `~/.yui/sessions_archive/<session_id>.json`, start new session, send user: "Previous conversation was archived due to length. Starting fresh." |
| E-13 | MCP server connection failed | Log warning, continue without that MCP server's tools. User message: "MCP server [name] is unavailable. Some features may be limited." |
| E-14 | MCP server timeout | Retry once after 5s. If still fails, skip tool call with error message. |
| E-15 | Audio capture permission denied (ScreenCaptureKit) | User message: "Screen Recording permission required. Go to System Preferences → Privacy & Security → Screen Recording and enable Yui." |
| E-16 | Whisper model not found / download failed | User message: "Whisper model not available. Run `pip install yui-agent[meeting]` to install meeting dependencies." |
| E-17 | Audio device not found (no mic / no system audio) | User message: "No audio input detected. Check microphone and system audio settings." |
| E-18 | Meeting recording already active | User message: "A meeting is already being recorded. Use `yui meeting stop` first." |
| E-19 | Whisper crash/OOM mid-meeting | Save raw audio buffer to `~/.yui/meetings/<id>/audio.wav`, log error, continue recording audio. User can re-transcribe later with `yui meeting transcribe <id>`. |
| E-20 | pyannote HuggingFace token missing | User message: "Speaker diarization requires HuggingFace token. Set HF_TOKEN environment variable. Get token at https://huggingface.co/settings/tokens" |

---

## 15. Dependency Inventory

| Package | Version | Purpose | License |
|---|---|---|---|
| `strands-agents` | ≥0.1.0 | Core agent SDK (loop, model, tools) | Apache 2.0 |
| `strands-agents-tools` | ≥0.1.0 | Built-in tools (shell, file, slack, memory, browser) | Apache 2.0 |
| `bedrock-agentcore` | ≥0.1.0 | AgentCore Browser, Memory, Code Interpreter SDKs | Apache 2.0 |
| `boto3` | ≥1.35.0 | AWS SDK (Bedrock, S3, etc.) | Apache 2.0 |
| `slack-bolt` | ≥1.21.0 | Slack Socket Mode adapter | MIT |
| `slack-sdk` | ≥3.33.0 | Slack API client (transitive via slack-bolt) | MIT |
| `pyyaml` | ≥6.0 | YAML config parsing | MIT |
| `rich` | ≥13.0 | CLI formatted output | MIT |
| `mcp` | ≥1.0.0 | MCP protocol client (for MCP server integration) | MIT |

**Total: 8 direct dependencies** (vs OpenClaw's 54). `slack-sdk` is transitive via `slack-bolt` (not counted separately). `sqlite3` is Python stdlib.

**Optional dependencies (meeting feature):**

| Package | Version | Purpose | License |
|---|---|---|---|
| `mlx-whisper` | ≥0.4 | Whisper inference on Apple Silicon | MIT |
| `sounddevice` | ≥0.5 | Audio capture | MIT |
| `numpy` | ≥1.26 | Audio buffer processing | BSD |

**Optional dependencies (UI/hotkey):**

| Package | Version | Purpose | License |
|---|---|---|---|
| `rumps` | ≥0.4 | macOS menu bar app | MIT |
| `pynput` | ≥1.7 | Global keyboard hotkeys | LGPL-3.0 |

---

## 16. Open Questions

| # | Question | Impact | Status |
|---|---|---|---|
| Q-01 | ~~Should web search use Tavily or Bedrock Agent inline search?~~ | Phase 2 tool selection | **Resolved** — Default: Bedrock KB (VPC-internal). Tavily opt-in only. |
| Q-02 | AgentCore Browser Tool availability — is it GA in target AWS region? | Phase 2 feasibility | Open — must verify in Pre-Phase 0 SDK Verification Gate |
| Q-03 | Project name "Yui" — confirmed or placeholder? | README/branding | Open |
| Q-04 | Should Heartbeat results be posted to a Slack channel? | Phase 3 behavior | Open |
| Q-05 | ~~MCP tool consumption — should Yui support loading tools from MCP servers?~~ | Future extensibility | Deferred to Phase 4+ |
| Q-06 | AgentCore Code Interpreter availability — GA in target region? | Phase 2 feasibility | Open — must verify in Pre-Phase 0 SDK Verification Gate |
| Q-07 | AgentCore Memory — namespace isolation strategy for multi-user? If multiple users share a Bedrock account, how to prevent memory leakage between users? Proposed: prefix all memory keys with `user_id` hash. | Phase 2+ | Open |

---

## 17. Glossary

| Term | Definition |
|---|---|
| Strands Agent SDK | AWS-official open-source Python SDK for building AI agents with Bedrock |
| Bedrock Converse API | AWS API for multi-turn LLM conversations with tool use support |
| Socket Mode | Slack connection method using WebSocket — no public URL needed |
| AgentCore | AWS Bedrock service providing managed browser, memory, and code interpreter |
| Kiro CLI | AWS IDE/CLI tool for agentic coding tasks |
| Compaction | Summarizing long conversation history to fit within model context window |
| HITL | Human-in-the-loop — requiring human approval before executing certain actions |
| Guardrails | Bedrock service that filters model inputs/outputs for safety and compliance |

---

## Changelog

| Date | Author | Change |
|---|---|---|
| 2026-02-25 | AYA | Initial draft — Discovery from OpenClaw source analysis + Strands SDK research |
| 2026-02-25 | AYA | v0.3.0 — Local/Cloud boundary redesign per han's directive + Kiro round 2 review. Section 4 fully rewritten with 3-tier model. |
| 2026-02-25 | AYA | v0.4.0 — han feedback incorporated: (①②③) AWS Bedrock features explicitly enumerated in Section 4.6. (④) Kiro CLI made required dependency with startup check; AGENTS.md ships with Kiro⇔Yui cross-review workflow. (⑤) Outlook tools replaced by aws-outlook-mcp corporate MCP server. (⑥) diagram/media tools replaced by MCP servers. New Section 4.4 for MCP integration. MCP config.yaml schema added. `mcp` package added as 9th dependency. E-13/E-14 error handling for MCP. AC-25a/b/c, AC-36/AC-37 added. |
| 2026-02-25 | AYA | v0.5.0 — HANA→Yui rename (per han's naming decision). New Section 9.5: Meeting Transcription & Automatic Minutes (Whisper + Bedrock). Discovery: Whisper local vs Amazon Transcribe comparison, mlx-whisper as default engine, ScreenCaptureKit for audio capture, hybrid local/cloud architecture (audio local, LLM cloud). New tools: meeting_recorder, whisper_transcribe. CLI: yui meeting start/stop/status/list/search. Auto-minutes with Bedrock (summary, action items, decisions). Real-time analysis during meetings. Optional deps via pyproject.toml extras [meeting]. AC-40–51, E-15–18 added. |
| 2026-02-25 | AYA | v0.6.0 — Kiro round 3 review: C-01 WER accuracy corrected (Whisper ~8-12%, Transcribe ~5-8%). C-02 ScreenCaptureKit confirmed capable of audio capture (capturesAudio API), but PyObjC stability note added + BlackHole fallback strengthened. C-03 `yui` console script added to pyproject.toml. C-04 realtime_enabled default→false, budget guard added. C-05 Meeting tool specs added (Section 4.10.1). M-01 Minutes template fixed (no attendees without diarization). M-02 pyaudio removed, sounddevice only. M-03 Whisper crash recovery (E-19). M-04 Privacy claim clarified for Transcribe opt-in. M-05 Meeting→Phase 2.5. M-06 Meeting app compatibility table added (Section 9.5.11). M-07 AgentCore Code Interpreter AC added. Minor: sliding window config, Slack mrkdwn note, FTS5 search, MCP allowlist docs, optional deps in Section 14, retention cleanup in daemon, test coverage clarification. |
| 2026-02-25 | AYA | v0.7.0 — Name: 結（ゆい / Yui）. Repo renamed: hana-agent → yui-agent. New Section 9.5.12: Meeting Trigger UI (Menu Bar App + Global Hotkey). rumps-based macOS menu bar icon with recording state indicator (🎤/🔴/⏳/✅). pynput global hotkeys (⌘⇧R toggle, ⌘⇧S stop, ⌘⇧M open minutes). IPC via Unix domain socket (~/.yui/yui.sock). launchd auto-start support. CLI: yui menubar [--install/--uninstall]. Optional deps: rumps, pynput. AC-52 through AC-61 added. Phase 2.5 scope expanded. |
| 2026-02-25 | AYA | v0.8.0 — New Section 5.2.1: Slack App/Bot Setup Guide (complete step-by-step). Full app manifest YAML with all required OAuth scopes (15 bot scopes). Socket Mode architecture explained (why no public URL needed, firewall-friendly). Token generation guide (Bot Token xoxb + App-Level Token xapp). Config integration (config.yaml + .env). Slack capabilities matrix (mention, DM, channels, reactions, file upload, threads). AC-62 through AC-66 added (setup validation, manifest shipping, token errors, response time, DM support). |
| 2026-02-26 | AYA | v0.9.0 — New Section 8: Autonomy Architecture (Phase 2–3). Single-agent ceiling analysis. Autonomy levels L0–L4 defined. Layer 1: Strands Agent Loop (ReAct). Layer 2: Yui ⇔ Kiro Cross-Review via GraphBuilder Reflexion Loop — requirements review by Kiro (per han directive), coding workflow, design review. Kiro CLI tools (`kiro_review`, `kiro_implement`) as Strands @tool. Layer 3: Self-Evaluation + Self-Improvement (task-level eval, weekly AGENTS.md PR proposals, OODA loop). Guardrails: AGENTS.md changes via PR only, cost budget, loop limits, maintenance window. Evidence from AYA ecosystem. Sections 8–16 renumbered to 9–17. AC-67 through AC-80 added (14 new, cumulative 80 ACs). |
| 2026-02-26 | AYA | v0.10.0 — Kiro review round 4: 20 findings (C4/M7/m9). ALL FIXED. C-01/C-02/C-03: Pre-Phase 0 SDK verification expanded (GraphBuilder cycles, @tool subprocess, Guardrails API). C-04: New Section 8.8 Failure Modes & Recovery (6 failure scenarios with detection/recovery). M-01: New Section 8.9 Level Transition Criteria (L0→L4 concrete metrics). M-02: AC-62 expanded with OAuth scope verification. M-03: AC-81 audio quality pre-test. M-04: New Section 8.10 Conflict Resolution Protocol (CHALLENGE mechanism). M-05: HEARTBEAT.md integrity check hardened (stop+notify+require reset). M-06: New Section 8.11 Self-Improvement Validation & Rollback (shadow mode, auto-revert, cool-down). M-07: Dependency count corrected (8 direct). Minors: code imports, Chime audio note, cost tracking mechanism, output truncation rationale, socket path configurable, Q-07 clarified, eval schema validation. AC-81 through AC-84 added (cumulative 84 ACs). |

---

## 障害振り返りプロセス（RCA標準手順）

> Issue #72 (2026-02-26 hanさん指摘) に基づき追加。

### 原則

障害振り返りは「現状スナップショットの列挙」ではなく、**時系列と5W1H** による因果分析を行う。

### 標準テンプレート

`docs/rca-template.md` を使用する（必須）。

```
cp docs/rca-template.md docs/rca-$(date +%Y-%m-%d)-<タイトル>.md
```

### 必須要素

1. **タイムライン**: `git log --follow <file>` で実際の日時を確認して記入
2. **5W1H分析**: Who/When/Where/What/Why/How を git タイムスタンプ + コード引用で根拠付き記述
3. **5 Whys**: 根本原因まで5回掘り下げ（抽象的な分類で止めない）
4. **再発防止策**: Issue 番号・担当者・期限を明記

### 禁止事項

- `「〜と思われる」「〜かもしれない」`（根拠不明の推測）
- 時系列を省略した現状スナップショットのみの分析
- 「手順不足」「認識不足」レベルで5 Whysを止める

### Changelog

| Date | Author | Change |
|---|---|---|
| 2026-03-06 | OCA | Issue #72 対応 — 障害振り返りプロセスセクション追加 + docs/rca-template.md 作成 |
