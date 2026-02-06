"""
WiFi Network Interface Provider
Implementation for wireless WiFi connections
"""

from typing import Dict, Optional, List
from providers.base import NetworkInterface, InterfaceStatus, InterfaceType
import subprocess
import re
import logging

logger = logging.getLogger(__name__)


class WiFiInterface(NetworkInterface):
    """WiFi network interface provider"""
    
    def __init__(self, interface_name: str = "wlan0"):
        super().__init__()
        self.interface_name = interface_name
        self.name = f"wifi_{interface_name}"
        self.display_name = f"WiFi ({interface_name})"
        self.interface_type = InterfaceType.WIFI
    
    def detect(self) -> bool:
        """Detect if WiFi interface exists"""
        try:
            result = subprocess.run(
                ['iw', 'dev', self.interface_name, 'info'],
                capture_output=True,
                text=True,
                timeout=2
            )
            return result.returncode == 0
        except:
            # Fallback: check via ip link
            try:
                result = subprocess.run(
                    ['ip', 'link', 'show', self.interface_name],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                return result.returncode == 0
            except:
                return False
    
    def get_status(self) -> Dict:
        """Get WiFi interface status"""
        if not self.detect():
            return {
                'status': InterfaceStatus.ERROR,
                'interface': self.interface_name,
                'type': self.interface_type.value,
                'error': f'Interface {self.interface_name} not found'
            }
        
        try:
            # Get interface state
            result = subprocess.run(
                ['ip', 'addr', 'show', self.interface_name],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode != 0:
                return {
                    'status': InterfaceStatus.ERROR,
                    'interface': self.interface_name,
                    'type': self.interface_type.value,
                    'error': 'Failed to get interface status'
                }
            
            output = result.stdout
            
            # Determine status
            if 'state UP' in output:
                status = InterfaceStatus.UP
            elif 'state DOWN' in output:
                status = InterfaceStatus.DOWN
            else:
                status = InterfaceStatus.ERROR
            
            # Extract IP address
            ip_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', output)
            ip_address = ip_match.group(1) if ip_match else None
            
            # Extract MAC address
            mac_match = re.search(r'link/ether ([0-9a-f:]+)', output)
            mac_address = mac_match.group(1) if mac_match else None
            
            # Get WiFi specific info
            ssid = self._get_ssid()
            signal_strength = self._get_signal_strength()
            
            # Get gateway
            gateway = self._get_gateway()
            
            # Get metric
            metric = self._get_metric()
            
            return {
                'status': status,
                'interface': self.interface_name,
                'type': self.interface_type.value,
                'ip_address': ip_address,
                'mac_address': mac_address,
                'gateway': gateway,
                'metric': metric,
                'ssid': ssid,
                'signal_strength': signal_strength
            }
        except Exception as e:
            logger.error(f"Error getting WiFi status: {e}")
            return {
                'status': InterfaceStatus.ERROR,
                'interface': self.interface_name,
                'type': self.interface_type.value,
                'error': str(e)
            }
    
    def bring_up(self) -> Dict:
        """Bring WiFi interface up"""
        try:
            result = subprocess.run(
                ['sudo', 'ip', 'link', 'set', self.interface_name, 'up'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                return {
                    'success': True,
                    'message': f'Interface {self.interface_name} brought up'
                }
            return {
                'success': False,
                'error': result.stderr or 'Failed to bring interface up'
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def bring_down(self) -> Dict:
        """Bring WiFi interface down"""
        try:
            result = subprocess.run(
                ['sudo', 'ip', 'link', 'set', self.interface_name, 'down'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                return {
                    'success': True,
                    'message': f'Interface {self.interface_name} brought down'
                }
            return {
                'success': False,
                'error': result.stderr or 'Failed to bring interface down'
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_ip_address(self) -> Optional[str]:
        """Get IP address of interface"""
        status = self.get_status()
        return status.get('ip_address')
    
    def set_metric(self, metric: int) -> Dict:
        """Set route metric for interface"""
        try:
            gateway = self._get_gateway()
            if not gateway:
                return {
                    'success': False,
                    'error': 'No gateway found for interface'
                }
            
            # Delete old route
            subprocess.run(
                ['sudo', 'ip', 'route', 'del', 'default', 'via', gateway, 'dev', self.interface_name],
                capture_output=True,
                timeout=2
            )
            
            # Add route with new metric
            result = subprocess.run(
                ['sudo', 'ip', 'route', 'add', 'default', 'via', gateway, 'dev', self.interface_name, 'metric', str(metric)],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                return {
                    'success': True,
                    'message': f'Metric set to {metric} for {self.interface_name}',
                    'metric': metric
                }
            return {
                'success': False,
                'error': result.stderr or 'Failed to set metric'
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def scan_networks(self) -> List[Dict]:
        """Scan for available WiFi networks"""
        try:
            result = subprocess.run(
                ['sudo', 'iw', 'dev', self.interface_name, 'scan'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return []
            
            networks = []
            current_network = {}
            
            for line in result.stdout.split('\n'):
                line = line.strip()
                
                if line.startswith('BSS '):
                    if current_network:
                        networks.append(current_network)
                    current_network = {}
                
                elif line.startswith('SSID:'):
                    ssid = line.split(':', 1)[1].strip()
                    if ssid:
                        current_network['ssid'] = ssid
                
                elif line.startswith('signal:'):
                    signal = line.split(':')[1].strip()
                    # Extract dBm value
                    match = re.search(r'(-?\d+\.\d+) dBm', signal)
                    if match:
                        dbm = float(match.group(1))
                        # Convert dBm to percentage (approximate)
                        if dbm >= -50:
                            percent = 100
                        elif dbm <= -100:
                            percent = 0
                        else:
                            percent = 2 * (dbm + 100)
                        current_network['signal_strength'] = int(percent)
                        current_network['signal_dbm'] = dbm
            
            if current_network:
                networks.append(current_network)
            
            return networks
        except Exception as e:
            logger.error(f"Error scanning networks: {e}")
            return []
    
    def _get_ssid(self) -> Optional[str]:
        """Get currently connected SSID"""
        try:
            result = subprocess.run(
                ['iw', 'dev', self.interface_name, 'link'],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'SSID:' in line:
                        return line.split('SSID:')[1].strip()
            return None
        except:
            return None
    
    def _get_signal_strength(self) -> Optional[int]:
        """Get current signal strength in percentage"""
        try:
            result = subprocess.run(
                ['iw', 'dev', self.interface_name, 'link'],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'signal:' in line:
                        match = re.search(r'(-?\d+) dBm', line)
                        if match:
                            dbm = int(match.group(1))
                            # Convert dBm to percentage
                            if dbm >= -50:
                                return 100
                            elif dbm <= -100:
                                return 0
                            else:
                                return 2 * (dbm + 100)
            return None
        except:
            return None
    
    def _get_gateway(self) -> Optional[str]:
        """Get gateway for interface"""
        try:
            result = subprocess.run(
                ['ip', 'route', 'show', 'dev', self.interface_name],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'default via' in line:
                        match = re.search(r'default via (\d+\.\d+\.\d+\.\d+)', line)
                        if match:
                            return match.group(1)
            return None
        except:
            return None
    
    def _get_metric(self) -> Optional[int]:
        """Get current route metric"""
        try:
            result = subprocess.run(
                ['ip', 'route', 'show', 'dev', self.interface_name],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'default' in line and 'metric' in line:
                        match = re.search(r'metric (\d+)', line)
                        if match:
                            return int(match.group(1))
            return None
        except:
            return None
    
    def get_info(self) -> Dict:
        """Get interface information"""
        return {
            'name': self.name,
            'display_name': self.display_name,
            'interface_name': self.interface_name,
            'type': self.interface_type.value,
            'description': f'Wireless WiFi interface {self.interface_name}',
            'features': [
                'Wireless connection',
                'Network scanning',
                'Signal strength monitoring',
                'SSID detection'
            ]
        }
