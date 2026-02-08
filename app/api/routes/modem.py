"""
Modem API Routes
Endpoints for managing modem connections and providers
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from providers import get_provider_registry
from app.i18n import get_language_from_request, translate

router = APIRouter(prefix="/api/modem", tags=["modem"])


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
                detail=translate(
                    "modem.provider_not_found", lang, provider=provider_name
                ),
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
                detail=translate(
                    "modem.provider_not_found", lang, provider=provider_name
                ),
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
                detail=translate(
                    "modem.provider_not_found", lang, provider=provider_name
                ),
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
async def configure_modem_band(
    provider_name: str, request: BandConfigRequest, req: Request
):
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
                detail=translate(
                    "modem.provider_not_found", lang, provider=provider_name
                ),
            )

        result = provider.configure_band(request.band_mask)

        if not result.get("success"):
            msg = result.get(
                "message", translate("modem.band_configuration_failed", lang)
            )
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
                detail=translate(
                    "modem.provider_not_found", lang, provider=provider_name
                ),
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
                detail=translate(
                    "modem.provider_not_found", lang, provider=provider_name
                ),
            )

        info = provider.get_info()
        return {"success": True, "provider": provider_name, "info": info}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
