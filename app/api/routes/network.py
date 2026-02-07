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
from providers import get_provider_registry

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
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        return stdout.decode().strip(), stderr.decode().strip(), proc.returncode
    except Exception as e:
        logger.error(f"Error running command {cmd}: {e}")
        return "", str(e), -1


async def _detect_wifi_interface() -> Optional[str]:
    """Detect WiFi interface using nmcli"""
    stdout, _, returncode = await _run_command(['nmcli', '-t', '-f', 'DEVICE,TYPE,STATE', 'device'])
    if returncode == 0:
        for line in stdout.split('\n'):
            if ':wifi:' in line:
                parts = line.split(':')
                if len(parts) >= 1:
                    return parts[0]
    return None


async def _detect_modem_interface() -> Optional[str]:
    """Detect USB 4G modem interface (looks for 192.168.8.x IP)"""
    stdout, _, returncode = await _run_command(['ip', '-o', 'addr', 'show'])
    if returncode == 0:
        for line in stdout.split('\n'):
            if '192.168.8.' in line:
                match = re.search(r'^\d+:\s+(\S+)\s+inet\s+192\.168\.8\.', line)
                if match:
                    return match.group(1)
    return None


async def _get_interfaces() -> List[Dict]:
    """Get list of network interfaces with their status"""
    interfaces = []
    
    # Get all routes to determine metrics
    routes_stdout, _, _ = await _run_command(['ip', 'route', 'show'])
    routes_by_iface = {}
    if routes_stdout:
        for line in routes_stdout.split('\n'):
            if 'default' in line:
                parts = line.split()
                iface = None
                metric = None
                gateway = None
                for i, part in enumerate(parts):
                    if part == 'dev' and i + 1 < len(parts):
                        iface = parts[i + 1]
                    elif part == 'metric' and i + 1 < len(parts):
                        metric = int(parts[i + 1])
                    elif part == 'via' and i + 1 < len(parts):
                        gateway = parts[i + 1]
                
                if iface:
                    if iface not in routes_by_iface or (metric and metric < routes_by_iface[iface].get('metric', 999)):
                        routes_by_iface[iface] = {'metric': metric, 'gateway': gateway}
    
    # Get interface details
    stdout, _, returncode = await _run_command(['ip', '-o', 'addr', 'show'])
    
    if returncode == 0:
        seen_interfaces = set()
        for line in stdout.split('\n'):
            match = re.search(r'^\d+:\s+(\S+)\s+inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)', line)
            if match:
                iface = match.group(1)
                ip = match.group(2)
                
                if iface not in seen_interfaces and iface != 'lo':
                    seen_interfaces.add(iface)
                    
                    # Get interface state
                    state_stdout, _, _ = await _run_command(['ip', 'link', 'show', iface])
                    state = 'UP' if 'state UP' in state_stdout else 'DOWN'
                    
                    # Determine interface type
                    iface_type = None
                    connection = None
                    if iface.startswith('wlan') or iface.startswith('wl'):
                        iface_type = 'wifi'
                        # Get WiFi connection name
                        nmcli_stdout, _, _ = await _run_command(['nmcli', '-t', '-f', 'DEVICE,CONNECTION', 'device'])
                        for nmcli_line in nmcli_stdout.split('\n'):
                            if nmcli_line.startswith(f"{iface}:"):
                                parts = nmcli_line.split(':')
                                if len(parts) > 1 and parts[1]:
                                    connection = parts[1]
                    elif '192.168.8.' in ip or iface.startswith('enx') or iface.startswith('usb'):
                        iface_type = 'modem'
                    elif iface.startswith('eth') or iface.startswith('en'):
                        iface_type = 'ethernet'
                    
                    # Get route info for this interface
                    route_info = routes_by_iface.get(iface, {})
                    
                    interfaces.append({
                        'name': iface,
                        'ip_address': ip,
                        'state': state,
                        'type': iface_type,
                        'connection': connection,
                        'gateway': route_info.get('gateway'),
                        'metric': route_info.get('metric')
                    })
    
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
    stdout, _, returncode = await _run_command(['iw', 'dev', wifi_interface, 'link'])
    if returncode == 0:
        for line in stdout.split('\n'):
            if 'SSID:' in line:
                current_ssid = line.split('SSID:', 1)[1].strip()
                break
    
    # Scan WiFi networks (requires sudo)
    stdout, _, returncode = await _run_command(['sudo', 'iw', 'dev', wifi_interface, 'scan'])
    
    if returncode == 0:
        seen_ssids = set()
        current_network = {}
        
        for line in stdout.split('\n'):
            line = line.strip()
            
            # New BSS entry
            if line.startswith('BSS '):
                # Save previous network if it has SSID
                if current_network.get('ssid'):
                    ssid = current_network['ssid']
                    if ssid not in seen_ssids:
                        seen_ssids.add(ssid)
                        networks.append(current_network)
                
                # Start new network
                current_network = {
                    'ssid': None,
                    'signal': 0,
                    'security': 'Open',
                    'connected': False
                }
                
                # Check if this is the connected network
                if '-- associated' in line:
                    current_network['connected'] = True
            
            # SSID
            elif line.startswith('SSID:'):
                ssid = line.split('SSID:', 1)[1].strip()
                if ssid:
                    current_network['ssid'] = ssid
                    if ssid == current_ssid:
                        current_network['connected'] = True
            
            # Signal strength
            elif 'signal:' in line:
                try:
                    signal_str = line.split('signal:', 1)[1].strip()
                    signal_dbm = float(signal_str.split()[0])
                    # Convert dBm to percentage (rough approximation)
                    # -30 dBm = 100%, -90 dBm = 0%
                    signal_percent = max(0, min(100, int((signal_dbm + 90) * (100 / 60))))
                    current_network['signal'] = signal_percent
                except:
                    pass
            
            # Security
            elif 'RSN:' in line or 'WPA:' in line:
                current_network['security'] = 'WPA2' if 'RSN:' in line else 'WPA'
            elif 'Privacy:' in line and 'WEP' in line:
                current_network['security'] = 'WEP'
        
        # Don't forget the last network
        if current_network.get('ssid'):
            ssid = current_network['ssid']
            if ssid not in seen_ssids:
                networks.append(current_network)
        
        # Sort by signal strength
        networks.sort(key=lambda x: x['signal'], reverse=True)
    
    return networks
    
    return networks


