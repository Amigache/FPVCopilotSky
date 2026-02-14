#!/usr/bin/env python3
"""
FPV Copilot Sky - Main Application
FastAPI server for MAVLink drone control
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import sys
import os
import asyncio
import threading
import time
import logging

logger = logging.getLogger(__name__)

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Modular providers system
from providers import init_provider_registry, get_provider_registry  # noqa: E402
from providers.vpn.tailscale import TailscaleProvider  # noqa: E402
from providers.modem.hilink.huawei import HuaweiE3372hProvider  # noqa: E402
from providers.network import (  # noqa: E402
    EthernetInterface,
    WiFiInterface,
    VPNInterface,
    ModemInterface,
)
from services.flight_data_logger import FlightDataLogger  # noqa: E402
from providers.board import BoardRegistry  # noqa: E402

# Use simplified MAVLink bridge and router
from services.mavlink_bridge import MAVLinkBridge  # noqa: E402
from services.mavlink_router import get_router  # noqa: E402
from services.websocket_manager import websocket_manager  # noqa: E402
from services.preferences import get_preferences  # noqa: E402
from services.serial_detector import get_detector  # noqa: E402
from services.gstreamer_service import init_gstreamer_service  # noqa: E402, F401
from services.webrtc_service import init_webrtc_service  # noqa: E402
from services.video_stream_info import (  # noqa: E402
    init_video_stream_info_service,
    get_video_stream_info_service,
)
from api.routes import mavlink, system  # noqa: E402
from api.routes import router as router_routes  # noqa: E402
from api.routes import video as video_routes  # noqa: E402
from api.routes import webrtc as webrtc_routes  # noqa: E402
from api.routes import network as network_routes  # noqa: E402
from api.routes import vpn as vpn_routes  # noqa: E402
from api.routes import modem as modem_routes  # noqa: E402
from api.routes import status as status_routes  # noqa: E402
from api.routes import network_interface as network_interface_routes  # noqa: E402

app = FastAPI(title="FPV Copilot Sky", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global services - event loop will be set on startup
mavlink_service = None
router_service = None
preferences_service = None
video_service = None
detected_board = None  # Board provider detection

# Include routers
app.include_router(mavlink.router, prefix="/api/mavlink", tags=["mavlink"])
app.include_router(system.router, prefix="/api/system", tags=["system"])
app.include_router(router_routes.router)
app.include_router(video_routes.router)
app.include_router(network_routes.router)
app.include_router(vpn_routes.router)
app.include_router(modem_routes.router)
app.include_router(status_routes.router)
app.include_router(network_interface_routes.router)
app.include_router(webrtc_routes.router)


# Global WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Global WebSocket endpoint for real-time updates"""
    await websocket_manager.connect(websocket)

    try:
        # Send initial status and telemetry
        await websocket_manager.broadcast("mavlink_status", mavlink_service.get_status())
        telemetry = mavlink_service.get_telemetry()
        if telemetry.get("connected"):
            await websocket_manager.broadcast("telemetry", telemetry)

        # Send initial video status
        if video_service:
            await websocket_manager.broadcast("video_status", video_service.get_status())

        # Send initial network status
        try:
            from api.routes.network import get_network_status

            network_status = await get_network_status()
            await websocket_manager.broadcast("network_status", network_status)
        except Exception as e:
            logger.debug(f"Initial network status error: {e}")

        # Send initial VPN status (from provider registry)
        try:
            from services.preferences import get_preferences

            registry = get_provider_registry()
            prefs = get_preferences()
            config = prefs.get_vpn_config()
            provider_name = config.get("provider")
            # Auto-detect first installed provider if not configured
            if not provider_name:
                available = registry.get_available_vpn_providers()
                installed = [p for p in available if p.get("installed")]
                if installed:
                    provider_name = installed[0]["name"]
            if provider_name:
                vpn_provider = registry.get_vpn_provider(provider_name)
                if vpn_provider:
                    status = vpn_provider.get_status()
                    await websocket_manager.broadcast("vpn_status", status)
        except Exception:  # noqa: E722
            pass  # VPN status not critical for startup

        # Keep connection alive and handle client messages
        while True:
            await websocket.receive_text()

            # Handle ping/pong (ignore for now, not needed)
            # WebSocket has built-in keep-alive

    except WebSocketDisconnect:
        print("WebSocket client disconnected")
    except Exception as e:
        logger.debug(f"WebSocket error: {e}")
    finally:
        websocket_manager.disconnect(websocket)


