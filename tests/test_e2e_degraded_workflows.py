"""E2E degraded-network workflow suite for Issue #37.

This suite validates recovery behavior across critical workflows and records
per-scenario recovery timings via pytest record_property.
"""

import time
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
import app.api.routes.network.status as network_status_routes
import app.api.routes.video as video_routes
import app.api.routes.vpn as vpn_routes


@pytest.fixture
def client(mock_api_services):
    """Create a TestClient with mocked services from conftest."""
    return TestClient(app, raise_server_exceptions=False)


def _measure_recovery(request_fn, is_recovered, max_attempts: int = 6, sleep_s: float = 0.02):
    """Execute repeated attempts until recovered and return attempts, elapsed_ms, last response."""
    t0 = time.monotonic()
    last_response = None

    for attempt in range(1, max_attempts + 1):
        last_response = request_fn()
        if is_recovered(last_response):
            elapsed_ms = (time.monotonic() - t0) * 1000
            return attempt, elapsed_ms, last_response
        time.sleep(sleep_s)

    elapsed_ms = (time.monotonic() - t0) * 1000
    return max_attempts, elapsed_ms, last_response


class TestE2EDegradedWorkflows:
    """Critical degraded scenarios: connectivity loss, timeout, failover, reconnection."""

    @pytest.mark.e2e
    def test_scenario_network_status_timeout_then_recovery(self, client, monkeypatch, record_property):
        """Scenario 1: /api/network/status suffers transient timeouts and recovers."""
        state = {"calls": 0}

        async def fake_get_interfaces():
            state["calls"] += 1
            if state["calls"] <= 2:
                raise TimeoutError("simulated interface probe timeout")
            return [
                {
                    "name": "wlan0",
                    "ip_address": "192.168.1.20",
                    "state": "UP",
                    "type": "wifi",
                    "connection": "TestWiFi",
                    "gateway": "192.168.1.1",
                    "metric": 100,
                }
            ]

        async def fake_get_routes():
            return [{"type": "default", "interface": "wlan0", "gateway": "192.168.1.1", "metric": 100}]

        async def fake_detect_modem_interface():
            return None

        async def fake_detect_wifi_interface():
            return "wlan0"

        async def fake_get_modem_info(_iface):
            return {
                "detected": False,
                "connected": False,
                "interface": None,
                "ip_address": None,
                "gateway": None,
            }

        monkeypatch.setattr(network_status_routes, "_get_interfaces", fake_get_interfaces)
        monkeypatch.setattr(network_status_routes, "_get_routes", fake_get_routes)
        monkeypatch.setattr(network_status_routes, "detect_modem_interface", fake_detect_modem_interface)
        monkeypatch.setattr(network_status_routes, "detect_wifi_interface", fake_detect_wifi_interface)
        monkeypatch.setattr(network_status_routes, "_get_modem_info", fake_get_modem_info)
        monkeypatch.setattr(network_status_routes._cache, "get", lambda _key: None)
        monkeypatch.setattr(network_status_routes._cache, "set", lambda _k, _v, ttl=2: None)

        attempts, recovery_ms, response = _measure_recovery(
            request_fn=lambda: client.get("/api/network/status"),
            is_recovered=lambda r: r.status_code == 200,
        )

        assert response is not None
        assert response.status_code == 200
        assert attempts >= 3

        record_property("scenario", "network_status_timeout_then_recovery")
        record_property("degradation_type", "connectivity_loss_timeout")
        record_property("attempts_to_recover", attempts)
        record_property("recovery_ms", round(recovery_ms, 3))
        record_property("scenario_success", True)

    @pytest.mark.e2e
    def test_scenario_failover_priority_timeout_then_recovery(self, client, monkeypatch, record_property):
        """Scenario 2: network failover priority changes fail initially and recover."""
        state = {"failed_add_rounds": 0}

        async def fake_detect_wifi_interface():
            return "wlan0"

        async def fake_detect_modem_interface():
            return "usb0"

        async def fake_get_gateway_for_interface(iface):
            if iface == "wlan0":
                return "192.168.1.1"
            if iface == "usb0":
                return "192.168.8.1"
            return None

        async def fake_run_command(cmd):
            if "add" in cmd:
                # First two rounds: route add fails (timeout/error simulation).
                if state["failed_add_rounds"] < 2:
                    state["failed_add_rounds"] += 1
                    return "", "simulated route timeout", 1
                return "", "", 0
            return "", "", 0

        monkeypatch.setattr(network_status_routes, "detect_wifi_interface", fake_detect_wifi_interface)
        monkeypatch.setattr(network_status_routes, "detect_modem_interface", fake_detect_modem_interface)
        monkeypatch.setattr(network_status_routes, "get_gateway_for_interface", fake_get_gateway_for_interface)
        monkeypatch.setattr(network_status_routes, "run_command", fake_run_command)
        monkeypatch.setattr(network_status_routes._cache, "invalidate", lambda _key: None)

        attempts, recovery_ms, response = _measure_recovery(
            request_fn=lambda: client.post("/api/network/priority", json={"mode": "wifi"}),
            is_recovered=lambda r: r.status_code == 200 and r.json().get("success") is True,
        )

        assert response is not None
        assert response.status_code == 200
        assert response.json().get("success") is True

        record_property("scenario", "failover_priority_timeout_then_recovery")
        record_property("degradation_type", "route_update_timeout")
        record_property("attempts_to_recover", attempts)
        record_property("recovery_ms", round(recovery_ms, 3))
        record_property("scenario_success", True)

    @pytest.mark.e2e
    def test_scenario_stream_start_fails_then_recovers(self, client, mock_api_services, record_property):
        """Scenario 3: stream start fails transiently and later recovers."""
        video_service = mock_api_services["video_service"]
        video_service.start = MagicMock(
            side_effect=[
                {"success": False, "message": "simulated encoder timeout"},
                {"success": False, "message": "simulated pipeline timeout"},
                {"success": True, "message": "stream started"},
            ]
        )

        attempts, recovery_ms, response = _measure_recovery(
            request_fn=lambda: client.post("/api/video/start"),
            is_recovered=lambda r: r.status_code == 200 and r.json().get("success") is True,
        )

        assert response is not None
        assert response.status_code == 200
        assert attempts >= 3

        record_property("scenario", "stream_start_timeout_then_recovery")
        record_property("degradation_type", "stream_recovery")
        record_property("attempts_to_recover", attempts)
        record_property("recovery_ms", round(recovery_ms, 3))
        record_property("scenario_success", True)

    @pytest.mark.e2e
    def test_scenario_vpn_connect_reconnect_after_timeout(self, client, monkeypatch, record_property):
        """Scenario 4: VPN connect initially fails and succeeds on retry."""
        provider = MagicMock()
        provider.connect = MagicMock(
            side_effect=[
                {"success": False, "error": "simulated vpn timeout"},
                {"success": True, "connected": True},
            ]
        )

        monkeypatch.setattr(vpn_routes, "_get_vpn_provider", lambda provider_name=None, lang="en": provider)

        attempts, recovery_ms, response = _measure_recovery(
            request_fn=lambda: client.post("/api/vpn/connect", json={}),
            is_recovered=lambda r: r.status_code == 200 and r.json().get("success") is True,
        )

        assert response is not None
        assert response.status_code == 200
        assert response.json().get("success") is True
        assert attempts >= 2

        record_property("scenario", "vpn_reconnect_after_timeout")
        record_property("degradation_type", "reconnection_timeout")
        record_property("attempts_to_recover", attempts)
        record_property("recovery_ms", round(recovery_ms, 3))
        record_property("scenario_success", True)
