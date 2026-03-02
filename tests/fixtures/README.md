# AgentCore sessions_spawn Testing

## Overview

Full flow integration tests for AgentCore `sessions_spawn` endpoint.

## Architecture

```
MockAgentCoreWSServer
├── HTTP Server (port 18080)
│   └── POST /sessions_spawn → session_id
└── WebSocket Server (port 18081)
    └── /ws/{session_id} → bidirectional communication
```

## Test Coverage

### Basic Flow
- ✅ Session creation (POST /sessions_spawn)
- ✅ WebSocket connection establishment
- ✅ Bidirectional message send/receive
- ✅ Tool call execution (file_read, git_tool)
- ✅ Session cleanup

### Error Handling
- ✅ Connection timeout
- ✅ Invalid session_id
- ✅ Connection close handling

### Concurrent Sessions
- ✅ Multiple parallel sessions
- ✅ Session isolation
- ✅ Message history separation

## Running Tests

```bash
# Install dependencies
pip install -e ".[dev]"

# Run all sessions_spawn tests
pytest tests/test_agentcore_sessions_spawn.py -v

# Run specific test class
pytest tests/test_agentcore_sessions_spawn.py::TestSessionsSpawnFlow -v

# Run with coverage
pytest tests/test_agentcore_sessions_spawn.py --cov=tests.fixtures.mock_agentcore_ws
```

## Mock Server Usage

```python
import asyncio
from tests.fixtures.mock_agentcore_ws import MockAgentCoreWSServer

async def main():
    server = MockAgentCoreWSServer(http_port=8080, ws_port=8081)
    await server.start()
    
    # Use server...
    
    await server.stop()

asyncio.run(main())
```

## Extending Mock Server

Add new tool simulations in `_process_message()`:

```python
async def _process_message(self, session_id: str, message: Dict) -> Dict:
    if msg_type == 'tool_call':
        tool_name = message.get('tool_name')
        
        if tool_name == 'your_new_tool':
            return {
                'type': 'tool_result',
                'tool_name': tool_name,
                'result': 'your mock result'
            }
```

## Integration with Real AgentCore

To test against real AgentCore endpoint:

```bash
# Set environment variable
export AGENTCORE_ENDPOINT=https://your-agentcore.com/api

# Run E2E tests
YUI_AWS_E2E=1 pytest tests/test_agentcore_e2e.py -v
```

## Troubleshooting

### Port conflicts
If ports 18080/18081 are in use, modify fixture:

```python
@pytest.fixture
async def mock_server():
    server = MockAgentCoreWSServer(http_port=28080, ws_port=28081)
    # ...
```

### WebSocket connection errors
Check firewall settings and ensure localhost access is allowed.

### Async test failures
Ensure `pytest-asyncio` is installed and tests are marked with `@pytest.mark.asyncio`.