@app.get("/")
async def root():
    return {"name": "FPV Copilot Sky", "version": "1.0.0", "status": "running"}


async def periodic_stats_broadcast():
    """Periodically broadcast router stats via WebSocket.

    OPTIMIZATION: Skip all processing when no WebSocket clients are connected.
    This saves CPU for video encoding and telemetry when the UI is closed.
    """
    counter = 0
    while True:
        await asyncio.sleep(1)
        counter += 1

        # Skip all processing if no clients connected (save CPU for video/telemetry)
        if not websocket_manager.has_clients:
            continue

        try:
            # Router status every 2 seconds
            if counter % 2 == 0 and router_service:
                outputs = router_service.get_outputs_list()
                await websocket_manager.broadcast("router_status", outputs)

            # Video status every 2 seconds (when streaming)
            if counter % 2 == 0 and video_service and video_service.is_streaming:
                await websocket_manager.broadcast("video_status", video_service.get_status())

            # Status health check every 5 seconds
            if counter % 5 == 0:
                from api.routes.status import (
                    check_python_dependencies,
                    check_npm_dependencies,
                    check_system_info,
                    get_app_version,
                    get_frontend_version,
                    get_user_permissions,
                    get_node_version,
                )

                status_data = {
                    "success": True,
                    "backend": {
                        "running": True,
                        "python_deps": check_python_dependencies(),
                        "system": check_system_info(),
                        "app_version": get_app_version(),
                    },
                    "frontend": {
                        "npm_deps": check_npm_dependencies(),
                        "frontend_version": get_frontend_version(),
                        "node_version": get_node_version(),
                    },
                    "permissions": get_user_permissions(),
                    "timestamp": int(time.time()),
                }
                await websocket_manager.broadcast("status", status_data)

            # Network status every 5 seconds
            if counter % 5 == 0:
                try:
                    from api.routes.network import get_network_status

                    network_status = await get_network_status()
                    await websocket_manager.broadcast("network_status", network_status)
                except Exception as e:
                    logger.debug(f"Network status broadcast error: {e}")

            # System resources (CPU/Memory) every 3 seconds
            if counter % 3 == 0:
                from services.system_service import SystemService

                await websocket_manager.broadcast(
                    "system_resources",
                    {
                        "cpu": SystemService.get_cpu_info(),
                        "memory": SystemService.get_memory_info(),
                    },
                )

            # Services status every 5 seconds
            if counter % 5 == 0:
                from services.system_service import SystemService

                services = SystemService.get_services_status()
                await websocket_manager.broadcast("system_services", {"services": services, "count": len(services)})

            # VPN status every 10 seconds
            if counter % 10 == 0:
                try:
                    registry = get_provider_registry()
                    prefs = get_preferences()
                    config = prefs.get_vpn_config()
                    provider_name = config.get("provider")
                    if not provider_name:
                        available = registry.get_available_vpn_providers()
                        installed = [p for p in available if p.get("installed")]
                        if installed:
                            provider_name = installed[0]["name"]
                    if provider_name:
                        vpn_provider = registry.get_vpn_provider(provider_name)
                        if vpn_provider:
                            loop = asyncio.get_event_loop()
                            vpn_status = await loop.run_in_executor(None, vpn_provider.get_status)
                            await websocket_manager.broadcast("vpn_status", vpn_status)
                except Exception as e:
                    logger.debug(f"VPN status broadcast error: {e}")

            # Modem status every 10 seconds (avoid hammering modem API)
            if counter % 10 == 0:
                try:
                    from providers import get_provider_registry

                    registry = get_provider_registry()
                    modem_provider = registry.get_modem_provider("huawei_e3372h")
                    if modem_provider and modem_provider.is_available:
                        # Use raw async methods for full data
                        import asyncio as _asyncio

                        device_task = (
                            modem_provider.async_get_raw_device_info()
                            if hasattr(modem_provider, "async_get_raw_device_info")
                            else _asyncio.sleep(0)
                        )
                        signal_task = (
                            modem_provider.async_get_signal_info()
                            if hasattr(modem_provider, "async_get_signal_info")
                            else _asyncio.sleep(0)
                        )
                        network_task = (
                            modem_provider.async_get_raw_network_info()
                            if hasattr(modem_provider, "async_get_raw_network_info")
                            else _asyncio.sleep(0)
                        )
                        traffic_task = (
                            modem_provider.async_get_traffic_stats()
                            if hasattr(modem_provider, "async_get_traffic_stats")
                            else _asyncio.sleep(0)
                        )

                        results = await _asyncio.gather(
                            device_task,
                            signal_task,
                            network_task,
                            traffic_task,
                            return_exceptions=True,
                        )

                        device_info = results[0] if not isinstance(results[0], Exception) else {}
                        signal_info = results[1] if not isinstance(results[1], Exception) else {}
                        network_info = results[2] if not isinstance(results[2], Exception) else {}
                        traffic_info = results[3] if not isinstance(results[3], Exception) else {}

                        device_info = device_info or {}
                        signal_info = signal_info or {}
                        network_info = network_info or {}
                        traffic_info = traffic_info or {}

                        available = any([device_info, signal_info, network_info, traffic_info])
                        conn_status = network_info.get("connection_status", "")
                        signal_percent = signal_info.get("signal_percent", 0) or 0
                        signal_bars = min(5, max(0, int(signal_percent / 20))) if signal_percent else 0

                        modem_data = {
                            "success": True,
                            "available": available,
                            "connected": conn_status == "Connected",
                            "video_mode_active": getattr(modem_provider, "video_mode_active", False),
                        }

                        if device_info:
                            modem_data["device"] = {
                                "device_name": device_info.get("device_name", ""),
                                "model": device_info.get("device_name", ""),
                                "imei": device_info.get("imei", ""),
                                "imsi": device_info.get("imsi", ""),
                                "iccid": device_info.get("iccid", ""),
                                "serial_number": device_info.get("serial_number", ""),
                                "hardware_version": device_info.get("hardware_version", ""),
                                "software_version": device_info.get("software_version", ""),
                                "product_family": device_info.get("product_family", ""),
                            }
                        if signal_info:
                            modem_data["signal"] = {
                                **signal_info,
                                "signal_bars": signal_bars,
                            }
                        if network_info:
                            modem_data["network"] = {
                                "operator": network_info.get("operator", ""),
                                "operator_code": network_info.get("operator_code", ""),
                                "network_type": network_info.get("network_type", ""),
                                "network_type_ex": network_info.get("network_type_ex", ""),
                                "connection_status": conn_status,
                                "signal_icon": network_info.get("signal_icon", signal_bars),
                                "roaming": network_info.get("roaming", False),
                                "primary_dns": network_info.get("primary_dns", ""),
                                "secondary_dns": network_info.get("secondary_dns", ""),
                            }
                        if traffic_info:
                            modem_data["traffic"] = traffic_info

                        # Add band/mode data (single extra call, reuses connection)
                        loop = asyncio.get_event_loop()
                        band_data = await loop.run_in_executor(None, modem_provider.get_current_band)
                        if band_data:
                            modem_data["current_band"] = band_data
                            modem_data["mode"] = {
                                "network_mode": band_data.get("network_mode", "00"),
                                "network_mode_name": band_data.get("network_mode_name", "Auto"),
                            }

                        # Add video quality
                        vq = await loop.run_in_executor(None, modem_provider.get_video_quality_assessment)
                        if vq and vq.get("available"):
                            modem_data["video_quality"] = vq

                        await websocket_manager.broadcast("modem_status", modem_data)
                except Exception as e:
                    logger.debug(f"Modem broadcast error: {e}")

        except Exception as e:
            logger.error(f"Error in periodic broadcast: {e}")
            pass


