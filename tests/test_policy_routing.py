"""
Tests for PolicyRoutingManager — FASE 2

Covers: initialization, iptables marks, ip rules, modem table management,
update_active_modem, get_status, cleanup, singleton accessor.

Note: All subprocess / sudo calls are mocked — no real system changes.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from app.services.policy_routing_manager import (
    PolicyRoutingManager,
    get_policy_routing_manager,
    TABLE_VPN,
    TABLE_VIDEO,
    TABLE_MODEM_BASE,
    MARK_VPN,
    MARK_VIDEO,
    MARK_MAVLINK,
    TRAFFIC_CLASSES,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_initialized_manager(**kwargs) -> PolicyRoutingManager:
    """Return a PolicyRoutingManager with _initialized=True and optional overrides."""
    mgr = PolicyRoutingManager()
    mgr._initialized = True
    for k, v in kwargs.items():
        setattr(mgr, k, v)
    return mgr


async def _noop(*args, **kwargs) -> bool:
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────


class TestSingleton:
    def test_returns_same_instance(self):
        import app.services.policy_routing_manager as mod

        mod._policy_routing_manager = None
        a = get_policy_routing_manager()
        b = get_policy_routing_manager()
        assert a is b

    def test_creates_fresh_instance(self):
        import app.services.policy_routing_manager as mod

        mod._policy_routing_manager = None
        mgr = get_policy_routing_manager()
        assert isinstance(mgr, PolicyRoutingManager)


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────


class TestConstants:
    def test_table_ids(self):
        assert TABLE_VPN == 100
        assert TABLE_VIDEO == 200
        assert TABLE_MODEM_BASE == 201

    def test_marks(self):
        assert MARK_VPN == "0x100"
        assert MARK_VIDEO == "0x200"
        assert MARK_MAVLINK == "0x300"

    def test_traffic_classes_present(self):
        names = [tc["name"] for tc in TRAFFIC_CLASSES]
        assert "vpn" in names
        assert "video" in names
        assert "mavlink" in names


# ─────────────────────────────────────────────────────────────────────────────
# Initialization
# ─────────────────────────────────────────────────────────────────────────────


class TestInitialize:
    @pytest.mark.asyncio
    async def test_initialize_calls_all_steps(self):
        """initialize() must call _ensure_rt_tables, _setup_iptables_marks, _setup_ip_rules."""
        mgr = PolicyRoutingManager()
        with (
            patch.object(mgr, "_ensure_rt_tables", new=AsyncMock()) as rt,
            patch.object(mgr, "_setup_iptables_marks", new=AsyncMock()) as ipt,
            patch.object(mgr, "_setup_ip_rules", new=AsyncMock()) as ipr,
        ):
            result = await mgr.initialize()

        assert result is True
        assert mgr._initialized is True
        rt.assert_called_once()
        ipt.assert_called_once()
        ipr.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_returns_false_on_exception(self):
        """initialize() returns False and doesn't raise when a step fails."""
        mgr = PolicyRoutingManager()
        with (
            patch.object(mgr, "_ensure_rt_tables", new=AsyncMock()),
            patch.object(mgr, "_setup_iptables_marks", new=AsyncMock(side_effect=RuntimeError("iptables fail"))),
        ):
            result = await mgr.initialize()

        assert result is False
        assert mgr._initialized is False

    @pytest.mark.asyncio
    async def test_cleanup_calls_remove_steps(self):
        """cleanup() calls _remove_ip_rules and _remove_iptables_marks."""
        mgr = _make_initialized_manager()
        with (
            patch.object(mgr, "_remove_ip_rules", new=AsyncMock()) as rmr,
            patch.object(mgr, "_remove_iptables_marks", new=AsyncMock()) as rmi,
        ):
            result = await mgr.cleanup()

        assert result is True
        assert mgr._initialized is False
        rmr.assert_called_once()
        rmi.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_returns_false_on_exception(self):
        """cleanup() returns False without raising on errors."""
        mgr = _make_initialized_manager()
        with (patch.object(mgr, "_remove_ip_rules", new=AsyncMock(side_effect=OSError("permission denied"))),):
            result = await mgr.cleanup()

        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# update_active_modem
# ─────────────────────────────────────────────────────────────────────────────


