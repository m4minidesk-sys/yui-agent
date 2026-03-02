"""AgentCore sessions_spawn Full Flow Integration Tests.

Tests the complete flow:
1. POST /sessions_spawn → receive session_id
2. WebSocket connection → maintain connection
3. Send/receive messages → bidirectional communication
4. Multiple tool calls → async processing
5. Session cleanup → proper teardown

Run with: pytest tests/test_agentcore_sessions_spawn.py -v
"""

import asyncio
import json

import pytest
import websockets
from aiohttp import ClientSession

from tests.fixtures.mock_agentcore_ws import MockAgentCoreWSServer


@pytest.fixture
async def mock_server():
    """Start mock AgentCore server with WebSocket support."""
    server = MockAgentCoreWSServer(http_port=18080, ws_port=18081)
    await server.start()
    yield server
    await server.stop()


@pytest.mark.asyncio
class TestSessionsSpawnFlow:
    """Test sessions_spawn full flow."""
    
    async def test_session_creation(self, mock_server):
        """Test POST /sessions_spawn returns valid session_id."""
        async with ClientSession() as session:
            async with session.post('http://localhost:18080/sessions_spawn') as resp:
                assert resp.status == 200
                data = await resp.json()
                
                assert 'session_id' in data
                assert 'ws_url' in data
                assert data['session_id']
                assert 'ws://' in data['ws_url']
    
    async def test_websocket_connection(self, mock_server):
        """Test WebSocket connection establishment."""
        # Create session
        async with ClientSession() as session:
            async with session.post('http://localhost:18080/sessions_spawn') as resp:
                data = await resp.json()
                session_id = data['session_id']
        
        # Connect WebSocket
        ws_url = f'ws://localhost:18081/ws/{session_id}'
        async with websockets.connect(ws_url) as ws:
            # Send ping
            await ws.send(json.dumps({'type': 'ping'}))
            
            # Receive pong
            response = await ws.recv()
            data = json.loads(response)
            
            assert data['type'] == 'pong'
    
    async def test_bidirectional_communication(self, mock_server):
        """Test send/receive messages."""
        # Create session
        async with ClientSession() as session:
            async with session.post('http://localhost:18080/sessions_spawn') as resp:
                data = await resp.json()
                session_id = data['session_id']
        
        # Connect and communicate
        ws_url = f'ws://localhost:18081/ws/{session_id}'
        async with websockets.connect(ws_url) as ws:
            # Send multiple messages
            messages = [
                {'type': 'test', 'data': 'message1'},
                {'type': 'test', 'data': 'message2'},
                {'type': 'test', 'data': 'message3'},
            ]
            
            for msg in messages:
                await ws.send(json.dumps(msg))
                response = await ws.recv()
                data = json.loads(response)
                assert data['type'] == 'echo'
                assert data['data'] == msg
    
    async def test_tool_call_execution(self, mock_server):
        """Test tool call through WebSocket."""
        # Create session
        async with ClientSession() as session:
            async with session.post('http://localhost:18080/sessions_spawn') as resp:
                data = await resp.json()
                session_id = data['session_id']
        
        # Execute tool call
        ws_url = f'ws://localhost:18081/ws/{session_id}'
        async with websockets.connect(ws_url) as ws:
            tool_call = {
                'type': 'tool_call',
                'tool_name': 'file_read',
                'input': {'path': '/test/file.txt'}
            }
            
            await ws.send(json.dumps(tool_call))
            response = await ws.recv()
            data = json.loads(response)
            
            assert data['type'] == 'tool_result'
            assert data['tool_name'] == 'file_read'
            assert 'Mock file content' in data['result']
    
    async def test_multiple_tool_calls(self, mock_server):
        """Test multiple tool calls in sequence."""
        # Create session
        async with ClientSession() as session:
            async with session.post('http://localhost:18080/sessions_spawn') as resp:
                data = await resp.json()
                session_id = data['session_id']
        
        # Execute multiple tools
        ws_url = f'ws://localhost:18081/ws/{session_id}'
        async with websockets.connect(ws_url) as ws:
            tools = [
                {'type': 'tool_call', 'tool_name': 'file_read', 'input': {'path': '/a.txt'}},
                {'type': 'tool_call', 'tool_name': 'git_tool', 'input': {'command': 'status'}},
                {'type': 'tool_call', 'tool_name': 'file_read', 'input': {'path': '/b.txt'}},
            ]
            
            for tool in tools:
                await ws.send(json.dumps(tool))
                response = await ws.recv()
                data = json.loads(response)
                
                assert data['type'] == 'tool_result'
                assert data['tool_name'] == tool['tool_name']
    
    async def test_session_cleanup(self, mock_server):
        """Test session cleanup after disconnect."""
        # Create session
        async with ClientSession() as session:
            async with session.post('http://localhost:18080/sessions_spawn') as resp:
                data = await resp.json()
                session_id = data['session_id']
        
        # Connect and disconnect
        ws_url = f'ws://localhost:18081/ws/{session_id}'
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({'type': 'ping'}))
            await ws.recv()
        
        # Verify session marked inactive
        session_state = mock_server.get_session(session_id)
        assert session_state is not None
        assert not session_state.active
    
    async def test_connection_timeout(self, mock_server):
        """Test connection timeout handling."""
        # Create session
        async with ClientSession() as session:
            async with session.post('http://localhost:18080/sessions_spawn') as resp:
                data = await resp.json()
                session_id = data['session_id']
        
        # Connect with timeout
        ws_url = f'ws://localhost:18081/ws/{session_id}'
        async with websockets.connect(ws_url) as ws:
            # Send message and wait with timeout
            await ws.send(json.dumps({'type': 'ping'}))
            
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(response)
                assert data['type'] == 'pong'
            except asyncio.TimeoutError:
                pytest.fail("WebSocket response timeout")
    
    async def test_invalid_session_id(self, mock_server):
        """Test connection with invalid session_id."""
        ws_url = 'ws://localhost:18081/ws/invalid-session-id'
        
        with pytest.raises(websockets.exceptions.ConnectionClosedError):
            async with websockets.connect(ws_url) as ws:
                await ws.send(json.dumps({'type': 'ping'}))
                await ws.recv()


