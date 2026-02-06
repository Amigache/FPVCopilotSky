"""
VPN API Routes
Endpoints for managing VPN connections
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from providers import get_provider_registry

router = APIRouter(prefix="/api/vpn", tags=["vpn"])

# Service references (will be set by main.py)
_vpn_service = None
_preferences_service = None


def set_vpn_service(service):
    """Set the VPN service instance"""
    global _vpn_service
    _vpn_service = service


def set_preferences_service(service):
    """Set the preferences service instance"""
    global _preferences_service
    _preferences_service = service


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
    if not _vpn_service:
        raise HTTPException(status_code=503, detail="VPN service not initialized")
    
    try:
        providers = _vpn_service.get_available_providers()
        return {
            "success": True,
            "providers": providers
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_status(provider: Optional[str] = None):
    """Get VPN connection status"""
    if not _vpn_service:
        raise HTTPException(status_code=503, detail="VPN service not initialized")
    
    try:
        status = _vpn_service.get_status(provider)
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/peers")
async def get_peers(provider: Optional[str] = None):
    """
    Get list of VPN peers/nodes
    
    Args:
        provider: VPN provider name (optional, uses current if not specified)
    
    Returns:
        List of peers in the VPN network with their status and information
    """
    if not _vpn_service:
        raise HTTPException(status_code=503, detail="VPN service not initialized")
    
    try:
        peers = _vpn_service.get_peers(provider)
        return {
            "success": True,
            "peers": peers,
            "count": len(peers)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/connect")
async def connect_vpn(request: VPNConnectRequest):
    """
    Connect to VPN
    
    Args:
        provider: VPN provider name (optional, uses current if not specified)
    
    Returns:
        Connection result with auth_url if authentication is needed
    """
    if not _vpn_service:
        raise HTTPException(status_code=503, detail="VPN service not initialized")
    
    try:
        result = _vpn_service.connect(request.provider)
        
        if not result.get("success") and not result.get("needs_auth") and not result.get("needs_logout"):
            raise HTTPException(status_code=400, detail=result.get("error", "Connection failed"))
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/disconnect")
async def disconnect_vpn(request: VPNDisconnectRequest):
    """
    Disconnect from VPN
    
    Args:
        provider: VPN provider name (optional, uses current if not specified)
    """
    if not _vpn_service:
        raise HTTPException(status_code=503, detail="VPN service not initialized")
    
    try:
        result = _vpn_service.disconnect(request.provider)
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Disconnection failed"))
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/logout")
async def logout_vpn(request: VPNDisconnectRequest):
    """
    Logout from VPN (clears local credentials)
    
    Args:
        provider: VPN provider name (optional, uses current if not specified)
    
    This is useful when you need to re-authenticate with fresh credentials,
    for example when the device has been deleted from the admin panel.
    """
    if not _vpn_service:
        raise HTTPException(status_code=503, detail="VPN service not initialized")
    
    try:
        result = _vpn_service.logout(request.provider)
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Logout failed"))
        
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
    if not _preferences_service:
        raise HTTPException(status_code=503, detail="Preferences service not initialized")
    
    try:
        # Run synchronous code in thread pool to avoid blocking
        import asyncio
        loop = asyncio.get_event_loop()
        config = await loop.run_in_executor(None, _preferences_service.get_vpn_config)
        return {
            "success": True,
            "preferences": config
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preferences")
async def save_vpn_preferences(preferences: VPNPreferencesModel):
    """
    Save VPN preferences to persistent storage
    
    Args:
        preferences: VPN preferences including provider, enabled, auto_connect, and provider_settings
    
    Returns:
        Success status and saved preferences
    """
    if not _preferences_service:
        raise HTTPException(status_code=503, detail="Preferences service not initialized")
    
    try:
        config = preferences.model_dump()
        # Run synchronous code in thread pool to avoid blocking
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: _preferences_service.set_vpn_config(config))
        
        return {
            "success": True,
            "message": "VPN preferences saved",
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
