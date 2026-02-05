"""
Network API Routes
Endpoints for WiFi, modem, and network priority management
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from services.network_service import get_network_service
from services.hilink_service import get_hilink_service

router = APIRouter(prefix="/api/network", tags=["network"])


class WiFiConnectRequest(BaseModel):
    ssid: str
    password: Optional[str] = None


class PriorityModeRequest(BaseModel):
    mode: str  # 'wifi' or 'modem'


class ForgetConnectionRequest(BaseModel):
    name: str


class NetworkModeRequest(BaseModel):
    mode: str  # '00'=Auto, '01'=2G, '02'=3G, '03'=4G


@router.get("/status")
async def get_network_status():
    """Get overall network status including interfaces, routes, and modem info"""
    service = get_network_service()
    status = await service.get_status()
    return {"success": True, **status}


@router.get("/interfaces")
async def get_interfaces():
    """Get list of all network interfaces"""
    service = get_network_service()
    interfaces = await service.get_interfaces()
    return {"success": True, "interfaces": interfaces}


@router.get("/wifi/networks")
async def get_wifi_networks():
    """Scan and return available WiFi networks"""
    service = get_network_service()
    networks = await service.get_wifi_networks()
    return {"success": True, "networks": networks}


@router.post("/wifi/connect")
async def connect_wifi(request: WiFiConnectRequest):
    """Connect to a WiFi network"""
    service = get_network_service()
    result = await service.connect_wifi(request.ssid, request.password)
    if result.get("success"):
        return result
    raise HTTPException(status_code=400, detail=result.get("error", "Connection failed"))


@router.post("/wifi/disconnect")
async def disconnect_wifi():
    """Disconnect from current WiFi network"""
    service = get_network_service()
    result = await service.disconnect_wifi()
    if result.get("success"):
        return result
    raise HTTPException(status_code=400, detail=result.get("error", "Disconnect failed"))


@router.get("/wifi/saved")
async def get_saved_connections():
    """Get list of saved network connections"""
    service = get_network_service()
    connections = await service.get_saved_connections()
    return {"success": True, "connections": connections}


@router.post("/wifi/forget")
async def forget_connection(request: ForgetConnectionRequest):
    """Delete a saved connection"""
    service = get_network_service()
    result = await service.forget_connection(request.name)
    if result.get("success"):
        return result
    raise HTTPException(status_code=400, detail=result.get("error", "Failed to delete"))


@router.get("/modem")
async def get_modem_info():
    """Get modem status and info"""
    service = get_network_service()
    info = await service.get_modem_info()
    return {"success": True, **info}


@router.get("/routes")
async def get_routes():
    """Get current routing table"""
    service = get_network_service()
    routes = await service.get_routes()
    return {"success": True, "routes": routes}


@router.post("/priority")
async def set_priority_mode(request: PriorityModeRequest):
    """
    Set network priority mode
    
    Args:
        mode: 'wifi' (WiFi primary) or 'modem' (4G primary)
    """
    if request.mode not in ['wifi', 'modem']:
        raise HTTPException(status_code=400, detail="Mode must be 'wifi' or 'modem'")
    
    service = get_network_service()
    result = await service.set_connection_priority(request.mode)
    
    if result.get("success"):
        return result
    raise HTTPException(status_code=400, detail=result.get("error", "Failed to set priority"))


# =====================
# HiLink Modem Endpoints
# =====================

@router.get("/hilink/status")
async def get_hilink_status():
    """Get full HiLink modem status including signal, network, traffic"""
    service = get_hilink_service()
    status = await service.get_full_status()
    return {"success": status.get('available', False), **status}


@router.get("/hilink/device")
async def get_hilink_device():
    """Get HiLink modem device information"""
    service = get_hilink_service()
    info = await service.get_device_info()
    if info:
        return {"success": True, **info}
    raise HTTPException(status_code=503, detail=service.last_error or "Could not connect to modem")


@router.get("/hilink/signal")
async def get_hilink_signal():
    """Get HiLink modem signal information"""
    service = get_hilink_service()
    info = await service.get_signal_info()
    if info:
        return {"success": True, **info}
    raise HTTPException(status_code=503, detail=service.last_error or "Could not connect to modem")


@router.get("/hilink/network")
async def get_hilink_network():
    """Get HiLink modem network/carrier information"""
    service = get_hilink_service()
    info = await service.get_network_info()
    if info:
        return {"success": True, **info}
    raise HTTPException(status_code=503, detail=service.last_error or "Could not connect to modem")


@router.get("/hilink/traffic")
async def get_hilink_traffic():
    """Get HiLink modem traffic statistics"""
    service = get_hilink_service()
    stats = await service.get_traffic_stats()
    if stats:
        return {"success": True, **stats}
    raise HTTPException(status_code=503, detail=service.last_error or "Could not connect to modem")


@router.get("/hilink/mode")
async def get_hilink_mode():
    """Get HiLink modem network mode settings"""
    service = get_hilink_service()
    mode = await service.get_network_mode()
    if mode:
        return {"success": True, **mode}
    raise HTTPException(status_code=503, detail=service.last_error or "Could not connect to modem")


@router.post("/hilink/mode")
async def set_hilink_mode(request: NetworkModeRequest):
    """
    Set HiLink modem network mode
    
    Modes:
    - '00': Auto (4G/3G/2G)
    - '01': 2G Only
    - '02': 3G Only
    - '03': 4G Only
    """
    valid_modes = ['00', '01', '02', '03']
    if request.mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Mode must be one of: {valid_modes}")
    
    service = get_hilink_service()
    result = await service.set_network_mode(request.mode)
    
    if result:
        return {"success": True, "message": f"Network mode set to {request.mode}"}
    raise HTTPException(status_code=500, detail=service.last_error or "Failed to set network mode")


@router.post("/hilink/reboot")
async def reboot_hilink():
    """Reboot the HiLink modem"""
    service = get_hilink_service()
    result = await service.reboot()
    
    if result:
        return {"success": True, "message": "Modem is rebooting"}
    raise HTTPException(status_code=500, detail=service.last_error or "Failed to reboot modem")


# =============================
# LTE Band Management Endpoints
# =============================

class LTEBandRequest(BaseModel):
    preset: Optional[str] = None  # 'all', 'orange_spain', 'urban', 'rural', etc.
    custom_mask: Optional[int] = None  # Custom band mask


@router.get("/hilink/band")
async def get_current_band():
    """Get current LTE band information"""
    service = get_hilink_service()
    band = await service.get_current_band()
    if band:
        return {"success": True, **band}
    raise HTTPException(status_code=503, detail=service.last_error or "Could not get band info")


@router.get("/hilink/band/presets")
async def get_band_presets():
    """Get available LTE band presets for Spain/Orange"""
    service = get_hilink_service()
    presets = service.get_band_presets()
    return {"success": True, **presets}


@router.post("/hilink/band")
async def set_lte_band(request: LTEBandRequest):
    """
    Set LTE band configuration
    
    Use preset names:
    - 'all': All bands (auto)
    - 'orange_spain': B3+B7+B20 (Orange optimal)
    - 'urban': B3+B7 (high speed)
    - 'rural': B20 only (best coverage)
    - 'balanced': B3+B20
    - 'b3_only', 'b7_only', 'b20_only': Single band
    
    Or provide custom_mask as integer for custom band selection.
    """
    if not request.preset and request.custom_mask is None:
        raise HTTPException(status_code=400, detail="Provide either preset or custom_mask")
    
    service = get_hilink_service()
    result = await service.set_lte_band(preset=request.preset, custom_mask=request.custom_mask)
    
    if result.get('success'):
        return result
    raise HTTPException(status_code=500, detail=result.get('error', 'Failed to set band'))


# =============================
# Video Quality Endpoints
# =============================

@router.get("/hilink/video-quality")
async def get_video_quality():
    """
    Get video streaming quality assessment based on current signal
    
    Returns quality rating, recommended bitrate, and streaming recommendations.
    """
    service = get_hilink_service()
    assessment = await service.get_video_quality_assessment()
    return {"success": assessment.get('available', False), **assessment}


@router.get("/hilink/status/enhanced")
async def get_enhanced_status():
    """Get full modem status with video optimization data"""
    service = get_hilink_service()
    status = await service.get_full_status_enhanced()
    return {"success": status.get('available', False), **status}


# =============================
# APN Configuration Endpoints  
# =============================

class APNRequest(BaseModel):
    preset: Optional[str] = None  # 'orange', 'orangeworld', 'simyo', 'internet'
    custom_apn: Optional[str] = None


@router.get("/hilink/apn")
async def get_apn_settings():
    """Get current APN settings and available presets"""
    service = get_hilink_service()
    settings = await service.get_apn_settings()
    return {"success": True, **settings}


@router.post("/hilink/apn")
async def set_apn(request: APNRequest):
    """
    Set APN configuration
    
    Presets for Spain:
    - 'orange': Standard Orange APN
    - 'orangeworld': Orange data APN
    - 'simyo': Simyo (uses Orange network)
    - 'internet': Generic APN
    """
    if not request.preset and not request.custom_apn:
        raise HTTPException(status_code=400, detail="Provide either preset or custom_apn")
    
    service = get_hilink_service()
    result = await service.set_apn(preset=request.preset, custom_apn=request.custom_apn)
    
    if result.get('success'):
        return result
    raise HTTPException(status_code=500, detail=result.get('error', 'Failed to set APN'))


# =============================
# Network Control Endpoints
# =============================

class RoamingRequest(BaseModel):
    enabled: bool


@router.post("/hilink/reconnect")
async def reconnect_network():
    """Force network reconnection to search for better cell tower"""
    service = get_hilink_service()
    result = await service.reconnect_network()
    
    if result.get('success'):
        return result
    raise HTTPException(status_code=500, detail=result.get('message', 'Reconnection failed'))


@router.post("/hilink/roaming")
async def set_roaming(request: RoamingRequest):
    """Enable or disable roaming"""
    service = get_hilink_service()
    result = await service.set_roaming(request.enabled)
    
    if result.get('success'):
        return result
    raise HTTPException(status_code=500, detail=service.last_error or "Failed to set roaming")


# =============================
# Video Mode Profile Endpoints
# =============================

@router.get("/hilink/video-mode")
async def get_video_mode_status():
    """Check if video mode is currently active"""
    service = get_hilink_service()
    return {
        "success": True,
        "video_mode_active": service.video_mode_active,
    }


@router.post("/hilink/video-mode/enable")
async def enable_video_mode():
    """
    Enable video-optimized modem settings:
    - Forces 4G Only mode
    - Optimizes for low latency
    - Saves original settings for restore
    """
    service = get_hilink_service()
    result = await service.enable_video_mode()
    
    if result.get('success'):
        return result
    raise HTTPException(status_code=500, detail=result.get('error', 'Failed to enable video mode'))


@router.post("/hilink/video-mode/disable")
async def disable_video_mode():
    """Disable video mode and restore original settings"""
    service = get_hilink_service()
    result = await service.disable_video_mode()
    
    if result.get('success'):
        return result
    raise HTTPException(status_code=500, detail=result.get('error', 'Failed to disable video mode'))


# =============================
# Flight Session Endpoints
# =============================

@router.get("/hilink/flight-session")
async def get_flight_session():
    """Get current flight session status and statistics"""
    service = get_hilink_service()
    status = await service.get_flight_session_status()
    return {"success": True, **status}


@router.post("/hilink/flight-session/start")
async def start_flight_session():
    """Start recording flight session statistics"""
    service = get_hilink_service()
    result = await service.start_flight_session()
    return result


@router.post("/hilink/flight-session/stop")
async def stop_flight_session():
    """Stop recording and get session statistics summary"""
    service = get_hilink_service()
    result = await service.stop_flight_session()
    
    if result.get('success'):
        return result
    raise HTTPException(status_code=400, detail=result.get('error', 'No active session'))


@router.post("/hilink/flight-session/sample")
async def record_flight_sample():
    """Record a signal quality sample (call periodically during flight)"""
    service = get_hilink_service()
    result = await service.record_flight_sample()
    
    if result.get('success'):
        return result
    raise HTTPException(status_code=400, detail=result.get('error', 'No active session'))


# =============================
# Latency Monitoring Endpoints
# =============================

class LatencyTestRequest(BaseModel):
    host: Optional[str] = None  # Default: 8.8.8.8
    count: Optional[int] = None  # Default: 3


@router.get("/hilink/latency")
async def measure_latency():
    """Measure current network latency and jitter"""
    service = get_hilink_service()
    result = await service.measure_latency()
    
    if result.get('success'):
        return result
    raise HTTPException(status_code=500, detail=result.get('error', 'Latency test failed'))


@router.post("/hilink/latency")
async def measure_latency_custom(request: LatencyTestRequest):
    """Measure latency to a custom host"""
    service = get_hilink_service()
    result = await service.measure_latency(host=request.host, count=request.count)
    
    if result.get('success'):
        return result
    raise HTTPException(status_code=500, detail=result.get('error', 'Latency test failed'))
