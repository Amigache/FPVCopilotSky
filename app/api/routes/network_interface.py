"""
Network Interface API endpoints - Provider-based network interface management
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Optional
from pydantic import BaseModel
import logging

from app.providers import get_provider_registry
from app.i18n import get_language_from_request, translate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/network-interfaces", tags=["network-interfaces"])


# ==================== Request/Response Models ====================


class SetMetricRequest(BaseModel):
    metric: int


class InterfaceActionResponse(BaseModel):
    success: bool
    message: str
    interface_name: Optional[str] = None
    status: Optional[Dict] = None


# ==================== Available Providers ====================


@router.get("/available")
async def get_available_interfaces() -> Dict:
    """
    Get list of available network interface providers.

    Returns:
        {
            "success": true,
            "interfaces": [
                {
                    "name": "ethernet",
                    "type": "ethernet",
                    "detected": true,
                    "status": {...},
                    "class": "EthernetInterface"
                },
                ...
            ],
            "count": 4
        }
    """
    try:
        registry = get_provider_registry()
        interfaces = registry.get_available_network_interfaces()

        return {"success": True, "interfaces": interfaces, "count": len(interfaces)}

    except Exception as e:
        logger.error(f"Error listing available network interfaces: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/detected")
async def get_detected_interfaces() -> Dict:
    """
    Get only detected (available) network interfaces.

    Returns:
        {
            "success": true,
            "interfaces": [
                {
                    "name": "ethernet",
                    "type": "ethernet",
                    "status": {...}
                },
                ...
            ],
            "count": 2
        }
    """
    try:
        registry = get_provider_registry()
        all_interfaces = registry.get_available_network_interfaces()

        # Filter only detected interfaces
        detected = [iface for iface in all_interfaces if iface.get("detected", False)]

        return {"success": True, "interfaces": detected, "count": len(detected)}

    except Exception as e:
        logger.error(f"Error listing detected network interfaces: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Interface Status ====================


@router.get("/status/{interface_name}")
async def get_interface_status(interface_name: str) -> Dict:
    """
    Get status of a specific network interface.

    Args:
        interface_name: Name of the interface provider (e.g., 'ethernet', 'wifi')

    Returns:
        {
            "success": true,
            "interface_name": "eth0",
            "interface_type": "ethernet",
            "state": "up",
            "ip_address": "192.168.1.100",
            ...
        }
    """
    try:
        registry = get_provider_registry()
        provider = registry.get_network_interface(interface_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=f"Network interface provider '{interface_name}' not found",
            )

        # Check if interface is detected
        if not provider.detect():
            return {
                "success": False,
                "error": f"Interface '{interface_name}' not detected on system",
            }

        # Get status
        status = provider.get_status()

        return {"success": True, **status}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting status for interface '{interface_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Interface Control ====================


@router.post("/bring-up/{interface_name}")
async def bring_up_interface(interface_name: str, request: Request) -> InterfaceActionResponse:
    """
    Bring up a network interface.

    Args:
        interface_name: Name of the interface provider (e.g., 'ethernet', 'wifi')

    Returns:
        InterfaceActionResponse with success status
    """
    try:
        lang = get_language_from_request(request)
        registry = get_provider_registry()
        provider = registry.get_network_interface(interface_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=f"Network interface provider '{interface_name}' not found",
            )

        # Check if interface exists
        if not provider.detect():
            raise HTTPException(
                status_code=404,
                detail=f"Interface '{interface_name}' not detected on system",
            )

        # Bring up the interface
        success = provider.bring_up()

        # Get updated status
        status = provider.get_status() if success else None

        return InterfaceActionResponse(
            success=success,
            message=(
                translate("network.interface_brought_up", lang, interface=interface_name)
                if success
                else translate("network.interface_up_failed", lang)
            ),
            interface_name=status.get("interface_name") if status else None,
            status=status,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error bringing up interface '{interface_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bring-down/{interface_name}")
async def bring_down_interface(interface_name: str, request: Request) -> InterfaceActionResponse:
    """
    Bring down a network interface.

    Args:
        interface_name: Name of the interface provider (e.g., 'ethernet', 'wifi')

    Returns:
        InterfaceActionResponse with success status
    """
    try:
        lang = get_language_from_request(request)
        registry = get_provider_registry()
        provider = registry.get_network_interface(interface_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=f"Network interface provider '{interface_name}' not found",
            )

        # Check if interface exists
        if not provider.detect():
            raise HTTPException(
                status_code=404,
                detail=f"Interface '{interface_name}' not detected on system",
            )

        # Bring down the interface
        success = provider.bring_down()

        # Get updated status
        status = provider.get_status() if provider.detect() else None

        return InterfaceActionResponse(
            success=success,
            message=(
                translate("network.interface_brought_down", lang, interface=interface_name)
                if success
                else translate("network.interface_down_failed", lang)
            ),
            interface_name=status.get("interface_name") if status else None,
            status=status,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error bringing down interface '{interface_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Routing Priority (Metric) ====================


@router.post("/set-metric/{interface_name}")
async def set_interface_metric(
    interface_name: str, request_body: SetMetricRequest, request: Request
) -> InterfaceActionResponse:
    """
    Set routing metric (priority) for a network interface.
    Lower metric = higher priority.

    Typical values:
    - VPN: 10 (highest priority)
    - Primary connection: 100
    - Secondary connection: 200

    Args:
        interface_name: Name of the interface provider
        request_body: SetMetricRequest with metric value

    Returns:
        InterfaceActionResponse with success status
    """
    try:
        lang = get_language_from_request(request)
        registry = get_provider_registry()
        provider = registry.get_network_interface(interface_name)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=f"Network interface provider '{interface_name}' not found",
            )

        # Check if interface exists
        if not provider.detect():
            raise HTTPException(
                status_code=404,
                detail=f"Interface '{interface_name}' not detected on system",
            )

        # Validate metric range
        if request_body.metric < 0 or request_body.metric > 999:
            raise HTTPException(status_code=400, detail="Metric must be between 0 and 999")

        # Set metric
        success = provider.set_metric(request_body.metric)

        # Get updated status
        status = provider.get_status() if success else None

        return InterfaceActionResponse(
            success=success,
            message=(
                translate(
                    "network.metric_set",
                    lang,
                    metric=request_body.metric,
                    interface=interface_name,
                )
                if success
                else translate("network.metric_set_failed", lang)
            ),
            interface_name=status.get("interface_name") if status else None,
            status=status,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting metric for interface '{interface_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== WiFi-specific endpoints ====================


@router.get("/wifi/scan")
async def scan_wifi_networks() -> Dict:
    """
    Scan for available WiFi networks.

    Returns:
        {
            "success": true,
            "networks": [
                {
                    "ssid": "MyWiFi",
                    "signal": 75,
                    "security": "WPA2"
                },
                ...
            ],
            "count": 5
        }
    """
    try:
        registry = get_provider_registry()
        provider = registry.get_network_interface("wifi")

        if not provider:
            raise HTTPException(status_code=404, detail="WiFi interface provider not found")

        # Check if WiFi interface exists
        if not provider.detect():
            return {
                "success": False,
                "error": "No WiFi interface detected on system",
                "networks": [],
                "count": 0,
            }

        # Scan networks
        networks = provider.scan_networks()

        return {"success": True, "networks": networks, "count": len(networks)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error scanning WiFi networks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class WiFiConnectRequest(BaseModel):
    ssid: str
    password: Optional[str] = None


@router.post("/wifi/connect")
async def connect_wifi(request: WiFiConnectRequest) -> InterfaceActionResponse:
    """
    Connect to a WiFi network.

    Args:
        request: WiFiConnectRequest with SSID and password

    Returns:
        InterfaceActionResponse with connection status
    """
    try:
        registry = get_provider_registry()
        provider = registry.get_network_interface("wifi")

        if not provider:
            raise HTTPException(status_code=404, detail="WiFi interface provider not found")

        # Check if WiFi interface exists
        if not provider.detect():
            raise HTTPException(status_code=404, detail="No WiFi interface detected on system")

        # Connect to network
        success = provider.connect(request.ssid, request.password)

        # Get updated status
        status = provider.get_status() if success else None

        return InterfaceActionResponse(
            success=success,
            message=(f"Connected to '{request.ssid}'" if success else f"Failed to connect to '{request.ssid}'"),
            interface_name=status.get("interface_name") if status else None,
            status=status,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error connecting to WiFi: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/wifi/disconnect")
async def disconnect_wifi() -> InterfaceActionResponse:
    """
    Disconnect from current WiFi network.

    Returns:
        InterfaceActionResponse with disconnection status
    """
    try:
        registry = get_provider_registry()
        provider = registry.get_network_interface("wifi")

        if not provider:
            raise HTTPException(status_code=404, detail="WiFi interface provider not found")

        # Check if WiFi interface exists
        if not provider.detect():
            raise HTTPException(status_code=404, detail="No WiFi interface detected on system")

        # Disconnect
        success = provider.disconnect()

        # Get updated status
        status = provider.get_status() if provider.detect() else None

        return InterfaceActionResponse(
            success=success,
            message="Disconnected from WiFi" if success else "Failed to disconnect",
            interface_name=status.get("interface_name") if status else None,
            status=status,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disconnecting WiFi: {e}")
        raise HTTPException(status_code=500, detail=str(e))
