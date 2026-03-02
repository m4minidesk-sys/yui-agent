"""Mock AgentCore WebSocket Server for sessions_spawn testing.

Provides minimal WebSocket server that simulates AgentCore sessions_spawn behavior:
- POST /sessions_spawn → returns session_id
- WebSocket /ws/{session_id} → bidirectional message handling
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import websockets
from aiohttp import web


@dataclass
class SessionState:
    """State for a single AgentCore session."""
    session_id: str
    messages: List[Dict] = field(default_factory=list)
    websocket: Optional[websockets.WebSocketServerProtocol] = None
    active: bool = True


class MockAgentCoreWSServer:
    """Mock AgentCore server with WebSocket support."""
    
    def __init__(self, http_port: int = 8080, ws_port: int = 8081):
        self.http_port = http_port
        self.ws_port = ws_port
        self.sessions: Dict[str, SessionState] = {}
        self.http_app = web.Application()
        self.http_runner: Optional[web.AppRunner] = None
        self.ws_server = None
        
        # Setup HTTP routes
        self.http_app.router.add_post('/sessions_spawn', self.handle_sessions_spawn)
    
    async def handle_sessions_spawn(self, request: web.Request) -> web.Response:
        """Handle POST /sessions_spawn - create new session."""
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = SessionState(session_id=session_id)
        
        return web.json_response({
            'session_id': session_id,
            'ws_url': f'ws://localhost:{self.ws_port}/ws/{session_id}'
        })
    
    async def handle_websocket(self, websocket: websockets.WebSocketServerProtocol, path: str):
        """Handle WebSocket connections for /ws/{session_id}."""
        # Extract session_id from path
        parts = path.strip('/').split('/')
        if len(parts) != 2 or parts[0] != 'ws':
            await websocket.close(code=1008, reason="Invalid path")
            return
        
        session_id = parts[1]
        session = self.sessions.get(session_id)
        
        if not session:
            await websocket.close(code=1008, reason="Session not found")
            return
        
        session.websocket = websocket
        
        try:
            async for message in websocket:
                data = json.loads(message)
                session.messages.append(data)
                
                # Echo response with tool execution simulation
                response = await self._process_message(session_id, data)
                await websocket.send(json.dumps(response))
        
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            session.active = False
            session.websocket = None
    
    async def _process_message(self, session_id: str, message: Dict) -> Dict:
        """Process incoming message and generate response."""
        msg_type = message.get('type')
        
        if msg_type == 'tool_call':
            tool_name = message.get('tool_name')
            tool_input = message.get('input', {})
            
            # Simulate tool execution
            if tool_name == 'file_read':
                return {
                    'type': 'tool_result',
                    'tool_name': tool_name,
                    'result': f"Mock file content for {tool_input.get('path', 'unknown')}"
                }
            elif tool_name == 'git_tool':
                return {
                    'type': 'tool_result',
                    'tool_name': tool_name,
                    'result': "Mock git status output"
                }
            else:
                return {
                    'type': 'tool_result',
                    'tool_name': tool_name,
                    'result': f"Mock result for {tool_name}"
                }
        
        elif msg_type == 'ping':
            return {'type': 'pong'}
        
        else:
            return {'type': 'echo', 'data': message}
    
    async def start(self):
        """Start both HTTP and WebSocket servers."""
        # Start HTTP server
        self.http_runner = web.AppRunner(self.http_app)
        await self.http_runner.setup()
        site = web.TCPSite(self.http_runner, 'localhost', self.http_port)
        await site.start()
        
        # Start WebSocket server
        self.ws_server = await websockets.serve(
            self.handle_websocket,
            'localhost',
            self.ws_port
        )
    
    async def stop(self):
        """Stop both servers."""
        if self.ws_server:
            self.ws_server.close()
            await self.ws_server.wait_closed()
        
        if self.http_runner:
            await self.http_runner.cleanup()
    
    def get_session(self, session_id: str) -> Optional[SessionState]:
        """Get session state for testing."""
        return self.sessions.get(session_id)
