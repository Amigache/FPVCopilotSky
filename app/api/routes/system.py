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
