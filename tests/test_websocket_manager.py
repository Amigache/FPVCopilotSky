"""Unit tests for the optimised WebSocketManager.

Covers the deduplication cache, concurrent-send behaviour, cache-clear on
new connection, and error handling introduced as part of issue #30.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.websocket_manager import WebSocketManager


def _make_ws(*, fail=False):
    """Return a mock WebSocket whose send_text either succeeds or raises."""
    ws = MagicMock()
    if fail:
        ws.send_text = AsyncMock(side_effect=RuntimeError("client gone"))
    else:
        ws.send_text = AsyncMock()
    return ws


class TestBroadcastDedup:
    """Payload deduplication — identical payloads are not re-sent."""

    async def test_first_broadcast_always_sends(self):
        mgr = WebSocketManager()
        ws = _make_ws()
        mgr.active_connections.append(ws)

        await mgr.broadcast("status", {"ok": True})

        ws.send_text.assert_awaited_once()

    async def test_duplicate_payload_skipped(self):
        mgr = WebSocketManager()
        ws = _make_ws()
        mgr.active_connections.append(ws)

        await mgr.broadcast("status", {"ok": True})
        await mgr.broadcast("status", {"ok": True})  # identical — should be skipped

        assert ws.send_text.await_count == 1

    async def test_changed_payload_sends_again(self):
        mgr = WebSocketManager()
        ws = _make_ws()
        mgr.active_connections.append(ws)

        await mgr.broadcast("status", {"ok": True})
        await mgr.broadcast("status", {"ok": False})  # different — must go through

        assert ws.send_text.await_count == 2

    async def test_different_message_types_independent_cache(self):
        mgr = WebSocketManager()
        ws = _make_ws()
        mgr.active_connections.append(ws)

        await mgr.broadcast("telemetry", {"lat": 1.0})
        await mgr.broadcast("telemetry", {"lat": 1.0})  # deduped
        await mgr.broadcast("video_status", {"lat": 1.0})  # different type — sent

        assert ws.send_text.await_count == 2


class TestCacheClearOnConnect:
    """New connection must reset cache so the joining client gets a fresh burst."""

    async def test_connect_clears_dedup_cache(self):
        mgr = WebSocketManager()
        ws1 = _make_ws()
        mgr.active_connections.append(ws1)

        # Prime the cache
        await mgr.broadcast("status", {"v": 1})
        assert ws1.send_text.await_count == 1

        # Second broadcast with same payload — deduped
        await mgr.broadcast("status", {"v": 1})
        assert ws1.send_text.await_count == 1

        # A new client connects — cache must be cleared
        ws2 = MagicMock()
        ws2.accept = AsyncMock()
        ws2.send_text = AsyncMock()
        await mgr.connect(ws2)

        # Same payload again — must go through because cache was cleared
        await mgr.broadcast("status", {"v": 1})
        assert ws1.send_text.await_count == 2
        assert ws2.send_text.await_count == 1


class TestConcurrentSend:
    """All connected clients receive the message in one gather call."""

    async def test_multiple_clients_all_receive(self):
        mgr = WebSocketManager()
        clients = [_make_ws() for _ in range(3)]
        mgr.active_connections.extend(clients)

        await mgr.broadcast("telemetry", {"lat": 10.0})

        for c in clients:
            c.send_text.assert_awaited_once()
            sent = json.loads(c.send_text.await_args.args[0])
            assert sent == {"type": "telemetry", "data": {"lat": 10.0}}

    async def test_json_serialised_once(self):
        """Serialisation should happen once regardless of client count."""
        mgr = WebSocketManager()
        clients = [_make_ws() for _ in range(4)]
        mgr.active_connections.extend(clients)

        with patch("app.services.websocket_manager.json.dumps", wraps=json.dumps) as mock_dumps:
            await mgr.broadcast("telemetry", {"x": 1})

        assert mock_dumps.call_count == 1


class TestFailedClientRemoval:
    """Clients that throw during send_text are removed from active_connections."""

    async def test_failing_client_is_removed(self):
        mgr = WebSocketManager()
        good = _make_ws()
        bad = _make_ws(fail=True)
        mgr.active_connections.extend([good, bad])

        await mgr.broadcast("status", {"v": 1})

        assert good in mgr.active_connections
        assert bad not in mgr.active_connections
        good.send_text.assert_awaited_once()


class TestNoClientsEarlyReturn:
    """broadcast() must be a no-op when no clients are connected."""

    async def test_no_clients_skips_serialisation(self):
        mgr = WebSocketManager()
        with patch("app.services.websocket_manager.json.dumps", wraps=json.dumps) as mock_dumps:
            await mgr.broadcast("status", {"v": 1})
        mock_dumps.assert_not_called()
