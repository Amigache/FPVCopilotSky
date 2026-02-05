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