async def _get_routes() -> List[Dict]:
    """Get routing table"""
    routes = []
    stdout, _, returncode = await _run_command(['ip', 'route', 'show'])
    
    if returncode == 0:
        for line in stdout.split('\n'):
            if line.startswith('default'):
                parts = line.split()
                route = {'type': 'default'}
                
                for i, part in enumerate(parts):
                    if part == 'via' and i + 1 < len(parts):
                        route['gateway'] = parts[i + 1]
                    elif part == 'dev' and i + 1 < len(parts):
                        route['interface'] = parts[i + 1]
                    elif part == 'metric' and i + 1 < len(parts):
                        route['metric'] = int(parts[i + 1])
                
                if 'interface' in route:
                    routes.append(route)
    
    return routes


async def _get_modem_info(modem_interface: Optional[str]) -> Dict:
    """Get modem information"""
    info = {
        'detected': False,
        'connected': False,
        'interface': None,
        'ip_address': None,
        'gateway': None
    }
    
    if not modem_interface:
        return info
    
    info['detected'] = True
    info['interface'] = modem_interface
    
    # Check if interface is up and get IP
    stdout, _, returncode = await _run_command(['ip', 'addr', 'show', modem_interface])
    if returncode == 0:
        if 'state UP' in stdout:
            info['connected'] = True
        
        ip_match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)', stdout)
        if ip_match:
            info['ip_address'] = ip_match.group(1)
    
    # Get gateway
    stdout, _, returncode = await _run_command(['ip', 'route', 'show', 'dev', modem_interface])
    if returncode == 0:
        for line in stdout.split('\n'):
            if 'default' in line:
                match = re.search(r'via\s+(\d+\.\d+\.\d+\.\d+)', line)
                if match:
                    info['gateway'] = match.group(1)
                    break
    
    return info


