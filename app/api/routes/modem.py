"""
Modem API Routes
Endpoints for managing modem connections and providers
"""

import asyncio
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from app.providers import get_provider_registry
from app.i18n import get_language_from_request, translate

router = APIRouter(prefix="/api/modem", tags=["modem"])

# =============================
# Request Models
# =============================


class NetworkModeRequest(BaseModel):
    """Network mode configuration request"""

    mode: str  # '00'=Auto, '01'=2G, '02'=3G, '03'=4G


class LTEBandRequest(BaseModel):
    """LTE band configuration request"""

    preset: Optional[str] = None  # 'all', 'orange_spain', 'urban', 'rural', 'balanced'
    custom_mask: Optional[int] = None  # Custom band mask


class APNRequest(BaseModel):
    """APN configuration request"""

    preset: Optional[str] = None
    custom_apn: Optional[str] = None


class RoamingRequest(BaseModel):
    """Roaming configuration request"""

    enabled: bool


class LatencyTestRequest(BaseModel):
    """Latency test configuration request"""

    host: Optional[str] = None
    count: Optional[int] = None


@router.get("/available-providers")
async def get_available_providers():
    """
    Get list of available modem providers from the provider registry

    This endpoint uses the new modular provider registry system.
    Returns all registered modem providers with their availability status.

    Returns:
        List of modem providers with their names, display names, availability status, and class
    """
    try:
        registry = get_provider_registry()
        providers = registry.get_available_modem_providers()
        return {"success": True, "providers": providers, "count": len(providers)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{provider_name}")
async def get_modem_status(provider_name: str, request: Request):
    """
    Get status of a specific modem provider

    Args:
        provider_name: Name of the modem provider (e.g., 'huawei_e3372h')

    Returns:
        Modem status including availability, connection state, signal info, etc.
    """
    lang = get_language_from_request(request)
    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider(provider_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=translate("modem.provider_not_found", lang, provider=provider_name),
            )

        status = provider.get_status()
        return {"success": True, "provider": provider_name, "status": status}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/connect/{provider_name}")
async def connect_modem(provider_name: str, request: Request):
    """
    Connect/activate a specific modem

    Args:
        provider_name: Name of the modem provider

    Returns:
        Connection result with success status and network info
    """
    lang = get_language_from_request(request)
    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider(provider_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=translate("modem.provider_not_found", lang, provider=provider_name),
            )

        result = provider.connect()

        if not result.get("success"):
            msg = result.get("message", translate("modem.connection_failed", lang))
            raise HTTPException(status_code=400, detail=msg)

        return {"success": True, "provider": provider_name, "result": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/disconnect/{provider_name}")
async def disconnect_modem(provider_name: str, request: Request):
    """
    Disconnect/deactivate a specific modem

    Args:
        provider_name: Name of the modem provider

    Returns:
        Disconnection result with success status
    """
    lang = get_language_from_request(request)
    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider(provider_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=translate("modem.provider_not_found", lang, provider=provider_name),
            )

        result = provider.disconnect()

        if not result.get("success"):
            msg = result.get("message", translate("modem.disconnection_failed", lang))
            raise HTTPException(status_code=400, detail=msg)

        return {"success": True, "provider": provider_name, "result": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class BandConfigRequest(BaseModel):
    """Band configuration request"""

    band_mask: int


@router.post("/configure-band/{provider_name}")
async def configure_modem_band(provider_name: str, request: BandConfigRequest, req: Request):
    """
    Configure LTE band for a specific modem

    Args:
        provider_name: Name of the modem provider
        request: Band configuration with band_mask

    Returns:
        Configuration result with success status
    """
    lang = get_language_from_request(req)
    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider(provider_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=translate("modem.provider_not_found", lang, provider=provider_name),
            )

        result = provider.configure_band(request.band_mask)

        if not result.get("success"):
            msg = result.get("message", translate("modem.band_configuration_failed", lang))
            raise HTTPException(status_code=400, detail=msg)

        return {"success": True, "provider": provider_name, "result": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reboot/{provider_name}")
async def reboot_modem(provider_name: str, request: Request):
    """
    Reboot a specific modem

    Args:
        provider_name: Name of the modem provider

    Returns:
        Reboot result with success status
    """
    lang = get_language_from_request(request)
    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider(provider_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=translate("modem.provider_not_found", lang, provider=provider_name),
            )

        result = provider.reboot()

        if not result.get("success"):
            msg = result.get("message", translate("modem.reboot_failed", lang))
            raise HTTPException(status_code=400, detail=msg)

        return {"success": True, "provider": provider_name, "result": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/info/{provider_name}")
async def get_modem_info(provider_name: str, request: Request):
    """
    Get detailed information about a modem provider

    Args:
        provider_name: Name of the modem provider

    Returns:
        Provider information including features and capabilities
    """
    lang = get_language_from_request(request)
    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider(provider_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=translate("modem.provider_not_found", lang, provider=provider_name),
            )

        info = provider.get_info()
        return {"success": True, "provider": provider_name, "info": info}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================
# Signal and Network Information
# =============================


@router.get("/signal/{provider_name}")
async def get_modem_signal(provider_name: str, request: Request):
    """
    Get modem signal information

    Args:
        provider_name: Name of the modem provider

    Returns:
        Signal strength, quality, and related metrics
    """
    lang = get_language_from_request(request)
    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider(provider_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=translate("modem.provider_not_found", lang, provider=provider_name),
            )

        if hasattr(provider, "async_get_signal_info"):
            info = await provider.async_get_signal_info()
        else:
            info = provider.get_signal_info()

        if info:
            return {"success": True, **info}
        raise HTTPException(status_code=503, detail="Could not get signal info")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/network/{provider_name}")
async def get_modem_network(provider_name: str, request: Request):
    """
    Get modem network/carrier information

    Args:
        provider_name: Name of the modem provider

    Returns:
        Network status, carrier info, and connection details
    """
    lang = get_language_from_request(request)
    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider(provider_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=translate("modem.provider_not_found", lang, provider=provider_name),
            )

        if hasattr(provider, "async_get_network_info"):
            info = await provider.async_get_network_info()
        else:
            info = provider.get_network_info()

        if info:
            return {"success": True, "status": str(info.status) if info else None}
        raise HTTPException(status_code=503, detail="Could not get network info")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/traffic/{provider_name}")
async def get_modem_traffic(provider_name: str, request: Request):
    """
    Get modem traffic statistics

    Args:
        provider_name: Name of the modem provider

    Returns:
        Data usage statistics (upload/download bytes)
    """
    lang = get_language_from_request(request)
    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider(provider_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=translate("modem.provider_not_found", lang, provider=provider_name),
            )

        if hasattr(provider, "async_get_traffic_stats"):
            stats = await provider.async_get_traffic_stats()
        else:
            stats = provider.get_traffic_stats()

        if stats:
            return {"success": True, **stats}
        raise HTTPException(status_code=503, detail="Could not get traffic stats")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/enhanced/{provider_name}")
async def get_enhanced_status(provider_name: str, request: Request):
    """
    Get full modem status with video optimization data

    Args:
        provider_name: Name of the modem provider

    Returns:
        Comprehensive status including device, signal, network, traffic, and video quality
    """
    lang = get_language_from_request(request)
    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider(provider_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=translate("modem.provider_not_found", lang, provider=provider_name),
            )

        # Gather all modem info in parallel using raw methods for full data
        device_task = provider.async_get_raw_device_info() if hasattr(provider, "async_get_raw_device_info") else None
        signal_task = provider.async_get_signal_info() if hasattr(provider, "async_get_signal_info") else None
        network_task = (
            provider.async_get_raw_network_info() if hasattr(provider, "async_get_raw_network_info") else None
        )
        traffic_task = provider.async_get_traffic_stats() if hasattr(provider, "async_get_traffic_stats") else None

        # Wait for all tasks
        results = await asyncio.gather(
            device_task if device_task else asyncio.sleep(0),
            signal_task if signal_task else asyncio.sleep(0),
            network_task if network_task else asyncio.sleep(0),
            traffic_task if traffic_task else asyncio.sleep(0),
            return_exceptions=True,
        )

        device_info = results[0] if device_task and not isinstance(results[0], Exception) else None
        signal_info = results[1] if signal_task and not isinstance(results[1], Exception) else None
        network_info = results[2] if network_task and not isinstance(results[2], Exception) else None
        traffic_info = results[3] if traffic_task and not isinstance(results[3], Exception) else None

        # Ensure dicts (not None)
        device_info = device_info or {}
        signal_info = signal_info or {}
        network_info = network_info or {}
        traffic_info = traffic_info or {}

        # Check if modem is available
        available = any([device_info, signal_info, network_info, traffic_info])

        # Determine connection status
        conn_status = network_info.get("connection_status", "")
        connected = conn_status == "Connected"

        # Calculate signal bars from percent
        signal_percent = signal_info.get("signal_percent", 0) or 0
        signal_bars = min(5, max(0, int(signal_percent / 20))) if signal_percent else 0

        # Build response with ALL fields the frontend expects
        response = {
            "success": True,
            "available": available,
            "connected": connected,
            "video_mode_active": getattr(provider, "video_mode_active", False),
            "video_quality": None,
        }

        # Add video quality assessment if signal data available
        if signal_info:
            try:
                loop = asyncio.get_event_loop()
                vq = await loop.run_in_executor(None, provider.get_video_quality_assessment)
                if vq and vq.get("available"):
                    response["video_quality"] = vq
            except Exception:
                pass

        # Device info - pass through all raw fields
        if device_info:
            response["device"] = {
                "device_name": device_info.get("device_name", "Unknown"),
                "model": device_info.get("device_name", "Unknown"),
                "imei": device_info.get("imei", ""),
                "imsi": device_info.get("imsi", ""),
                "iccid": device_info.get("iccid", ""),
                "serial_number": device_info.get("serial_number", ""),
                "hardware_version": device_info.get("hardware_version", ""),
                "software_version": device_info.get("software_version", ""),
                "mac_address1": device_info.get("mac_address1", ""),
                "mac_address2": device_info.get("mac_address2", ""),
                "product_family": device_info.get("product_family", ""),
            }

        # Signal info - pass through with calculated signal_bars
        if signal_info:
            response["signal"] = {
                **signal_info,
                "signal_bars": signal_bars,
            }

        # Network info - pass through ALL raw fields
        if network_info:
            response["network"] = {
                "operator": network_info.get("operator", ""),
                "operator_code": network_info.get("operator_code", ""),
                "network_type": network_info.get("network_type", ""),
                "network_type_ex": network_info.get("network_type_ex", ""),
                "connection_status": conn_status,
                "signal_icon": network_info.get("signal_icon", signal_bars),
                "roaming": network_info.get("roaming", False),
                "primary_dns": network_info.get("primary_dns", ""),
                "secondary_dns": network_info.get("secondary_dns", ""),
                "rat": network_info.get("rat", ""),
                "sim_status": network_info.get("sim_status", ""),
                "fly_mode": network_info.get("fly_mode", False),
            }

        # Traffic info - pass through as-is
        if traffic_info:
            response["traffic"] = traffic_info

        # Add current_band and mode data (needed by frontend config section)
        if available:
            try:
                loop = asyncio.get_event_loop()
                band_data = await loop.run_in_executor(None, provider.get_current_band)
                if band_data:
                    response["current_band"] = band_data
                    # Extract mode info from the same net_mode read
                    response["mode"] = {
                        "network_mode": band_data.get("network_mode", "00"),
                        "network_mode_name": band_data.get("network_mode_name", "Auto"),
                    }
            except Exception:
                pass

        if not available:
            response["error"] = "Could not connect to modem"

        return response

    except HTTPException:
        # Modem provider not available
        return {
            "success": True,
            "available": False,
            "connected": False,
            "error": "Modem provider not available",
        }
    except Exception as e:
        return {
            "success": True,
            "available": False,
            "connected": False,
            "error": str(e),
        }


# =============================
# Network Mode Management
# =============================


@router.get("/mode/{provider_name}")
async def get_modem_mode(provider_name: str, request: Request):
    """
    Get modem network mode settings

    Args:
        provider_name: Name of the modem provider

    Returns:
        Current network mode (Auto/2G/3G/4G)
    """
    lang = get_language_from_request(request)
    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider(provider_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=translate("modem.provider_not_found", lang, provider=provider_name),
            )

        if hasattr(provider, "get_network_mode"):
            loop = asyncio.get_event_loop()
            mode = await loop.run_in_executor(None, provider.get_network_mode)
            if mode:
                return {"success": True, **mode}
        raise HTTPException(status_code=503, detail="Could not get network mode")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mode/{provider_name}")
async def set_modem_mode(provider_name: str, mode_request: NetworkModeRequest, request: Request):
    """
    Set modem network mode

    Args:
        provider_name: Name of the modem provider
        mode_request: Network mode configuration

    Modes:
    - '00': Auto (4G/3G/2G)
    - '01': 2G Only
    - '02': 3G Only
    - '03': 4G Only

    Returns:
        Configuration result
    """
    lang = get_language_from_request(request)
    valid_modes = ["00", "01", "02", "03"]
    if mode_request.mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Mode must be one of: {valid_modes}")

    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider(provider_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=translate("modem.provider_not_found", lang, provider=provider_name),
            )

        if hasattr(provider, "set_network_mode"):
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: provider.set_network_mode(mode_request.mode))
            if result:
                return {"success": True, "message": f"Network mode set to {mode_request.mode}"}
        raise HTTPException(status_code=500, detail="Failed to set network mode")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================
# LTE Band Management
# =============================


@router.get("/band/{provider_name}")
async def get_current_band(provider_name: str, request: Request):
    """
    Get current LTE band information

    Args:
        provider_name: Name of the modem provider

    Returns:
        Current band configuration and active band
    """
    lang = get_language_from_request(request)
    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider(provider_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=translate("modem.provider_not_found", lang, provider=provider_name),
            )

        if hasattr(provider, "get_current_band"):
            loop = asyncio.get_event_loop()
            band = await loop.run_in_executor(None, provider.get_current_band)
            if band:
                return {"success": True, **band}
        raise HTTPException(status_code=503, detail="Could not get band info")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/band/presets/{provider_name}")
async def get_band_presets(provider_name: str, request: Request):
    """
    Get available LTE band presets

    Args:
        provider_name: Name of the modem provider

    Returns:
        List of available band presets
    """
    lang = get_language_from_request(request)
    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider(provider_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=translate("modem.provider_not_found", lang, provider=provider_name),
            )

        if hasattr(provider, "get_band_presets"):
            presets = provider.get_band_presets()
            return {"success": True, **presets}
        raise HTTPException(status_code=503, detail="Could not get presets")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/band/{provider_name}")
async def set_lte_band(provider_name: str, band_request: LTEBandRequest, request: Request):
    """
    Set LTE band configuration

    Args:
        provider_name: Name of the modem provider
        band_request: Band configuration

    Presets:
    - 'all': All bands (auto)
    - 'orange_spain': B3+B7+B20 (Orange optimal)
    - 'urban': B3+B7 (high speed)
    - 'rural': B20 only (best coverage)
    - 'balanced': B3+B20

    Returns:
        Configuration result
    """
    lang = get_language_from_request(request)
    if not band_request.preset and band_request.custom_mask is None:
        raise HTTPException(status_code=400, detail="Provide either preset or custom_mask")

    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider(provider_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=translate("modem.provider_not_found", lang, provider=provider_name),
            )

        if hasattr(provider, "set_lte_band"):
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: provider.set_lte_band(preset=band_request.preset, custom_mask=band_request.custom_mask),
            )
            if result and result.get("success"):
                return result
        raise HTTPException(status_code=500, detail="Failed to set band")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================
# APN Configuration
# =============================


@router.get("/apn/{provider_name}")
async def get_apn_settings(provider_name: str, request: Request):
    """
    Get current APN settings and available presets

    Args:
        provider_name: Name of the modem provider

    Returns:
        Current APN configuration and available presets
    """
    lang = get_language_from_request(request)
    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider(provider_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=translate("modem.provider_not_found", lang, provider=provider_name),
            )

        if hasattr(provider, "get_apn_settings"):
            loop = asyncio.get_event_loop()
            settings = await loop.run_in_executor(None, provider.get_apn_settings)
            return {"success": True, **settings}
        raise HTTPException(status_code=503, detail="Could not get APN settings")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apn/{provider_name}")
async def set_apn(provider_name: str, apn_request: APNRequest, request: Request):
    """
    Set APN configuration

    Args:
        provider_name: Name of the modem provider
        apn_request: APN configuration

    Presets for Spain:
    - 'orange': Standard Orange APN
    - 'orangeworld': Orange data APN
    - 'simyo': Simyo (uses Orange network)

    Returns:
        Configuration result
    """
    lang = get_language_from_request(request)
    if not apn_request.preset and not apn_request.custom_apn:
        raise HTTPException(status_code=400, detail="Provide either preset or custom_apn")

    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider(provider_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=translate("modem.provider_not_found", lang, provider=provider_name),
            )

        if hasattr(provider, "set_apn"):
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: provider.set_apn(preset=apn_request.preset, custom_apn=apn_request.custom_apn),
            )
            if result and result.get("success"):
                return result
        raise HTTPException(status_code=500, detail="Failed to set APN")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================
# Network Control
# =============================


@router.post("/reconnect/{provider_name}")
async def reconnect_network(provider_name: str, request: Request):
    """
    Force network reconnection to search for better cell tower

    Args:
        provider_name: Name of the modem provider

    Returns:
        Reconnection result
    """
    lang = get_language_from_request(request)
    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider(provider_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=translate("modem.provider_not_found", lang, provider=provider_name),
            )

        if hasattr(provider, "reconnect_network"):
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, provider.reconnect_network)
            if result and result.get("success"):
                return result
        raise HTTPException(status_code=500, detail="Reconnection failed")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/roaming/{provider_name}")
async def set_roaming(provider_name: str, roaming_request: RoamingRequest, request: Request):
    """
    Enable or disable roaming

    Args:
        provider_name: Name of the modem provider
        roaming_request: Roaming configuration

    Returns:
        Configuration result
    """
    lang = get_language_from_request(request)
    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider(provider_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=translate("modem.provider_not_found", lang, provider=provider_name),
            )

        if hasattr(provider, "set_roaming"):
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: provider.set_roaming(roaming_request.enabled))
            if result and result.get("success"):
                return result
        raise HTTPException(status_code=500, detail="Failed to set roaming")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================
