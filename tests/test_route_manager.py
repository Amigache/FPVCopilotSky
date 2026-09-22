"""Tests for RouteManager (single owner of main-table default metrics)."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.services.route_manager import RouteManager


def make_run_command(routes_output):
    async def fake_run(cmd, *args, **kwargs):
        if cmd[:3] == ["ip", "route", "show"]:
            return routes_output, "", 0
        return "", "", 0

    return AsyncMock(side_effect=fake_run)


def test_set_priority_promotes_primary_and_demotes_others():
    manager = RouteManager()
    routes = "default via 192.168.1.1 dev wlan0 proto dhcp metric 100\n" "default via 192.168.8.1 dev eth1 metric 200"

    with patch("app.api.routes.network.common.run_command", new=make_run_command(routes)) as run_command:
        result = asyncio.run(manager.set_priority("eth1"))

    assert result["success"] is True
    cmds = [call.args[0] for call in run_command.call_args_list]
    assert ["sudo", "ip", "route", "replace", "default", "dev", "eth1", "via", "192.168.8.1", "metric", "100"] in cmds
    assert ["sudo", "ip", "route", "replace", "default", "dev", "wlan0", "via", "192.168.1.1", "metric", "200"] in cmds


def test_set_priority_is_noop_within_cooldown():
    manager = RouteManager(cooldown_s=60.0)
    routes = "default via 192.168.8.1 dev eth1 metric 100"

    with patch("app.api.routes.network.common.run_command", new=make_run_command(routes)) as run_command:
        asyncio.run(manager.set_priority("eth1"))
        run_command.reset_mock()
        second = asyncio.run(manager.set_priority("eth1"))

    assert second["changes"] == []
    run_command.assert_not_called()


def test_set_priority_no_default_routes():
    manager = RouteManager()
    with patch("app.api.routes.network.common.run_command", new=make_run_command("")):
        result = asyncio.run(manager.set_priority("eth1"))
    assert result["success"] is False
    assert "No default routes" in result["message"]


def test_set_priority_without_interface():
    manager = RouteManager()
    result = asyncio.run(manager.set_priority(""))
    assert result["success"] is False


def test_get_status_reports_primary():
    manager = RouteManager()
    routes = "default via 192.168.1.1 dev wlan0 metric 200\n" "default via 192.168.8.1 dev eth1 metric 100"
    with patch("app.api.routes.network.common.run_command", new=make_run_command(routes)):
        status = asyncio.run(manager.get_status())
    assert status["primary"] == "eth1"
    assert len(status["routes"]) == 2


def test_set_priority_removes_redundant_duplicate():
    manager = RouteManager()
    # Same gateway on the same interface with two metrics (leftover backup).
    routes = "default via 192.168.1.1 dev wlan0 metric 100\n" "default via 192.168.1.1 dev wlan0 metric 200"

    with patch("app.api.routes.network.common.run_command", new=make_run_command(routes)) as run_command:
        result = asyncio.run(manager.set_priority("wlan0"))

    cmds = [call.args[0] for call in run_command.call_args_list]
    assert [
        "sudo",
        "ip",
        "route",
        "del",
        "default",
        "dev",
        "wlan0",
        "via",
        "192.168.1.1",
        "metric",
        "200",
    ] in cmds
    assert any("removed redundant" in change for change in result["changes"])
