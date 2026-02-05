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

# Use simplified MAVLink bridge and router
from services.mavlink_bridge import MAVLinkBridge
from services.mavlink_router import get_router
from services.websocket_manager import websocket_manager
from services.preferences import get_preferences
from services.serial_detector import get_detector
from services.gstreamer_service import init_gstreamer_service, get_gstreamer_service
from services.vpn_service import init_vpn_service, get_vpn_service
from api.routes import mavlink, system
from api.routes import router as router_routes
from api.routes import video as video_routes
from api.routes import network as network_routes
from api.routes import vpn as vpn_routes
from api.routes import status as status_routes

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
vpn_service = None

# Include routers
app.include_router(mavlink.router, prefix="/api/mavlink", tags=["mavlink"])
app.include_router(system.router, prefix="/api/system", tags=["system"])
app.include_router(router_routes.router)
app.include_router(video_routes.router)
app.include_router(network_routes.router)
app.include_router(vpn_routes.router)
app.include_router(status_routes.router)

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
        
        # Send initial VPN status
        if vpn_service:
            await websocket_manager.broadcast("vpn_status", vpn_service.get_status())
        
        # Keep connection alive and handle client messages
        while True:
            data = await websocket.receive_text()
            
            # Handle ping/pong (ignore for now, not needed)
            # WebSocket has built-in keep-alive
                
    except WebSocketDisconnect:
        print("WebSocket client disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        websocket_manager.disconnect(websocket)

@app.get("/")
async def root():
    return {
        "name": "FPV Copilot Sky",
        "version": "1.0.0",
        "status": "running"
    }

async def periodic_stats_broadcast():
    """Periodically broadcast router stats via WebSocket."""
    counter = 0
    while True:
        await asyncio.sleep(1)
        counter += 1
        
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
                    get_user_permissions
                )
                
                status_data = {
                    "success": True,
                    "backend": {
                        "running": True,
                        "python_deps": check_python_dependencies(),
                        "system": check_system_info(),
                        "app_version": get_app_version()
                    },
                    "frontend": {
                        "npm_deps": check_npm_dependencies(),
                        "frontend_version": get_frontend_version()
                    },
                    "permissions": get_user_permissions(),
                    "timestamp": int(time.time())
                }
                await websocket_manager.broadcast("status", status_data)
            
            # Network status every 10 seconds
            if counter % 10 == 0:
                from services.network_service import get_network_service
                network_service = get_network_service()
                network_status = await network_service.get_status()
                await websocket_manager.broadcast("network_status", {"success": True, **network_status})
            
            # System resources (CPU/Memory) every 3 seconds
            if counter % 3 == 0:
                from services.system_service import SystemService
                await websocket_manager.broadcast("system_resources", {
                    "cpu": SystemService.get_cpu_info(),
                    "memory": SystemService.get_memory_info()
                })
            
            # Services status every 5 seconds
            if counter % 5 == 0:
                from services.system_service import SystemService
                services = SystemService.get_services_status()
                await websocket_manager.broadcast("system_services", {
                    "services": services,
                    "count": len(services)
                })
            
        except Exception as e:
            logger.error(f"Error in periodic broadcast: {e}")
            pass


