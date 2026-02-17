"""
Network Event Bridge - Self-healing Streaming

This module provides the network-video event bridge that automatically
adapts video encoding parameters based on real-time network conditions.

Features:
- Cellular signal monitoring (SINR, RSRQ, cell changes)
- Composite quality score calculation
- Automatic video parameter adaptation
- Event history and telemetry
"""

from fastapi import APIRouter, HTTPException
from app.services.network_event_bridge import get_network_event_bridge
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/bridge/status")
async def get_bridge_status():
    """
    Get network-video event bridge status.

    Returns composite quality score, cell state, latency metrics,
    and recent network events with video actions taken.
    """
    try:
        bridge = get_network_event_bridge()
        return {"success": True, **bridge.get_status()}
    except Exception as e:
        logger.error(f"Error getting bridge status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bridge/start")
async def start_event_bridge():
    """
    Start the network-video event bridge.

    Begins monitoring cellular signal metrics and automatically
    adapts video encoding parameters based on network conditions.
    """
    try:
        bridge = get_network_event_bridge()
        await bridge.start()
        return {"success": True, "message": "Network event bridge started"}
    except Exception as e:
        logger.error(f"Error starting bridge: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bridge/stop")
async def stop_event_bridge():
    """Stop the network-video event bridge"""
    try:
        bridge = get_network_event_bridge()
        await bridge.stop()
        return {"success": True, "message": "Network event bridge stopped"}
    except Exception as e:
        logger.error(f"Error stopping bridge: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bridge/events")
async def get_bridge_events(last_n: int = 100):
    """
    Get network event history.

    Shows cell changes, SINR drops, jitter spikes, and the
    video actions that were triggered in response.
    """
    try:
        bridge = get_network_event_bridge()
        events = bridge.get_event_history(last_n)
        return {"success": True, "events": events, "count": len(events)}
    except Exception as e:
        logger.error(f"Error getting bridge events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bridge/quality-score")
async def get_quality_score():
    """
    Get composite network quality score (0-100).

    Weighted combination of SINR, RSRQ, jitter, and packet loss.
    Includes recommended bitrate, resolution, and framerate.
    """
    try:
        bridge = get_network_event_bridge()
        status = bridge.get_status()
        return {"success": True, **status.get("quality_score", {})}
    except Exception as e:
        logger.error(f"Error getting quality score: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bridge/clear-events")
async def clear_bridge_events():
    """
    Clear network event history.

    Useful when changing network mode (e.g., from modem to WiFi)
    to start with a fresh event log for the new connection type.
    """
    try:
        bridge = get_network_event_bridge()
        bridge.clear_events()
        return {"success": True, "message": "Event history cleared"}
    except Exception as e:
        logger.error(f"Error clearing bridge events: {e}")
        raise HTTPException(status_code=500, detail=str(e))
