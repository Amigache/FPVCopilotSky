"""
ModemPool API Routes - Multi-modem management endpoints
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/modems")


class SelectModemRequest(BaseModel):
    interface: str


class SelectionModeRequest(BaseModel):
    mode: str  # "manual" | "best_score" | "best_sinr" | "best_latency"


def _get_pool():
    from app.services.modem_pool import get_modem_pool

    return get_modem_pool()


@router.get("")
async def list_all_modems():
    """List all detected modems (connected and disconnected)"""
    pool = _get_pool()
    modems = await pool.get_all_modems()
    return {
        "success": True,
        "modems": [m.to_dict() for m in modems],
        "count": len(modems),
    }


@router.get("/connected")
async def list_connected_modems():
    """List only currently connected modems"""
    pool = _get_pool()
    modems = await pool.get_connected_modems()
    return {
        "success": True,
        "modems": [m.to_dict() for m in modems],
        "count": len(modems),
    }


@router.get("/healthy")
async def list_healthy_modems():
    """List connected and healthy modems"""
    pool = _get_pool()
    modems = await pool.get_healthy_modems()
    return {
        "success": True,
        "modems": [m.to_dict() for m in modems],
        "count": len(modems),
    }


@router.get("/active")
async def get_active_modem():
    """Get currently active (selected) modem"""
    pool = _get_pool()
    modem = await pool.get_active_modem()
    return {
        "success": True,
        "modem": modem.to_dict() if modem else None,
    }


@router.get("/best")
async def get_best_modem():
    """Get modem with highest quality score"""
    pool = _get_pool()
    modem = await pool.get_best_modem()
    return {
        "success": True,
        "modem": modem.to_dict() if modem else None,
    }


@router.get("/status")
async def get_pool_status():
    """Get full pool summary"""
    pool = _get_pool()
    status = await pool.get_status()
    return {"success": True, **status}


@router.get("/{interface}")
async def get_modem(interface: str):
    """Get info for a specific modem interface"""
    pool = _get_pool()
    modem = await pool.get_modem(interface)
    if not modem:
        return {"success": False, "error": f"Modem {interface} not found"}
    return {"success": True, "modem": modem.to_dict()}


@router.post("/select")
async def select_modem(request: SelectModemRequest):
    """Manually select a modem as active"""
    pool = _get_pool()
    success = await pool.select_modem(request.interface, reason="manual")
    return {
        "success": success,
        "active_modem": request.interface if success else None,
        "message": f"Switched to {request.interface}" if success else f"Failed to switch to {request.interface}",
    }


@router.post("/refresh")
async def refresh_modems():
    """Force immediate re-detection of all modems"""
    pool = _get_pool()
    await pool.refresh()
    modems = await pool.get_all_modems()
    return {
        "success": True,
        "message": "Modem detection refreshed",
        "modems": [m.to_dict() for m in modems],
        "count": len(modems),
    }


@router.post("/mode")
async def set_selection_mode(request: SelectionModeRequest):
    """Set modem auto-selection mode"""
    valid_modes = ["manual", "best_score", "best_sinr", "best_latency", "round_robin"]
    if request.mode not in valid_modes:
        return {
            "success": False,
            "error": f"Invalid mode '{request.mode}'. Valid: {valid_modes}",
        }
    pool = _get_pool()
    success = pool.set_selection_mode(request.mode)
    return {
        "success": success,
        "mode": request.mode,
        "message": f"Selection mode set to {request.mode}" if success else "Failed to set mode",
    }