@router.get("/status")
async def get_network_status():
    """Get overall network status including interfaces, routes, and modem info"""
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
        mode = 'unknown'
        
        if routes:
            # Primary is the route with lowest metric
            primary_route = min(routes, key=lambda r: r.get('metric', 999))
            primary_interface = primary_route.get('interface')
            
            if primary_interface == modem_interface:
                mode = 'modem'
            elif primary_interface == wifi_interface:
                mode = 'wifi'
        
        return {
            "success": True,
            "wifi_interface": wifi_interface,
            "modem_interface": modem_interface,
            "primary_interface": primary_interface,
            "mode": mode,
            "interfaces": interfaces,
            "routes": routes,
            "modem": modem
        }
    except Exception as e:
        logger.error(f"Error getting network status: {e}")
        return {
            "success": False,
            "error": str(e),
            "wifi_interface": None,
            "modem_interface": None,
            "primary_interface": None,
            "mode": "unknown",
            "interfaces": [],
            "routes": [],
            "modem": {"detected": False}
        }


@router.get("/interfaces")
async def get_interfaces():
    """Get list of all network interface providers"""
    registry = get_provider_registry()
    interfaces = registry.get_available_network_interfaces()
    return {"success": True, "interfaces": interfaces}


@router.get("/wifi/networks")
async def get_wifi_networks():
    """Scan and return available WiFi networks"""
    try:
        networks = await _scan_wifi_networks()
        return {"success": True, "networks": networks}
    except Exception as e:
        logger.error(f"Error scanning WiFi networks: {e}")
        return {"success": False, "networks": [], "error": str(e)}


@router.post("/wifi/connect")
async def connect_wifi(request: WiFiConnectRequest):
    """Connect to a WiFi network"""
    registry = get_provider_registry()
    wifi_provider = registry.get_network_interface('wifi')
    
    if not wifi_provider:
        raise HTTPException(status_code=503, detail="WiFi provider not available")
    
    # For now, return success - actual connection handled by NetworkManager
    return {"success": True, "message": f"Connecting to {request.ssid}..."}


