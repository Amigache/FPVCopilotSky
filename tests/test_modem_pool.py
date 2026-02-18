"""
Tests for ModemPool — FASE 1 + FASE 3 VPN integration

Covers: modem registration, select_modem happy/sad paths,
FASE 3 pre/post VPN checks, rollback flow, helper methods,
_is_vpn_health_enabled, _get_vpn_recovery_timeout, get_status.

All subprocess and hardware calls are mocked.
"""

import asyncio
import sys
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch, call
from dataclasses import dataclass, field

from app.services.modem_pool import (
    ModemPool,
    ModemInfo,
    ModemSignalMetrics,
    ModemNetworkMetrics,
    ModemSelectionMode,
    get_modem_pool,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _make_modem(
    interface: str, connected: bool = True, active: bool = False, gateway: str = "10.0.0.1", quality: float = 80.0
) -> ModemInfo:
    return ModemInfo(
        interface=interface,
        ip_address="10.0.0.2",
        gateway=gateway,
        is_connected=connected,
        is_active=active,
        is_healthy=True,
        quality_score=quality,
    )


def _make_pool_with_modems(*interfaces: str, active: str = None) -> ModemPool:
    """Create a ModemPool pre-loaded with modem infos."""
    pool = ModemPool()
    pool._running = True
    for iface in interfaces:
        modem = _make_modem(iface, active=(iface == active))
        pool._modems[iface] = modem
    pool._active_modem = active
    return pool


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────


class TestSingleton:
    def test_returns_same_instance(self):
        import app.services.modem_pool as mod

        mod._modem_pool = None
        a = get_modem_pool()
        b = get_modem_pool()
        assert a is b

    def test_creates_fresh_instance(self):
        import app.services.modem_pool as mod

        mod._modem_pool = None
        pool = get_modem_pool()
        assert isinstance(pool, ModemPool)


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────


class TestModemInfo:
    def test_to_dict_keys(self):
        modem = _make_modem("wwan0")
        d = modem.to_dict()
        for key in ("interface", "ip_address", "gateway", "is_connected", "is_active", "is_healthy", "quality_score"):
            assert key in d

    def test_to_dict_interface(self):
        modem = _make_modem("wwan1")
        assert modem.to_dict()["interface"] == "wwan1"


# ─────────────────────────────────────────────────────────────────────────────
# select_modem — basic
# ─────────────────────────────────────────────────────────────────────────────


class TestSelectModemBasic:
    @pytest.mark.asyncio
    async def test_select_unknown_modem(self):
        """Selecting an unknown interface returns False."""
        pool = _make_pool_with_modems("wwan0")
        with patch.object(pool, "_apply_modem_priority", new=AsyncMock(return_value=True)):
            result = await pool.select_modem("wwan9", reason="manual")
        assert result is False

    @pytest.mark.asyncio
    async def test_select_disconnected_modem(self):
        """Selecting a disconnected modem returns False."""
        pool = _make_pool_with_modems("wwan0")
        pool._modems["wwan0"].is_connected = False
        result = await pool.select_modem("wwan0", reason="manual")
        assert result is False

    @pytest.mark.asyncio
    async def test_select_already_active(self):
        """Selecting the already-active modem returns True without doing anything."""
        pool = _make_pool_with_modems("wwan0", active="wwan0")
        with patch.object(pool, "_apply_modem_priority", new=AsyncMock()) as apm:
            result = await pool.select_modem("wwan0", reason="manual")
        assert result is True
        # No routing change needed
        apm.assert_not_called()

    @pytest.mark.asyncio
    async def test_select_success_no_vpn_check(self):
        """When VPN health check is disabled, select_modem succeeds normally."""
        pool = _make_pool_with_modems("wwan0", "wwan1", active="wwan0")
        with (
            patch.object(pool, "_is_vpn_health_enabled", return_value=False),
            patch.object(pool, "_apply_modem_priority", new=AsyncMock(return_value=True)),
        ):
            result = await pool.select_modem("wwan1", reason="manual")

        assert result is True
        assert pool._active_modem == "wwan1"
        assert pool._modems["wwan1"].is_active is True
        assert pool._modems["wwan0"].is_active is False


# ─────────────────────────────────────────────────────────────────────────────
# select_modem — FASE 3 VPN integration
# ─────────────────────────────────────────────────────────────────────────────


class TestSelectModemVpnIntegration:
    def _make_vpn_result(self, healthy: bool, rtt: float = None) -> dict:
        return {
            "healthy": healthy,
            "vpn_type": "tailscale",
            "peer_ip": "100.64.0.1",
            "rtt_ms": rtt,
            "interface_up": healthy,
            "message": "OK" if healthy else "down",
        }

    @pytest.mark.asyncio
    async def test_vpn_pre_ok_post_recovers_success(self):
        """VPN healthy before and after switch → select_modem returns True."""
        pool = _make_pool_with_modems("wwan0", "wwan1", active="wwan0")
        mock_checker = MagicMock()
        mock_checker.check_vpn_health = AsyncMock(return_value=self._make_vpn_result(True, rtt=8.0))
        mock_checker.wait_for_vpn_recovery = AsyncMock(return_value=True)

        # modem_pool does a local `from app.services.vpn_health_checker import get_vpn_health_checker`
        # so we patch on the source module
        with (
            patch.object(pool, "_is_vpn_health_enabled", return_value=True),
            patch.object(pool, "_get_vpn_recovery_timeout", return_value=15.0),
            patch.object(pool, "_apply_modem_priority", new=AsyncMock(return_value=True)),
            patch("app.services.vpn_health_checker.get_vpn_health_checker", return_value=mock_checker),
        ):
            result = await pool.select_modem("wwan1", reason="auto")

        assert result is True
        assert pool._active_modem == "wwan1"

    @pytest.mark.asyncio
    async def test_vpn_unhealthy_before_switch_proceeds_with_warning(self):
        """VPN unhealthy before switch → still switches (warning only)."""
        pool = _make_pool_with_modems("wwan0", "wwan1", active="wwan0")
        mock_checker = MagicMock()
        mock_checker.check_vpn_health = AsyncMock(return_value=self._make_vpn_result(False))
        mock_checker.wait_for_vpn_recovery = AsyncMock(return_value=True)

        with (
            patch.object(pool, "_is_vpn_health_enabled", return_value=True),
            patch.object(pool, "_get_vpn_recovery_timeout", return_value=15.0),
            patch.object(pool, "_apply_modem_priority", new=AsyncMock(return_value=True)),
            patch("app.services.vpn_health_checker.get_vpn_health_checker", return_value=mock_checker),
        ):
            result = await pool.select_modem("wwan1", reason="manual")

        # Switch still succeeds (pre-check is advisory)
        assert result is True

    @pytest.mark.asyncio
    async def test_vpn_recovery_fails_triggers_rollback(self):
        """VPN doesn't recover post-switch → rollback, select_modem returns False."""
        pool = _make_pool_with_modems("wwan0", "wwan1", active="wwan0")
        mock_checker = MagicMock()
        mock_checker.check_vpn_health = AsyncMock(return_value=self._make_vpn_result(True))
        mock_checker.wait_for_vpn_recovery = AsyncMock(return_value=False)  # never recovers

        with (
            patch.object(pool, "_is_vpn_health_enabled", return_value=True),
            patch.object(pool, "_get_vpn_recovery_timeout", return_value=5.0),
            patch.object(pool, "_apply_modem_priority", new=AsyncMock(return_value=True)),
            patch.object(pool, "_rollback_to_modem", new=AsyncMock()) as rollback,
            patch("app.services.vpn_health_checker.get_vpn_health_checker", return_value=mock_checker),
        ):
            result = await pool.select_modem("wwan1", reason="manual")

        assert result is False
        rollback.assert_called_once_with("wwan0", "wwan1")

    @pytest.mark.asyncio
    async def test_rollback_reason_skips_vpn_check(self):
        """When reason='rollback', VPN check is skipped entirely."""
        pool = _make_pool_with_modems("wwan0", "wwan1", active="wwan1")
        mock_checker = MagicMock()
        mock_checker.check_vpn_health = AsyncMock()  # should not be called
        mock_checker.wait_for_vpn_recovery = AsyncMock()  # should not be called

        with (
            patch.object(pool, "_is_vpn_health_enabled", return_value=True),
            patch.object(pool, "_apply_modem_priority", new=AsyncMock(return_value=True)),
            patch("app.services.vpn_health_checker.get_vpn_health_checker", return_value=mock_checker),
        ):
            result = await pool.select_modem("wwan0", reason="rollback")

        assert result is True
        mock_checker.check_vpn_health.assert_not_called()
        mock_checker.wait_for_vpn_recovery.assert_not_called()

    @pytest.mark.asyncio
    async def test_vpn_check_exception_is_non_fatal(self):
        """An exception in the VPN pre-check is swallowed and switch proceeds."""
        pool = _make_pool_with_modems("wwan0", "wwan1", active="wwan0")

        with (
            patch.object(pool, "_is_vpn_health_enabled", return_value=True),
            patch.object(pool, "_apply_modem_priority", new=AsyncMock(return_value=True)),
            patch("app.services.vpn_health_checker.get_vpn_health_checker", side_effect=RuntimeError("import error")),
        ):
            result = await pool.select_modem("wwan1", reason="manual")

        # Switch should still complete
        assert result is True


# ─────────────────────────────────────────────────────────────────────────────
# _rollback_to_modem
# ─────────────────────────────────────────────────────────────────────────────


class TestRollback:
    @pytest.mark.asyncio
    async def test_rollback_restores_previous(self):
        """_rollback_to_modem restores previous modem as active."""
        pool = _make_pool_with_modems("wwan0", "wwan1", active="wwan1")
        with patch.object(pool, "_apply_modem_priority", new=AsyncMock(return_value=True)):
            await pool._rollback_to_modem("wwan0", "wwan1")

        assert pool._active_modem == "wwan0"
        assert pool._modems["wwan0"].is_active is True
        assert pool._modems["wwan1"].is_active is False

    @pytest.mark.asyncio
    async def test_rollback_disconnected_previous_sets_none(self):
        """If previous modem is disconnected, active modem becomes None."""
        pool = _make_pool_with_modems("wwan0", "wwan1", active="wwan1")
        pool._modems["wwan0"].is_connected = False
        with patch.object(pool, "_apply_modem_priority", new=AsyncMock(return_value=True)):
            await pool._rollback_to_modem("wwan0", "wwan1")

        assert pool._active_modem is None


# ─────────────────────────────────────────────────────────────────────────────
# Preference helpers
# ─────────────────────────────────────────────────────────────────────────────


class TestPreferenceHelpers:
    def test_is_vpn_health_enabled_default_true(self):
        """When preferences_service module is absent, defaults to True."""
        pool = ModemPool()
        # preferences_service module doesn't exist in the codebase yet; the try/except
        # in _is_vpn_health_enabled catches ImportError and returns True.
        # Ensure the module is not in sys.modules so the import actually raises.
        sys.modules.pop("app.services.preferences_service", None)
        result = pool._is_vpn_health_enabled()
        assert result is True

    def test_is_vpn_health_enabled_reads_pref(self):
        """Reads vpn_health_check_enabled from preferences via injected module."""
        pool = ModemPool()
        mock_svc = MagicMock()
        mock_svc.get_all_preferences.return_value = {"network": {"vpn_health_check_enabled": False}}
        mock_module = MagicMock()
        mock_module.get_preferences_service.return_value = mock_svc
        sys.modules["app.services.preferences_service"] = mock_module
        try:
            result = pool._is_vpn_health_enabled()
        finally:
            sys.modules.pop("app.services.preferences_service", None)
        assert result is False

    def test_get_vpn_recovery_timeout_default(self):
        """When preferences_service module is absent, defaults to 15s."""
        pool = ModemPool()
        sys.modules.pop("app.services.preferences_service", None)
        result = pool._get_vpn_recovery_timeout()
        assert result == 15.0

    def test_get_vpn_recovery_timeout_reads_pref(self):
        """Reads vpn_recovery_timeout_s from preferences via injected module."""
        pool = ModemPool()
        mock_svc = MagicMock()
        mock_svc.get_all_preferences.return_value = {"network": {"vpn_recovery_timeout_s": 30}}
        mock_module = MagicMock()
        mock_module.get_preferences_service.return_value = mock_svc
        sys.modules["app.services.preferences_service"] = mock_module
        try:
            result = pool._get_vpn_recovery_timeout()
        finally:
            sys.modules.pop("app.services.preferences_service", None)
        assert result == 30.0


# ─────────────────────────────────────────────────────────────────────────────
# Modem queries
# ─────────────────────────────────────────────────────────────────────────────


class TestModemQueries:
    @pytest.mark.asyncio
    async def test_get_all_modems(self):
        pool = _make_pool_with_modems("wwan0", "wwan1")
        modems = await pool.get_all_modems()
        assert len(modems) == 2

    @pytest.mark.asyncio
    async def test_get_connected_modems_filters(self):
        pool = _make_pool_with_modems("wwan0", "wwan1")
        pool._modems["wwan1"].is_connected = False
        modems = await pool.get_connected_modems()
        assert len(modems) == 1
        assert modems[0].interface == "wwan0"

    @pytest.mark.asyncio
    async def test_get_active_modem_returns_active(self):
        pool = _make_pool_with_modems("wwan0", "wwan1", active="wwan0")
        modem = await pool.get_active_modem()
        assert modem is not None
        assert modem.interface == "wwan0"

    @pytest.mark.asyncio
    async def test_get_active_modem_none_when_no_active(self):
        pool = _make_pool_with_modems("wwan0")
        modem = await pool.get_active_modem()
        assert modem is None

    @pytest.mark.asyncio
    async def test_get_best_modem_returns_highest_quality(self):
        pool = _make_pool_with_modems("wwan0", "wwan1")
        pool._modems["wwan0"].quality_score = 60.0
        pool._modems["wwan1"].quality_score = 90.0
        best = await pool.get_best_modem()
        assert best.interface == "wwan1"

    @pytest.mark.asyncio
    async def test_get_modem_by_interface(self):
        pool = _make_pool_with_modems("wwan0", "wwan1")
        modem = await pool.get_modem("wwan1")
        assert modem is not None
        assert modem.interface == "wwan1"

    @pytest.mark.asyncio
    async def test_get_modem_not_found_returns_none(self):
        pool = _make_pool_with_modems("wwan0")
        modem = await pool.get_modem("wwan9")
        assert modem is None


# ─────────────────────────────────────────────────────────────────────────────
# get_status
# ─────────────────────────────────────────────────────────────────────────────


class TestGetStatus:
    @pytest.mark.asyncio
    async def test_status_structure(self):
        pool = _make_pool_with_modems("wwan0", "wwan1", active="wwan0")
        status = await pool.get_status()

        assert "total_modems" in status
        assert "connected_modems" in status
        assert "healthy_modems" in status
        assert "active_modem" in status
        assert "selection_mode" in status
        assert "modems" in status

    @pytest.mark.asyncio
    async def test_status_counts(self):
        pool = _make_pool_with_modems("wwan0", "wwan1", active="wwan0")
        pool._modems["wwan1"].is_connected = False
        status = await pool.get_status()

        assert status["total_modems"] == 2
        assert status["connected_modems"] == 1
        assert status["active_modem"] == "wwan0"

    @pytest.mark.asyncio
    async def test_status_modems_list(self):
        pool = _make_pool_with_modems("wwan0")
        status = await pool.get_status()

        assert len(status["modems"]) == 1
        assert status["modems"][0]["interface"] == "wwan0"


# ─────────────────────────────────────────────────────────────────────────────
# set_selection_mode
# ─────────────────────────────────────────────────────────────────────────────


class TestSelectionMode:
    def test_set_valid_mode(self):
        pool = ModemPool()
        result = pool.set_selection_mode("manual")
        assert result is True
        assert pool._selection_mode == ModemSelectionMode.MANUAL

    def test_set_invalid_mode(self):
        pool = ModemPool()
        result = pool.set_selection_mode("nonexistent_mode")
        assert result is False