def auto_connect_vpn():
    """
    Auto-connect to VPN based on preferences.
    Runs in a separate thread to not block startup.
    """
    global preferences_service

    try:
        # Wait a bit to ensure preferences are loaded
        import time

        time.sleep(0.5)

        prefs = preferences_service
        if not prefs:
            print("⚠️ Preferences not initialized for VPN auto-connect")
            return

        vpn_config = prefs.get_vpn_config()

        # Check enabled AND auto_connect
        if not vpn_config.get("enabled", False):
            print("⏭️ VPN not enabled in preferences")
            return

        if not vpn_config.get("auto_connect", False):
            print("⏭️ VPN auto-connect disabled in preferences")
            return

        provider_name = vpn_config.get("provider")
        if not provider_name:
            print("⏭️ No VPN provider configured")
            return

        from providers import get_provider_registry

        registry = get_provider_registry()
        vpn_provider = registry.get_vpn_provider(provider_name)

        if not vpn_provider:
            print(f"⚠️ VPN provider '{provider_name}' not available")
            return

        # Check if already connected
        status = vpn_provider.get_status()
        if status.get("connected"):
            print(f"✅ VPN already connected ({provider_name})")
            return

        # Try to connect
        print(f"🔄 Auto-connecting to VPN ({provider_name})...")
        result = vpn_provider.connect()

        if result.get("success"):
            print(f"✅ Auto-connected to VPN ({provider_name})")
        elif result.get("needs_auth"):
            print(f"ℹ️ VPN requires authentication: {result.get('auth_url', 'Check VPN settings')}")
        else:
            print(f"⚠️ VPN auto-connect failed: {result.get('error', 'Unknown error')}")
    except Exception as e:
        print(f"⚠️ VPN auto-connect error: {e}")