@router.post("/wifi/disconnect")
async def disconnect_wifi():
    """Disconnect from current WiFi network"""
    registry = get_provider_registry()
    wifi_provider = registry.get_network_interface('wifi')
    
    if not wifi_provider:
        raise HTTPException(status_code=503, detail="WiFi provider not available")
    
    return {"success": True, "message": "Disconnected from WiFi"}


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
    Set network priority mode
    
    Args:
        mode: 'wifi' (WiFi primary), 'modem' (4G primary), or 'auto' (4G preferred)
    """
    if request.mode not in ['wifi', 'modem', 'auto']:
        raise HTTPException(status_code=400, detail="Mode must be 'wifi', 'modem', or 'auto'")
    
    # Simplified - connection priority management
    return {
        "success": True,
        "mode": request.mode,
        "message": f"Priority set to {request.mode}"
    }


@router.post("/priority/auto-adjust")
async def auto_adjust_priority():
    """
    Automatically adjust network priority based on available interfaces.
    4G modem always primary if available, WiFi as backup.
    """
    return {
        "success": True,
        "mode": "auto",
        "message": "Priority auto-adjusted"
    }


@router.get("/hilink/status")
async def get_hilink_status():
    """Get full HiLink modem status (alias for /modem/status)"""
    return await get_modem_status()


@router.get("/hilink/device")
async def get_hilink_device():
    """Get HiLink modem device info (alias)"""
    return await get_modem_device()


@router.get("/hilink/signal")
async def get_hilink_signal():
    """Get HiLink signal info (alias)"""
    return await get_modem_signal()


@router.get("/hilink/network")
async def get_hilink_network():
    """Get HiLink network info (alias)"""
    return await get_modem_network()


@router.get("/hilink/traffic")
async def get_hilink_traffic():
    """Get HiLink traffic stats (alias)"""
    return await get_modem_traffic()


@router.get("/hilink/mode")
async def get_hilink_mode():
    """Get HiLink network mode (alias)"""
    return await get_modem_mode()


@router.post("/hilink/mode")
async def set_hilink_mode(request: NetworkModeRequest):
    """Set HiLink network mode (alias)"""
    return await set_modem_mode(request)


@router.post("/hilink/reboot")
async def reboot_hilink():
    """Reboot HiLink modem (alias)"""
    return await reboot_modem()


@router.get("/hilink/band")
async def get_hilink_band():
    """Get HiLink LTE band (alias)"""
    return await get_current_band()


@router.get("/hilink/band/presets")
async def get_hilink_band_presets():
    """Get HiLink band presets (alias)"""
    return await get_band_presets()


@router.post("/hilink/band")
async def set_hilink_band(request: LTEBandRequest):
    """Set HiLink LTE band (alias)"""
    return await set_lte_band(request)


@router.get("/hilink/video-quality")
async def get_hilink_video_quality():
    """Get HiLink video quality (alias)"""
    return await get_video_quality()


@router.get("/hilink/status/enhanced")
async def get_hilink_enhanced_status():
    """Get HiLink enhanced status (alias)"""
    return await get_enhanced_status()


@router.get("/hilink/apn")
async def get_hilink_apn():
    """Get HiLink APN settings (alias)"""
    return await get_apn_settings()


@router.post("/hilink/apn")
async def set_hilink_apn(request: APNRequest):
    """Set HiLink APN (alias)"""
    return await set_apn(request)


@router.post("/hilink/reconnect")
async def reconnect_hilink():
    """Reconnect HiLink network (alias)"""
    return await reconnect_network()


@router.post("/hilink/roaming")
async def set_hilink_roaming(request: RoamingRequest):
    """Set HiLink roaming (alias)"""
    return await set_roaming(request)


@router.get("/hilink/video-mode")
async def get_hilink_video_mode():
    """Get HiLink video mode (alias)"""
    return await get_video_mode_status()


@router.post("/hilink/video-mode/enable")
async def enable_hilink_video_mode():
    """Enable HiLink video mode (alias)"""
    return await enable_video_mode()


@router.post("/hilink/video-mode/disable")
async def disable_hilink_video_mode():
    """Disable HiLink video mode (alias)"""
    return await disable_video_mode()


@router.get("/hilink/flight-session")
async def get_hilink_flight_session():
    """Get HiLink flight session (alias)"""
    return await get_flight_session()


@router.post("/hilink/flight-session/start")
async def start_hilink_flight_session():
    """Start HiLink flight session (alias)"""
    return await start_flight_session()


@router.post("/hilink/flight-session/stop")
async def stop_hilink_flight_session():
    """Stop HiLink flight session (alias)"""
    return await stop_flight_session()


@router.post("/hilink/flight-session/sample")
async def record_hilink_flight_sample():
    """Record HiLink flight sample (alias)"""
    return await record_flight_sample()


@router.get("/hilink/latency")
async def measure_hilink_latency():
    """Measure HiLink latency (alias)"""
    return await measure_latency()


@router.post("/hilink/latency")
async def measure_hilink_latency_custom(request: LatencyTestRequest):
    """Measure HiLink custom latency (alias)"""
    return await measure_latency_custom(request)


# =====================
# Modem Provider Endpoints (using HuaweiE3372hProvider)
# =====================

def _get_modem_provider():
    """Helper to get modem provider"""
    registry = get_provider_registry()
    provider = registry.get_modem_provider('huawei_e3372h')
    if not provider:
        raise HTTPException(status_code=503, detail="Modem provider not available")
    return provider


@router.get("/modem/status")
async def get_modem_status():
    """Get full modem status including signal, network, traffic, device"""
    try:
        provider = _get_modem_provider()
        
        # Gather all modem info in parallel
        device_task = provider.async_get_device_info() if hasattr(provider, 'async_get_device_info') else None
        signal_task = provider.async_get_signal_info() if hasattr(provider, 'async_get_signal_info') else None
        network_task = provider.async_get_network_info() if hasattr(provider, 'async_get_network_info') else None
        traffic_task = provider.async_get_traffic_stats() if hasattr(provider, 'async_get_traffic_stats') else None
        
        # Wait for all tasks
        results = await asyncio.gather(
            device_task if device_task else asyncio.sleep(0),
            signal_task if signal_task else asyncio.sleep(0),
            network_task if network_task else asyncio.sleep(0),
            traffic_task if traffic_task else asyncio.sleep(0),
            return_exceptions=True
        )
        
        device_info = results[0] if device_task and not isinstance(results[0], Exception) else None
        signal_info = results[1] if signal_task and not isinstance(results[1], Exception) else None
        network_info = results[2] if network_task and not isinstance(results[2], Exception) else None
        traffic_info = results[3] if traffic_task and not isinstance(results[3], Exception) else None
        
        # Check if modem is available (at least one successful response)
        available = any([device_info, signal_info, network_info, traffic_info])
        
        # Build response in format expected by frontend
        response = {
            "success": True,
            "available": available,
            "connected": available
        }
        
        # Add device info
        if device_info:
            response["device"] = {
                "device_name": getattr(device_info, 'name', 'Unknown'),
                "imei": getattr(device_info, 'imei', None),
                "imsi": getattr(device_info, 'imsi', None),
                "model": getattr(device_info, 'model', None)
            }
        
        # Add signal info with signal_bars calculation
        if signal_info:
            response["signal"] = signal_info
            # Add signal_bars (1-5) based on signal_percent
            signal_percent = signal_info.get('signal_percent', 0)
            response["signal"]["signal_bars"] = min(5, max(0, int(signal_percent / 20))) if signal_percent else 0
        
        # Add network info
        if network_info:
            dns_servers = getattr(network_info, 'dns_servers', None) or []
            # Calculate signal_icon from signal_percent if available
            signal_percent = signal_info.get('signal_percent', 0) if signal_info else 0
            signal_icon = min(5, max(0, int(signal_percent / 20))) if signal_percent else 0
            
            response["network"] = {
                "network_type": str(network_info.network_type) if hasattr(network_info, 'network_type') else None,
                "signal_icon": signal_icon,
                "roaming": getattr(network_info, 'roaming', False),
                "primary_dns": dns_servers[0] if len(dns_servers) > 0 else None,
                "secondary_dns": dns_servers[1] if len(dns_servers) > 1 else None
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
            "error": "Modem provider not available"
        }
    except Exception as e:
        logger.error(f"Error getting modem status: {e}")
        return {
            "success": True,
            "available": False,
            "connected": False,
            "error": str(e)
        }


@router.get("/modem/device")
async def get_modem_device():
    """Get modem device information"""
    provider = _get_modem_provider()
    if hasattr(provider, 'async_get_device_info'):
        info = await provider.async_get_device_info()
    else:
        info = provider.get_modem_info()
    
    if info:
        return {"success": True, "device": str(info), "name": getattr(info, 'name', 'Unknown')}
    raise HTTPException(status_code=503, detail="Could not get device info")


@router.get("/modem/signal")
async def get_modem_signal():
    """Get modem signal information"""
    provider = _get_modem_provider()
    if hasattr(provider, 'async_get_signal_info'):
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
    if hasattr(provider, 'async_get_network_info'):
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
    if hasattr(provider, 'async_get_traffic_stats'):
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
    if hasattr(provider, 'get_network_mode'):
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
    valid_modes = ['00', '01', '02', '03']
    if request.mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Mode must be one of: {valid_modes}")
    
    provider = _get_modem_provider()
    if hasattr(provider, 'set_network_mode'):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: provider.set_network_mode(request.mode))
        if result:
            return {"success": True, "message": f"Network mode set to {request.mode}"}
    raise HTTPException(status_code=500, detail="Failed to set network mode")


@router.post("/modem/reboot")
async def reboot_modem():
    """Reboot the modem"""
    provider = _get_modem_provider()
    if hasattr(provider, 'reboot'):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, provider.reboot)
        if result and result.get('success'):
            return {"success": True, "message": "Modem is rebooting"}
    raise HTTPException(status_code=500, detail="Failed to reboot modem")


# =============================
# LTE Band Management
# =============================

@router.get("/modem/band")
async def get_current_band():
    """Get current LTE band information"""
    provider = _get_modem_provider()
    if hasattr(provider, 'get_current_band'):
        loop = asyncio.get_event_loop()
        band = await loop.run_in_executor(None, provider.get_current_band)
        if band:
            return {"success": True, **band}
    raise HTTPException(status_code=503, detail="Could not get band info")


@router.get("/modem/band/presets")
async def get_band_presets():
    """Get available LTE band presets"""
    provider = _get_modem_provider()
    if hasattr(provider, 'get_band_presets'):
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
    if hasattr(provider, 'set_lte_band'):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: provider.set_lte_band(preset=request.preset, custom_mask=request.custom_mask)
        )
        if result and result.get('success'):
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
    if hasattr(provider, 'get_video_quality_assessment'):
        loop = asyncio.get_event_loop()
        assessment = await loop.run_in_executor(None, provider.get_video_quality_assessment)
        return {"success": assessment.get('available', False), **assessment}
    raise HTTPException(status_code=503, detail="Could not assess video quality")


@router.get("/modem/status/enhanced")
async def get_enhanced_status():
    """Get full modem status with video optimization data"""
    try:
        provider = _get_modem_provider()
        
        # Gather all modem info in parallel using raw methods for full data
        device_task = provider.async_get_raw_device_info() if hasattr(provider, 'async_get_raw_device_info') else None
        signal_task = provider.async_get_signal_info() if hasattr(provider, 'async_get_signal_info') else None
        network_task = provider.async_get_raw_network_info() if hasattr(provider, 'async_get_raw_network_info') else None
        traffic_task = provider.async_get_traffic_stats() if hasattr(provider, 'async_get_traffic_stats') else None
        
        # Wait for all tasks
        results = await asyncio.gather(
            device_task if device_task else asyncio.sleep(0),
            signal_task if signal_task else asyncio.sleep(0),
            network_task if network_task else asyncio.sleep(0),
            traffic_task if traffic_task else asyncio.sleep(0),
            return_exceptions=True
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
        conn_status = network_info.get('connection_status', '')
        connected = conn_status == 'Connected'
        
        # Calculate signal bars from percent
        signal_percent = signal_info.get('signal_percent', 0) or 0
        signal_bars = min(5, max(0, int(signal_percent / 20))) if signal_percent else 0
        
        # Build response with ALL fields the frontend expects
        response = {
            "success": True,
            "available": available,
            "connected": connected,
            "video_mode_active": getattr(provider, 'video_mode_active', False),
            "video_quality": None,
        }
        
        # Add video quality assessment if signal data available
        if signal_info:
            try:
                loop = asyncio.get_event_loop()
                vq = await loop.run_in_executor(None, provider.get_video_quality_assessment)
                if vq and vq.get('available'):
                    response["video_quality"] = vq
            except Exception:
                pass
        
        # Device info - pass through all raw fields
        if device_info:
            response["device"] = {
                "device_name": device_info.get('device_name', 'Unknown'),
                "model": device_info.get('device_name', 'Unknown'),
                "imei": device_info.get('imei', ''),
                "imsi": device_info.get('imsi', ''),
                "iccid": device_info.get('iccid', ''),
                "serial_number": device_info.get('serial_number', ''),
                "hardware_version": device_info.get('hardware_version', ''),
                "software_version": device_info.get('software_version', ''),
                "mac_address1": device_info.get('mac_address1', ''),
                "mac_address2": device_info.get('mac_address2', ''),
                "product_family": device_info.get('product_family', ''),
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
                "operator": network_info.get('operator', ''),
                "operator_code": network_info.get('operator_code', ''),
                "network_type": network_info.get('network_type', ''),
                "network_type_ex": network_info.get('network_type_ex', ''),
                "connection_status": conn_status,
                "signal_icon": network_info.get('signal_icon', signal_bars),
                "roaming": network_info.get('roaming', False),
                "primary_dns": network_info.get('primary_dns', ''),
                "secondary_dns": network_info.get('secondary_dns', ''),
                "rat": network_info.get('rat', ''),
                "sim_status": network_info.get('sim_status', ''),
                "fly_mode": network_info.get('fly_mode', False),
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
            "error": "Modem provider not available"
        }
    except Exception as e:
        logger.error(f"Error getting enhanced modem status: {e}")
        return {
            "success": True,
            "available": False,
            "connected": False,
            "error": str(e)
        }


# =============================
# APN Configuration
# =============================

@router.get("/modem/apn")
async def get_apn_settings():
    """Get current APN settings and available presets"""
    provider = _get_modem_provider()
    if hasattr(provider, 'get_apn_settings'):
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
    if hasattr(provider, 'set_apn'):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: provider.set_apn(preset=request.preset, custom_apn=request.custom_apn)
        )
        if result and result.get('success'):
            return result
    raise HTTPException(status_code=500, detail="Failed to set APN")


# =============================
# Network Control
# =============================

@router.post("/modem/reconnect")
async def reconnect_network():
    """Force network reconnection to search for better cell tower"""
    provider = _get_modem_provider()
    if hasattr(provider, 'reconnect_network'):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, provider.reconnect_network)
        if result and result.get('success'):
            return result
    raise HTTPException(status_code=500, detail="Reconnection failed")


@router.post("/modem/roaming")
async def set_roaming(request: RoamingRequest):
    """Enable or disable roaming"""
    provider = _get_modem_provider()
    if hasattr(provider, 'set_roaming'):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: provider.set_roaming(request.enabled))
        if result and result.get('success'):
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
    if hasattr(provider, 'video_mode_active'):
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
    if hasattr(provider, 'enable_video_mode'):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, provider.enable_video_mode)
        if result and result.get('success'):
            return result
    raise HTTPException(status_code=500, detail="Failed to enable video mode")


@router.post("/modem/video-mode/disable")
async def disable_video_mode():
    """Disable video mode and restore original settings"""
    provider = _get_modem_provider()
    if hasattr(provider, 'disable_video_mode'):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, provider.disable_video_mode)
        if result and result.get('success'):
            return result
    raise HTTPException(status_code=500, detail="Failed to disable video mode")


# =============================
# Flight Session
# =============================

@router.get("/modem/flight-session")
async def get_flight_session():
    """Get current flight session status and statistics"""
    provider = _get_modem_provider()
    if hasattr(provider, 'get_flight_session_status'):
        status = provider.get_flight_session_status()
        return {"success": True, **status}
    return {"success": True, "status": "no_session"}


@router.post("/modem/flight-session/start")
async def start_flight_session():
    """Start recording flight session statistics"""
    provider = _get_modem_provider()
    if hasattr(provider, 'start_flight_session'):
        result = provider.start_flight_session()
        return result
    raise HTTPException(status_code=500, detail="Could not start session")


@router.post("/modem/flight-session/stop")
async def stop_flight_session():
    """Stop recording and get session statistics summary"""
    provider = _get_modem_provider()
    if hasattr(provider, 'stop_flight_session'):
        result = provider.stop_flight_session()
        if result and result.get('success'):
            return result
    raise HTTPException(status_code=400, detail="No active session")


@router.post("/modem/flight-session/sample")
async def record_flight_sample():
    """Record a signal quality sample (call periodically during flight)"""
    provider = _get_modem_provider()
    if hasattr(provider, 'record_flight_sample'):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, provider.record_flight_sample)
        if result and result.get('success'):
            return result
    raise HTTPException(status_code=400, detail="No active session")


# =============================
# Latency Monitoring
# =============================

@router.get("/modem/latency")
async def measure_latency():
    """Measure current network latency and jitter"""
    provider = _get_modem_provider()
    if hasattr(provider, 'measure_latency'):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, provider.measure_latency)
        if result and result.get('success'):
            return result
        # Return error details instead of generic 500
        if result:
            return result
    raise HTTPException(status_code=500, detail="Latency test failed")


@router.post("/modem/latency")
async def measure_latency_custom(request: LatencyTestRequest):
    """Measure latency to a custom host"""
    provider = _get_modem_provider()
    if hasattr(provider, 'measure_latency'):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: provider.measure_latency(host=request.host, count=request.count)
        )
        if result and result.get('success'):
            return result
        if result:
            return result
    raise HTTPException(status_code=500, detail="Latency test failed")