# Video Mode Profile
# =============================


@router.get("/video-mode/{provider_name}")
async def get_video_mode_status(provider_name: str, request: Request):
    """
    Check if video mode is currently active

    Args:
        provider_name: Name of the modem provider

    Returns:
        Video mode status
    """
    lang = get_language_from_request(request)
    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider(provider_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=translate("modem.provider_not_found", lang, provider=provider_name),
            )

        video_mode_active = getattr(provider, "video_mode_active", False)
        return {"success": True, "video_mode_active": video_mode_active}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/video-mode/enable/{provider_name}")
async def enable_video_mode(provider_name: str, request: Request):
    """
    Enable video-optimized modem settings:
    - Forces 4G Only mode
    - Optimizes for low latency

    Args:
        provider_name: Name of the modem provider

    Returns:
        Configuration result
    """
    lang = get_language_from_request(request)
    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider(provider_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=translate("modem.provider_not_found", lang, provider=provider_name),
            )

        if hasattr(provider, "enable_video_mode"):
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, provider.enable_video_mode)
            if result and result.get("success"):
                return result
        raise HTTPException(status_code=500, detail="Failed to enable video mode")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/video-mode/disable/{provider_name}")
async def disable_video_mode(provider_name: str, request: Request):
    """
    Disable video mode and restore original settings

    Args:
        provider_name: Name of the modem provider

    Returns:
        Configuration result
    """
    lang = get_language_from_request(request)
    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider(provider_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=translate("modem.provider_not_found", lang, provider=provider_name),
            )

        if hasattr(provider, "disable_video_mode"):
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, provider.disable_video_mode)
            if result and result.get("success"):
                return result
        raise HTTPException(status_code=500, detail="Failed to disable video mode")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================