def auto_connect_serial():
    """
    Auto-detect and connect to flight controller.
    Runs in a separate thread to not block startup.
    Verifies connection persistence and saves preferences only if successful.
    """
    global mavlink_service, preferences_service

    import time

    try:
        # Wait a bit to ensure services are initialized
        time.sleep(1)

        if not preferences_service or not mavlink_service:
            print("⚠️ Services not initialized for serial auto-connect")
            return

        prefs = preferences_service
        serial_config = prefs.get_serial_config()

        # Check if auto-connect is enabled
        if not serial_config.auto_connect:
            print("⏭️ Serial auto-connect disabled in preferences")
            return

        print("🔄 Starting serial auto-connect sequence...")

        # If we have a previously successful connection, try that first
        if serial_config.last_successful and serial_config.port:
            print(f"🔄 Attempting saved connection: {serial_config.port} @ {serial_config.baudrate} baud")
            result = mavlink_service.connect(serial_config.port, serial_config.baudrate)

            if result.get("success"):
                # Verify connection is stable
                time.sleep(1)
                status = mavlink_service.get_status()
                if status.get("connected"):
                    print(f"✅ Auto-connected to saved port: {serial_config.port}")
                    return
                else:
                    print("⚠️ Saved connection unstable, scanning for alternatives...")
            else:
                print(f"⚠️ Saved connection failed: {result.get('message', 'Unknown error')}")

        # Auto-detect flight controller
        print("🔍 Scanning for flight controller...")
        detector = get_detector()

        if not detector:
            print("⚠️ Serial detector not available")
            return

        detection = detector.detect_flight_controller(
            preferred_port=(serial_config.port if not serial_config.last_successful else None),
            preferred_baudrate=(serial_config.baudrate if not serial_config.last_successful else None),
        )

        if detection:
            print(f"📍 Found flight controller: {detection.get('description', detection['port'])}")
            print(f"   Port: {detection['port']} @ {detection['baudrate']} baud")

            # Try to connect
            result = mavlink_service.connect(detection["port"], detection["baudrate"])

            if result.get("success"):
                # Verify connection is stable before saving
                time.sleep(1)
                status = mavlink_service.get_status()

                if status.get("connected"):
                    # Save successful connection to preferences
                    try:
                        prefs.set_serial_config(
                            port=detection["port"],
                            baudrate=detection["baudrate"],
                            successful=True,
                        )
                        print(f"✅ Auto-connected and saved: {detection['port']} @ {detection['baudrate']} baud")
                        return
                    except Exception as e:
                        print(f"⚠️ Connected but failed to save preferences: {e}")
                        # Connection is good, so don't disconnect
                else:
                    print("⚠️ Detection succeeded and initial connect returned success, but connection unstable")
            else:
                print(f"⚠️ Connection attempt failed: {result.get('message', 'Unknown error')}")
        else:
            print("⚠️ No flight controller detected - the system is ready for manual connection")
            print("ℹ️  Connect a flight controller via serial and use the UI to establish connection")

    except Exception as e:
        print(f"⚠️ Serial auto-connect error: {e}")
        import traceback

        traceback.print_exc()


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global mavlink_service, router_service, preferences_service, video_service, detected_board
    loop = asyncio.get_event_loop()

    # Initialize preferences first
    preferences_service = get_preferences()

    # Initialize Board Provider detection
    # This detects the hardware platform and capabilities
    try:
        board_registry = BoardRegistry()
        detected_board = board_registry.get_detected_board()
        if detected_board:
            print(f"✅ Board detected: {detected_board.board_name}")
            print(f"   - Variant: {detected_board.variant.name}")
            print(f"   - CPU: {detected_board.hardware.cpu_cores} cores @ {detected_board.hardware.cpu_model}")
            print(f"   - RAM: {detected_board.hardware.ram_gb}GB")
            print(f"   - Storage: {detected_board.hardware.storage_gb}GB ({detected_board.variant.storage_type.value})")
            print(f"   - Video Sources: {', '.join([f.value for f in detected_board.variant.video_sources])}")
            print(f"   - Video Encoders: {', '.join([f.value for f in detected_board.variant.video_encoders])}")
        else:
            print("⚠️  No board detected - using generic configuration")
    except Exception as e:
        logger.error(f"Board detection failed: {e}")
        print("⚠️  Board detection error - using generic configuration")

    # Initialize provider registry (VPN, Modem, Network providers)
    provider_registry = init_provider_registry()

    # Register VPN providers
    provider_registry.register_vpn_provider("tailscale", TailscaleProvider)

    # Register Modem providers
    provider_registry.register_modem_provider("huawei_e3372h", HuaweiE3372hProvider)

    # Register Network Interface providers
    provider_registry.register_network_interface("ethernet", EthernetInterface)
    provider_registry.register_network_interface("wifi", WiFiInterface)
    provider_registry.register_network_interface("vpn", VPNInterface)
    provider_registry.register_network_interface("modem", ModemInterface)

    # Initialize Video providers (auto-register from registry_init modules)
    from app.providers import video_registry_init  # noqa: E402, F401
    from app.providers import video_source_registry_init  # noqa: E402, F401

    print("✅ Provider registry initialized:")
    print("   - VPN: Tailscale")
    print("   - Modem: Huawei E3372h")
    print("   - Network Interfaces: Ethernet, WiFi, VPN, Modem")
    print("   - Video Sources: V4L2, LibCamera, HDMI Capture, Network Stream")
    print("   - Video Encoders: Hardware H.264, MJPEG, x264, OpenH264")

    # Log available encoders
    available_encoders = provider_registry.get_available_video_encoders()
    encoder_names = [e["display_name"] for e in available_encoders if e["available"]]
    if encoder_names:
        print(f"   - Video Encoders: {', '.join(encoder_names)}")
    else:
        print("   - Video Encoders: None available (GStreamer plugins may be missing)")

    # Create router for additional outputs (uses preferences for config)
    router_service = get_router()

    # Create MAVLink bridge
    mavlink_service = MAVLinkBridge(websocket_manager, loop)

    # Connect router to bridge for forwarding
    mavlink_service.set_router(router_service)

    # Initialize flight data logger for CSV recording
    flight_prefs = preferences_service.get_all_preferences().get("flight_session", {})
    log_directory = flight_prefs.get("log_directory", "")
    flight_logger = FlightDataLogger(mavlink_service, log_directory)

    # Configure modem provider with flight logger
    modem_provider = provider_registry.get_modem_provider("huawei_e3372h")
    if modem_provider:
        modem_provider.set_flight_logger(flight_logger)
        print(f"✅ Flight data logger configured: {flight_logger.log_directory}")

    # Initialize WebRTC signaling service
    webrtc_service = init_webrtc_service(websocket_manager, loop)
    webrtc_routes.set_webrtc_service(webrtc_service)

    # Initialize video streaming service
    video_service = init_gstreamer_service(websocket_manager, loop, webrtc_service)
    video_routes.set_video_service(video_service)

    # Initialize video stream information service (for MAVLink VIDEO_STREAM_INFORMATION)
    video_stream_info_service = init_video_stream_info_service(mavlink_service, video_service)
    video_stream_info_service.start()

    # Auto-connect to VPN not needed - handled by VPN provider/routes on demand

    # Load video config from preferences
    video_config = preferences_service.get_video_config()
    streaming_config = preferences_service.get_streaming_config()
    if video_config or streaming_config:
        video_service.configure(video_config=video_config, streaming_config=streaming_config)

    # Set callback to broadcast router status changes via WebSocket (for immediate updates)
    def broadcast_router_status():
        try:
            outputs = router_service.get_outputs_list()
            asyncio.run_coroutine_threadsafe(websocket_manager.broadcast("router_status", outputs), loop)
        except Exception:
            pass

    router_service.set_status_callback(broadcast_router_status)

    # Start periodic stats broadcast task
    asyncio.create_task(periodic_stats_broadcast())

    # Inject services into routes
    mavlink.set_mavlink_service(mavlink_service)
    router_routes.set_router_service(router_service)

    print("🚀 FPV Copilot Sky starting up...")
    print("✅ Router ready for outputs")
    print("✅ VPN service initialized")

    # Auto-start video if configured
    if streaming_config and streaming_config.get("auto_start", False):
        print("📹 Video auto-start enabled in preferences")

        def start_video():
            import time

            time.sleep(2)  # Wait for system to settle
            try:
                if not video_service:
                    print("⚠️ Video service not available for auto-start")
                    return

                if not video_service.is_available():
                    print("⚠️ No video devices available for auto-start")
                    return

                print("🔄 Attempting to auto-start video stream...")
                result = video_service.start()

                if result.get("success"):
                    # Verify stream is actually running
                    time.sleep(1)
                    status = video_service.get_status()
                    if status.get("streaming"):
                        print("✅ Video streaming auto-started successfully")
                    else:
                        print("⚠️ Video start returned success but stream not confirmed")
                else:
                    print(f"⚠️ Video auto-start failed: {result.get('message', 'Unknown error')}")
            except Exception as e:
                print(f"⚠️ Video auto-start exception: {e}")

        video_thread = threading.Thread(target=start_video, daemon=True, name="VideoAutoStart")
        video_thread.start()
    else:
        print("⏭️ Video auto-start disabled in preferences")

    # Start auto-connect VPN in background thread (non-blocking)
    vpn_thread = threading.Thread(target=auto_connect_vpn, daemon=True, name="VPNAutoConnect")
    vpn_thread.start()

    # Start auto-connect in background thread (non-blocking)
    auto_connect_thread = threading.Thread(target=auto_connect_serial, daemon=True, name="AutoConnect")
    auto_connect_thread.start()


def get_detected_board():
    """Get detected board info (singleton pattern)"""
    return detected_board


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    print("🛑 FPV Copilot Sky shutting down...")

    # Stop video stream info service
    video_stream_info_service = get_video_stream_info_service()
    if video_stream_info_service:
        video_stream_info_service.stop()

    if video_service:
        video_service.shutdown()
    if router_service:
        router_service.shutdown()
    if mavlink_service and mavlink_service.is_connected():
        mavlink_service.disconnect()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
