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
    """Get status of monitored systemd services (fpvcopilot-sky, nginx) with resource usage"""
    services = SystemService.get_services_status()
    
    return {
        "services": services,
        "count": len(services)
    }

@router.get("/memory")
async def get_memory_info():
    """Get RAM memory usage information"""
    return SystemService.get_memory_info()

@router.get("/cpu")
async def get_cpu_info():
    """Get CPU usage and information"""
    return SystemService.get_cpu_info()

@router.get("/resources")
async def get_system_resources():
    """Get combined CPU and memory information"""
    return {
        "cpu": SystemService.get_cpu_info(),
        "memory": SystemService.get_memory_info()
    }
