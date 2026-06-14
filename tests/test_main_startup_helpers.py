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


@pytest.mark.asyncio
async def test_startup_init_optional_services_all_enabled(monkeypatch):
    prefs = types.SimpleNamespace(
        get_all_preferences=lambda: {
            "network": {
                "policy_routing_enabled": True,
                "vpn_health_check_enabled": True,
            }
        }
    )

    modem_pool = types.SimpleNamespace(set_services=MagicMock(), start=AsyncMock())
    policy_manager = types.SimpleNamespace(initialize=AsyncMock(return_value=True))
    vpn_checker = types.SimpleNamespace(
        initialize=AsyncMock(return_value=True),
        _vpn_type="tailscale",
        _peer_ip="100.64.0.1",
    )

    modem_pool_module = __import__("app.services.modem_pool", fromlist=["get_modem_pool"])
    monkeypatch.setattr(modem_pool_module, "get_modem_pool", lambda: modem_pool)

    policy_module = __import__("app.services.policy_routing_manager", fromlist=["get_policy_routing_manager"])
    monkeypatch.setattr(policy_module, "get_policy_routing_manager", lambda: policy_manager)

    vpn_module = __import__("app.services.vpn_health_checker", fromlist=["get_vpn_health_checker"])
    monkeypatch.setattr(vpn_module, "get_vpn_health_checker", lambda: vpn_checker)

    await main_module._startup_init_optional_services(prefs, modem_provider=object(), latency_monitor=object())

    modem_pool.set_services.assert_called_once()
    modem_pool.start.assert_awaited_once()
    policy_manager.initialize.assert_awaited_once()
    vpn_checker.initialize.assert_awaited_once()


@pytest.mark.asyncio
async def test_startup_init_optional_services_with_disabled_features(monkeypatch):
    prefs = types.SimpleNamespace(
        get_all_preferences=lambda: {
            "network": {
                "policy_routing_enabled": False,
                "vpn_health_check_enabled": False,
            }
        }
    )

    modem_pool = types.SimpleNamespace(set_services=MagicMock(), start=AsyncMock())
    policy_manager = types.SimpleNamespace(initialize=AsyncMock(return_value=True))
    vpn_checker = types.SimpleNamespace(initialize=AsyncMock(return_value=True))

    modem_pool_module = __import__("app.services.modem_pool", fromlist=["get_modem_pool"])
    monkeypatch.setattr(modem_pool_module, "get_modem_pool", lambda: modem_pool)

    policy_module = __import__("app.services.policy_routing_manager", fromlist=["get_policy_routing_manager"])
    monkeypatch.setattr(policy_module, "get_policy_routing_manager", lambda: policy_manager)

    vpn_module = __import__("app.services.vpn_health_checker", fromlist=["get_vpn_health_checker"])
    monkeypatch.setattr(vpn_module, "get_vpn_health_checker", lambda: vpn_checker)

    await main_module._startup_init_optional_services(prefs, modem_provider=None, latency_monitor=None)

    modem_pool.start.assert_awaited_once()
    policy_manager.initialize.assert_not_called()
    vpn_checker.initialize.assert_not_called()


@pytest.mark.asyncio
async def test_startup_init_optional_services_handles_failures(monkeypatch):
    prefs = types.SimpleNamespace(
        get_all_preferences=lambda: {
            "network": {
                "policy_routing_enabled": True,
                "vpn_health_check_enabled": True,
            }
        }
    )

    modem_pool = types.SimpleNamespace(set_services=MagicMock(), start=AsyncMock(side_effect=RuntimeError("x")))
    policy_manager = types.SimpleNamespace(initialize=AsyncMock(return_value=False))
    vpn_checker = types.SimpleNamespace(initialize=AsyncMock(side_effect=RuntimeError("y")))

    modem_pool_module = __import__("app.services.modem_pool", fromlist=["get_modem_pool"])
    monkeypatch.setattr(modem_pool_module, "get_modem_pool", lambda: modem_pool)

    policy_module = __import__("app.services.policy_routing_manager", fromlist=["get_policy_routing_manager"])
    monkeypatch.setattr(policy_module, "get_policy_routing_manager", lambda: policy_manager)

    vpn_module = __import__("app.services.vpn_health_checker", fromlist=["get_vpn_health_checker"])
    monkeypatch.setattr(vpn_module, "get_vpn_health_checker", lambda: vpn_checker)

    await main_module._startup_init_optional_services(prefs, modem_provider=None, latency_monitor=None)


@pytest.mark.asyncio
async def test_broadcast_vpn_status_autodetects_provider(monkeypatch):
    provider = types.SimpleNamespace(get_status=lambda: {"connected": True})
    registry = types.SimpleNamespace(
        get_available_vpn_providers=lambda: [{"name": "tailscale", "installed": True}],
        get_vpn_provider=lambda _name: provider,
    )
    prefs = types.SimpleNamespace(get_vpn_config=lambda: {"provider": ""})

    loop = types.SimpleNamespace(run_in_executor=AsyncMock(return_value={"connected": True}))
    monkeypatch.setattr(main_module.asyncio, "get_event_loop", lambda: loop)
    monkeypatch.setattr(main_module, "get_provider_registry", lambda: registry)
    monkeypatch.setattr(main_module, "get_preferences", lambda: prefs)

    broadcast = AsyncMock()
    monkeypatch.setattr(main_module.websocket_manager, "broadcast", broadcast)

    await main_module._broadcast_vpn_status()

    broadcast.assert_awaited_once_with("vpn_status", {"connected": True})


