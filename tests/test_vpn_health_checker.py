"""
Tests for VPNHealthChecker — FASE 3

Covers: initialization, VPN type detection, health checks,
recovery polling, ping helpers, and singleton accessor.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from app.services.vpn_health_checker import (
    VPNHealthChecker,
    get_vpn_health_checker,
    VPN_TYPE_NONE,
    VPN_TYPE_TAILSCALE,
    VPN_TYPE_WIREGUARD,
    VPN_TYPE_OPENVPN,
    VPN_TYPE_UNKNOWN,
    HEALTHY_RTT_MS,
    POLL_INTERVAL,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_checker(**kwargs) -> VPNHealthChecker:
    """Create a VPNHealthChecker with optional pre-set attributes."""
    checker = VPNHealthChecker()
    for k, v in kwargs.items():
        setattr(checker, k, v)
    return checker


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────


class TestSingleton:
    def test_returns_same_instance(self):
        """get_vpn_health_checker() must always return the same object."""
        import app.services.vpn_health_checker as mod

        mod._vpn_health_checker = None  # reset
        a = get_vpn_health_checker()
        b = get_vpn_health_checker()
        assert a is b

    def test_creates_instance_if_none(self):
        """Returns a fresh VPNHealthChecker when global is None."""
        import app.services.vpn_health_checker as mod

        mod._vpn_health_checker = None
        checker = get_vpn_health_checker()
        assert isinstance(checker, VPNHealthChecker)


# ─────────────────────────────────────────────────────────────────────────────
# Initialization
# ─────────────────────────────────────────────────────────────────────────────


class TestInitialize:
    @pytest.mark.asyncio
    async def test_initialize_no_vpn(self):
        """When no VPN is detected, initialize() returns False."""
        checker = VPNHealthChecker()
        with patch.object(checker, "_detect_vpn_type", new=AsyncMock(return_value=VPN_TYPE_NONE)):
            result = await checker.initialize()
        assert result is False
        assert checker._vpn_type == VPN_TYPE_NONE
        assert checker._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_tailscale_with_peer(self):
        """Tailscale with peer IP — returns True."""
        checker = VPNHealthChecker()
        with (
            patch.object(checker, "_detect_vpn_type", new=AsyncMock(return_value=VPN_TYPE_TAILSCALE)),
            patch.object(checker, "_get_peer_ip", new=AsyncMock(return_value="100.64.1.1")),
        ):
            result = await checker.initialize()
        assert result is True
        assert checker._vpn_type == VPN_TYPE_TAILSCALE
        assert checker._peer_ip == "100.64.1.1"
        assert checker._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_wireguard_no_peer(self):
        """WireGuard detected but no reachable peer — returns True (VPN present)."""
        checker = VPNHealthChecker()
        with (
            patch.object(checker, "_detect_vpn_type", new=AsyncMock(return_value=VPN_TYPE_WIREGUARD)),
            patch.object(checker, "_get_peer_ip", new=AsyncMock(return_value=None)),
        ):
            result = await checker.initialize()
        assert result is True
        assert checker._peer_ip is None
        assert checker._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self):
        """Second call to initialize() is safe and re-runs."""
        checker = _make_checker(_initialized=True, _vpn_type=VPN_TYPE_TAILSCALE)
        with (
            patch.object(checker, "_detect_vpn_type", new=AsyncMock(return_value=VPN_TYPE_TAILSCALE)),
            patch.object(checker, "_get_peer_ip", new=AsyncMock(return_value="100.64.1.2")),
        ):
            result = await checker.initialize()
        assert result is True


# ─────────────────────────────────────────────────────────────────────────────
# check_vpn_health
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckVpnHealth:
    @pytest.mark.asyncio
    async def test_no_vpn_always_healthy(self):
        """When VPN type is NONE, check_vpn_health() reports healthy=True."""
        checker = _make_checker(
            _initialized=True,
            _vpn_type=VPN_TYPE_NONE,
            _peer_ip=None,
        )
        result = await checker.check_vpn_health()
        assert result["healthy"] is True
        assert result["vpn_type"] == VPN_TYPE_NONE
        assert result["peer_ip"] is None
        assert "No VPN" in result["message"]

    @pytest.mark.asyncio
    async def test_healthy_with_peer_ping(self):
        """Interface UP + successful ping → healthy=True."""
        checker = _make_checker(
            _initialized=True,
            _vpn_type=VPN_TYPE_TAILSCALE,
            _peer_ip="100.64.0.1",
        )
        with (
            patch.object(checker, "_check_interface_up", new=AsyncMock(return_value=True)),
            patch.object(checker, "_ping", new=AsyncMock(return_value=12.3)),
        ):
            result = await checker.check_vpn_health()

        assert result["healthy"] is True
        assert result["vpn_type"] == VPN_TYPE_TAILSCALE
        assert result["peer_ip"] == "100.64.0.1"
        assert result["rtt_ms"] == 12.3
        assert result["interface_up"] is True

    @pytest.mark.asyncio
    async def test_unhealthy_interface_down(self):
        """Interface DOWN → healthy=False regardless of ping."""
        checker = _make_checker(
            _initialized=True,
            _vpn_type=VPN_TYPE_WIREGUARD,
            _peer_ip="10.0.0.1",
        )
        with (
            patch.object(checker, "_check_interface_up", new=AsyncMock(return_value=False)),
            patch.object(checker, "_ping", new=AsyncMock()) as mock_ping,
        ):
            result = await checker.check_vpn_health()

        assert result["healthy"] is False
        assert result["interface_up"] is False
        mock_ping.assert_not_called()

    @pytest.mark.asyncio
    async def test_unhealthy_ping_fails(self):
        """Interface UP but ping times out → healthy=False."""
        checker = _make_checker(
            _initialized=True,
            _vpn_type=VPN_TYPE_TAILSCALE,
            _peer_ip="100.64.0.1",
        )
        with (
            patch.object(checker, "_check_interface_up", new=AsyncMock(return_value=True)),
            patch.object(checker, "_ping", new=AsyncMock(return_value=None)),
        ):
            result = await checker.check_vpn_health()

        assert result["healthy"] is False
        assert result["rtt_ms"] is None

    @pytest.mark.asyncio
    async def test_interface_up_no_peer_is_healthy(self):
        """Interface UP with no peer IP → treated as healthy (interface-only check)."""
        checker = _make_checker(
            _initialized=True,
            _vpn_type=VPN_TYPE_WIREGUARD,
            _peer_ip=None,
        )
        with patch.object(checker, "_check_interface_up", new=AsyncMock(return_value=True)):
            result = await checker.check_vpn_health()

        assert result["healthy"] is True
        assert result["rtt_ms"] is None

    @pytest.mark.asyncio
    async def test_calls_initialize_if_not_initialized(self):
        """check_vpn_health() calls initialize() when _initialized=False."""
        checker = VPNHealthChecker()
        with patch.object(checker, "initialize", new=AsyncMock()) as mock_init:
            # Set VPN to NONE after init so the check short-circuits
            async def fake_init():
                checker._initialized = True
                checker._vpn_type = VPN_TYPE_NONE

            mock_init.side_effect = fake_init
            result = await checker.check_vpn_health()
        mock_init.assert_called_once()
        assert result["healthy"] is True

    @pytest.mark.asyncio
    async def test_rtt_rounded_to_one_decimal(self):
        """RTT should be returned rounded to 1 decimal place."""
        checker = _make_checker(
            _initialized=True,
            _vpn_type=VPN_TYPE_TAILSCALE,
            _peer_ip="100.64.0.1",
        )
        with (
            patch.object(checker, "_check_interface_up", new=AsyncMock(return_value=True)),
            patch.object(checker, "_ping", new=AsyncMock(return_value=15.678)),
        ):
            result = await checker.check_vpn_health()
        assert result["rtt_ms"] == 15.7


# ─────────────────────────────────────────────────────────────────────────────
# wait_for_vpn_recovery
# ─────────────────────────────────────────────────────────────────────────────


class TestWaitForVpnRecovery:
    @pytest.mark.asyncio
    async def test_no_vpn_returns_immediately(self):
        """VPN_TYPE_NONE → True immediately without polling."""
        checker = _make_checker(
            _initialized=True,
            _vpn_type=VPN_TYPE_NONE,
        )
        result = await checker.wait_for_vpn_recovery(timeout_s=5.0)
        assert result is True

    @pytest.mark.asyncio
    async def test_recovers_on_first_poll(self):
        """Returns True on the very first healthy poll."""
        checker = _make_checker(
            _initialized=True,
            _vpn_type=VPN_TYPE_TAILSCALE,
            _peer_ip="100.64.0.1",
        )
        healthy_result = {
            "healthy": True,
            "vpn_type": VPN_TYPE_TAILSCALE,
            "peer_ip": "100.64.0.1",
            "rtt_ms": 8.0,
            "interface_up": True,
            "message": "OK",
        }
        with (
            patch.object(checker, "check_vpn_health", new=AsyncMock(return_value=healthy_result)),
            patch("app.services.vpn_health_checker.asyncio.sleep", new=AsyncMock()),
        ):
            result = await checker.wait_for_vpn_recovery(timeout_s=10.0)

        assert result is True

    @pytest.mark.asyncio
    async def test_recovers_after_retries(self):
        """Returns True after failing twice then succeeding."""
        checker = _make_checker(
            _initialized=True,
            _vpn_type=VPN_TYPE_TAILSCALE,
            _peer_ip="100.64.0.1",
        )
        unhealthy = {
            "healthy": False,
            "vpn_type": VPN_TYPE_TAILSCALE,
            "peer_ip": "100.64.0.1",
            "rtt_ms": None,
            "interface_up": False,
            "message": "down",
        }
        healthy = {
            "healthy": True,
            "vpn_type": VPN_TYPE_TAILSCALE,
            "peer_ip": "100.64.0.1",
            "rtt_ms": 5.0,
            "interface_up": True,
            "message": "OK",
        }

        with (
            patch.object(checker, "check_vpn_health", new=AsyncMock(side_effect=[unhealthy, unhealthy, healthy])),
            patch("app.services.vpn_health_checker.asyncio.sleep", new=AsyncMock()),
        ):
            result = await checker.wait_for_vpn_recovery(timeout_s=30.0)

        assert result is True

    @pytest.mark.asyncio
    async def test_timeout_returns_false(self):
        """Returns False when VPN never recovers within timeout."""
        checker = _make_checker(
            _initialized=True,
            _vpn_type=VPN_TYPE_TAILSCALE,
            _peer_ip="100.64.0.1",
        )
        unhealthy = {
            "healthy": False,
            "vpn_type": VPN_TYPE_TAILSCALE,
            "peer_ip": "100.64.0.1",
            "rtt_ms": None,
            "interface_up": False,
            "message": "down",
        }

        with (
            patch.object(checker, "check_vpn_health", new=AsyncMock(return_value=unhealthy)),
            patch("app.services.vpn_health_checker.asyncio.sleep", new=AsyncMock()),
            patch("app.services.vpn_health_checker.time") as mock_time,
        ):
            # Simulate monotonic clock advancing past timeout on the 3rd call
            mono_values = [0.0, 0.5, 1.0, 2.0, 3.0, 5.0, 6.0]
            mock_time.monotonic.side_effect = mono_values
            result = await checker.wait_for_vpn_recovery(timeout_s=5.0)

        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# get_peer_ip
# ─────────────────────────────────────────────────────────────────────────────


class TestGetPeerIp:
    @pytest.mark.asyncio
    async def test_returns_cached_peer_ip(self):
        """Returns cached peer IP without re-detecting."""
        checker = _make_checker(
            _initialized=True,
            _vpn_type=VPN_TYPE_TAILSCALE,
            _peer_ip="100.100.1.1",
        )
        result = await checker.get_peer_ip()
        assert result == "100.100.1.1"

    @pytest.mark.asyncio
    async def test_detects_peer_when_none(self):
        """Calls _get_peer_ip when cached peer is None."""
        checker = _make_checker(
            _initialized=True,
            _vpn_type=VPN_TYPE_TAILSCALE,
            _peer_ip=None,
        )
        with patch.object(checker, "_get_peer_ip", new=AsyncMock(return_value="100.64.2.2")) as mock_get:
            result = await checker.get_peer_ip()
        mock_get.assert_called_once_with(VPN_TYPE_TAILSCALE)
        assert result == "100.64.2.2"
