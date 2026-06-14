"""
WebSocket Manager
Manages WebSocket connections and broadcasts messages to all clients
"""

import asyncio
import json
import logging
from typing import Any, Dict, List

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        # Deduplication cache: last serialised payload per message type.
        # Cleared when a new client connects so they always receive a fresh burst.
        self._last_payloads: Dict[str, str] = {}

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
        # Clear dedup cache so the new client receives a complete state refresh
        # on the very next broadcast tick.
        self._last_payloads.clear()
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
        Broadcast a message to all connected clients.

        Optimisations:
        - Returns immediately when no clients are connected.
        - Serialises JSON exactly once regardless of client count.
        - Skips send when the payload is identical to the last one for this
          message type (deduplication).  Cache is cleared whenever a new
          client connects so they always get a full refresh.
        - Sends to all clients concurrently via asyncio.gather().

        Args:
            message_type: Type of message (e.g., 'telemetry', 'status', 'video')
            data: Message data
        """
        if not self.active_connections:
            return

        # Serialise once — reused for every connected client.
        message = json.dumps({"type": message_type, "data": data})

        # Skip if nothing changed since the last broadcast for this type.
        if self._last_payloads.get(message_type) == message:
            return
        self._last_payloads[message_type] = message

        async def _send_safe(connection: WebSocket):
            try:
                await connection.send_text(message)
                return None
            except Exception as e:
                logger.warning("Error sending to WebSocket client", extra={"error": str(e)})
                return connection

        # Snapshot the list before awaiting to avoid mutation during iteration.
        results = await asyncio.gather(*(_send_safe(c) for c in list(self.active_connections)))

        # Remove any clients that failed during this broadcast.
        for failed in results:
            if failed is not None:
                self.disconnect(failed)


# Global instance
websocket_manager = WebSocketManager()
