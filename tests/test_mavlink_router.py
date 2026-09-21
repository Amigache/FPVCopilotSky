"""Unit tests for MAVLinkRouter (no real sockets or hardware)."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.mavlink_router import MAVLinkRouter, OutputConfig, OutputState, OutputType


def make_router():
    """Create a router with an empty preferences config (no auto-start)."""
    with patch("app.services.preferences.get_preferences") as get_prefs:
        get_prefs.return_value.get_router_outputs.return_value = []
        router = MAVLinkRouter()
    # Keep _save_config from touching preferences in subsequent calls.
    router._save_config = MagicMock()
    return router


def cfg(output_id="o1", type_=OutputType.TCP_SERVER, **kwargs):
    return OutputConfig(id=output_id, type=type_, host="127.0.0.1", port=5760, auto_start=False, **kwargs)


class TestOutputManagement:
    def test_add_output(self):
        router = make_router()
        ok, msg = router.add_output(cfg())
        assert ok is True
        assert "o1" in router.outputs

    def test_add_duplicate_output(self):
        router = make_router()
        router.add_output(cfg())
        ok, msg = router.add_output(cfg())
        assert ok is False
        assert "already exists" in msg

    def test_remove_output(self):
        router = make_router()
        router.add_output(cfg())
        ok, msg = router.remove_output("o1")
        assert ok is True
        assert "o1" not in router.outputs

    def test_remove_missing_output(self):
        router = make_router()
        ok, msg = router.remove_output("nope")
        assert ok is False
        assert "not found" in msg

    def test_update_output(self):
        router = make_router()
        router.add_output(cfg())
        ok, _ = router.update_output("o1", {"host": "0.0.0.0", "port": 14550, "name": "gcs"})
        assert ok is True
        state = router.outputs["o1"]
        assert state.config.host == "0.0.0.0"
        assert state.config.port == 14550
        assert state.config.name == "gcs"

    def test_update_output_type_from_string(self):
        router = make_router()
        router.add_output(cfg())
        router.update_output("o1", {"type": "udp"})
        assert router.outputs["o1"].config.type == OutputType.UDP

    def test_update_missing_output(self):
        router = make_router()
        ok, msg = router.update_output("nope", {"port": 1})
        assert ok is False
        assert "not found" in msg

    def test_get_outputs_list(self):
        router = make_router()
        router.add_output(cfg())
        outputs = router.get_outputs_list()
        assert len(outputs) == 1
        assert outputs[0]["id"] == "o1"

    def test_get_status_counts_running(self):
        router = make_router()
        router.add_output(cfg("a"))
        router.outputs["a"].running = True
        router.add_output(cfg("b"))
        status = router.get_status()
        assert status["total_outputs"] == 2
        assert status["active_outputs"] == 1


class TestTypeValue:
    def test_enum_and_string(self):
        router = make_router()
        assert router._get_type_value(OutputType.UDP) == "udp"
        assert router._get_type_value("tcp_client") == "tcp_client"


class TestForwardToOutputs:
    def _state(self, type_, **kwargs):
        return OutputState(config=cfg(type_=type_), running=True, **kwargs)

    def test_tcp_server_forwards_to_clients(self):
        router = make_router()
        client = MagicMock()
        router.outputs["srv"] = self._state(OutputType.TCP_SERVER, clients=[client])
        router.forward_to_outputs(b"DATA")
        client.sendall.assert_called_once_with(b"DATA")

    def test_tcp_client_forwards_to_socket(self):
        router = make_router()
        sock = MagicMock()
        router.outputs["cli"] = self._state(OutputType.TCP_CLIENT, sock=sock)
        router.forward_to_outputs(b"DATA")
        sock.sendall.assert_called_once_with(b"DATA")

    def test_udp_forwards_via_sendto(self):
        router = make_router()
        sock = MagicMock()
        router.outputs["udp"] = self._state(OutputType.UDP, sock=sock)
        router.forward_to_outputs(b"DATA")
        sock.sendto.assert_called_once_with(b"DATA", ("127.0.0.1", 5760))

    def test_stopped_output_is_skipped(self):
        router = make_router()
        client = MagicMock()
        state = self._state(OutputType.TCP_SERVER, clients=[client])
        state.running = False
        router.outputs["srv"] = state
        router.forward_to_outputs(b"DATA")
        client.sendall.assert_not_called()

    def test_dead_tcp_client_is_pruned(self):
        router = make_router()
        dead = MagicMock()
        dead.sendall.side_effect = OSError("broken pipe")
        router.outputs["srv"] = self._state(OutputType.TCP_SERVER, clients=[dead])
        router.forward_to_outputs(b"DATA")
        assert router.outputs["srv"].clients == []
        assert router.outputs["srv"].stats["errors"] >= 0


class TestStatusCallback:
    def test_callback_is_invoked(self):
        router = make_router()
        called = []
        router.set_status_callback(lambda: called.append(True))
        router.add_output(cfg())
        router.remove_output("o1")
        assert called  # remove_output notifies

    def test_callback_exception_is_swallowed(self):
        router = make_router()

        def boom():
            raise RuntimeError("nope")

        router.set_status_callback(boom)
        router.add_output(cfg())
        router.remove_output("o1")  # must not raise


class TestShutdown:
    def test_shutdown_stops_running_outputs(self):
        router = make_router()
        state = OutputState(config=cfg(type_=OutputType.UDP), running=True, sock=MagicMock())
        router.outputs["udp"] = state
        router.shutdown()
        assert router.running is False
        assert state.running is False


class TestRestart:
    def test_restart_without_running_outputs(self):
        router = make_router()
        router.add_output(cfg())
        ok, msg = router.restart()
        assert ok is True
        assert "No running" in msg

    def test_restart_restarts_running_outputs(self, monkeypatch):
        router = make_router()
        router.add_output(cfg("a"))
        router.outputs["a"].running = True
        called = []

        def fake_restart(output_id):
            called.append(output_id)
            return True, "ok"

        monkeypatch.setattr(router, "restart_output", fake_restart)
        ok, msg = router.restart()
        assert ok is True
        assert called == ["a"]
        assert "1/1" in msg