@pytest.mark.asyncio
async def test_broadcast_vpn_status_without_provider_does_nothing(monkeypatch):
    registry = types.SimpleNamespace(
        get_available_vpn_providers=lambda: [],
        get_vpn_provider=lambda _name: None,
    )
    prefs = types.SimpleNamespace(get_vpn_config=lambda: {"provider": ""})

    monkeypatch.setattr(main_module, "get_provider_registry", lambda: registry)
    monkeypatch.setattr(main_module, "get_preferences", lambda: prefs)

    broadcast = AsyncMock()
    monkeypatch.setattr(main_module.websocket_manager, "broadcast", broadcast)

    await main_module._broadcast_vpn_status()

    broadcast.assert_not_called()


@pytest.mark.asyncio
async def test_broadcast_status_health_payload(monkeypatch):
    status_module = __import__("app.api.routes.status", fromlist=["check_python_dependencies"])

    monkeypatch.setattr(status_module, "check_python_dependencies", lambda: {"ok": True})
    monkeypatch.setattr(status_module, "check_npm_dependencies", lambda: {"ok": True})
    monkeypatch.setattr(status_module, "check_system_info", lambda: {"os": "linux"})
    monkeypatch.setattr(status_module, "get_app_version", lambda: "1.2.3")
    monkeypatch.setattr(status_module, "get_frontend_version", lambda: "4.5.6")
    monkeypatch.setattr(status_module, "get_user_permissions", lambda: {"sudo": False})
    monkeypatch.setattr(status_module, "get_node_version", lambda: "20")

    broadcast = AsyncMock()
    monkeypatch.setattr(main_module.websocket_manager, "broadcast", broadcast)

    await main_module._broadcast_status_health()

    broadcast.assert_awaited_once()
    event, payload = broadcast.await_args.args
    assert event == "status"
    assert payload["success"] is True
    assert payload["backend"]["app_version"] == "1.2.3"


def test_broadcast_router_status_uses_threadsafe_call(monkeypatch):
    main_module.router_service = types.SimpleNamespace(get_outputs_list=MagicMock(return_value=[{"ok": True}]))
    broadcast = MagicMock(return_value=object())
    monkeypatch.setattr(main_module.websocket_manager, "broadcast", broadcast)

    submit = MagicMock()
    monkeypatch.setattr(main_module.asyncio, "run_coroutine_threadsafe", submit)

    main_module._broadcast_router_status(loop=object())

    submit.assert_called_once()


def test_auto_start_video_success(monkeypatch):
    monkeypatch.setattr(main_module.time, "sleep", lambda _x: None)
    main_module.video_service = types.SimpleNamespace(
        start=MagicMock(return_value={"success": True}),
        get_status=MagicMock(return_value={"streaming": True}),
    )

    main_module._auto_start_video()

    main_module.video_service.start.assert_called_once()
    main_module.video_service.get_status.assert_called_once()


def test_auto_start_video_handles_failure(monkeypatch):
    monkeypatch.setattr(main_module.time, "sleep", lambda _x: None)
    main_module.video_service = types.SimpleNamespace(
        start=MagicMock(return_value={"success": False, "message": "nope"}),
        get_status=MagicMock(),
    )

    main_module._auto_start_video()

    main_module.video_service.start.assert_called_once()
    main_module.video_service.get_status.assert_not_called()


# ── Tests for domain-scoped startup helpers (#33) ────────────────────────────


def test_startup_init_board_returns_detected_board(monkeypatch):
    """_startup_init_board returns the detected board when hardware is found."""
    fake_board = types.SimpleNamespace(
        board_name="Radxa Zero",
        board_identifier="radxa_zero_amlogic_s905y2",
        variant=types.SimpleNamespace(
            name="Armbian 22.08",
            storage_type=types.SimpleNamespace(value="emmc"),
            video_sources=[],
            video_encoders=[],
        ),
        hardware=types.SimpleNamespace(
            cpu_cores=4,
            cpu_model="S905Y2",
            ram_gb=4,
            storage_gb=16,
        ),
    )
    monkeypatch.setattr(
        main_module, "BoardRegistry", lambda: types.SimpleNamespace(get_detected_board=lambda: fake_board)
    )
    prefs = types.SimpleNamespace(get_serial_config=lambda: types.SimpleNamespace(port="/dev/ttyS0"))

    result = main_module._startup_init_board(prefs)

    assert result is fake_board


def test_startup_init_board_returns_none_on_detection_failure(monkeypatch):
    """_startup_init_board returns None without raising when board detection fails."""

    def _raise():
        raise RuntimeError("board error")

    monkeypatch.setattr(main_module, "BoardRegistry", _raise)
    prefs = types.SimpleNamespace(get_serial_config=lambda: types.SimpleNamespace(port=None))

    result = main_module._startup_init_board(prefs)

    assert result is None


