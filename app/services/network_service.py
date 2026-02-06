"""
Network Service for FPVCopilotSky
Manages WiFi, USB 4G modems, and network metrics
"""

import subprocess
import re
import asyncio
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class NetworkInterface:
    """Represents a network interface"""
    name: str
    type: str  # 'wifi', 'modem', 'ethernet', 'unknown'
    connection: Optional[str] = None
    state: str = 'disconnected'
    ip_address: Optional[str] = None
    gateway: Optional[str] = None
    metric: Optional[int] = None
    mac_address: Optional[str] = None
    speed: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'type': self.type,
            'connection': self.connection,
            'state': self.state,
            'ip_address': self.ip_address,
            'gateway': self.gateway,
            'metric': self.metric,
            'mac_address': self.mac_address,
            'speed': self.speed
        }


@dataclass
class WiFiNetwork:
    """Represents a WiFi network"""
    ssid: str
    signal: int
    security: str
    connected: bool = False
    
    def to_dict(self) -> Dict:
        return {
            'ssid': self.ssid,
            'signal': self.signal,
            'security': self.security,
            'connected': self.connected
        }


class NetworkService:
    """Service for managing network connections"""
    
    # Metric constants
    METRIC_PRIMARY = 50      # Primary connection (lowest = preferred)
    METRIC_SECONDARY = 100   # Secondary connection
    METRIC_TERTIARY = 600    # Tertiary/backup connection
    
    def __init__(self):
        self._wifi_interface: Optional[str] = None
        self._modem_interface: Optional[str] = None
        self._interfaces_detected = False
        self._loop = None
        
    async def _run_command(self, cmd: List[str], timeout: int = 10) -> subprocess.CompletedProcess:
        """Run a command asynchronously"""
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return subprocess.CompletedProcess(
                cmd, proc.returncode, 
                stdout.decode() if stdout else '', 
                stderr.decode() if stderr else ''
            )
        except asyncio.TimeoutError:
            logger.error(f"Command timed out: {' '.join(cmd)}")
            return subprocess.CompletedProcess(cmd, 1, '', 'Command timed out')
        except Exception as e:
            logger.error(f"Command failed: {e}")
            return subprocess.CompletedProcess(cmd, 1, '', str(e))
    
    def _run_command_sync(self, cmd: List[str], timeout: int = 10) -> subprocess.CompletedProcess:
        """Run a command synchronously"""
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(cmd, 1, '', 'Command timed out')
        except Exception as e:
            return subprocess.CompletedProcess(cmd, 1, '', str(e))
    
    async def detect_interfaces(self, force: bool = False) -> None:
        """Detect WiFi and modem interfaces (cached unless force=True)"""
        if self._interfaces_detected and not force:
            return
        
        # Detect WiFi interface
        result = await self._run_command(['nmcli', '-t', '-f', 'DEVICE,TYPE,STATE', 'device'])
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if ':wifi:' in line:
                    parts = line.split(':')
                    if len(parts) >= 1:
                        if self._wifi_interface != parts[0]:
                            self._wifi_interface = parts[0]
                            logger.info(f"WiFi interface: {self._wifi_interface}")
                        break
        
        # Detect USB 4G modem - look for any interface with 192.168.8.x IP
        # This is the default subnet for USB modems in HiLink mode
        result = await self._run_command(['ip', '-o', 'addr', 'show'])
        if result.returncode == 0:
            # Use -o flag for one-line output per interface, easier to parse
            for line in result.stdout.strip().split('\n'):
                # Look for 192.168.8.x IP on any interface
                if '192.168.8.' in line:
                    # Extract interface name (format: "N: interface inet IP/mask ...")
                    match = re.search(r'^\d+:\s+(\S+)\s+inet\s+192\.168\.8\.', line)
                    if match:
                        iface = match.group(1)
                        if self._modem_interface != iface:
                            self._modem_interface = iface
                            logger.info(f"USB 4G modem detected: {self._modem_interface}")
                        break
        
        self._interfaces_detected = True
    
    async def get_interfaces(self) -> List[Dict]:
        """Get all network interfaces with their status"""
        await self.detect_interfaces()
        interfaces = []
        
        # Get interfaces from nmcli
        result = await self._run_command(['nmcli', '-t', '-f', 'DEVICE,TYPE,STATE,CONNECTION', 'device'])
        if result.returncode != 0:
            return interfaces
        
        for line in result.stdout.strip().split('\n'):
            if not line or line.startswith('lo'):
                continue
            
            parts = line.split(':')
            if len(parts) < 3:
                continue
            
            device = parts[0]
            dev_type = parts[1]
            state = parts[2]
            connection = parts[3] if len(parts) > 3 else None
            
            # Skip loopback and docker interfaces
            if device in ['lo', 'docker0'] or device.startswith('veth') or device.startswith('br-'):
                continue
            
            # Determine interface type
            if dev_type == 'wifi':
                iface_type = 'wifi'
            elif device == self._modem_interface or (device.startswith('enx') and '192.168.8' in str(self._get_ip_sync(device))):
                iface_type = 'modem'
            elif dev_type == 'ethernet':
                iface_type = 'ethernet'
            else:
                iface_type = 'unknown'
            
            # Get additional info
            ip_info = await self._get_interface_details(device)
            
            # Determine connected state: nmcli says 'connected', or interface has an IP
            # (covers unmanaged interfaces like tailscale, tun, etc.)
            has_ip = ip_info.get('ip') is not None
            is_connected = (state == 'connected') or has_ip
            
            interface = NetworkInterface(
                name=device,
                type=iface_type,
                connection=connection if connection else None,
                state='connected' if is_connected else 'disconnected',
                ip_address=ip_info.get('ip'),
                gateway=ip_info.get('gateway'),
                metric=ip_info.get('metric'),
                mac_address=ip_info.get('mac'),
                speed=ip_info.get('speed')
            )
            interfaces.append(interface.to_dict())
        
        return interfaces
    
    def _get_ip_sync(self, device: str) -> Optional[str]:
        """Get IP address synchronously"""
        result = self._run_command_sync(['ip', 'addr', 'show', device])
        if result.returncode == 0:
            match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)', result.stdout)
            if match:
                return match.group(1)
        return None
    
    async def _get_interface_details(self, device: str) -> Dict:
        """Get detailed info for an interface"""
        info = {}
        
        # Get IP address
        result = await self._run_command(['ip', 'addr', 'show', device])
        if result.returncode == 0:
            ip_match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)', result.stdout)
            if ip_match:
                info['ip'] = ip_match.group(1)
            
            mac_match = re.search(r'link/ether\s+([a-f0-9:]+)', result.stdout)
            if mac_match:
                info['mac'] = mac_match.group(1)
        
        # Get default route and metric
        result = await self._run_command(['ip', 'route', 'show', 'default'])
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if device in line:
                    gateway_match = re.search(r'via\s+(\d+\.\d+\.\d+\.\d+)', line)
                    if gateway_match:
                        info['gateway'] = gateway_match.group(1)
                    
                    metric_match = re.search(r'metric\s+(\d+)', line)
                    if metric_match:
                        info['metric'] = int(metric_match.group(1))
                    break
        
        # Get speed
        try:
            with open(f'/sys/class/net/{device}/speed', 'r') as f:
                speed = int(f.read().strip())
                if speed > 0:
                    info['speed'] = f'{speed} Mbps'
        except:
            try:
                with open(f'/sys/class/net/{device}/carrier', 'r') as f:
                    carrier = int(f.read().strip())
                    info['speed'] = 'Linked' if carrier == 1 else 'No link'
            except:
                pass
        
        return info
    
    async def get_wifi_networks(self) -> List[Dict]:
        """Scan and return available WiFi networks"""
        networks = []
        
        if not self._wifi_interface:
            await self.detect_interfaces()
        
        if not self._wifi_interface:
            return networks
        
        # Check if interface is managed by NetworkManager
        is_managed = await self._is_nm_managed(self._wifi_interface)
        
        if is_managed:
            networks = await self._scan_wifi_nmcli()
        
        # Fallback to wpa_cli if nmcli returned nothing (unmanaged or failed)
        if not networks:
            networks = await self._scan_wifi_wpa_cli()
        
        # Sort by signal strength
        networks.sort(key=lambda x: x['signal'], reverse=True)
        return networks
    
    async def _is_nm_managed(self, device: str) -> bool:
        """Check if a device is managed by NetworkManager"""
        result = await self._run_command(
            ['nmcli', '-t', '-f', 'DEVICE,STATE', 'device'], timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                parts = line.split(':')
                if len(parts) >= 2 and parts[0] == device:
                    return parts[1] not in ('unmanaged', 'unavailable')
        return False
    
    async def _scan_wifi_nmcli(self) -> List[Dict]:
        """Scan WiFi networks using nmcli (for NM-managed interfaces)"""
        networks = []
        
        # Request a rescan
        rescan = await self._run_command(
            ['nmcli', 'device', 'wifi', 'rescan', 'ifname', self._wifi_interface], timeout=15
        )
        if rescan.returncode != 0:
            logger.warning(f"nmcli rescan failed: {rescan.stderr.strip()}")
        
        # Get networks list
        result = await self._run_command(
            ['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY,IN-USE', 'device', 'wifi', 'list',
             'ifname', self._wifi_interface],
            timeout=10
        )
        
        if result.returncode != 0 or not result.stdout.strip():
            return networks
        
        seen_ssids = set()
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            
            parts = line.split(':')
            if len(parts) < 3:
                continue
            
            ssid = parts[0].strip()
            if not ssid or ssid in seen_ssids:
                continue
            
            seen_ssids.add(ssid)
            
            try:
                signal = int(parts[1]) if parts[1] else 0
            except:
                signal = 0
            
            security = parts[2] if len(parts) > 2 else ''
            in_use = '*' in (parts[3] if len(parts) > 3 else '')
            
            networks.append(WiFiNetwork(
                ssid=ssid, signal=signal, security=security, connected=in_use
            ).to_dict())
        
        return networks
    
    async def _scan_wifi_wpa_cli(self) -> List[Dict]:
        """Scan WiFi networks using wpa_cli (for wpa_supplicant-managed interfaces)"""
        networks = []
        
        # Get currently connected SSID
        current_ssid = None
        status_result = await self._run_command(
            ['wpa_cli', '-i', self._wifi_interface, 'status'], timeout=5
        )
        if status_result.returncode == 0:
            for line in status_result.stdout.strip().split('\n'):
                if line.startswith('ssid='):
                    current_ssid = line.split('=', 1)[1]
                    break
        
        # Trigger scan
        scan_result = await self._run_command(
            ['wpa_cli', '-i', self._wifi_interface, 'scan'], timeout=10
        )
        if scan_result.returncode != 0:
            logger.warning(f"wpa_cli scan failed: {scan_result.stderr.strip()}")
        
        # Wait for scan to complete
        await asyncio.sleep(2)
        
        # Get results
        result = await self._run_command(
            ['wpa_cli', '-i', self._wifi_interface, 'scan_results'], timeout=10
        )
        
        if result.returncode != 0:
            logger.error(f"wpa_cli scan_results failed: {result.stderr}")
            return networks
        
        seen_ssids = set()
        for line in result.stdout.strip().split('\n'):
            # Skip header line
            if line.startswith('bssid') or not line.strip():
                continue
            
            # Format: bssid / frequency / signal level / flags / ssid
            parts = line.split('\t')
            if len(parts) < 5:
                continue
            
            ssid = parts[4].strip()
            if not ssid or ssid in seen_ssids:
                continue
            
            seen_ssids.add(ssid)
            
            # Convert dBm signal to percentage (roughly: -30 dBm = 100%, -90 dBm = 0%)
            try:
                dbm = int(parts[2])
                signal = max(0, min(100, 2 * (dbm + 100)))
            except:
                signal = 0
            
            # Parse security flags like [WPA2-PSK-CCMP][WPS][ESS]
            flags = parts[3] if len(parts) > 3 else ''
            if 'WPA3' in flags:
                security = 'WPA3'
            elif 'WPA2' in flags:
                security = 'WPA2'
            elif 'WPA' in flags:
                security = 'WPA'
            elif 'WEP' in flags:
                security = 'WEP'
            else:
                security = ''
            
            is_connected = (ssid == current_ssid) if current_ssid else False
            
            networks.append(WiFiNetwork(
                ssid=ssid, signal=signal, security=security, connected=is_connected
            ).to_dict())
        
        if networks:
            logger.info(f"wpa_cli found {len(networks)} WiFi networks")
        else:
            logger.warning("wpa_cli scan returned no networks")
        
        return networks
    
    async def connect_wifi(self, ssid: str, password: Optional[str] = None) -> Dict:
        """Connect to a WiFi network"""
        try:
            if password:
                result = await self._run_command(
                    ['nmcli', 'device', 'wifi', 'connect', ssid, 'password', password],
                    timeout=30
                )
            else:
                result = await self._run_command(
                    ['nmcli', 'device', 'wifi', 'connect', ssid],
                    timeout=30
                )
            
            if result.returncode == 0:
                logger.info(f"Connected to WiFi: {ssid}")
                return {'success': True, 'message': f'Connected to {ssid}'}
            else:
                logger.error(f"Failed to connect to WiFi: {result.stderr}")
                return {'success': False, 'error': result.stderr.strip()}
        
        except Exception as e:
            logger.error(f"Error connecting to WiFi: {e}")
            return {'success': False, 'error': str(e)}
    
    async def disconnect_wifi(self) -> Dict:
        """Disconnect from current WiFi network"""
        try:
            if not self._wifi_interface:
                await self.detect_interfaces()
            
            if not self._wifi_interface:
                return {'success': False, 'error': 'No WiFi interface found'}
            
            result = await self._run_command(
                ['nmcli', 'device', 'disconnect', self._wifi_interface],
                timeout=10
            )
            
            if result.returncode == 0:
                logger.info("Disconnected from WiFi")
                return {'success': True, 'message': 'Disconnected from WiFi'}
            else:
                return {'success': False, 'error': result.stderr.strip()}
        
        except Exception as e:
            logger.error(f"Error disconnecting WiFi: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_saved_connections(self) -> List[Dict]:
        """Get list of saved network connections"""
        connections = []
        
        result = await self._run_command(
            ['nmcli', '-t', '-f', 'NAME,TYPE,DEVICE', 'connection', 'show']
        )
        
        if result.returncode != 0:
            return connections
        
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            
            parts = line.split(':')
            if len(parts) >= 2:
                connections.append({
                    'name': parts[0],
                    'type': parts[1],
                    'device': parts[2] if len(parts) > 2 else None,
                    'active': bool(parts[2]) if len(parts) > 2 else False
                })
        
        return connections
    
    async def forget_connection(self, name: str) -> Dict:
        """Delete a saved connection"""
        try:
            result = await self._run_command(
                ['nmcli', 'connection', 'delete', name],
                timeout=10
            )
            
            if result.returncode == 0:
                logger.info(f"Deleted connection: {name}")
                return {'success': True, 'message': f'Deleted {name}'}
            else:
                return {'success': False, 'error': result.stderr.strip()}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def set_connection_priority(self, mode: str) -> Dict:
        """
        Set network connection priority mode
        
        Args:
            mode: 'wifi' (WiFi primary, modem backup) or 'modem' (modem primary, WiFi backup)
        """
        try:
            await self.detect_interfaces()
            
            if mode == 'wifi':
                wifi_metric = self.METRIC_PRIMARY      # 50
                modem_metric = self.METRIC_TERTIARY    # 600
            elif mode == 'modem':
                modem_metric = self.METRIC_PRIMARY     # 50
                wifi_metric = self.METRIC_TERTIARY     # 600
            else:
                return {'success': False, 'error': f'Invalid mode: {mode}'}
            
            results = []
            
            # Set WiFi metric
            if self._wifi_interface:
                result = await self._set_interface_metric(self._wifi_interface, wifi_metric)
                results.append(('wifi', result))
            
            # Set modem metric
            if self._modem_interface:
                result = await self._set_modem_metric(modem_metric)
                results.append(('modem', result))
            
            # Check results
            all_success = all(r[1].get('success', False) for r in results)
            
            if all_success:
                logger.info(f"Network priority set to: {mode}")
                return {
                    'success': True,
                    'message': f'Priority mode set to {mode}',
                    'mode': mode,
                    'wifi_metric': wifi_metric if self._wifi_interface else None,
                    'modem_metric': modem_metric if self._modem_interface else None
                }
            else:
                errors = [f"{r[0]}: {r[1].get('error', 'unknown')}" for r in results if not r[1].get('success')]
                return {'success': False, 'error': '; '.join(errors)}
        
        except Exception as e:
            logger.error(f"Error setting priority: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _set_interface_metric(self, interface: str, metric: int) -> Dict:
        """Set metric for an interface by modifying its default route"""
        try:
            # Get current default route info
            result = await self._run_command(['ip', 'route', 'show', 'default'])
            if result.returncode != 0:
                return {'success': False, 'error': 'Failed to get routes'}
            
            gateway = None
            for line in result.stdout.strip().split('\n'):
                if interface in line:
                    match = re.search(r'via\s+(\d+\.\d+\.\d+\.\d+)', line)
                    if match:
                        gateway = match.group(1)
                    break
            
            if not gateway:
                return {'success': False, 'error': f'No gateway found for {interface}'}
            
            # Delete existing default route for this interface
            await self._run_command(
                ['sudo', 'ip', 'route', 'del', 'default', 'via', gateway, 'dev', interface]
            )
            
            # Add new route with metric
            result = await self._run_command(
                ['sudo', 'ip', 'route', 'add', 'default', 'via', gateway, 
                 'dev', interface, 'metric', str(metric)]
            )
            
            if result.returncode != 0:
                return {'success': False, 'error': result.stderr.strip()}
            
            # Also persist in NetworkManager
            conn_result = await self._run_command(
                ['nmcli', '-t', '-f', 'NAME,DEVICE', 'connection', 'show', '--active']
            )
            
            for line in conn_result.stdout.strip().split('\n'):
                if ':' in line:
                    name, device = line.split(':', 1)
                    if device == interface:
                        await self._run_command(
                            ['nmcli', 'connection', 'modify', name, 'ipv4.route-metric', str(metric)]
                        )
                        break
            
            return {'success': True, 'message': f'Metric set to {metric}'}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _set_modem_metric(self, metric: int) -> Dict:
        """Set metric for the USB 4G modem"""
        try:
            if not self._modem_interface:
                return {'success': False, 'error': 'No modem interface found'}
            
            # Get modem IP
            result = await self._run_command(['ip', 'addr', 'show', self._modem_interface])
            if result.returncode != 0:
                return {'success': False, 'error': 'Failed to get modem IP'}
            
            ip_match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)', result.stdout)
            if not ip_match:
                return {'success': False, 'error': 'Modem has no IP address'}
            
            modem_ip = ip_match.group(1)
            
            # Derive gateway (typically .1 in same subnet for USB modems)
            ip_parts = modem_ip.split('.')
            ip_parts[-1] = '1'
            modem_gateway = '.'.join(ip_parts)
            
            # Remove existing default routes for modem
            routes_result = await self._run_command(['ip', 'route', 'show', 'default'])
            for line in routes_result.stdout.strip().split('\n'):
                if self._modem_interface in line and line.strip():
                    parts = line.split()
                    if len(parts) >= 3 and parts[0] == 'default' and parts[1] == 'via':
                        existing_gw = parts[2]
                        await self._run_command(
                            ['sudo', 'ip', 'route', 'del', 'default', 'via', existing_gw, 
                             'dev', self._modem_interface]
                        )
            
            # Add new route with metric
            result = await self._run_command(
                ['sudo', 'ip', 'route', 'add', 'default', 'via', modem_gateway,
                 'dev', self._modem_interface, 'metric', str(metric)]
            )
            
            if result.returncode != 0 and 'File exists' not in result.stderr:
                return {'success': False, 'error': result.stderr.strip()}
            
            logger.info(f"Modem {self._modem_interface} metric set to {metric}")
            return {'success': True, 'message': f'Modem metric set to {metric}'}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def get_modem_info(self) -> Dict:
        """Get modem status and info"""
        info = {
            'detected': False,
            'connected': False,
            'interface': None,
            'ip_address': None,
            'gateway': None,
            'signal_strength': None,
            'operator': None,
            'technology': None
        }
        
        try:
            await self.detect_interfaces()
            
            if not self._modem_interface:
                return info
            
            info['detected'] = True
            info['interface'] = self._modem_interface
            
            # Check if interface is up
            result = await self._run_command(['ip', 'addr', 'show', self._modem_interface])
            if result.returncode == 0:
                if 'state UP' in result.stdout:
                    info['connected'] = True
                
                ip_match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)', result.stdout)
                if ip_match:
                    info['ip_address'] = ip_match.group(1)
                    # Derive gateway
                    ip_parts = ip_match.group(1).split('.')
                    ip_parts[-1] = '1'
                    info['gateway'] = '.'.join(ip_parts)
            
            # Try ModemManager for signal info (if available)
            try:
                result = await self._run_command(['mmcli', '-L'], timeout=5)
                if result.returncode == 0:
                    modem_match = re.search(r'/Modem/(\d+)', result.stdout)
                    if modem_match:
                        modem_num = modem_match.group(1)
                        
                        result = await self._run_command(['mmcli', '-m', modem_num], timeout=5)
                        if result.returncode == 0:
                            signal_match = re.search(r'signal quality:\s+(\d+)%', result.stdout)
                            if signal_match:
                                info['signal_strength'] = int(signal_match.group(1))
                            
                            operator_match = re.search(r'operator name:\s+(.+)', result.stdout)
                            if operator_match:
                                info['operator'] = operator_match.group(1).strip()
                            
                            tech_match = re.search(r'access tech:\s+(.+)', result.stdout)
                            if tech_match:
                                info['technology'] = tech_match.group(1).strip()
            except:
                pass
        
        except Exception as e:
            logger.error(f"Error getting modem info: {e}")
        
        return info
    
    async def get_routes(self) -> List[Dict]:
        """Get current routing table"""
        routes = []
        
        result = await self._run_command(['ip', 'route', 'show', 'default'])
        if result.returncode != 0:
            return routes
        
        for line in result.stdout.strip().split('\n'):
            if not line.startswith('default'):
                continue
            
            route = {'destination': 'default'}
            parts = line.split()
            
            i = 1
            while i < len(parts):
                if parts[i] == 'via' and i + 1 < len(parts):
                    route['gateway'] = parts[i + 1]
                    i += 2
                elif parts[i] == 'dev' and i + 1 < len(parts):
                    route['interface'] = parts[i + 1]
                    i += 2
                elif parts[i] == 'metric' and i + 1 < len(parts):
                    route['metric'] = int(parts[i + 1])
                    i += 2
                else:
                    i += 1
            
            if 'interface' in route:
                routes.append(route)
        
        # Sort by metric (lower = higher priority)
        routes.sort(key=lambda x: x.get('metric', 999))
        return routes
    
    async def get_status(self) -> Dict:
        """Get overall network status"""
        # Force re-detection to catch hot-plugged devices
        await self.detect_interfaces(force=True)
        
        interfaces = await self.get_interfaces()
        routes = await self.get_routes()
        modem = await self.get_modem_info()
        
        # Determine primary connection
        primary = None
        if routes:
            primary = routes[0].get('interface')
        
        # Determine current mode
        if primary == self._modem_interface:
            mode = 'modem'
        elif primary == self._wifi_interface:
            mode = 'wifi'
        else:
            mode = 'unknown'
        
        return {
            'wifi_interface': self._wifi_interface,
            'modem_interface': self._modem_interface,
            'primary_interface': primary,
            'mode': mode,
            'interfaces': interfaces,
            'routes': routes,
            'modem': modem
        }


# Singleton instance
_network_service: Optional[NetworkService] = None


def get_network_service() -> NetworkService:
    """Get or create the NetworkService singleton"""
    global _network_service
    if _network_service is None:
        _network_service = NetworkService()
    return _network_service
