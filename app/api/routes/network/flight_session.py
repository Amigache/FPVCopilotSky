"""
Flight Session - Network Performance Recording

This module handles flight session recording, which tracks network performance
metrics during flights for analysis and optimization.

Flight sessions record:
- Signal quality samples
- Latency measurements
- Connection stability
- Data usage statistics
"""

import asyncio
from fastapi import APIRouter, HTTPException
from app.providers.registry import get_provider_registry
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/flight-session/status")
async def get_flight_session_status():
    """
    Get current flight session status and statistics

    Flight session records network performance metrics during flights:
    - Signal quality samples
    - Latency measurements
    - Connection stability
    - Data usage

    Returns:
        Flight session statistics and status (active/stopped/no_session)
    """
    try:
        # Get default modem provider automatically (like flight-mode does)
        registry = get_provider_registry()
        provider = registry.get_modem_provider("huawei_e3372h")

        if not provider:
            return {"success": True, "status": "no_modem"}

        if hasattr(provider, "get_flight_session_status"):
            status = provider.get_flight_session_status()
            return {"success": True, **status}
        return {"success": True, "status": "no_session"}
    except Exception as e:
        logger.error(f"Error getting flight session status: {e}")
        return {"success": False, "error": str(e), "status": "error"}


@router.post("/flight-session/start")
async def start_flight_session():
    """
    Start recording flight session statistics

    Begins collecting network performance metrics for analysis.
    Call /sample periodically during flight to record data points.

    Returns:
        Result with success status and session info
    """
    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider("huawei_e3372h")

        if not provider:
            raise HTTPException(status_code=503, detail="Modem not available")

        if hasattr(provider, "start_flight_session"):
            result = provider.start_flight_session()
            return result
        raise HTTPException(status_code=500, detail="Flight session not supported by modem")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting flight session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/flight-session/stop")
async def stop_flight_session():
    """
    Stop recording and get session statistics summary

    Ends the flight session and returns complete statistics including:
    - Total duration
    - Average/min/max signal quality
    - Connection drops
    - Data transferred

    Returns:
        Session summary with aggregated statistics
    """
    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider("huawei_e3372h")

        if not provider:
            raise HTTPException(status_code=503, detail="Modem not available")

        if hasattr(provider, "stop_flight_session"):
            result = provider.stop_flight_session()
            if result and result.get("success"):
                return result
        raise HTTPException(status_code=400, detail="No active flight session")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping flight session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/flight-session/sample")
async def record_flight_sample():
    """
    Record a signal quality sample during flight

    Call this endpoint periodically (e.g., every 5-10 seconds) during
    flight to record current network conditions. Data is aggregated
    for the final session statistics.

    Returns:
        Sample recording result with current metrics
    """
    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider("huawei_e3372h")

        if not provider:
            return {"success": False, "message": "Modem not available"}

        if hasattr(provider, "record_flight_sample"):
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, provider.record_flight_sample)
            if result:
                if result.get("success"):
                    return result
                else:
                    # Session not active, return success=False instead of 400 error
                    return {
                        "success": False,
                        "message": result.get("message", "No active session"),
                    }
        return {"success": False, "message": "Flight session not available"}
    except Exception as e:
        logger.error(f"Error recording flight sample: {e}")
        return {"success": False, "message": str(e)}
