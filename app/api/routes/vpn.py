"""
VPN API Routes
Endpoints for managing VPN connections
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.providers import get_provider_registry
from app.services.preferences import get_preferences
from app.i18n import get_language_from_request, translate
from app.exceptions import VPNConnectionError, VPNConfigError, ProviderError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vpn", tags=["vpn"])

# Service references (will be set by main.py)
_preferences_service = None


def set_preferences_service(service):
    """Set the preferences service instance"""
    global _preferences_service
    _preferences_service = service


def _get_preferences_service():
    """Get preferences service instance"""
    global _preferences_service
    if _preferences_service:
        return _preferences_service
    return get_preferences()


def _get_vpn_provider(provider_name: Optional[str] = None, lang: str = "en"):
    """Get VPN provider from registry"""
    registry = get_provider_registry()

    # If provider_name not specified, get from preferences
    if not provider_name:
        prefs = _get_preferences_service()
        config = prefs.get_vpn_config()
        provider_name = config.get("provider")

    # If still no provider, auto-detect first installed one
    if not provider_name:
        available = registry.get_available_vpn_providers()
        installed = [p for p in available if p.get("installed")]
        if installed:
            provider_name = installed[0]["name"]

    if not provider_name:
        raise HTTPException(status_code=400, detail=translate("vpn.no_provider_configured", lang))

    provider = registry.get_vpn_provider(provider_name)
    if not provider:
        raise HTTPException(
            status_code=503,
            detail=translate("vpn.provider_not_available", lang, provider=provider_name),
        )

    return provider


class VPNConnectRequest(BaseModel):
    """VPN connection request"""

    provider: Optional[str] = None


class VPNDisconnectRequest(BaseModel):
    """VPN disconnection request"""

    provider: Optional[str] = None


class VPNPreferencesModel(BaseModel):
    """VPN preferences model"""

    provider: str = ""  # "tailscale", "zerotier", "wireguard", or "" for none
    enabled: bool = False
    auto_connect: bool = False
    provider_settings: Dict[str, Any] = {}


@router.get("/providers")
async def get_providers():
    """Get list of available VPN providers"""
    try:
        registry = get_provider_registry()
        providers = registry.get_available_vpn_providers()
        return {"success": True, "providers": providers}
    except (AttributeError, TypeError, ValueError, RuntimeError) as e:
        logger.error("Error listing VPN providers (%s): %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve VPN providers")
    except ProviderError as e:
        logger.error("Provider error", extra=e.to_dict())
        raise HTTPException(status_code=503, detail="VPN provider unavailable")


@router.get("/status")
async def get_status(request: Request, provider: Optional[str] = None):
    """Get VPN connection status"""
    lang = get_language_from_request(request)
    try:
        vpn_provider = _get_vpn_provider(provider, lang)
        status = vpn_provider.get_status()
        return status
    except HTTPException as e:
        # If no VPN provider configured or not available, return a neutral status
        if e.status_code in [400, 503]:
            return {
                "success": False,
                "installed": False,
                "connected": False,
                "authenticated": False,
                "provider": None,
                "message": str(e.detail),
            }
        raise
    except (AttributeError, TypeError, ValueError, RuntimeError, KeyError) as e:
        logger.error("Error retrieving VPN status (%s): %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve VPN status")
    except VPNConnectionError as e:
        logger.warning("VPN status check failed", extra=e.to_dict())
        return {
            "success": False,
            "installed": False,
            "connected": False,
            "authenticated": False,
            "provider": provider,
            "message": "VPN connection check failed",
        }


@router.get("/peers")
async def get_peers(request: Request, provider: Optional[str] = None):
    """
    Get list of VPN peers/nodes

    Args:
        provider: VPN provider name (optional, uses current if not specified)

    Returns:
        List of peers in the VPN network with their status and information
    """
    lang = get_language_from_request(request)
    try:
        vpn_provider = _get_vpn_provider(provider, lang)
        peers = vpn_provider.get_peers()
        return {"success": True, "peers": peers, "count": len(peers)}
    except HTTPException as e:
        # If no VPN provider configured or not available, return empty list
        if e.status_code in [400, 503]:
            return {"success": True, "peers": [], "count": 0}
        raise
    except (AttributeError, TypeError, ValueError, RuntimeError, KeyError) as e:
        logger.error("Error retrieving VPN peers (%s): %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve VPN peers")
    except VPNConnectionError as e:
        logger.warning("Could not retrieve peers", extra=e.to_dict())
        return {"success": True, "peers": [], "count": 0}


@router.post("/connect")
async def connect_vpn(request: VPNConnectRequest, req: Request):
    """
    Connect to VPN

    Args:
        provider: VPN provider name (optional, uses current if not specified)

    Returns:
        Connection result with auth_url if authentication is needed
    """
    lang = get_language_from_request(req)
    try:
        vpn_provider = _get_vpn_provider(request.provider, lang)
        result = vpn_provider.connect()

        if not result.get("success") and not result.get("needs_auth"):
            msg = result.get("error", translate("vpn.connection_failed", lang))
            raise HTTPException(status_code=400, detail=msg)

        return result
    except HTTPException:
        raise
    except (AttributeError, TypeError, ValueError, RuntimeError, KeyError) as e:
        logger.error("Error connecting VPN (%s): %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to connect VPN")
    except VPNConnectionError as e:
        logger.error("VPN connection error", extra=e.to_dict())
        raise HTTPException(status_code=503, detail="Could not connect to VPN")


@router.post("/disconnect")
async def disconnect_vpn(request: VPNDisconnectRequest, req: Request):
    """
    Disconnect from VPN

    Args:
        provider: VPN provider name (optional, uses current if not specified)
    """
    lang = get_language_from_request(req)
    try:
        vpn_provider = _get_vpn_provider(request.provider, lang)
        result = vpn_provider.disconnect()

        if not result.get("success"):
            msg = result.get("error", translate("vpn.disconnection_failed", lang))
            raise HTTPException(status_code=400, detail=msg)

        return result
    except HTTPException:
        raise
    except (AttributeError, TypeError, ValueError, RuntimeError, KeyError) as e:
        logger.error("Error disconnecting VPN (%s): %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to disconnect VPN")
    except VPNConnectionError as e:
        logger.error("VPN disconnection error", extra=e.to_dict())
        raise HTTPException(status_code=503, detail="Could not disconnect from VPN")


@router.post("/logout")
async def logout_vpn(request: VPNDisconnectRequest, req: Request):
    """
    Logout from VPN (clears local credentials)

    Args:
        provider: VPN provider name (optional, uses current if not specified)

    This is useful when you need to re-authenticate with fresh credentials,
    for example when the device has been deleted from the admin panel.
    """
    lang = get_language_from_request(req)
    try:
        vpn_provider = _get_vpn_provider(request.provider, lang)
        result = vpn_provider.logout()

        if not result.get("success"):
            msg = result.get("error", translate("vpn.logout_failed", lang))
            raise HTTPException(status_code=400, detail=msg)

        return result
    except HTTPException:
        raise
    except (AttributeError, TypeError, ValueError, RuntimeError, KeyError) as e:
        logger.error("Error logging out VPN (%s): %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to logout VPN")
    except VPNConnectionError as e:
        logger.error("VPN logout error", extra=e.to_dict())
        raise HTTPException(status_code=503, detail="Could not logout from VPN")


@router.get("/preferences")
async def get_vpn_preferences():
    """
    Get VPN preferences from persistent storage

    Returns:
        VPN configuration including provider, enabled state, and auto-connect settings
    """
    try:
        prefs = _get_preferences_service()
        loop = asyncio.get_event_loop()
        config = await loop.run_in_executor(None, prefs.get_vpn_config)
        return {"success": True, "preferences": config}
    except (TypeError, ValueError, RuntimeError) as e:
        logger.error("Error retrieving preferences (%s): %s", type(e).__name__, e)
        raise HTTPException(status_code=500, detail="Failed to retrieve preferences")
    except VPNConfigError as e:
        logger.error("VPN config error", extra=e.to_dict())
        raise HTTPException(status_code=500, detail="Could not retrieve VPN preferences")


@router.post("/preferences")
async def save_vpn_preferences(preferences: VPNPreferencesModel, request: Request):
    """
    Save VPN preferences to persistent storage

    Args:
        preferences: VPN preferences including provider, enabled, auto_connect, and provider_settings

    Returns:
        Success status and saved preferences
    """
    try:
        lang = get_language_from_request(request)
        prefs = _get_preferences_service()
        config = preferences.model_dump()

        loop = asyncio.get_event_loop()

        # Save the config
        await loop.run_in_executor(None, lambda: prefs.set_vpn_config(config))

        # Verify the save
        saved_config = await loop.run_in_executor(None, prefs.get_vpn_config)

        if (
            saved_config.get("provider") == config.get("provider")
            and saved_config.get("enabled") == config.get("enabled")
            and saved_config.get("auto_connect") == config.get("auto_connect")
        ):
            return {
                "success": True,
                "message": translate("vpn.preferences_saved", lang),
                "preferences": config,
            }
        else:
            logger.warning("VPN preferences verification failed")
            return {
                "success": False,
                "message": "Failed to verify saved preferences",
                "preferences": saved_config,
            }
    except (TypeError, ValueError, RuntimeError) as e:
        logger.error("Error saving VPN preferences (%s): %s", type(e).__name__, e)
        raise HTTPException(status_code=500, detail="Failed to save VPN preferences")
    except VPNConfigError as e:
        logger.error("VPN config save failed", extra=e.to_dict())
        raise HTTPException(status_code=500, detail="Could not save VPN preferences")
