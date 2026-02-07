"""
VPN API Routes
Endpoints for managing VPN connections
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any
from providers import get_provider_registry
from services.preferences import get_preferences
from app.i18n import get_language_from_request, translate

router = APIRouter(prefix="/api/vpn", tags=["vpn"])

# Service references (will be set by main.py)
_vpn_service = None
_preferences_service = None


def set_vpn_service(service):
    """Deprecated: Set the VPN service instance (kept for compatibility)"""
    global _vpn_service
    _vpn_service = service


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


def _get_vpn_provider(provider_name: Optional[str] = None, lang: str = 'en'):
    """Get VPN provider from registry"""
    registry = get_provider_registry()
    
    # If provider_name not specified, get from preferences
    if not provider_name:
        prefs = _get_preferences_service()
        config = prefs.get_vpn_config()
        provider_name = config.get('provider')
    
    # If still no provider, auto-detect first installed one
    if not provider_name:
        available = registry.get_available_vpn_providers()
        installed = [p for p in available if p.get('installed')]
        if installed:
            provider_name = installed[0]['name']
    
    if not provider_name:
        raise HTTPException(status_code=400, detail=translate("vpn.no_provider_configured", lang))
    
    provider = registry.get_vpn_provider(provider_name)
    if not provider:
        raise HTTPException(status_code=503, detail=translate("vpn.provider_not_available", lang, provider=provider_name))
    
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
        return {
            "success": True,
            "providers": providers
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_status(request: Request, provider: Optional[str] = None):
    """Get VPN connection status"""
    lang = get_language_from_request(request)
    try:
        vpn_provider = _get_vpn_provider(provider, lang)
        status = vpn_provider.get_status()
        return status
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
        return {
            "success": True,
            "peers": peers,
            "count": len(peers)
        }
    except HTTPException as e:
        # If no VPN provider configured, return empty list instead of error
        if e.status_code == 400 and translate("vpn.no_provider_configured", lang) in str(e.detail):
            return {
                "success": True,
                "peers": [],
                "count": 0
            }
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preferences")
async def get_vpn_preferences():
    """
    Get VPN preferences from persistent storage
    
    Returns:
        VPN configuration including provider, enabled state, and auto-connect settings
    """
    try:
        prefs = _get_preferences_service()
        # Run synchronous code in thread pool to avoid blocking
        import asyncio
        loop = asyncio.get_event_loop()
        config = await loop.run_in_executor(None, prefs.get_vpn_config)
        return {
            "success": True,
            "preferences": config
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
        # Run synchronous code in thread pool to avoid blocking
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: prefs.set_vpn_config(config))
        
        return {
            "success": True,
            "message": translate("vpn.preferences_saved", lang),
            "preferences": config
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/available-providers")
async def get_available_providers():
    """
    Get list of available VPN providers from the provider registry
    
    This endpoint uses the new modular provider registry system.
    Returns all registered VPN providers with their installation status.
    
    Returns:
        List of VPN providers with their names, display names, installation status, and class
    """
    try:
        registry = get_provider_registry()
        providers = registry.get_available_vpn_providers()
        return {
            "success": True,
            "providers": providers,
            "count": len(providers)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
