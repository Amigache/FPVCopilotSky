"""
System API Routes
Endpoints for system information
"""

from fastapi import APIRouter, BackgroundTasks, Request
from app.services.system_service import SystemService
from app.i18n import get_language_from_request, translate

router = APIRouter()


@router.get("/version/current")
async def get_current_version():
    """Get current installed version"""
    return SystemService.get_version()


@router.get("/version/check")
async def check_for_updates():
    """Check for updates on GitHub"""
    return SystemService.check_for_updates()


@router.get("/version/can-rollback")
async def can_rollback():
    """Check if rollback to previous version is available"""
    return SystemService.can_rollback()


@router.post("/version/update")
async def apply_system_update(background_tasks: BackgroundTasks):
    """
    Apply system update to the latest version from GitHub.

    The update process runs synchronously (git fetch, checkout, pip install,
    npm build) and returns a response BEFORE restarting the service.
    The restart is scheduled as a BackgroundTask so the client receives
    the success response first.
    """
    result = SystemService.apply_update(do_restart=False)
    if result.get("success"):
        background_tasks.add_task(SystemService._restart_service_delayed)
    return result


@router.post("/version/rollback")
async def rollback_to_previous_version(background_tasks: BackgroundTasks):
    """
    Rollback to the previous version of the system.

    The rollback process runs synchronously (git checkout, pip install,
    npm build) and returns a response BEFORE restarting the service.
    The restart is scheduled as a BackgroundTask so the client receives
    the success response first.
    """
    result = SystemService.rollback_to_previous_version(do_restart=False)
    if result.get("success"):
        background_tasks.add_task(SystemService._restart_service_delayed)
    return result


@router.get("/info")
async def get_system_info():
    """Get system information"""
    return SystemService.get_system_info()


@router.get("/ports")
async def get_available_ports():
    """Get list of available serial ports"""
    ports = SystemService.get_available_serial_ports()

    return {"ports": ports, "count": len(ports)}


@router.get("/services")
async def get_services_status():
    """Get status of monitored systemd services (fpvcopilot-sky, nginx) with resource usage"""
    services = SystemService.get_services_status()

    return {"services": services, "count": len(services)}


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
        "memory": SystemService.get_memory_info(),
    }


@router.get("/processes/cpu")
async def get_top_cpu_processes(limit: int = 10):
    """
    Get top processes by CPU usage

    Args:
        limit: Maximum number of processes to return (default: 10, max: 50)
    """
    # Limit the limit parameter to prevent excessive processing
    limit = min(limit, 50)
    processes = SystemService.get_top_processes_by_cpu(limit)
    return {"processes": processes, "count": len(processes)}


@router.get("/processes/memory")
async def get_top_memory_processes(limit: int = 10):
    """
    Get top processes by memory (RAM) usage

    Args:
        limit: Maximum number of processes to return (default: 10, max: 50)
    """
    # Limit the limit parameter to prevent excessive processing
    limit = min(limit, 50)
    processes = SystemService.get_top_processes_by_memory(limit)
    return {"processes": processes, "count": len(processes)}


@router.get("/preferences")
async def get_preferences_all():
    """Get all preferences"""
    try:
        from app.services.preferences import get_preferences

        prefs = get_preferences()
        return prefs.get_all_preferences()
    except Exception as e:
        return {"error": str(e)}


@router.post("/preferences")
async def update_preferences(request: Request):
    """Update preferences (partial update)"""
    try:
        from app.services.preferences import get_preferences

        prefs = get_preferences()
        data = await request.json()

        # Update each preference section provided
        for key, value in data.items():
            if key == "flight_session":
                # Deep merge flight_session preferences
                current = prefs.get_all_preferences().get("flight_session", {})
                current.update(value)
                prefs._preferences["flight_session"] = current
            elif key == "serial":
                if "port" in value and "baudrate" in value:
                    prefs.set_serial_config(value["port"], value["baudrate"])
                if "auto_connect" in value:
                    prefs.set_serial_auto_connect(value["auto_connect"])
            elif key == "video":
                prefs.set_video_config(value)
            elif key == "streaming":
                prefs.set_streaming_config(value)
            elif key == "vpn":
                prefs.set_vpn_config(value)
            elif key == "ui":
                for ui_key, ui_value in value.items():
                    prefs.set_ui_preference(ui_key, ui_value)
            else:
                # Generic update for other keys
                prefs._preferences[key] = value

        prefs._save()
        return {"success": True, "message": "Preferences updated"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/preferences/reset")
async def reset_preferences(request: Request):
    """Reset all preferences to defaults"""
    try:
        lang = get_language_from_request(request)
        from app.services.preferences import get_preferences

        prefs = get_preferences()
        success = prefs.reset_preferences()

        if success:
            return {
                "success": True,
                "message": translate("system.preferences_reset_success", lang),
            }
        else:
            return {
                "success": False,
                "message": translate("system.preferences_reset_failed", lang),
            }
    except Exception as e:
        lang = get_language_from_request(request)
        return {
            "success": False,
            "message": translate("system.preferences_reset_error", lang, error=str(e)),
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
            "message": translate("system.restart_backend_error", lang, error=str(e)),
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
            "message": translate("system.restart_frontend_error", lang, error=str(e)),
        }


@router.get("/logs/backend")
async def get_backend_logs(lines: int = 100, request: Request = None):
    """Get backend service logs (journalctl)"""
    try:
        logs = SystemService.get_backend_logs(lines)
        return {
            "success": True,
            "logs": logs,
            "lines": len(logs.split("\n")) if logs else 0,
        }
    except Exception as e:
        lang = get_language_from_request(request) if request else "en"
        return {
            "success": False,
            "message": translate("system.backend_logs_error", lang, error=str(e)),
            "logs": "",
        }


@router.get("/logs/frontend")
async def get_frontend_logs(lines: int = 100, request: Request = None):
    """Get frontend logs (nginx access/error logs)"""
    try:
        logs = SystemService.get_frontend_logs(lines)
        return {
            "success": True,
            "logs": logs,
            "lines": len(logs.split("\n")) if logs else 0,
        }
    except Exception as e:
        lang = get_language_from_request(request) if request else "en"
        return {
            "success": False,
            "message": translate("system.frontend_logs_error", lang, error=str(e)),
            "logs": "",
        }


@router.get("/board")
async def get_board_info(request: Request):
    """Get detected board/platform information with hardware specs and supported features"""
    try:
        lang = get_language_from_request(request)
        from app.providers.board import BoardRegistry

        registry = BoardRegistry()
        detected_board = registry.get_detected_board()

        if detected_board:
            return {"success": True, "data": detected_board.to_dict()}
        else:
            return {
                "success": False,
                "message": translate("system.board_not_detected", lang),
                "data": None,
            }
    except Exception as e:
        lang = get_language_from_request(request)
        return {
            "success": False,
            "message": translate("system.board_info_error", lang, error=str(e)),
            "data": None,
        }


@router.get("/video-devices")
async def get_video_devices():
    """Get all detected video devices with capabilities from all source providers"""
    from app.services.video_device_service import get_video_device_service

    service = get_video_device_service()
    return service.get_scan_info()


@router.post("/video-devices/scan")
async def rescan_video_devices():
    """Force a rescan of all video devices"""
    from app.services.video_device_service import get_video_device_service

    service = get_video_device_service()
    service.scan_devices()
    return service.get_scan_info()
