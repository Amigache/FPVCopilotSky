"""
Flight Mode - Network Optimization for FPV Streaming

This module handles network-level optimizations for low-latency video streaming.
Flight mode is activated automatically by ModemPool when a modem is detected,
and deactivated when all modems disconnect.

Manual endpoints are available for override/diagnostic purposes.

Flight mode applies:
1. MTU optimization (1420 bytes, optimal for LTE)
2. QoS DSCP marking for video traffic (EF class, ports 5600/5601/8554)
3. TCP tuning (BBR congestion control, increased buffers)
4. Interface power saving disabled (txqueuelen 10000)
5. CAKE bufferbloat mitigation (auto-calibrated uplink BW)
6. VPN policy routing (video traffic bypasses tunnel)
7. Modem set as primary network interface (metrics/routing)
"""

import asyncio
from fastapi import APIRouter, HTTPException
from app.services.network_optimizer import get_network_optimizer
from .common import detect_modem_interfaces, PriorityModeRequest
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


async def _detect_modem_interface():
    """Internal helper for modem detection"""
    interfaces = await detect_modem_interfaces()
    return interfaces[0] if interfaces else None


async def _detect_wifi_interface():
    """Internal helper for WiFi detection"""
    from .common import detect_wifi_interface

    return await detect_wifi_interface()


async def set_priority_mode(request: PriorityModeRequest):
    """Internal helper to set priority mode (imported from status module)"""
    from .status import set_priority_mode as status_set_priority

    return await status_set_priority(request)


@router.get("/flight-mode/status")
async def get_flight_mode_status():
    """
    Get Flight Mode status.

    Flight Mode is auto-managed by ModemPool: enabled when a modem is detected,
    disabled when all modems disconnect.

    Returns:
        Current network optimizer state and active config
    """
    try:
        optimizer = get_network_optimizer()
        network_status = optimizer.get_status()

        return {
            "success": True,
            "flight_mode_active": network_status["active"],
            "network_optimizer": network_status,
            "optimizations": {
                "network": network_status.get("config", {}) if network_status["active"] else "Not active",
            },
        }
    except Exception as e:
        logger.error(f"Error getting Flight Mode status: {e}")
        return {"success": False, "error": str(e), "flight_mode_active": False}


@router.post("/flight-mode/enable")
async def enable_flight_mode():
    """
    Enable Flight Mode manually (normally auto-activated by ModemPool on modem detection).

    Applies:
    - MTU 1420 (optimal for LTE)
    - QoS DSCP EF marking on video ports (5600, 5601, 8554)
    - TCP BBR + increased buffers
    - Interface power saving disabled
    - CAKE bufferbloat mitigation
    - VPN policy routing (video traffic isolation)
    - Modem set as primary network

    Returns:
        Result of network optimizations applied
    """
    try:
        results = {"network": {"success": False}}
        errors = []

        # 1. Enable network optimizer
        try:
            optimizer = get_network_optimizer()
            loop = asyncio.get_event_loop()
            network_result = await loop.run_in_executor(None, optimizer.enable_flight_mode)
            results["network"] = network_result
            if not network_result.get("success"):
                errors.append(f"Network: {network_result.get('message', 'Unknown error')}")
        except Exception as e:
            errors.append(f"Network: {str(e)}")
            logger.error(f"Error enabling network optimizer: {e}")

        # 3. Set modem as primary network when flight mode is enabled
        try:
            modem_interface = await _detect_modem_interface()
            if modem_interface:
                priority_result = await set_priority_mode(PriorityModeRequest(mode="modem"))
                results["priority"] = priority_result
                if not priority_result.get("success"):
                    errors.append(f"Priority: {priority_result.get('message', 'Unknown error')}")
                else:
                    logger.info("Flight Mode: modem set as primary network")
            else:
                logger.warning("Flight Mode: modem not detected, skipping priority switch")
        except Exception as e:
            errors.append(f"Priority: {str(e)}")
            logger.error(f"Error setting modem priority in flight mode: {e}")

        # Determine overall success
        network_success = results["network"].get("success", False)

        if network_success:
            message = "Flight Mode enabled: Network optimization active"
            success = True
        else:
            message = f"Flight Mode failed: {', '.join(errors)}"
            success = False

        return {
            "success": success,
            "message": message,
            "flight_mode_active": network_success,
            "details": results,
            "errors": errors if errors else None,
        }

    except Exception as e:
        logger.error(f"Error enabling Flight Mode: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to enable Flight Mode: {str(e)}")


@router.post("/flight-mode/disable")
async def disable_flight_mode():
    """
    Disable Flight Mode manually and restore original network settings.

    Restores:
    - MTU, TCP parameters to previous values
    - Removes QoS iptables rules
    - Removes CAKE qdisc
    - Restores network priority to auto

    Returns:
        Result of restoration
    """
    try:
        results = {"network": {"success": False}}
        errors = []

        # 1. Disable network optimizer
        try:
            optimizer = get_network_optimizer()
            loop = asyncio.get_event_loop()
            network_result = await loop.run_in_executor(None, optimizer.disable_flight_mode)
            results["network"] = network_result
            if not network_result.get("success"):
                errors.append(f"Network: {network_result.get('message', 'Unknown error')}")
        except Exception as e:
            errors.append(f"Network: {str(e)}")
            logger.error(f"Error disabling network optimizer: {e}")

        # 3. Restore WiFi as primary (undo flight mode priority)
        try:
            wifi_interface = await _detect_wifi_interface()
            if wifi_interface:
                priority_result = await set_priority_mode(PriorityModeRequest(mode="auto"))
                results["priority"] = priority_result
                logger.info("Flight Mode disabled: network priority restored")
        except Exception as e:
            errors.append(f"Priority restore: {str(e)}")
            logger.error(f"Error restoring priority after flight mode: {e}")

        # Determine overall success
        network_success = results["network"].get("success", False)

        if network_success:
            message = "Flight Mode disabled: Settings restored"
            success = True
        else:
            message = f"Flight Mode disable failed: {', '.join(errors)}"
            success = False

        return {
            "success": success,
            "message": message,
            "flight_mode_active": False,
            "details": results,
            "errors": errors if errors else None,
        }

    except Exception as e:
        logger.error(f"Error disabling Flight Mode: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to disable Flight Mode: {str(e)}")


@router.get("/flight-mode/metrics")
async def get_flight_mode_metrics():
    """
    Get current network performance metrics

    Returns current values for:
    - TCP congestion control algorithm
    - Buffer sizes
    - MTU
    - Active QoS rules
    """
    try:
        optimizer = get_network_optimizer()
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, optimizer.get_network_metrics)
        return result
    except Exception as e:
        logger.error(f"Error getting Flight Mode metrics: {e}")
        return {"success": False, "error": str(e)}