@pytest.mark.asyncio
class TestConcurrentSessions:
    """Test concurrent session handling."""
    
    async def test_multiple_sessions_parallel(self, mock_server):
        """Test multiple sessions running in parallel."""
        # Create multiple sessions
        session_ids = []
        async with ClientSession() as session:
            for _ in range(3):
                async with session.post('http://localhost:18080/sessions_spawn') as resp:
                    data = await resp.json()
                    session_ids.append(data['session_id'])
        
        # Connect all sessions in parallel
        async def session_task(session_id):
            ws_url = f'ws://localhost:18081/ws/{session_id}'
            async with websockets.connect(ws_url) as ws:
                await ws.send(json.dumps({'type': 'ping'}))
                response = await ws.recv()
                data = json.loads(response)
                return data['type'] == 'pong'
        
        results = await asyncio.gather(*[session_task(sid) for sid in session_ids])
        assert all(results)
    
    async def test_session_isolation(self, mock_server):
        """Test that sessions are isolated from each other."""
        # Create two sessions
        async with ClientSession() as session:
            async with session.post('http://localhost:18080/sessions_spawn') as resp:
                data1 = await resp.json()
                session_id1 = data1['session_id']
            
            async with session.post('http://localhost:18080/sessions_spawn') as resp:
                data2 = await resp.json()
                session_id2 = data2['session_id']
        
        # Send different messages to each
        ws_url1 = f'ws://localhost:18081/ws/{session_id1}'
        ws_url2 = f'ws://localhost:18081/ws/{session_id2}'
        
        async with websockets.connect(ws_url1) as ws1, websockets.connect(ws_url2) as ws2:
            # Session 1 message
            await ws1.send(json.dumps({'type': 'test', 'data': 'session1'}))
            resp1 = await ws1.recv()
            
            # Session 2 message
            await ws2.send(json.dumps({'type': 'test', 'data': 'session2'}))
            resp2 = await ws2.recv()
            
            data1 = json.loads(resp1)
            data2 = json.loads(resp2)
            
            # Verify isolation
            assert data1['data']['data'] == 'session1'
            assert data2['data']['data'] == 'session2'
        
        # Verify separate message histories
        state1 = mock_server.get_session(session_id1)
        state2 = mock_server.get_session(session_id2)
        
        assert len(state1.messages) == 1
        assert len(state2.messages) == 1
        assert state1.messages[0]['data'] == 'session1'
        assert state2.messages[0]['data'] == 'session2'
