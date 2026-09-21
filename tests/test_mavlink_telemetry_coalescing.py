"""T2/T3: telemetry WebSocket coalescing in MAVLinkBridge.

Reader threads must only flag a dirty event; a dedicated thread performs the
snapshot + broadcast at a bounded rate so the serial parser never blocks on
deepcopy/JSON for every incoming message.
"""

import threading
import time
from unittest.mock import MagicMock

from app.services.mavlink_bridge import MAVLinkBridge


def make_bridge():
    return MAVLinkBridge(websocket_manager=MagicMock(), event_loop=MagicMock())


def test_mark_telemetry_dirty_sets_event():
    bridge = make_bridge()
    assert not bridge._telemetry_dirty.is_set()

    bridge._mark_telemetry_dirty()

    assert bridge._telemetry_dirty.is_set()


def test_processing_message_marks_dirty_without_broadcasting(monkeypatch):
    bridge = make_bridge()
    bridge.connected = True
    bridge._telemetry_dirty.clear()

    broadcast = MagicMock()
    monkeypatch.setattr(bridge, "_broadcast_telemetry", broadcast)

    msg = MagicMock()
    msg.get_type.return_value = "ATTITUDE"
    msg.roll = 1.0
    msg.pitch = 2.0
    msg.yaw = 3.0

    bridge._process_telemetry(msg)

    broadcast.assert_not_called()
    assert bridge._telemetry_dirty.is_set()


def test_broadcast_loop_emits_on_dirty(monkeypatch):
    bridge = make_bridge()
    bridge.running = True
    bridge.telemetry_broadcast_interval = 0.01

    calls = []

    def fake_broadcast():
        calls.append(1)

    monkeypatch.setattr(bridge, "_broadcast_telemetry", fake_broadcast)

    loop = threading.Thread(target=bridge._telemetry_broadcast_loop, daemon=True)
    loop.start()
    try:
        bridge._mark_telemetry_dirty()
        deadline = time.time() + 1.0
        while not calls and time.time() < deadline:
            time.sleep(0.01)
    finally:
        bridge.running = False
        bridge._telemetry_dirty.set()
        loop.join(timeout=1)

    assert calls, "broadcaster should emit when telemetry is dirty"
