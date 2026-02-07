"""
System API Routes
Endpoints for system information
"""

from fastapi import APIRouter, Request
from services.system_service import SystemService
from app.i18n import get_language_from_request, translate

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


@router.post("/preferences/reset")
async def reset_preferences(request: Request):
    """Reset all preferences to defaults"""
    try:
        lang = get_language_from_request(request)
        from services.preferences import get_preferences
        prefs = get_preferences()
        success = prefs.reset_preferences()
        
        if success:
            return {
                "success": True,
                "message": translate("system.preferences_reset_success", lang)
            }
        else:
            return {
                "success": False,
                "message": translate("system.preferences_reset_failed", lang)
            }
    except Exception as e:
        lang = get_language_from_request(request)
        return {
            "success": False,
            "message": translate("system.preferences_reset_error", lang, error=str(e))
        }


@router.post("/restart/backend")
async def restart_backend(request: Request):
    """Restart backend service (fpvcopilot-sky)"""
    try:
        result = SystemService.restart_backend()
        return result
    except Exception as e:
        lang = get_language_from_request(request)
        return {
            "success": False,
            "message": translate("system.restart_backend_error", lang, error=str(e))
        }


@router.post("/restart/frontend")
async def restart_frontend(request: Request):
    """Rebuild frontend (requires manual deployment)"""
    try:
        result = SystemService.restart_frontend()
        return result
    except Exception as e:
        lang = get_language_from_request(request)
        return {
            "success": False,
            "message": translate("system.restart_frontend_error", lang, error=str(e))
        }


@router.get("/logs/backend")
async def get_backend_logs(lines: int = 100, request: Request = None):
    """Get backend service logs (journalctl)"""
    try:
        logs = SystemService.get_backend_logs(lines)
        return {
            "success": True,
            "logs": logs,
            "lines": len(logs.split('\n')) if logs else 0
        }
    except Exception as e:
        lang = get_language_from_request(request) if request else "en"
        return {
            "success": False,
            "message": translate("system.backend_logs_error", lang, error=str(e)),
            "logs": ""
        }


@router.get("/logs/frontend")
async def get_frontend_logs(lines: int = 100, request: Request = None):
    """Get frontend logs (nginx access/error logs)"""
    try:
        logs = SystemService.get_frontend_logs(lines)
        return {
            "success": True,
            "logs": logs,
            "lines": len(logs.split('\n')) if logs else 0
        }
    except Exception as e:
        lang = get_language_from_request(request) if request else "en"
        return {
            "success": False,
            "message": translate("system.frontend_logs_error", lang, error=str(e)),
            "logs": ""
        }


@router.get("/board")
async def get_board_info(request: Request):
    """Get detected board/platform information with hardware specs and supported features"""
    try:
        lang = get_language_from_request(request)
        from providers.board import BoardRegistry

        registry = BoardRegistry()
        detected_board = registry.get_detected_board()
        
        if detected_board:
            return {
                "success": True,
                "data": detected_board.to_dict()
            }
        else:
            return {
                "success": False,
                "message": translate("system.board_not_detected", lang),
                "data": None
            }
    except Exception as e:
        lang = get_language_from_request(request)
        return {
            "success": False,
            "message": translate("system.board_info_error", lang, error=str(e)),
            "data": None
        }
