"""
Flight Mode - Complete Network Optimization for FPV Streaming

This module handles all flight mode operations, combining modem and network
optimizations for the best possible low-latency video streaming experience.

Flight mode activates:
1. Modem optimizations (4G Only, urban bands)
2. Network optimizations (MTU, QoS, TCP tuning)
3. Priority network switching (modem as primary)
"""

import asyncio
from fastapi import APIRouter, HTTPException
from app.services.network_optimizer import get_network_optimizer
from app.providers.registry import get_provider_registry
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
    Get Flight Mode status

    Flight Mode combines:
    - Modem optimization (4G Only, urban bands)
    - Network optimization (MTU, QoS, TCP tuning)

    Returns:
        Status of both modem video mode and network optimizer
    """
    try:
        optimizer = get_network_optimizer()
        network_status = optimizer.get_status()

        # Get modem video mode status from provider registry
        registry = get_provider_registry()
        provider = registry.get_modem_provider("huawei_e3372h")
        modem_video_active = getattr(provider, "video_mode_active", False) if provider else False

        # Flight Mode is fully active only if both are enabled
        fully_active = network_status["active"] and modem_video_active

        return {
            "success": True,
            "flight_mode_active": fully_active,
            "network_optimizer": network_status,
            "modem_video_mode": modem_video_active,
            "optimizations": {
                "modem": "4G Only + Urban Bands (B3+B7)" if modem_video_active else "Not active",
                "network": network_status.get("config", {}) if network_status["active"] else "Not active",
            },
        }
    except Exception as e:
        logger.error(f"Error getting Flight Mode status: {e}")
        return {"success": False, "error": str(e), "flight_mode_active": False}


@router.post("/flight-mode/enable")
async def enable_flight_mode():
    """
    Enable Flight Mode - Full optimization for FPV streaming

    Activates:
    1. Modem optimizations:
       - Force 4G Only mode
       - Configure urban bands (B3+B7) for lowest latency

    2. Network optimizations:
       - Set MTU to 1420 (optimal for LTE)
       - Enable QoS with DSCP marking (EF class)
       - Optimize TCP (BBR, increased buffers)
       - Disable power saving

    Returns:
        Combined result of all optimizations
    """
    try:
        results = {"modem": {"success": False}, "network": {"success": False}}
        errors = []

        # 1. Enable modem video mode
        try:
            registry = get_provider_registry()
            provider = registry.get_modem_provider("huawei_e3372h")
            if provider and hasattr(provider, "enable_video_mode"):
                loop = asyncio.get_event_loop()
                modem_result = await loop.run_in_executor(None, provider.enable_video_mode)
                results["modem"] = modem_result
                if not modem_result.get("success"):
                    errors.append(f"Modem: {modem_result.get('message', 'Unknown error')}")
            elif not provider:
                errors.append("Modem: Provider not available")
        except Exception as e:
            errors.append(f"Modem: {str(e)}")
            logger.error(f"Error enabling modem video mode: {e}")

        # 2. Enable network optimizer
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
        modem_success = results["modem"].get("success", False)
        network_success = results["network"].get("success", False)

        if modem_success and network_success:
            message = "Flight Mode enabled: Full optimization active"
            success = True
        elif modem_success or network_success:
            message = f"Flight Mode partially enabled. Issues: {', '.join(errors)}"
            success = True  # Partial success
        else:
            message = f"Flight Mode failed: {', '.join(errors)}"
            success = False

        return {
            "success": success,
            "message": message,
            "flight_mode_active": modem_success and network_success,
            "details": results,
            "errors": errors if errors else None,
        }

    except Exception as e:
        logger.error(f"Error enabling Flight Mode: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to enable Flight Mode: {str(e)}")


@router.post("/flight-mode/disable")
async def disable_flight_mode():
    """
    Disable Flight Mode and restore original settings

    Restores:
    - Modem to auto mode and all bands
    - Network settings (MTU, TCP, QoS)

    Returns:
        Combined result of restoration
    """
    try:
        results = {"modem": {"success": False}, "network": {"success": False}}
        errors = []

        # 1. Disable modem video mode
        try:
            registry = get_provider_registry()
            provider = registry.get_modem_provider("huawei_e3372h")
            if provider and hasattr(provider, "disable_video_mode"):
                loop = asyncio.get_event_loop()
                modem_result = await loop.run_in_executor(None, provider.disable_video_mode)
                results["modem"] = modem_result
                if not modem_result.get("success"):
                    errors.append(f"Modem: {modem_result.get('message', 'Unknown error')}")
            elif not provider:
                errors.append("Modem: Provider not available")
        except Exception as e:
            errors.append(f"Modem: {str(e)}")
            logger.error(f"Error disabling modem video mode: {e}")

        # 2. Disable network optimizer
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
        modem_success = results["modem"].get("success", False)
        network_success = results["network"].get("success", False)

        if modem_success and network_success:
            message = "Flight Mode disabled: Settings restored"
            success = True
        elif modem_success or network_success:
            message = f"Flight Mode partially disabled. Issues: {', '.join(errors)}"
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