def auto_connect_serial():
    """
    Auto-detect and connect to flight controller.
    Runs in a separate thread to not block startup.
    """
    global mavlink_service, preferences_service
    
    prefs = preferences_service
    serial_config = prefs.get_serial_config()
    
    if not serial_config.auto_connect:
        print("⏭️ Auto-connect disabled in preferences")
        return
    
    # If we have a saved successful connection, try that first
    if serial_config.last_successful and serial_config.port:
        print(f"🔄 Trying saved connection: {serial_config.port} @ {serial_config.baudrate}")
        result = mavlink_service.connect(serial_config.port, serial_config.baudrate)
        if result["success"]:
            print(f"✅ Auto-connected to {serial_config.port}")
            return
        print(f"⚠️ Saved connection failed, scanning for flight controller...")
    
    # Auto-detect flight controller
    detector = get_detector()
    detection = detector.detect_flight_controller(
        preferred_port=serial_config.port,
        preferred_baudrate=serial_config.baudrate
    )
    
    if detection:
        # Connect with detected settings
        result = mavlink_service.connect(detection["port"], detection["baudrate"])
        if result["success"]:
            # Save successful connection
            prefs.set_serial_config(
                port=detection["port"],
                baudrate=detection["baudrate"],
                successful=True
            )
            print(f"✅ Auto-connected and saved: {detection['port']} @ {detection['baudrate']}")
        else:
            print(f"⚠️ Detection succeeded but connection failed: {result['message']}")
    else:
        print("⚠️ No flight controller found - waiting for manual connection")


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global mavlink_service, router_service, preferences_service, video_service, vpn_service
    loop = asyncio.get_event_loop()
    
    # Initialize preferences first
    preferences_service = get_preferences()
    
    # Create router for additional outputs (uses preferences for config)
    router_service = get_router()
    
    # Create MAVLink bridge
    mavlink_service = MAVLinkBridge(websocket_manager, loop)
    
    # Connect router to bridge for forwarding
    mavlink_service.set_router(router_service)
    
    # Initialize video streaming service
    video_service = init_gstreamer_service(websocket_manager, loop)
    video_routes.set_video_service(video_service)
    
    # Initialize VPN service
    vpn_service = init_vpn_service(websocket_manager, loop)
    vpn_routes.set_vpn_service(vpn_service)
    
    # Auto-connect to VPN on startup (if not already connected)
    def auto_connect_vpn():
        try:
            time.sleep(2)  # Wait for system to stabilize
            status = vpn_service.get_status()
            if status.get('installed') and status.get('authenticated') and not status.get('connected'):
                logger.info("Attempting auto-connect to VPN...")
                result = vpn_service.connect()
                if result.get('success'):
                    logger.info("VPN auto-connect successful")
                    # Broadcast updated status
                    asyncio.run_coroutine_threadsafe(
                        websocket_manager.broadcast("vpn_status", vpn_service.get_status()),
                        loop
                    )
                elif result.get('needs_auth'):
                    logger.info("VPN requires authentication")
        except Exception as e:
            logger.error(f"Error during VPN auto-connect: {e}")
    
    # Start auto-connect in background thread
    vpn_thread = threading.Thread(target=auto_connect_vpn, daemon=True)
    vpn_thread.start()
    
    # Load video config from preferences
    video_config = preferences_service.get_video_config()
    streaming_config = preferences_service.get_streaming_config()
    if video_config or streaming_config:
        video_service.configure(
            video_config=video_config,
            streaming_config=streaming_config
        )
    
    # Set callback to broadcast router status changes via WebSocket (for immediate updates)
    def broadcast_router_status():
        try:
            outputs = router_service.get_outputs_list()
            asyncio.run_coroutine_threadsafe(
                websocket_manager.broadcast("router_status", outputs),
                loop
            )
        except:
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
        def start_video():
            import time
            time.sleep(2)  # Wait for system to settle
            if video_service.is_available():
                result = video_service.start()
                if result["success"]:
                    print("🎥 Video streaming auto-started")
                else:
                    print(f"⚠️ Video auto-start failed: {result['message']}")
        
        video_thread = threading.Thread(target=start_video, daemon=True, name="VideoAutoStart")
        video_thread.start()
    
    # Start auto-connect in background thread (non-blocking)
    auto_connect_thread = threading.Thread(
        target=auto_connect_serial,
        daemon=True,
        name="AutoConnect"
    )
    auto_connect_thread.start()
    
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    print("🛑 FPV Copilot Sky shutting down...")
    if video_service:
        video_service.shutdown()
    if router_service:
        router_service.shutdown()
    if mavlink_service and mavlink_service.is_connected():
        mavlink_service.disconnect()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