def test_startup_init_providers_registers_all(monkeypatch):
    """_startup_init_providers registers VPN, Modem, Network, and Video providers."""
    registry = types.SimpleNamespace(
        register_vpn_provider=MagicMock(),
        register_modem_provider=MagicMock(),
        register_network_interface=MagicMock(),
    )
    monkeypatch.setattr(main_module, "init_provider_registry", lambda: registry)

    result = main_module._startup_init_providers()

    assert result is registry
    registry.register_vpn_provider.assert_called_once_with("tailscale", main_module.TailscaleProvider)
    registry.register_modem_provider.assert_called_once_with("huawei_e3372h", main_module.HuaweiE3372hProvider)
    assert registry.register_network_interface.call_count == 4


def test_startup_init_core_services_wires_all_routes(monkeypatch):
    """_startup_init_core_services initialises and injects all core services into routes."""
    router_svc = types.SimpleNamespace(set_status_callback=MagicMock())
    mav_svc = types.SimpleNamespace(set_router=MagicMock())
    vid_svc = types.SimpleNamespace(
        set_opencv_service=MagicMock(),
        configure=MagicMock(),
    )
    webrtc_svc = types.SimpleNamespace()
    opencv_svc = types.SimpleNamespace(
        set_telemetry_service=MagicMock(),
    )
    vid_stream_info = types.SimpleNamespace(start=MagicMock())
    flight_logger = types.SimpleNamespace(log_directory="/tmp/logs")

    monkeypatch.setattr(main_module, "get_router", lambda: router_svc)
    monkeypatch.setattr(main_module, "MAVLinkBridge", lambda *_: mav_svc)
    monkeypatch.setattr(main_module, "FlightDataLogger", lambda *_: flight_logger)
    monkeypatch.setattr(main_module, "init_webrtc_service", lambda *_: webrtc_svc)
    monkeypatch.setattr(main_module, "init_gstreamer_service", lambda *_: vid_svc)
    monkeypatch.setattr(main_module, "init_video_stream_info_service", lambda *_: vid_stream_info)
    monkeypatch.setattr(main_module, "init_opencv_service", lambda: opencv_svc)
    monkeypatch.setattr(main_module.mavlink, "set_mavlink_service", MagicMock())
    monkeypatch.setattr(main_module.router_routes, "set_router_service", MagicMock())
    monkeypatch.setattr(main_module.webrtc_routes, "set_webrtc_service", MagicMock())
    monkeypatch.setattr(main_module.video_routes, "set_video_service", MagicMock())
    monkeypatch.setattr(main_module.experimental_routes, "set_opencv_service", MagicMock())

    prefs = types.SimpleNamespace(
        get_all_preferences=lambda: {},
        get_video_config=lambda: None,
        get_streaming_config=lambda: None,
        set_video_config=MagicMock(),
    )
    registry = types.SimpleNamespace(
        get_modem_provider=lambda _: None,
        get_video_encoder=lambda _: None,
    )

    r, m, v, sc = main_module._startup_init_core_services(registry, prefs, object())

    assert r is router_svc
    assert m is mav_svc
    assert v is vid_svc
    assert sc is None
    vid_stream_info.start.assert_called_once()
    main_module.mavlink.set_mavlink_service.assert_called_once_with(mav_svc)
    main_module.router_routes.set_router_service.assert_called_once_with(router_svc)


@pytest.mark.asyncio
async def test_lifespan_shutdown_stops_latency_and_webrtc(monkeypatch):
    """_lifespan_shutdown calls latency_monitor.stop() and webrtc_service.shutdown()."""
    monkeypatch.setattr(main_module, "stop_auto_failover", AsyncMock())

    modem_pool = types.SimpleNamespace(stop=AsyncMock())
    modem_pool_module = __import__("app.services.modem_pool", fromlist=["get_modem_pool"])
    monkeypatch.setattr(modem_pool_module, "get_modem_pool", lambda: modem_pool)

    policy_manager = types.SimpleNamespace(_initialized=False)
    policy_module = __import__("app.services.policy_routing_manager", fromlist=["get_policy_routing_manager"])
    monkeypatch.setattr(policy_module, "get_policy_routing_manager", lambda: policy_manager)

    event_bridge = types.SimpleNamespace(stop=AsyncMock())
    monkeypatch.setattr(main_module, "get_network_event_bridge", lambda: event_bridge)

    latency_monitor = types.SimpleNamespace(stop=AsyncMock())
    monkeypatch.setattr(main_module, "get_latency_monitor", lambda: latency_monitor)

    webrtc_svc = types.SimpleNamespace(shutdown=MagicMock())
    monkeypatch.setattr(main_module, "get_webrtc_service", lambda: webrtc_svc)

    monkeypatch.setattr(main_module, "get_video_stream_info_service", lambda: None)
    main_module.video_service = None
    main_module.router_service = None
    main_module.mavlink_service = None

    await main_module._lifespan_shutdown()

    latency_monitor.stop.assert_awaited_once()
    webrtc_svc.shutdown.assert_called_once()