# Video Quality Assessment
# =============================


@router.get("/video-quality/{provider_name}")
async def get_video_quality(provider_name: str, request: Request):
    """
    Get video streaming quality assessment based on current signal

    Args:
        provider_name: Name of the modem provider

    Returns:
        Video quality assessment (excellent/good/fair/poor)
    """
    lang = get_language_from_request(request)
    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider(provider_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=translate("modem.provider_not_found", lang, provider=provider_name),
            )

        if hasattr(provider, "get_video_quality_assessment"):
            loop = asyncio.get_event_loop()
            assessment = await loop.run_in_executor(None, provider.get_video_quality_assessment)
            return {"success": assessment.get("available", False), **assessment}
        raise HTTPException(status_code=503, detail="Could not assess video quality")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================
# Latency Monitoring
# =============================


@router.get("/latency/{provider_name}")
async def measure_latency(provider_name: str, request: Request):
    """
    Measure current network latency and jitter

    Args:
        provider_name: Name of the modem provider

    Returns:
        Latency test results (avg, min, max, jitter)
    """
    lang = get_language_from_request(request)
    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider(provider_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=translate("modem.provider_not_found", lang, provider=provider_name),
            )

        if hasattr(provider, "measure_latency"):
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, provider.measure_latency)
            if result and result.get("success"):
                return result
            # Return error details instead of generic 500
            if result:
                return result
        raise HTTPException(status_code=500, detail="Latency test failed")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/latency/{provider_name}")
async def measure_latency_custom(provider_name: str, latency_request: LatencyTestRequest, request: Request):
    """
    Measure latency to a custom host

    Args:
        provider_name: Name of the modem provider
        latency_request: Latency test configuration

    Returns:
        Latency test results
    """
    lang = get_language_from_request(request)
    try:
        registry = get_provider_registry()
        provider = registry.get_modem_provider(provider_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=translate("modem.provider_not_found", lang, provider=provider_name),
            )

        if hasattr(provider, "measure_latency"):
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: provider.measure_latency(host=latency_request.host, count=latency_request.count),
            )
            if result and result.get("success"):
                return result
            if result:
                return result
        raise HTTPException(status_code=500, detail="Latency test failed")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
