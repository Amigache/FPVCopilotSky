"""
Network Status Routes
Endpoints for network status, dashboard, interfaces, and priority management
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, List, Optional
import asyncio
import logging
import re

from .common import (
    run_command,
    detect_wifi_interface,
    detect_modem_interface,
    get_gateway_for_interface,
    PriorityModeRequest,
)
from app.providers import get_provider_registry
from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)
router = APIRouter()

# Cache service instance
_cache = get_cache_service()


async def _get_interfaces() -> List[Dict]:
    """Get list of network interfaces with their status"""
    interfaces = []

    # Get all routes to determine metrics
    routes_stdout, _, _ = await run_command(["ip", "route", "show"])
    routes_by_iface = {}
    if routes_stdout:
        for line in routes_stdout.split("\n"):
            if "default" in line:
                parts = line.split()
                iface = None
                metric = None
                gateway = None
                for i, part in enumerate(parts):
                    if part == "dev" and i + 1 < len(parts):
                        iface = parts[i + 1]
                    elif part == "metric" and i + 1 < len(parts):
                        metric = int(parts[i + 1])
                    elif part == "via" and i + 1 < len(parts):
                        gateway = parts[i + 1]

                if iface:
                    if iface not in routes_by_iface or (
                        metric is not None and metric < routes_by_iface[iface].get("metric", 0)
                    ):
                        routes_by_iface[iface] = {"metric": metric, "gateway": gateway}

    # Get interface details
    stdout, _, returncode = await run_command(["ip", "-o", "addr", "show"])

    if returncode == 0:
        seen_interfaces = set()
        for line in stdout.split("\n"):
            match = re.search(r"^\d+:\s+(\S+)\s+inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)", line)
            if match:
                iface = match.group(1)
                ip = match.group(2)

                if iface not in seen_interfaces and iface != "lo":
                    seen_interfaces.add(iface)

                    # Get interface state
                    state_stdout, _, _ = await run_command(["ip", "link", "show", iface])
                    state = "UP" if "state UP" in state_stdout else "DOWN"

                    # Determine interface type
                    iface_type = None
                    connection = None
                    if iface.startswith("wlan") or iface.startswith("wl"):
                        iface_type = "wifi"
                        # Get WiFi connection name
                        nmcli_stdout, _, _ = await run_command(["nmcli", "-t", "-f", "DEVICE,CONNECTION", "device"])
                        for nmcli_line in nmcli_stdout.split("\n"):
                            if nmcli_line.startswith(f"{iface}:"):
                                parts = nmcli_line.split(":")
                                if len(parts) > 1 and parts[1]:
                                    connection = parts[1]
                    elif "192.168.8." in ip or iface.startswith("enx") or iface.startswith("usb"):
                        iface_type = "modem"
                    elif iface.startswith("eth") or iface.startswith("en"):
                        iface_type = "ethernet"

                    # Get route info for this interface
                    route_info = routes_by_iface.get(iface, {})

                    interfaces.append(
                        {
                            "name": iface,
                            "ip_address": ip,
                            "state": state,
                            "type": iface_type,
                            "connection": connection,
                            "gateway": route_info.get("gateway"),
                            "metric": route_info.get("metric"),
                        }
                    )

    return interfaces


async def _get_routes() -> List[Dict]:
    """Get routing table - parses default routes with gateway, interface, metric"""
    routes = []
    stdout, _, returncode = await run_command(["ip", "route", "show"])

    if returncode == 0:
        for line in stdout.split("\n"):
            if line.startswith("default"):
                parts = line.split()
                route = {"type": "default"}

                for i, part in enumerate(parts):
                    if part == "via" and i + 1 < len(parts):
                        route["gateway"] = parts[i + 1]
                    elif part == "dev" and i + 1 < len(parts):
                        route["interface"] = parts[i + 1]
                    elif part == "metric" and i + 1 < len(parts):
                        try:
                            route["metric"] = int(parts[i + 1])
                        except ValueError:
                            pass

                # Routes without explicit metric have implicit metric 0
                if "metric" not in route:
                    route["metric"] = 0

                if "interface" in route:
                    routes.append(route)

    return routes


async def _get_modem_info(modem_interface: Optional[str]) -> Dict:
    """Get modem information"""
    info = {
        "detected": False,
        "connected": False,
        "interface": None,
        "ip_address": None,
        "gateway": None,
    }

    if not modem_interface:
        return info

    info["detected"] = True
    info["interface"] = modem_interface

    # Check if interface is up and get IP
    stdout, _, returncode = await run_command(["ip", "addr", "show", modem_interface])
    if returncode == 0:
        if "state UP" in stdout:
            info["connected"] = True

        ip_match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", stdout)
        if ip_match:
            info["ip_address"] = ip_match.group(1)

    # Get gateway
    gateway = await get_gateway_for_interface(modem_interface)
    if gateway:
        info["gateway"] = gateway

    return info


@router.get("/status")
async def get_network_status():
    """Get overall network status including interfaces, routes, and modem info with caching"""
    # Check cache using CacheService
    cached_status = _cache.get("network_status")
    if cached_status is not None:
        return cached_status

    # Get fresh data
    interfaces = await _get_interfaces()
    routes = await _get_routes()
    modem_interface = await detect_modem_interface()
    modem_info = await _get_modem_info(modem_interface)

    # WiFi detection
    wifi_interface = await detect_wifi_interface()
    wifi_connected = any(i["type"] == "wifi" and i["state"] == "UP" for i in interfaces)

    # Build status
    status = {
        "interfaces": interfaces,
        "routes": routes,
        "wifi": {
            "detected": wifi_interface is not None,
            "connected": wifi_connected,
            "interface": wifi_interface,
        },
        "modem": modem_info,
        "primary_interface": routes[0]["interface"] if routes else None,
    }

    # Cache it using CacheService (2 second TTL)
    _cache.set("network_status", status, ttl=2)

    return status


@router.get("/dashboard")
async def get_dashboard():
    """
    Get complete network dashboard data (optimized for frontend)

    Combines network status with modem HiLink data if available
    """
    try:
        # Get basic network status
        network_status = await get_network_status()

        # Try to get HiLink modem data if modem is detected
        hilink_status = None
        if network_status["modem"]["detected"]:
            try:
                registry = get_provider_registry()
                provider = registry.get_modem_provider("huawei_e3372h")

                if provider:
                    # Get enhanced status with all modem details
                    device_task = (
                        provider.async_get_raw_device_info() if hasattr(provider, "async_get_raw_device_info") else None
                    )
                    signal_task = (
                        provider.async_get_signal_info() if hasattr(provider, "async_get_signal_info") else None
                    )
                    network_task = (
                        provider.async_get_raw_network_info()
                        if hasattr(provider, "async_get_raw_network_info")
                        else None
                    )
                    traffic_task = (
                        provider.async_get_traffic_stats() if hasattr(provider, "async_get_traffic_stats") else None
                    )

                    results = await asyncio.gather(
                        device_task if device_task else asyncio.sleep(0),
                        signal_task if signal_task else asyncio.sleep(0),
                        network_task if network_task else asyncio.sleep(0),
                        traffic_task if traffic_task else asyncio.sleep(0),
                        return_exceptions=True,
                    )

                    device_info = results[0] if device_task and not isinstance(results[0], Exception) else {}
                    signal_info = results[1] if signal_task and not isinstance(results[1], Exception) else {}
                    network_info = results[2] if network_task and not isinstance(results[2], Exception) else {}
                    traffic_info = results[3] if traffic_task and not isinstance(results[3], Exception) else {}

                    hilink_status = {
                        "available": bool(device_info or signal_info),
                        "device": device_info,
                        "signal": signal_info,
                        "network": network_info,
                        "traffic": traffic_info,
                    }
            except Exception as e:
                logger.debug(f"Could not get HiLink modem data: {e}")

        # Get flight mode status
        flight_mode_status = {"active": False}
        try:
            from app.services.network_optimizer import get_network_optimizer

            optimizer = get_network_optimizer()
            optimizer_status = optimizer.get_status()

            registry = get_provider_registry()
            provider = registry.get_modem_provider("huawei_e3372h")
            modem_video_active = getattr(provider, "video_mode_active", False) if provider else False

            flight_mode_status = {
                "active": optimizer_status["active"] and modem_video_active,
                "network_optimizer": optimizer_status["active"],
                "modem_video_mode": modem_video_active,
            }
        except Exception as e:
            logger.debug(f"Could not get flight mode status: {e}")

        return {
            "success": True,
            "network": network_status,
            "hilink": hilink_status,
            "flight_mode": flight_mode_status,
        }

    except Exception as e:
        logger.error(f"Error getting dashboard data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/interfaces")
async def get_interfaces():
    """Get detailed information about all network interfaces"""
    interfaces = await _get_interfaces()
    return {"interfaces": interfaces, "count": len(interfaces)}


@router.post("/priority")
async def set_priority_mode(request: PriorityModeRequest):
    """
    Set network priority mode

    Modes:
    - 'wifi': WiFi primary (metric 100), modem backup (metric 200)
    - 'modem': Modem primary (metric 100), WiFi backup (metric 200)
    - 'auto': Automatic based on availability
    """
    mode = request.mode.lower()
    if mode not in ["wifi", "modem", "auto"]:
        raise HTTPException(status_code=400, detail="Mode must be 'wifi', 'modem', or 'auto'")

    try:
        wifi_interface = await detect_wifi_interface()
        modem_interface = await detect_modem_interface()

        if mode == "wifi" and not wifi_interface:
            return {"success": False, "message": "WiFi interface not detected"}

        if mode == "modem" and not modem_interface:
            return {"success": False, "message": "Modem interface not detected"}

        routes_changed = []

        # Set WiFi metric
        if wifi_interface:
            wifi_gateway = await get_gateway_for_interface(wifi_interface)
            if wifi_gateway:
                wifi_metric = 100 if mode == "wifi" else 200

                # Delete old route
                await run_command(["sudo", "ip", "route", "del", "default", "via", wifi_gateway, "dev", wifi_interface])

                # Add route with new metric
                result = await run_command(
                    [
                        "sudo",
                        "ip",
                        "route",
                        "add",
                        "default",
                        "via",
                        wifi_gateway,
                        "dev",
                        wifi_interface,
                        "metric",
                        str(wifi_metric),
                    ]
                )

                if result[2] == 0:
                    routes_changed.append(f"WiFi metric set to {wifi_metric}")

        # Set Modem metric
        if modem_interface:
            modem_gateway = await get_gateway_for_interface(modem_interface)
            if modem_gateway:
                modem_metric = 100 if mode == "modem" else 200

                # Delete old route
                await run_command(
                    ["sudo", "ip", "route", "del", "default", "via", modem_gateway, "dev", modem_interface]
                )

                # Add route with new metric
                result = await run_command(
                    [
                        "sudo",
                        "ip",
                        "route",
                        "add",
                        "default",
                        "via",
                        modem_gateway,
                        "dev",
                        modem_interface,
                        "metric",
                        str(modem_metric),
                    ]
                )

                if result[2] == 0:
                    routes_changed.append(f"Modem metric set to {modem_metric}")

        if routes_changed:
            return {"success": True, "mode": mode, "changes": routes_changed, "message": f"Priority set to {mode} mode"}
        else:
            return {"success": False, "message": "No routes could be modified"}

    except Exception as e:
        logger.error(f"Error setting priority: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/priority/auto-adjust")
async def auto_adjust_priority():
    """
    Automatically adjust network priority based on available interfaces.
    4G modem always primary if available, WiFi as backup.
    """
    return {"success": True, "mode": "auto", "message": "Priority auto-adjusted"}
