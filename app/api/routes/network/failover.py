"""
Auto-Failover - Automatic Network Switching

This module provides intelligent automatic network switching based on
latency and quality metrics. When network performance degrades, it
automatically switches to a backup interface.

Features:
- Latency-based switching
- Configurable thresholds and timings
- Preferred mode restoration
- Manual override capability
"""

from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from app.services.auto_failover import get_auto_failover, stop_auto_failover, NetworkMode
from app.services.latency_monitor import start_latency_monitoring
from app.services.preferences import get_preferences
from app.exceptions import FailoverError, NetworkException
from .common import PriorityModeRequest
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


async def set_priority_mode(request: PriorityModeRequest):
    """Internal helper to set priority mode (imported from status module)"""
    from .status import set_priority_mode as status_set_priority

    return await status_set_priority(request)


@router.post("/failover/start")
async def start_failover(initial_mode: str = "modem"):
    """
    Start automatic network failover

    Args:
        initial_mode: Initial network mode ('wifi' or 'modem')
    """
    try:
        # Parse initial mode
        mode = NetworkMode.MODEM if initial_mode == "modem" else NetworkMode.WIFI

        # Start latency monitoring if not already running
        await start_latency_monitoring()

        # Start auto-failover with switch callback
        failover = get_auto_failover()

        # Define switch callback
        async def switch_network(target_mode: NetworkMode) -> bool:
            try:
                # Call priority endpoint to switch
                request = PriorityModeRequest(mode=target_mode.value)
                result = await set_priority_mode(request)
                return result.get("success", False)
            except NetworkException as e:
                logger.error("Failover switch callback failed", extra=e.to_dict())
                return False

        # Set callback and start
        failover.switch_callback = switch_network
        await failover.start(initial_mode=mode)

        return {"success": True, "message": "Auto-failover started", "initial_mode": initial_mode}

    except FailoverError as e:
        logger.error("Failed to start auto-failover", extra=e.to_dict())
        raise HTTPException(status_code=500, detail="Could not start auto-failover")
    except NetworkException as e:
        logger.error("Network error starting failover", extra=e.to_dict())
        raise HTTPException(status_code=503, detail="Network service unavailable")


@router.post("/failover/stop")
async def stop_failover():
    """Stop automatic network failover"""
    try:
        await stop_auto_failover()
        return {"success": True, "message": "Auto-failover stopped"}
    except FailoverError as e:
        logger.error("Failed to stop auto-failover", extra=e.to_dict())
        raise HTTPException(status_code=500, detail="Could not stop auto-failover")


@router.get("/failover/status")
async def get_failover_status():
    """Get current auto-failover status and configuration"""
    try:
        failover = get_auto_failover()
        state = await failover.get_state()

        return {"success": True, **state}

    except FailoverError as e:
        logger.error("Failed to get failover status", extra=e.to_dict())
        raise HTTPException(status_code=500, detail="Could not retrieve failover status")


class FailoverConfigRequest(BaseModel):
    latency_threshold_ms: Optional[float] = None
    latency_check_window: Optional[int] = None
    switch_cooldown_s: Optional[float] = None
    restore_delay_s: Optional[float] = None
    preferred_mode: Optional[str] = None


class FailoverStartupPreferencesRequest(BaseModel):
    enabled: Optional[bool] = None
    preferred_mode: Optional[str] = None


@router.post("/failover/config")
async def update_failover_config(config: FailoverConfigRequest):
    """
    Update auto-failover configuration

    Args:
        latency_threshold_ms: Switch if latency exceeds this (default: 200)
        latency_check_window: Consecutive bad samples before switching (default: 15)
        switch_cooldown_s: Minimum time between switches (default: 30)
        restore_delay_s: Wait time before restoring preferred mode (default: 60)
        preferred_mode: Preferred network mode ('wifi' or 'modem', default: 'modem')
    """
    try:
        failover = get_auto_failover()

        # Build update dict
        updates = {}
        if config.latency_threshold_ms is not None:
            updates["latency_threshold_ms"] = config.latency_threshold_ms
        if config.latency_check_window is not None:
            updates["latency_check_window"] = config.latency_check_window
        if config.switch_cooldown_s is not None:
            updates["switch_cooldown_s"] = config.switch_cooldown_s
        if config.restore_delay_s is not None:
            updates["restore_delay_s"] = config.restore_delay_s
        if config.preferred_mode is not None:
            mode = NetworkMode.MODEM if config.preferred_mode == "modem" else NetworkMode.WIFI
            updates["preferred_mode"] = mode

        await failover.update_config(**updates)

        return {"success": True, "message": "Failover configuration updated", "updated": updates}

    except ValueError as e:
        logger.warning("Invalid failover config parameter", extra={"error": str(e)})
        raise HTTPException(status_code=400, detail="Invalid configuration parameter")
    except FailoverError as e:
        logger.error("Failed to update failover config", extra=e.to_dict())
        raise HTTPException(status_code=500, detail="Could not update failover configuration")


@router.get("/failover/preferences")
async def get_failover_startup_preferences():
    """Get persisted startup preferences for auto-failover."""
    try:
        prefs = get_preferences()
        net = prefs.get_network_config()
        return {
            "success": True,
            "enabled": bool(net.get("auto_failover_enabled", False)),
            "preferred_mode": str(net.get("auto_failover_preferred_mode", "modem")),
        }
    except FailoverError as e:
        logger.error("Failed to get failover preferences", extra=e.to_dict())
        raise HTTPException(status_code=500, detail="Could not retrieve failover preferences")


@router.post("/failover/preferences")
async def set_failover_startup_preferences(config: FailoverStartupPreferencesRequest):
    """Set persisted startup preferences for auto-failover."""
    try:
        updates = {}
        if config.enabled is not None:
            updates["auto_failover_enabled"] = bool(config.enabled)
        if config.preferred_mode is not None:
            mode = config.preferred_mode.lower()
            if mode not in ("wifi", "modem"):
                raise HTTPException(status_code=400, detail="preferred_mode must be 'wifi' or 'modem'")
            updates["auto_failover_preferred_mode"] = mode

        if not updates:
            raise HTTPException(status_code=400, detail="No valid fields provided")

        prefs = get_preferences()
        prefs.set_network_config(updates)
        net = prefs.get_network_config()

        return {
            "success": True,
            "enabled": bool(net.get("auto_failover_enabled", False)),
            "preferred_mode": str(net.get("auto_failover_preferred_mode", "modem")),
            "message": "Failover startup preferences saved",
        }
    except HTTPException:
        raise
    except FailoverError as e:
        logger.error("Failed to set failover preferences", extra=e.to_dict())
        raise HTTPException(status_code=500, detail="Could not save failover preferences")


@router.post("/failover/force-switch")
async def force_failover_switch(target_mode: str, reason: str = "Manual override"):
    """
    Force an immediate network switch

    Args:
        target_mode: Target mode ('wifi' or 'modem')
        reason: Reason for switch (default: 'Manual override')
    """
    try:
        # Parse target mode
        mode = NetworkMode.MODEM if target_mode == "modem" else NetworkMode.WIFI

        failover = get_auto_failover()
        success = await failover.force_switch(mode, reason)

        if success:
            return {
                "success": True,
                "message": f"Switched to {target_mode}",
                "target_mode": target_mode,
                "reason": reason,
            }
        else:
            raise FailoverError("current", target_mode, "switch failed")

    except FailoverError as e:
        logger.error("Force switch failed", extra=e.to_dict())
        raise HTTPException(status_code=500, detail="Could not execute network switch")