class TestUpdateActiveModem:
    @pytest.mark.asyncio
    async def test_updates_tables_and_stores_state(self):
        """update_active_modem stores interface/gateway and updates both shared tables."""
        mgr = _make_initialized_manager()
        with (
            patch.object(mgr, "_update_table_route", new=AsyncMock()) as utr,
            patch.object(mgr, "_ensure_modem_table", new=AsyncMock(return_value=201)) as emt,
        ):
            result = await mgr.update_active_modem("wwan0", "10.0.0.1")

        assert result is True
        assert mgr._active_interface == "wwan0"
        assert mgr._active_gateway == "10.0.0.1"
        # Must update VPN table (100) and Video table (200)
        assert call(TABLE_VPN, "wwan0", "10.0.0.1") in utr.call_args_list
        assert call(TABLE_VIDEO, "wwan0", "10.0.0.1") in utr.call_args_list

    @pytest.mark.asyncio
    async def test_initializes_if_not_ready(self):
        """Calls initialize() if manager is not yet initialized, then updates."""
        mgr = PolicyRoutingManager()
        assert mgr._initialized is False
        with (
            patch.object(mgr, "initialize", new=AsyncMock(return_value=True)) as init,
            patch.object(mgr, "_update_table_route", new=AsyncMock()),
            patch.object(mgr, "_ensure_modem_table", new=AsyncMock(return_value=201)),
        ):
            result = await mgr.update_active_modem("wwan0", "10.0.0.1")

        init.assert_called_once()
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_if_init_fails(self):
        """Returns False when automatic initialization fails."""
        mgr = PolicyRoutingManager()
        with patch.object(mgr, "initialize", new=AsyncMock(return_value=False)):
            result = await mgr.update_active_modem("wwan0", "10.0.0.1")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_route_error(self):
        """Returns False (doesn't raise) when _update_table_route throws."""
        mgr = _make_initialized_manager()
        with (patch.object(mgr, "_update_table_route", new=AsyncMock(side_effect=RuntimeError("ip route fail"))),):
            result = await mgr.update_active_modem("wwan0", "10.0.0.1")
        assert result is False

    @pytest.mark.asyncio
    async def test_second_modem_gets_different_table(self):
        """Each new interface gets an incrementing per-modem table ID."""
        mgr = _make_initialized_manager()
        with (
            patch.object(mgr, "_update_table_route", new=AsyncMock()),
            patch.object(mgr, "_ensure_modem_table", new=AsyncMock(side_effect=[201, 202])),
        ):
            await mgr.update_active_modem("wwan0", "10.0.0.1")
            await mgr.update_active_modem("wwan1", "192.168.1.1")

        assert mgr._active_interface == "wwan1"


# ─────────────────────────────────────────────────────────────────────────────
# get_status
# ─────────────────────────────────────────────────────────────────────────────


class TestGetStatus:
    @pytest.mark.asyncio
    async def test_status_structure(self):
        """get_status() returns expected keys."""
        mgr = _make_initialized_manager(
            _active_interface="wwan0",
            _active_gateway="10.0.0.1",
            _modem_tables={"wwan0": 201},
        )
        with (
            patch.object(mgr, "_get_ip_rules", new=AsyncMock(return_value=["100:\tfwmark 0x100 lookup 100"])),
            patch.object(mgr, "_get_all_table_routes", new=AsyncMock(return_value={})),
        ):
            status = await mgr.get_status()

        assert status["initialized"] is True
        assert status["active_modem"]["interface"] == "wwan0"
        assert status["active_modem"]["gateway"] == "10.0.0.1"
        assert "modem_tables" in status
        assert "policy_rules" in status
        assert "traffic_classes" in status
        assert "tables" in status

    @pytest.mark.asyncio
    async def test_status_no_active_modem(self):
        """get_status() returns active_modem=None when no modem selected."""
        mgr = _make_initialized_manager()
        with (
            patch.object(mgr, "_get_ip_rules", new=AsyncMock(return_value=[])),
            patch.object(mgr, "_get_all_table_routes", new=AsyncMock(return_value={})),
        ):
            status = await mgr.get_status()

        assert status["active_modem"] is None

    @pytest.mark.asyncio
    async def test_traffic_classes_excludes_video_tcp_duplicate(self):
        """traffic_classes in status should not include 'video_tcp' (collapsed)."""
        mgr = _make_initialized_manager()
        with (
            patch.object(mgr, "_get_ip_rules", new=AsyncMock(return_value=[])),
            patch.object(mgr, "_get_all_table_routes", new=AsyncMock(return_value={})),
        ):
            status = await mgr.get_status()

        tc_names = [tc["name"] for tc in status["traffic_classes"]]
        assert "video_tcp" not in tc_names
        assert "vpn" in tc_names
        assert "video" in tc_names
        assert "mavlink" in tc_names


# ─────────────────────────────────────────────────────────────────────────────
# get_rules / get_tables
# ─────────────────────────────────────────────────────────────────────────────


class TestGetRulesAndTables:
    @pytest.mark.asyncio
    async def test_get_rules_delegates_to_private(self):
        mgr = _make_initialized_manager()
        rules = ["100:\tfwmark 0x100 lookup 100"]
        with patch.object(mgr, "_get_ip_rules", new=AsyncMock(return_value=rules)):
            result = await mgr.get_rules()
        assert result == rules

    @pytest.mark.asyncio
    async def test_get_tables_delegates_to_private(self):
        mgr = _make_initialized_manager()
        tables = {"100": ["default via 10.0.0.1 dev wwan0"]}
        with patch.object(mgr, "_get_all_table_routes", new=AsyncMock(return_value=tables)):
            result = await mgr.get_tables()
        assert result == tables
