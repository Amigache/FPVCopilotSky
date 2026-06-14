import types
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.main as main_module


@pytest.mark.asyncio
async def test_startup_init_network_bridge_success(monkeypatch):
    latency_monitor = types.SimpleNamespace(start=AsyncMock())
    event_bridge = types.SimpleNamespace(set_services=MagicMock(), start=AsyncMock())

    monkeypatch.setattr(main_module, "get_latency_monitor", lambda: latency_monitor)
    monkeypatch.setattr(main_module, "get_network_event_bridge", lambda: event_bridge)

    result = await main_module._startup_init_network_bridge(
        modem_provider=None,
        video_service=object(),
        webrtc_service=object(),
        wsm=object(),
    )

    assert result is latency_monitor
    latency_monitor.start.assert_awaited_once()
    event_bridge.start.assert_awaited_once()
    event_bridge.set_services.assert_called_once()


@pytest.mark.asyncio
async def test_startup_init_network_bridge_outer_error(monkeypatch):
    monkeypatch.setattr(main_module, "get_latency_monitor", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    result = await main_module._startup_init_network_bridge(
        modem_provider=None,
        video_service=object(),
        webrtc_service=object(),
        wsm=object(),
    )

    assert result is None


@pytest.mark.asyncio
async def test_startup_init_auto_failover_disabled(monkeypatch):
    prefs = types.SimpleNamespace(get_network_config=lambda: {"auto_failover_enabled": False})

    await main_module._startup_init_auto_failover(prefs)


@pytest.mark.asyncio
async def test_startup_init_auto_failover_requires_wifi_and_modem(monkeypatch):
    prefs = types.SimpleNamespace(
        get_network_config=lambda: {
            "auto_failover_enabled": True,
            "auto_failover_preferred_mode": "wifi",
        }
    )

    async def fake_status():
        return {
            "mode": "wifi",
            "wifi": {"detected": True},
            "modem": {"detected": False},
        }

    failover = types.SimpleNamespace(
        switch_callback=None,
        update_config=AsyncMock(),
        start=AsyncMock(),
    )

    monkeypatch.setattr(main_module.network_routes, "get_network_status", fake_status)
    monkeypatch.setattr(main_module, "get_auto_failover", lambda: failover)

    await main_module._startup_init_auto_failover(prefs)

    failover.update_config.assert_not_called()
    failover.start.assert_not_called()


@pytest.mark.asyncio
async def test_startup_init_auto_failover_starts_when_topology_is_valid(monkeypatch):
    prefs = types.SimpleNamespace(
        get_network_config=lambda: {
            "auto_failover_enabled": True,
            "auto_failover_preferred_mode": "modem",
        }
    )

    async def fake_status():
        return {
            "mode": "wifi",
            "wifi": {"detected": True},
            "modem": {"detected": True},
        }

    async def fake_set_priority_mode(_request):
        return {"success": True}

    failover = types.SimpleNamespace(
        switch_callback=None,
        update_config=AsyncMock(),
        start=AsyncMock(),
    )

    monkeypatch.setattr(main_module.network_routes, "get_network_status", fake_status)
    monkeypatch.setattr(main_module, "get_auto_failover", lambda: failover)

    network_status_module = __import__("app.api.routes.network.status", fromlist=["set_priority_mode"])
    monkeypatch.setattr(network_status_module, "set_priority_mode", fake_set_priority_mode)

    await main_module._startup_init_auto_failover(prefs)

    failover.update_config.assert_awaited_once()
    failover.start.assert_awaited_once()
    assert failover.switch_callback is not None


def test_auto_connect_vpn_skips_when_preferences_unavailable(monkeypatch):
    monkeypatch.setattr(main_module.time, "sleep", lambda _x: None)
    monkeypatch.setattr(main_module, "preferences_service", None)

    main_module.auto_connect_vpn()


def test_auto_connect_vpn_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(main_module.time, "sleep", lambda _x: None)

    prefs = types.SimpleNamespace(get_vpn_config=lambda: {"auto_connect": False})
    monkeypatch.setattr(main_module, "preferences_service", prefs)

    main_module.auto_connect_vpn()


def test_auto_connect_vpn_connects_successfully(monkeypatch):
    monkeypatch.setattr(main_module.time, "sleep", lambda _x: None)

    prefs = types.SimpleNamespace(
        get_vpn_config=lambda: {
            "auto_connect": True,
            "provider": "tailscale",
        }
    )
    monkeypatch.setattr(main_module, "preferences_service", prefs)

    provider = types.SimpleNamespace(
        get_status=lambda: {"connected": False},
        connect=lambda: {"success": True},
    )
    registry = types.SimpleNamespace(get_vpn_provider=lambda _name: provider)

    providers_module = __import__("app.providers", fromlist=["get_provider_registry"])
    monkeypatch.setattr(providers_module, "get_provider_registry", lambda: registry)

    main_module.auto_connect_vpn()


def test_auto_connect_serial_skips_when_services_missing(monkeypatch):
    monkeypatch.setattr(main_module.time, "sleep", lambda _x: None)
    monkeypatch.setattr(main_module, "preferences_service", None)
    monkeypatch.setattr(main_module, "mavlink_service", None)

    main_module.auto_connect_serial()


def test_auto_connect_serial_uses_saved_connection(monkeypatch):
    monkeypatch.setattr(main_module.time, "sleep", lambda _x: None)

    serial_cfg = types.SimpleNamespace(
        auto_connect=True,
        last_successful=True,
        port="/dev/ttyS1",
        baudrate=57600,
    )
    prefs = types.SimpleNamespace(get_serial_config=lambda: serial_cfg)

    mavlink = types.SimpleNamespace(
        connect=MagicMock(return_value={"success": True}),
        get_status=MagicMock(return_value={"connected": True}),
    )

    monkeypatch.setattr(main_module, "preferences_service", prefs)
    monkeypatch.setattr(main_module, "mavlink_service", mavlink)

    main_module.auto_connect_serial()

    mavlink.connect.assert_called_once_with("/dev/ttyS1", 57600)


def test_auto_connect_serial_detects_and_saves(monkeypatch):
    monkeypatch.setattr(main_module.time, "sleep", lambda _x: None)

    serial_cfg = types.SimpleNamespace(
        auto_connect=True,
        last_successful=False,
        port="",
        baudrate=115200,
    )

    prefs = types.SimpleNamespace(
        get_serial_config=lambda: serial_cfg,
        set_serial_config=MagicMock(),
    )

    mavlink = types.SimpleNamespace(
        connect=MagicMock(return_value={"success": True}),
        get_status=MagicMock(return_value={"connected": True}),
    )

    detector = types.SimpleNamespace(
        detect_flight_controller=MagicMock(
            return_value={
                "port": "/dev/ttyS4",
                "baudrate": 115200,
                "description": "FC",
            }
        )
    )

    monkeypatch.setattr(main_module, "preferences_service", prefs)
    monkeypatch.setattr(main_module, "mavlink_service", mavlink)
    monkeypatch.setattr(main_module, "get_detector", lambda: detector)

    main_module.auto_connect_serial()

    prefs.set_serial_config.assert_called_once_with(port="/dev/ttyS4", baudrate=115200, successful=True)


@pytest.mark.asyncio
async def test_broadcast_modem_status_builds_payload(monkeypatch):
    async def _async_value(data):
        return data

    modem_provider = types.SimpleNamespace(
        is_available=True,
        async_get_raw_device_info=lambda: _async_value(
            {
                "device_name": "Huawei",
                "imei": "123",
                "imsi": "456",
                "iccid": "789",
            }
        ),
        async_get_signal_info=lambda: _async_value({"signal_percent": 75}),
        async_get_raw_network_info=lambda: _async_value(
            {
                "connection_status": "Connected",
                "operator": "Carrier",
                "network_type": "LTE",
            }
        ),
        async_get_traffic_stats=lambda: _async_value({"rx": 1, "tx": 2}),
        get_current_band=lambda: {"network_mode": "03", "network_mode_name": "LTE"},
        get_video_quality_assessment=lambda: {"available": True, "score": 90},
    )

    registry = types.SimpleNamespace(get_modem_provider=lambda _name: modem_provider)
    providers_module = __import__("app.providers", fromlist=["get_provider_registry"])
    monkeypatch.setattr(providers_module, "get_provider_registry", lambda: registry)

    loop = types.SimpleNamespace(
        run_in_executor=AsyncMock(
            side_effect=[
                {"network_mode": "03", "network_mode_name": "LTE"},
                {"available": True, "score": 90},
            ]
        )
    )
    monkeypatch.setattr(main_module.asyncio, "get_event_loop", lambda: loop)

    broadcast = AsyncMock()
    monkeypatch.setattr(main_module.websocket_manager, "broadcast", broadcast)

    await main_module._broadcast_modem_status()

    broadcast.assert_awaited_once()
    event, payload = broadcast.await_args.args
    assert event == "modem_status"
    assert payload["connected"] is True
    assert payload["signal"]["signal_bars"] == 3
    assert payload["video_quality"]["score"] == 90


@pytest.mark.asyncio
async def test_lifespan_shutdown_calls_services(monkeypatch):
    stop_auto_failover = AsyncMock()
    monkeypatch.setattr(main_module, "stop_auto_failover", stop_auto_failover)

    modem_pool = types.SimpleNamespace(stop=AsyncMock())
    modem_pool_module = __import__("app.services.modem_pool", fromlist=["get_modem_pool"])
    monkeypatch.setattr(modem_pool_module, "get_modem_pool", lambda: modem_pool)

    policy_manager = types.SimpleNamespace(_initialized=True, cleanup=AsyncMock())
    policy_module = __import__("app.services.policy_routing_manager", fromlist=["get_policy_routing_manager"])
    monkeypatch.setattr(policy_module, "get_policy_routing_manager", lambda: policy_manager)

    event_bridge = types.SimpleNamespace(stop=AsyncMock())
    monkeypatch.setattr(main_module, "get_network_event_bridge", lambda: event_bridge)

    stream_info = types.SimpleNamespace(stop=MagicMock())
    monkeypatch.setattr(main_module, "get_video_stream_info_service", lambda: stream_info)

    main_module.video_service = types.SimpleNamespace(shutdown=MagicMock())
    main_module.router_service = types.SimpleNamespace(shutdown=MagicMock())
    main_module.mavlink_service = types.SimpleNamespace(
        is_connected=MagicMock(return_value=True),
        disconnect=MagicMock(),
    )

    await main_module._lifespan_shutdown()

    modem_pool.stop.assert_awaited_once()
    stop_auto_failover.assert_awaited_once()
    policy_manager.cleanup.assert_awaited_once()
    event_bridge.stop.assert_awaited_once()
    stream_info.stop.assert_called_once()
    main_module.video_service.shutdown.assert_called_once()
    main_module.router_service.shutdown.assert_called_once()
    main_module.mavlink_service.disconnect.assert_called_once()
