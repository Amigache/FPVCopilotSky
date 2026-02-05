"""
System API Routes
Endpoints for system information
"""

from fastapi import APIRouter
from services.system_service import SystemService

router = APIRouter()

@router.get("/info")
async def get_system_info():
    """Get system information"""
    return SystemService.get_system_info()

@router.get("/ports")
async def get_available_ports():
    """Get list of available serial ports"""
    ports = SystemService.get_available_serial_ports()
    
    return {
        "ports": ports,
        "count": len(ports)
    }

@router.get("/services")
async def get_services_status():
    """Get status of monitored systemd services (fpvcopilot-sky, nginx)"""
    services = SystemService.get_services_status()
    
    return {
        "services": services,
        "count": len(services)
    }
