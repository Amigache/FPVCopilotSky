"""
WebSocket Manager
Manages WebSocket connections and broadcasts messages to all clients
"""

import json
import logging
from typing import List, Dict, Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    @property
    def has_clients(self) -> bool:
        """Check if there are any connected clients (used to skip processing when idle)"""
        return len(self.active_connections) > 0

    @property
    def client_count(self) -> int:
        """Get the number of connected clients"""
        return len(self.active_connections)

    async def connect(self, websocket: WebSocket):
        """Accept and register a new WebSocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket client connected", extra={"total_clients": len(self.active_connections)})

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection"""
        try:
            self.active_connections.remove(websocket)
            logger.info("WebSocket client disconnected", extra={"total_clients": len(self.active_connections)})
        except ValueError:
            pass

    async def broadcast(self, message_type: str, data: Dict[str, Any]):
        """
        Broadcast a message to all connected clients

        Args:
            message_type: Type of message (e.g., 'telemetry', 'status', 'video')
            data: Message data
        """
        if not self.active_connections:
            return

        message = json.dumps({"type": message_type, "data": data})

        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.warning("Error sending to WebSocket client", extra={"error": str(e)})
                disconnected.append(connection)

        # Remove disconnected clients
        for connection in disconnected:
            self.disconnect(connection)


# Global instance
websocket_manager = WebSocketManager()
