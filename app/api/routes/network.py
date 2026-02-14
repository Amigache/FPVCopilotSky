"""
Network API Routes - Provider-based implementation
Endpoints for WiFi, modem, and network priority management

Uses new modular provider system:
- ModemProvider (HuaweiE3372hProvider) for 4G modem operations
- NetworkInterface providers for connection management
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, List
import logging
import asyncio
import re
import time
from providers import get_provider_registry
from app.services.network_optimizer import get_network_optimizer
from app.services.latency_monitor import get_latency_monitor, start_latency_monitoring, stop_latency_monitoring
from app.services.auto_failover import get_auto_failover, stop_auto_failover, NetworkMode
from app.services.dns_cache import get_dns_cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/network", tags=["network"])


class WiFiConnectRequest(BaseModel):
    ssid: str
    password: Optional[str] = None


class PriorityModeRequest(BaseModel):
    mode: str  # 'wifi', 'modem', or 'auto'


class ForgetConnectionRequest(BaseModel):
    name: str


class NetworkModeRequest(BaseModel):
    mode: str  # '00'=Auto, '01'=2G, '02'=3G, '03'=4G


class LTEBandRequest(BaseModel):
    preset: Optional[str] = None  # 'all', 'orange', 'urban', 'rural', etc.
    custom_mask: Optional[int] = None  # Custom band mask


class APNRequest(BaseModel):
    preset: Optional[str] = None
    custom_apn: Optional[str] = None


class RoamingRequest(BaseModel):
    enabled: bool


class LatencyTestRequest(BaseModel):
    host: Optional[str] = None
    count: Optional[int] = None


# =====================
# Helper Functions for Network Status
# =====================


async def _run_command(cmd: List[str]) -> tuple:
    """Run a command asynchronously and return stdout, stderr, returncode"""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        return stdout.decode().strip(), stderr.decode().strip(), proc.returncode
    except Exception as e:
        logger.error(f"Error running command {cmd}: {e}")
        return "", str(e), -1


async def _detect_wifi_interface() -> Optional[str]:
    """Detect WiFi interface using nmcli"""
    stdout, _, returncode = await _run_command(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device"])
    if returncode == 0:
        for line in stdout.split("\n"):
            if ":wifi:" in line:
                parts = line.split(":")
                if len(parts) >= 1:
                    return parts[0]
    return None


async def _detect_modem_interface() -> Optional[str]:
    """Detect USB 4G modem interface (looks for 192.168.8.x IP)"""
    stdout, _, returncode = await _run_command(["ip", "-o", "addr", "show"])
    if returncode == 0:
        for line in stdout.split("\n"):
            if "192.168.8." in line:
                match = re.search(r"^\d+:\s+(\S+)\s+inet\s+192\.168\.8\.", line)
                if match:
                    return match.group(1)
    return None


async def _get_interfaces() -> List[Dict]:
    """Get list of network interfaces with their status"""
    interfaces = []

    # Get all routes to determine metrics
    routes_stdout, _, _ = await _run_command(["ip", "route", "show"])
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
    stdout, _, returncode = await _run_command(["ip", "-o", "addr", "show"])

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
                    state_stdout, _, _ = await _run_command(["ip", "link", "show", iface])
                    state = "UP" if "state UP" in state_stdout else "DOWN"

                    # Determine interface type
                    iface_type = None
                    connection = None
                    if iface.startswith("wlan") or iface.startswith("wl"):
                        iface_type = "wifi"
                        # Get WiFi connection name
                        nmcli_stdout, _, _ = await _run_command(["nmcli", "-t", "-f", "DEVICE,CONNECTION", "device"])
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


async def _scan_wifi_networks() -> List[Dict]:
    """Scan for available WiFi networks using iw"""
    networks = []

    # Get WiFi interface
    wifi_interface = await _detect_wifi_interface()
    if not wifi_interface:
        return networks

    # Get current connection SSID
    current_ssid = None
    stdout, _, returncode = await _run_command(["iw", "dev", wifi_interface, "link"])
    if returncode == 0:
        for line in stdout.split("\n"):
            if "SSID:" in line:
                current_ssid = line.split("SSID:", 1)[1].strip()
                break

    # Scan WiFi networks (requires sudo)
    stdout, _, returncode = await _run_command(["sudo", "iw", "dev", wifi_interface, "scan"])

    if returncode == 0:
        seen_ssids = set()
        current_network = {}

        for line in stdout.split("\n"):
            line = line.strip()

            # New BSS entry
            if line.startswith("BSS "):
                # Save previous network if it has SSID
                if current_network.get("ssid"):
                    ssid = current_network["ssid"]
                    if ssid not in seen_ssids:
                        seen_ssids.add(ssid)
                        networks.append(current_network)

                # Start new network
                current_network = {
                    "ssid": None,
                    "signal": 0,
                    "security": "Open",
                    "connected": False,
                }

                # Check if this is the connected network
                if "-- associated" in line:
                    current_network["connected"] = True

            # SSID
            elif line.startswith("SSID:"):
                ssid = line.split("SSID:", 1)[1].strip()
                if ssid:
                    current_network["ssid"] = ssid
                    if ssid == current_ssid:
                        current_network["connected"] = True

            # Signal strength
            elif "signal:" in line:
                try:
                    signal_str = line.split("signal:", 1)[1].strip()
                    signal_dbm = float(signal_str.split()[0])
                    # Convert dBm to percentage (rough approximation)
                    # -30 dBm = 100%, -90 dBm = 0%
                    signal_percent = max(0, min(100, int((signal_dbm + 90) * (100 / 60))))
                    current_network["signal"] = signal_percent
                except Exception:
                    pass

            # Security
            elif "RSN:" in line or "WPA:" in line:
                current_network["security"] = "WPA2" if "RSN:" in line else "WPA"
            elif "Privacy:" in line and "WEP" in line:
                current_network["security"] = "WEP"

        # Don't forget the last network
        if current_network.get("ssid"):
            ssid = current_network["ssid"]
            if ssid not in seen_ssids:
                networks.append(current_network)

        # Sort by signal strength
        networks.sort(key=lambda x: x["signal"], reverse=True)

    return networks

    return networks


async def _get_routes() -> List[Dict]:
    """Get routing table - parses default routes with gateway, interface, metric"""
    routes = []
    stdout, _, returncode = await _run_command(["ip", "route", "show"])

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
    stdout, _, returncode = await _run_command(["ip", "addr", "show", modem_interface])
    if returncode == 0:
        if "state UP" in stdout:
            info["connected"] = True

        ip_match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", stdout)
        if ip_match:
            info["ip_address"] = ip_match.group(1)

    # Get gateway
    stdout, _, returncode = await _run_command(["ip", "route", "show", "dev", modem_interface])
    if returncode == 0:
        for line in stdout.split("\n"):
            if "default" in line:
                match = re.search(r"via\s+(\d+\.\d+\.\d+\.\d+)", line)
                if match:
                    info["gateway"] = match.group(1)
                    break

    return info


# Network status cache
_network_status_cache = {"data": None, "timestamp": 0, "ttl": 2}  # Cache for 2 seconds


@router.get("/status")
async def get_network_status():
    """Get overall network status including interfaces, routes, and modem info with caching"""
    current_time = time.time()

    # Check cache
    if _network_status_cache["data"] is not None:
        cache_age = current_time - _network_status_cache["timestamp"]
        if cache_age < _network_status_cache["ttl"]:
            return _network_status_cache["data"]

    # Cache miss or expired - fetch fresh data
    try:
        # Detect interfaces
        wifi_interface = await _detect_wifi_interface()
        modem_interface = await _detect_modem_interface()

        # Get network data
        interfaces = await _get_interfaces()
        routes = await _get_routes()
        modem = await _get_modem_info(modem_interface)

        # Determine primary interface and mode
        primary_interface = None
        mode = "unknown"

        if routes:
            # Primary is the route with lowest metric
            primary_route = min(routes, key=lambda r: r.get("metric", 0))
            primary_interface = primary_route.get("interface")

            if primary_interface == modem_interface:
                mode = "modem"
            elif primary_interface == wifi_interface:
                mode = "wifi"

        result = {
            "success": True,
            "wifi_interface": wifi_interface,
            "modem_interface": modem_interface,
            "primary_interface": primary_interface,
            "mode": mode,
            "interfaces": interfaces,
            "routes": routes,
            "modem": modem,
        }

        # Update cache
        _network_status_cache["data"] = result
        _network_status_cache["timestamp"] = current_time

        return result
    except Exception as e:
        logger.error(f"Error getting network status: {e}")
        error_result = {
            "success": False,
            "error": str(e),
            "wifi_interface": None,
            "modem_interface": None,
            "primary_interface": None,
            "mode": "unknown",
            "interfaces": [],
            "routes": [],
            "modem": {"detected": False},
        }

        # Don't cache errors, but return them
        return error_result


# =============================
# Dashboard - Unified Endpoint
# =============================

# Simple in-memory cache
_dashboard_cache = {"data": None, "timestamp": 0, "ttl": 2}  # Cache for 2 seconds


@router.get("/dashboard")
async def get_network_dashboard(force_refresh: bool = False):
    """
    Unified dashboard endpoint - returns all network data in one call

    Combines:
    - Network status (interfaces, routes, mode)
    - Modem HiLink status (device, signal, network, traffic)
    - WiFi networks list
    - Flight Mode status

    Uses intelligent caching (2s TTL) to avoid redundant calls.
    Use ?force_refresh=true to bypass cache.

    Returns:
        Complete network dashboard data
    """
    current_time = time.time()

    # Check cache (unless force refresh)
    if not force_refresh and _dashboard_cache["data"] is not None:
        cache_age = current_time - _dashboard_cache["timestamp"]
        if cache_age < _dashboard_cache["ttl"]:
            logger.debug(f"Returning cached dashboard (age: {cache_age:.2f}s)")
            return {**_dashboard_cache["data"], "cached": True, "cache_age": round(cache_age, 2)}

    try:
        # Execute all data fetching in parallel for maximum speed
        results = await asyncio.gather(
            _get_network_status_internal(),  # Network status
            _get_modem_status_internal(),  # Modem HiLink status
            _get_wifi_networks_internal(),  # WiFi networks
            _get_flight_mode_status_internal(),  # Flight Mode
            return_exceptions=True,
        )

        network_status = results[0] if not isinstance(results[0], Exception) else {}
        modem_status = results[1] if not isinstance(results[1], Exception) else {"available": False}
        wifi_networks = results[2] if not isinstance(results[2], Exception) else []
        flight_mode = results[3] if not isinstance(results[3], Exception) else {"active": False}

        dashboard_data = {
            "success": True,
            "timestamp": current_time,
            "network": network_status,
            "modem": modem_status,
            "wifi_networks": wifi_networks,
            "flight_mode": flight_mode,
            "cached": False,
        }

        # Update cache
        _dashboard_cache["data"] = dashboard_data
        _dashboard_cache["timestamp"] = current_time

        logger.debug("Dashboard data refreshed")
        return dashboard_data

    except Exception as e:
        logger.error(f"Error building dashboard: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to build dashboard: {str(e)}")


async def _get_network_status_internal() -> Dict:
    """Internal: Get network status (interfaces, routes, mode)"""
    try:
        wifi_interface = await _detect_wifi_interface()
        modem_interface = await _detect_modem_interface()
        interfaces = await _get_interfaces()
        routes = await _get_routes()
        modem = await _get_modem_info(modem_interface)

        primary_interface = None
        mode = "unknown"

        if routes:
            primary_route = min(routes, key=lambda r: r.get("metric", 0))
            primary_interface = primary_route.get("interface")

            if primary_interface == modem_interface:
                mode = "modem"
            elif primary_interface == wifi_interface:
                mode = "wifi"

        return {
            "wifi_interface": wifi_interface,
            "modem_interface": modem_interface,
            "primary_interface": primary_interface,
            "mode": mode,
            "interfaces": interfaces,
            "routes": routes,
            "modem": modem,
        }
    except Exception as e:
        logger.error(f"Error in _get_network_status_internal: {e}")
        return {
            "wifi_interface": None,
            "modem_interface": None,
            "primary_interface": None,
            "mode": "unknown",
            "interfaces": [],
            "routes": [],
            "modem": {"detected": False},
        }


async def _get_modem_status_internal() -> Dict:
    """Internal: Get modem HiLink status"""
    try:
        provider = _get_modem_provider()

        # Gather all modem info in parallel
        tasks = []
        if hasattr(provider, "async_get_device_info"):
            tasks.append(provider.async_get_device_info())
        if hasattr(provider, "async_get_signal_info"):
            tasks.append(provider.async_get_signal_info())
        if hasattr(provider, "async_get_network_info"):
            tasks.append(provider.async_get_network_info())
        if hasattr(provider, "async_get_traffic_stats"):
            tasks.append(provider.async_get_traffic_stats())

        if not tasks:
            return {"available": False, "error": "No async methods available"}

        results = await asyncio.gather(*tasks, return_exceptions=True)

        device_info = results[0] if len(results) > 0 and not isinstance(results[0], Exception) else None
        signal_info = results[1] if len(results) > 1 and not isinstance(results[1], Exception) else None
        network_info = results[2] if len(results) > 2 and not isinstance(results[2], Exception) else None
        traffic_info = results[3] if len(results) > 3 and not isinstance(results[3], Exception) else None

        available = any([device_info, signal_info, network_info, traffic_info])

        response = {"available": available, "connected": available}

        if device_info:
            response["device"] = {
                "device_name": getattr(device_info, "name", "Unknown"),
                "imei": getattr(device_info, "imei", None),
                "model": getattr(device_info, "model", None),
            }

        if signal_info:
            response["signal"] = signal_info
            signal_percent = signal_info.get("signal_percent", 0)
            response["signal"]["signal_bars"] = min(5, max(0, int(signal_percent / 20))) if signal_percent else 0

        if network_info:
            dns_servers = getattr(network_info, "dns_servers", None) or []
            signal_percent = signal_info.get("signal_percent", 0) if signal_info else 0
            signal_icon = min(5, max(0, int(signal_percent / 20))) if signal_percent else 0

            response["network"] = {
                "network_type": str(network_info.network_type) if hasattr(network_info, "network_type") else None,
                "signal_icon": signal_icon,
                "roaming": getattr(network_info, "roaming", False),
                "primary_dns": dns_servers[0] if len(dns_servers) > 0 else None,
                "secondary_dns": dns_servers[1] if len(dns_servers) > 1 else None,
            }

        if traffic_info:
            response["traffic"] = traffic_info

        return response

    except Exception as e:
        logger.debug(f"Modem not available: {e}")
        return {"available": False, "connected": False}


async def _get_wifi_networks_internal() -> List[Dict]:
    """Internal: Get WiFi networks list"""
    try:
        networks = await _scan_wifi_networks()
        return networks
    except Exception as e:
        logger.debug(f"WiFi scan failed: {e}")
        return []


async def _get_flight_mode_status_internal() -> Dict:
    """Internal: Get Flight Mode status"""
    try:
        optimizer = get_network_optimizer()
        network_status = optimizer.get_status()

        provider = _get_modem_provider()
        modem_video_active = getattr(provider, "video_mode_active", False)

        fully_active = network_status["active"] and modem_video_active

        return {
            "active": fully_active,
            "network_optimizer_active": network_status["active"],
            "modem_video_mode_active": modem_video_active,
        }
    except Exception as e:
        logger.debug(f"Flight Mode status unavailable: {e}")
        return {"active": False}


@router.get("/interfaces")
async def get_interfaces():
    """Get list of all network interface providers"""
    registry = get_provider_registry()
    interfaces = registry.get_available_network_interfaces()
    return {"success": True, "interfaces": interfaces}


@router.get("/wifi/networks")
async def get_wifi_networks():
    """Scan and return available WiFi networks using WiFi provider"""
    try:
        # Get WiFi provider
        registry = get_provider_registry()
        wifi_provider = registry.get_network_interface("wifi")

        if not wifi_provider:
            logger.warning("WiFi provider not available")
            return {"success": True, "networks": []}

        # Use provider's scan_networks method
        loop = asyncio.get_event_loop()
        networks = await loop.run_in_executor(None, wifi_provider.scan_networks)

        # Add security info (stub for now - could be enhanced)
        for network in networks:
            if "security" not in network:
                network["security"] = "WPA2"  # Default assumption
            if "connected" not in network:
                # Check if this network is currently connected
                status = wifi_provider.get_status()
                network["connected"] = network.get("ssid") == status.get("ssid")

        return {"success": True, "networks": networks}

    except Exception as e:
        logger.error(f"Error scanning WiFi networks: {e}")
        return {"success": False, "networks": [], "error": str(e)}


@router.post("/wifi/connect")
async def connect_wifi(request: WiFiConnectRequest):
    """Connect to a WiFi network using NetworkManager"""
    try:
        # Get WiFi provider
        registry = get_provider_registry()
        wifi_provider = registry.get_network_interface("wifi")

        if not wifi_provider:
            raise HTTPException(status_code=503, detail="WiFi provider not available")

        # Use provider's connect method
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, wifi_provider.connect, request.ssid, request.password)

        if result.get("success"):
            logger.info(f"Successfully connected to WiFi: {request.ssid}")
            # Wait a moment for connection to stabilize
            await asyncio.sleep(1)

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error connecting to WiFi {request.ssid}: {e}")
        raise HTTPException(status_code=500, detail=f"Connection failed: {str(e)}")


@router.post("/wifi/disconnect")
async def disconnect_wifi():
    """Disconnect from current WiFi network"""
    try:
        # Get WiFi provider
        registry = get_provider_registry()
        wifi_provider = registry.get_network_interface("wifi")

        if not wifi_provider:
            raise HTTPException(status_code=404, detail="WiFi provider not available")

        # Use provider's disconnect method
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, wifi_provider.disconnect)

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disconnecting WiFi: {e}")
        raise HTTPException(status_code=500, detail=f"Disconnection failed: {str(e)}")


@router.get("/wifi/saved")
async def get_saved_connections():
    """Get list of saved network connections"""
    # Return empty list - saved connections managed by NetworkManager
    return {"success": True, "connections": []}


@router.post("/wifi/forget")
async def forget_connection(request: ForgetConnectionRequest):
    """Delete a saved connection"""
    return {"success": True, "message": f"Removed {request.name}"}


@router.get("/routes")
async def get_routes():
    """Get current routing table"""
    # Simplified - returns empty routes for now
    return {"success": True, "routes": []}


@router.post("/priority")
async def set_priority_mode(request: PriorityModeRequest):
    """
    Set network priority mode by adjusting route metrics.

    Uses nmcli for NetworkManager-managed interfaces (WiFi) and
    ip route for non-NM interfaces (USB modem).

    Args:
        mode: 'wifi' (WiFi primary), 'modem' (4G primary), or 'auto' (4G preferred)
    """
    if request.mode not in ["wifi", "modem", "auto"]:
        raise HTTPException(status_code=400, detail="Mode must be 'wifi', 'modem', or 'auto'")

    try:
        # Auto mode: prefer modem if available, else WiFi
        if request.mode == "auto":
            modem_interface = await _detect_modem_interface()
            if modem_interface:
                return await set_priority_mode(PriorityModeRequest(mode="modem"))
            else:
                wifi_interface = await _detect_wifi_interface()
                if wifi_interface:
                    return await set_priority_mode(PriorityModeRequest(mode="wifi"))
                else:
                    raise HTTPException(status_code=503, detail="No interfaces available")

        # Detect interfaces
        wifi_interface = await _detect_wifi_interface()
        modem_interface = await _detect_modem_interface()

        if not wifi_interface and not modem_interface:
            raise HTTPException(status_code=503, detail="No network interfaces detected")

        if request.mode == "wifi" and not wifi_interface:
            raise HTTPException(status_code=503, detail="WiFi interface not detected")
        if request.mode == "modem" and not modem_interface:
            raise HTTPException(status_code=503, detail="Modem interface not detected")

        errors = []

        # --- WiFi metric (NM-managed) ---
        if wifi_interface:
            wifi_metric = 100 if request.mode == "wifi" else 600
            wifi_conn = await _get_nm_connection_name(wifi_interface)
            if wifi_conn:
                # Set metric via nmcli (persistent)
                _, stderr, rc = await _run_command(
                    [
                        "sudo",
                        "nmcli",
                        "connection",
                        "modify",
                        wifi_conn,
                        "ipv4.route-metric",
                        str(wifi_metric),
                    ]
                )
                if rc != 0:
                    errors.append(f"WiFi metric modify failed: {stderr}")
                    logger.error(f"nmcli modify failed for {wifi_conn}: {stderr}")
                else:
                    # Reactivate connection to apply new metric
                    _, stderr, rc = await _run_command(["sudo", "nmcli", "connection", "up", wifi_conn])
                    if rc != 0:
                        errors.append(f"WiFi connection reactivate failed: {stderr}")
                        logger.error(f"nmcli connection up failed for {wifi_conn}: {stderr}")
                    else:
                        logger.info(f"WiFi {wifi_conn} metric set to {wifi_metric}")
            else:
                logger.warning(f"No NM connection found for {wifi_interface}, " "trying ip route fallback")
                await _set_route_metric_fallback(wifi_interface, wifi_metric, errors)

        # --- Modem metric (not NM-managed, use ip route) ---
        if modem_interface:
            modem_metric = 100 if request.mode == "modem" else 600
            modem_conn = await _get_nm_connection_name(modem_interface)
            if modem_conn:
                # Modem is NM-managed, use nmcli
                _, stderr, rc = await _run_command(
                    [
                        "sudo",
                        "nmcli",
                        "connection",
                        "modify",
                        modem_conn,
                        "ipv4.route-metric",
                        str(modem_metric),
                    ]
                )
                if rc != 0:
                    errors.append(f"Modem metric modify failed: {stderr}")
                else:
                    _, stderr, rc = await _run_command(["sudo", "nmcli", "connection", "up", modem_conn])
                    if rc != 0:
                        errors.append(f"Modem connection reactivate failed: {stderr}")
                    else:
                        logger.info(f"Modem {modem_conn} metric set to {modem_metric}")
            else:
                # Modem is not NM-managed, use ip route directly
                await _set_route_metric_fallback(modem_interface, modem_metric, errors)

        # Wait for routes to settle
        await asyncio.sleep(1.0)

        # Verify the switch actually worked
        routes = await _get_routes()
        primary_route = min(routes, key=lambda r: r.get("metric", 0)) if routes else None
        actual_primary = primary_route.get("interface") if primary_route else None

        expected_primary = wifi_interface if request.mode == "wifi" else modem_interface
        verified = actual_primary == expected_primary

        if errors:
            logger.warning(f"Priority mode {request.mode} set with errors: {errors}")
        if not verified:
            logger.warning(f"Priority verification failed: expected {expected_primary}, " f"got {actual_primary}")

        logger.info(f"Network priority set to {request.mode} " f"(verified={verified}, primary={actual_primary})")

        # Invalidate dashboard cache
        _dashboard_cache["data"] = None
        _dashboard_cache["timestamp"] = 0

        return {
            "success": len(errors) == 0,
            "mode": request.mode,
            "verified": verified,
            "actual_primary": actual_primary,
            "message": (
                f"Priority set to {request.mode}" if not errors else f"Priority set with warnings: {'; '.join(errors)}"
            ),
            "errors": errors if errors else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting network priority: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to set priority: {str(e)}")


async def _get_nm_connection_name(interface: str) -> Optional[str]:
    """Get the NetworkManager connection name for an interface"""
    stdout, _, rc = await _run_command(["nmcli", "-t", "-f", "DEVICE,NAME", "connection", "show", "--active"])
    if rc == 0:
        for line in stdout.split("\n"):
            parts = line.split(":", 1)
            if len(parts) == 2 and parts[0] == interface:
                return parts[1]
    return None


async def _set_route_metric_fallback(interface: str, metric: int, errors: list):
    """Fallback: set route metric using ip route for non-NM interfaces"""
    # Find current default route for this interface
    routes = await _get_routes()
    iface_routes = [r for r in routes if r.get("interface") == interface]

    gateway = None
    if iface_routes:
        gateway = iface_routes[0].get("gateway")

    if not gateway:
        # Try to discover gateway from interface's subnet
        gateway = await _discover_gateway(interface)

    if not gateway:
        errors.append(f"No gateway found for {interface}")
        logger.error(f"Cannot set metric for {interface}: no gateway found")
        return

    # Delete existing default routes for this interface
    for route in iface_routes:
        gw = route.get("gateway")
        if gw:
            del_cmd = [
                "sudo",
                "ip",
                "route",
                "del",
                "default",
                "via",
                gw,
                "dev",
                interface,
            ]
            _, stderr, rc = await _run_command(del_cmd)
            if rc != 0:
                logger.warning(f"Failed to delete route for {interface}: {stderr}")

    # Add new route with desired metric
    add_cmd = [
        "sudo",
        "ip",
        "route",
        "add",
        "default",
        "via",
        gateway,
        "dev",
        interface,
        "metric",
        str(metric),
    ]
    _, stderr, rc = await _run_command(add_cmd)
    if rc != 0:
        errors.append(f"Failed to add route for {interface}: {stderr}")
        logger.error(f"ip route add failed for {interface}: {stderr}")
    else:
        logger.info(f"Route metric for {interface} set to {metric}")


async def _discover_gateway(interface: str) -> Optional[str]:
    """Discover default gateway for an interface from its IP subnet"""
    stdout, _, rc = await _run_command(["ip", "-o", "addr", "show", interface])
    if rc == 0:
        match = re.search(r"inet\s+(\d+\.\d+\.\d+)\.\d+", stdout)
        if match:
            # Assume gateway is .1 on the subnet
            return f"{match.group(1)}.1"
    return None


@router.post("/priority/auto-adjust")
async def auto_adjust_priority():
    """
    Automatically adjust network priority based on available interfaces.
    4G modem always primary if available, WiFi as backup.
    """
    return {"success": True, "mode": "auto", "message": "Priority auto-adjusted"}


# =====================
# Modem Provider Endpoints (using HuaweiE3372hProvider)
# =====================


def _get_modem_provider():
    """Helper to get modem provider"""
    registry = get_provider_registry()
    provider = registry.get_modem_provider("huawei_e3372h")
    if not provider:
        raise HTTPException(status_code=503, detail="Modem provider not available")
    return provider


@router.get("/modem/status")
async def get_modem_status():
    """Get full modem status including signal, network, traffic, device"""
    try:
        provider = _get_modem_provider()

        # Gather all modem info in parallel
        device_task = provider.async_get_device_info() if hasattr(provider, "async_get_device_info") else None
        signal_task = provider.async_get_signal_info() if hasattr(provider, "async_get_signal_info") else None
        network_task = provider.async_get_network_info() if hasattr(provider, "async_get_network_info") else None
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

        # Check if modem is available (at least one successful response)
        available = any([device_info, signal_info, network_info, traffic_info])

        # Build response in format expected by frontend
        response = {"success": True, "available": available, "connected": available}

        # Add device info
        if device_info:
            response["device"] = {
                "device_name": getattr(device_info, "name", "Unknown"),
                "imei": getattr(device_info, "imei", None),
                "imsi": getattr(device_info, "imsi", None),
                "model": getattr(device_info, "model", None),
            }

        # Add signal info with signal_bars calculation
        if signal_info:
            response["signal"] = signal_info
            # Add signal_bars (1-5) based on signal_percent
            signal_percent = signal_info.get("signal_percent", 0)
            response["signal"]["signal_bars"] = min(5, max(0, int(signal_percent / 20))) if signal_percent else 0

        # Add network info
        if network_info:
            dns_servers = getattr(network_info, "dns_servers", None) or []
            # Calculate signal_icon from signal_percent if available
            signal_percent = signal_info.get("signal_percent", 0) if signal_info else 0
            signal_icon = min(5, max(0, int(signal_percent / 20))) if signal_percent else 0

            response["network"] = {
                "network_type": (str(network_info.network_type) if hasattr(network_info, "network_type") else None),
                "signal_icon": signal_icon,
                "roaming": getattr(network_info, "roaming", False),
                "primary_dns": dns_servers[0] if len(dns_servers) > 0 else None,
                "secondary_dns": dns_servers[1] if len(dns_servers) > 1 else None,
            }

        # Add traffic info
        if traffic_info:
            response["traffic"] = traffic_info

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
        logger.error(f"Error getting modem status: {e}")
        return {
            "success": True,
            "available": False,
            "connected": False,
            "error": str(e),
        }


@router.get("/modem/device")
async def get_modem_device():
    """Get modem device information"""
    provider = _get_modem_provider()
    if hasattr(provider, "async_get_device_info"):
        info = await provider.async_get_device_info()
    else:
        info = provider.get_modem_info()

    if info:
        return {
            "success": True,
            "device": str(info),
            "name": getattr(info, "name", "Unknown"),
        }
    raise HTTPException(status_code=503, detail="Could not get device info")


@router.get("/modem/signal")
async def get_modem_signal():
    """Get modem signal information"""
    provider = _get_modem_provider()
    if hasattr(provider, "async_get_signal_info"):
        info = await provider.async_get_signal_info()
    else:
        info = provider.get_signal_info()

    if info:
        return {"success": True, **info}
    raise HTTPException(status_code=503, detail="Could not get signal info")


@router.get("/modem/network")
async def get_modem_network():
    """Get modem network/carrier information"""
    provider = _get_modem_provider()
    if hasattr(provider, "async_get_network_info"):
        info = await provider.async_get_network_info()
    else:
        info = provider.get_network_info()

    if info:
        return {"success": True, "status": str(info.status) if info else None}
    raise HTTPException(status_code=503, detail="Could not get network info")


@router.get("/modem/traffic")
async def get_modem_traffic():
    """Get modem traffic statistics"""
    provider = _get_modem_provider()
    if hasattr(provider, "async_get_traffic_stats"):
        stats = await provider.async_get_traffic_stats()
    else:
        stats = provider.get_traffic_stats()

    if stats:
        return {"success": True, **stats}
    raise HTTPException(status_code=503, detail="Could not get traffic stats")


@router.get("/modem/mode")
async def get_modem_mode():
    """Get modem network mode settings"""
    provider = _get_modem_provider()
    if hasattr(provider, "get_network_mode"):
        loop = asyncio.get_event_loop()
        mode = await loop.run_in_executor(None, provider.get_network_mode)
        if mode:
            return {"success": True, **mode}
    raise HTTPException(status_code=503, detail="Could not get network mode")


@router.post("/modem/mode")
async def set_modem_mode(request: NetworkModeRequest):
    """
    Set modem network mode

    Modes:
    - '00': Auto (4G/3G/2G)
    - '01': 2G Only
    - '02': 3G Only
    - '03': 4G Only
    """
    valid_modes = ["00", "01", "02", "03"]
    if request.mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Mode must be one of: {valid_modes}")

    provider = _get_modem_provider()
    if hasattr(provider, "set_network_mode"):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: provider.set_network_mode(request.mode))
        if result:
            return {"success": True, "message": f"Network mode set to {request.mode}"}
    raise HTTPException(status_code=500, detail="Failed to set network mode")


@router.post("/modem/reboot")
async def reboot_modem():
    """Reboot the modem"""
    provider = _get_modem_provider()
    if hasattr(provider, "reboot"):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, provider.reboot)
        if result and result.get("success"):
            return {"success": True, "message": "Modem is rebooting"}
    raise HTTPException(status_code=500, detail="Failed to reboot modem")


# =============================
# LTE Band Management
# =============================


@router.get("/modem/band")
async def get_current_band():
    """Get current LTE band information"""
    provider = _get_modem_provider()
    if hasattr(provider, "get_current_band"):
        loop = asyncio.get_event_loop()
        band = await loop.run_in_executor(None, provider.get_current_band)
        if band:
            return {"success": True, **band}
    raise HTTPException(status_code=503, detail="Could not get band info")


@router.get("/modem/band/presets")
async def get_band_presets():
    """Get available LTE band presets"""
    provider = _get_modem_provider()
    if hasattr(provider, "get_band_presets"):
        presets = provider.get_band_presets()
        return {"success": True, **presets}
    raise HTTPException(status_code=503, detail="Could not get presets")


@router.post("/modem/band")
async def set_lte_band(request: LTEBandRequest):
    """
    Set LTE band configuration

    Presets:
    - 'all': All bands (auto)
    - 'orange_spain': B3+B7+B20 (Orange optimal)
    - 'urban': B3+B7 (high speed)
    - 'rural': B20 only (best coverage)
    - 'balanced': B3+B20
    """
    if not request.preset and request.custom_mask is None:
        raise HTTPException(status_code=400, detail="Provide either preset or custom_mask")

    provider = _get_modem_provider()
    if hasattr(provider, "set_lte_band"):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: provider.set_lte_band(preset=request.preset, custom_mask=request.custom_mask),
        )
        if result and result.get("success"):
            return result
    raise HTTPException(status_code=500, detail="Failed to set band")


# =============================
# Video Quality Assessment
# =============================


@router.get("/modem/video-quality")
async def get_video_quality():
    """
    Get video streaming quality assessment based on current signal
    """
    provider = _get_modem_provider()
    if hasattr(provider, "get_video_quality_assessment"):
        loop = asyncio.get_event_loop()
        assessment = await loop.run_in_executor(None, provider.get_video_quality_assessment)
        return {"success": assessment.get("available", False), **assessment}
    raise HTTPException(status_code=503, detail="Could not assess video quality")


@router.get("/modem/status/enhanced")
async def get_enhanced_status():
    """Get full modem status with video optimization data"""
    try:
        provider = _get_modem_provider()

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
        # get_current_band() already reads net_mode which includes network_mode, so we avoid a duplicate call
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
        logger.error(f"Error getting enhanced modem status: {e}")
        return {
            "success": True,
            "available": False,
            "connected": False,
            "error": str(e),
        }


# =============================
# APN Configuration
# =============================


@router.get("/modem/apn")
async def get_apn_settings():
    """Get current APN settings and available presets"""
    provider = _get_modem_provider()
    if hasattr(provider, "get_apn_settings"):
        loop = asyncio.get_event_loop()
        settings = await loop.run_in_executor(None, provider.get_apn_settings)
        return {"success": True, **settings}
    raise HTTPException(status_code=503, detail="Could not get APN settings")


@router.post("/modem/apn")
async def set_apn(request: APNRequest):
    """
    Set APN configuration

    Presets for Spain:
    - 'orange': Standard Orange APN
    - 'orangeworld': Orange data APN
    - 'simyo': Simyo (uses Orange network)
    """
    if not request.preset and not request.custom_apn:
        raise HTTPException(status_code=400, detail="Provide either preset or custom_apn")

    provider = _get_modem_provider()
    if hasattr(provider, "set_apn"):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: provider.set_apn(preset=request.preset, custom_apn=request.custom_apn),
        )
        if result and result.get("success"):
            return result
    raise HTTPException(status_code=500, detail="Failed to set APN")


# =============================
# Network Control
# =============================


@router.post("/modem/reconnect")
async def reconnect_network():
    """Force network reconnection to search for better cell tower"""
    provider = _get_modem_provider()
    if hasattr(provider, "reconnect_network"):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, provider.reconnect_network)
        if result and result.get("success"):
            return result
    raise HTTPException(status_code=500, detail="Reconnection failed")


@router.post("/modem/roaming")
async def set_roaming(request: RoamingRequest):
    """Enable or disable roaming"""
    provider = _get_modem_provider()
    if hasattr(provider, "set_roaming"):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: provider.set_roaming(request.enabled))
        if result and result.get("success"):
            return result
    raise HTTPException(status_code=500, detail="Failed to set roaming")


# =============================
# Video Mode Profile
# =============================


@router.get("/modem/video-mode")
async def get_video_mode_status():
    """Check if video mode is currently active"""
    provider = _get_modem_provider()
    video_mode_active = False
    if hasattr(provider, "video_mode_active"):
        video_mode_active = provider.video_mode_active
    return {"success": True, "video_mode_active": video_mode_active}


@router.post("/modem/video-mode/enable")
async def enable_video_mode():
    """
    Enable video-optimized modem settings:
    - Forces 4G Only mode
    - Optimizes for low latency
    """
    provider = _get_modem_provider()
    if hasattr(provider, "enable_video_mode"):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, provider.enable_video_mode)
        if result and result.get("success"):
            return result
    raise HTTPException(status_code=500, detail="Failed to enable video mode")


@router.post("/modem/video-mode/disable")
async def disable_video_mode():
    """Disable video mode and restore original settings"""
    provider = _get_modem_provider()
    if hasattr(provider, "disable_video_mode"):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, provider.disable_video_mode)
        if result and result.get("success"):
            return result
    raise HTTPException(status_code=500, detail="Failed to disable video mode")


# =============================
# Flight Session
# =============================


@router.get("/modem/flight-session")
async def get_flight_session():
    """Get current flight session status and statistics"""
    provider = _get_modem_provider()
    if hasattr(provider, "get_flight_session_status"):
        status = provider.get_flight_session_status()
        return {"success": True, **status}
    return {"success": True, "status": "no_session"}


@router.post("/modem/flight-session/start")
async def start_flight_session():
    """Start recording flight session statistics"""
    provider = _get_modem_provider()
    if hasattr(provider, "start_flight_session"):
        result = provider.start_flight_session()
        return result
    raise HTTPException(status_code=500, detail="Could not start session")


@router.post("/modem/flight-session/stop")
async def stop_flight_session():
    """Stop recording and get session statistics summary"""
    provider = _get_modem_provider()
    if hasattr(provider, "stop_flight_session"):
        result = provider.stop_flight_session()
        if result and result.get("success"):
            return result
    raise HTTPException(status_code=400, detail="No active session")


@router.post("/modem/flight-session/sample")
async def record_flight_sample():
    """Record a signal quality sample (call periodically during flight)"""
    provider = _get_modem_provider()
    if hasattr(provider, "record_flight_sample"):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, provider.record_flight_sample)
        if result:
            if result.get("success"):
                return result
            else:
                # Session not active, return success=False instead of 400 error
                return {
                    "success": False,
                    "message": result.get("message", "No active session"),
                }
    return {"success": False, "message": "Flight session not available"}


# =============================
# Latency Monitoring
# =============================


@router.get("/modem/latency")
async def measure_latency():
    """Measure current network latency and jitter"""
    provider = _get_modem_provider()
    if hasattr(provider, "measure_latency"):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, provider.measure_latency)
        if result and result.get("success"):
            return result
        # Return error details instead of generic 500
        if result:
            return result
    raise HTTPException(status_code=500, detail="Latency test failed")


@router.post("/modem/latency")
async def measure_latency_custom(request: LatencyTestRequest):
    """Measure latency to a custom host"""
    provider = _get_modem_provider()
    if hasattr(provider, "measure_latency"):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: provider.measure_latency(host=request.host, count=request.count),
        )
        if result and result.get("success"):
            return result
        if result:
            return result
    raise HTTPException(status_code=500, detail="Latency test failed")


# =============================
# Flight Mode - Complete Network Optimization
# =============================


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

        # Get modem video mode status
        provider = _get_modem_provider()
        modem_video_active = getattr(provider, "video_mode_active", False)

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
            provider = _get_modem_provider()
            if hasattr(provider, "enable_video_mode"):
                loop = asyncio.get_event_loop()
                modem_result = await loop.run_in_executor(None, provider.enable_video_mode)
                results["modem"] = modem_result
                if not modem_result.get("success"):
                    errors.append(f"Modem: {modem_result.get('message', 'Unknown error')}")
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
            provider = _get_modem_provider()
            if hasattr(provider, "disable_video_mode"):
                loop = asyncio.get_event_loop()
                modem_result = await loop.run_in_executor(None, provider.disable_video_mode)
                results["modem"] = modem_result
                if not modem_result.get("success"):
                    errors.append(f"Modem: {modem_result.get('message', 'Unknown error')}")
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


# =====================
# Latency Monitoring Endpoints
# =====================


@router.post("/latency/start")
async def start_latency_monitor():
    """Start continuous latency monitoring"""
    try:
        await start_latency_monitoring()
        return {"success": True, "message": "Latency monitoring started"}
    except Exception as e:
        logger.error(f"Error starting latency monitor: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/latency/stop")
async def stop_latency_monitor():
    """Stop continuous latency monitoring"""
    try:
        await stop_latency_monitoring()
        return {"success": True, "message": "Latency monitoring stopped"}
    except Exception as e:
        logger.error(f"Error stopping latency monitor: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latency/current")
async def get_current_latency():
    """
    Get current latency statistics for all monitored targets

    Returns average, min, max latency and packet loss for each target
    """
    try:
        monitor = get_latency_monitor()
        stats = await monitor.get_current_latency()

        # Convert LatencyStats objects to dicts
        stats_dict = {}
        for target, stat in stats.items():
            stats_dict[target] = {
                "target": stat.target,
                "interface": stat.interface,
                "avg_latency_ms": round(stat.avg_latency, 2),
                "min_latency_ms": round(stat.min_latency, 2),
                "max_latency_ms": round(stat.max_latency, 2),
                "packet_loss_percent": round(stat.packet_loss, 2),
                "sample_count": stat.sample_count,
                "last_update": stat.last_update,
            }

        return {"success": True, "latency": stats_dict, "timestamp": time.time()}

    except Exception as e:
        logger.error(f"Error getting current latency: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latency/history")
async def get_latency_history(target: Optional[str] = None, last_n: int = 30):
    """
    Get historical latency data

    Args:
        target: Specific target to query (None for all)
        last_n: Number of recent samples to return
    """
    try:
        monitor = get_latency_monitor()
        history = monitor.get_history(target=target, last_n=last_n)

        # Convert to serializable format
        history_dict = {}
        for t, results in history.items():
            history_dict[t] = [
                {
                    "target": r.target,
                    "latency_ms": r.latency_ms,
                    "timestamp": r.timestamp,
                    "success": r.success,
                    "interface": r.interface,
                }
                for r in results
            ]

        return {"success": True, "history": history_dict, "sample_count": sum(len(v) for v in history_dict.values())}

    except Exception as e:
        logger.error(f"Error getting latency history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latency/interface/{interface}")
async def get_interface_latency(interface: str):
    """
    Get latency statistics for a specific network interface

    Args:
        interface: Network interface name (e.g., wlan0, enx...)
    """
    try:
        monitor = get_latency_monitor()
        stat = await monitor.get_interface_latency(interface)

        if not stat:
            return {"success": True, "available": False, "message": "No latency data available for this interface"}

        return {
            "success": True,
            "available": True,
            "interface": interface,
            "latency": {
                "avg_ms": round(stat.avg_latency, 2),
                "min_ms": round(stat.min_latency, 2),
                "max_ms": round(stat.max_latency, 2),
                "packet_loss_percent": round(stat.packet_loss, 2),
                "sample_count": stat.sample_count,
                "last_update": stat.last_update,
            },
        }

    except Exception as e:
        logger.error(f"Error getting interface latency: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/latency/test/{interface}")
async def test_interface_latency(interface: str, count: int = 3):
    """
    Perform one-time latency test for an interface

    Args:
        interface: Network interface to test
        count: Number of pings per target (default: 3)
    """
    try:
        monitor = get_latency_monitor()
        stat = await monitor.test_interface_latency(interface, count)

        return {
            "success": True,
            "interface": interface,
            "test_results": {
                "avg_ms": round(stat.avg_latency, 2),
                "min_ms": round(stat.min_latency, 2),
                "max_ms": round(stat.max_latency, 2),
                "packet_loss_percent": round(stat.packet_loss, 2),
                "samples": stat.sample_count,
                "targets_tested": len(monitor.targets),
            },
        }

    except Exception as e:
        logger.error(f"Error testing interface latency: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/latency/history")
async def clear_latency_history():
    """Clear all latency history"""
    try:
        monitor = get_latency_monitor()
        monitor.clear_history()
        return {"success": True, "message": "Latency history cleared"}
    except Exception as e:
        logger.error(f"Error clearing latency history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================
# Auto-Failover Endpoints
# =====================


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
            except Exception as e:
                logger.error(f"Error in failover switch callback: {e}")
                return False

        # Set callback and start
        failover.switch_callback = switch_network
        await failover.start(initial_mode=mode)

        return {"success": True, "message": "Auto-failover started", "initial_mode": initial_mode}

    except Exception as e:
        logger.error(f"Error starting auto-failover: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/failover/stop")
async def stop_failover():
    """Stop automatic network failover"""
    try:
        await stop_auto_failover()
        return {"success": True, "message": "Auto-failover stopped"}
    except Exception as e:
        logger.error(f"Error stopping auto-failover: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/failover/status")
async def get_failover_status():
    """Get current auto-failover status and configuration"""
    try:
        failover = get_auto_failover()
        state = await failover.get_state()

        return {"success": True, **state}

    except Exception as e:
        logger.error(f"Error getting failover status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class FailoverConfigRequest(BaseModel):
    latency_threshold_ms: Optional[float] = None
    latency_check_window: Optional[int] = None
    switch_cooldown_s: Optional[float] = None
    restore_delay_s: Optional[float] = None
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

    except Exception as e:
        logger.error(f"Error updating failover config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
            raise HTTPException(status_code=500, detail="Failed to execute switch")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error forcing failover switch: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================
# DNS Caching Endpoints
# =====================


@router.get("/dns/status")
async def get_dns_cache_status():
    """Get DNS cache status and statistics"""
    try:
        dns_cache = get_dns_cache()
        status = await dns_cache.get_status()

        return {"success": True, **status}

    except Exception as e:
        logger.error(f"Error getting DNS cache status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dns/start")
async def start_dns_cache():
    """Start DNS caching service (dnsmasq)"""
    try:
        dns_cache = get_dns_cache()
        success = await dns_cache.start()

        if success:
            return {"success": True, "message": "DNS caching started", "cache_size": dns_cache.config.cache_size}
        else:
            raise HTTPException(status_code=500, detail="Failed to start DNS cache")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting DNS cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dns/stop")
async def stop_dns_cache():
    """Stop DNS caching service"""
    try:
        dns_cache = get_dns_cache()
        success = await dns_cache.stop()

        if success:
            return {"success": True, "message": "DNS caching stopped"}
        else:
            raise HTTPException(status_code=500, detail="Failed to stop DNS cache")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping DNS cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dns/clear")
async def clear_dns_cache():
    """Clear DNS cache"""
    try:
        dns_cache = get_dns_cache()
        success = await dns_cache.clear_cache()

        if success:
            return {"success": True, "message": "DNS cache cleared"}
        else:
            raise HTTPException(status_code=500, detail="Failed to clear DNS cache")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing DNS cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dns/install")
async def install_dns_cache():
    """Install dnsmasq package"""
    try:
        dns_cache = get_dns_cache()

        # Check if already installed
        if await dns_cache.is_installed():
            return {"success": True, "message": "dnsmasq already installed", "already_installed": True}

        success = await dns_cache.install()

        if success:
            return {"success": True, "message": "dnsmasq installed successfully", "already_installed": False}
        else:
            raise HTTPException(status_code=500, detail="Failed to install dnsmasq")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error installing DNS cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))
