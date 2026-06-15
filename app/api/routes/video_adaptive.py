"""Video adaptive quality control routes"""

import logging

from fastapi import APIRouter, HTTPException, Request

from app.services.preferences import get_preferences

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video", tags=["video"])


@router.get("/config/auto-adaptive-bitrate")
async def get_auto_adaptive_bitrate():
    """Get auto-adaptive bitrate configuration"""
    prefs = get_preferences()
    enabled = prefs.get_auto_adaptive_bitrate()

    return {
        "enabled": enabled,
        "description": (
            "Auto-adaptive bitrate adjusts video quality based on network conditions "
            "(SINR, RTT, jitter, packet loss). Recommended for 4G/LTE connections. "
            "Disable for manual control on stable networks (WiFi/Ethernet)."
        ),
    }


@router.post("/config/auto-adaptive-bitrate")
async def set_auto_adaptive_bitrate(request: Request):
    """Enable or disable auto-adaptive bitrate"""
    try:
        body = await request.json()
        enabled = body.get("enabled", True)

        prefs = get_preferences()
        prefs.set_auto_adaptive_bitrate(enabled)

        # If enabling, start the Network Event Bridge
        # If disabling, stop it
        from app.services.network_event_bridge import get_network_event_bridge

        bridge = get_network_event_bridge()

        if enabled:
            await bridge.start()
            message = "Auto-adaptive bitrate enabled. Network Event Bridge started."
        else:
            await bridge.stop()
            message = "Auto-adaptive bitrate disabled. You can now control bitrate manually."

        return {
            "success": True,
            "enabled": enabled,
            "message": message,
        }
    except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config/auto-adaptive-resolution")
async def get_auto_adaptive_resolution():
    """Get auto-adaptive resolution configuration"""
    prefs = get_preferences()
    enabled = prefs.get_auto_adaptive_resolution()

    return {
        "enabled": enabled,
        "description": (
            "Auto-adaptive resolution downscales video when network quality drops "
            "severely. Works together with bitrate adaptation to maintain smooth "
            "streaming. Disable if you need fixed resolution regardless of "
            "connection quality."
        ),
    }


@router.post("/config/auto-adaptive-resolution")
async def set_auto_adaptive_resolution(request: Request):
    """Enable or disable auto-adaptive resolution"""
    try:
        body = await request.json()
        enabled = body.get("enabled", True)

        prefs = get_preferences()
        prefs.set_auto_adaptive_resolution(enabled)

        return {
            "success": True,
            "enabled": enabled,
            "message": f"Auto-adaptive resolution {'enabled' if enabled else 'disabled'}.",
        }
    except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=str(e))
