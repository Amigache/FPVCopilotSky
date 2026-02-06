"""
VPN Service for FPV Copilot Sky
Manages VPN connections with support for multiple providers:
- Tailscale
- ZeroTier (future)
- WireGuard (future)
"""

import subprocess
import logging
import re
from typing import Dict, Optional, List
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class VPNProvider(ABC):
    """Abstract base class for VPN providers"""
    
    @abstractmethod
    def is_installed(self) -> bool:
        """Check if VPN provider is installed"""
        pass
    
    @abstractmethod
    def get_status(self) -> Dict:
        """Get connection status"""
        pass
    
    @abstractmethod
    def connect(self) -> Dict:
        """Connect to VPN"""
        pass
    
    @abstractmethod
    def disconnect(self) -> Dict:
        """Disconnect from VPN"""
        pass
    
    @abstractmethod
    def get_info(self) -> Dict:
        """Get provider information and capabilities"""
        pass
    
    @abstractmethod
    def get_peers(self) -> List[Dict]:
        """Get list of peers/nodes in the VPN network"""
        pass


class TailscaleProvider(VPNProvider):
    """Tailscale VPN provider implementation"""
    
    def __init__(self):
        self.name = "tailscale"
        self.display_name = "Tailscale"
        
    def is_installed(self) -> bool:
        """Check if Tailscale is installed"""
        try:
            result = subprocess.run(
                ['which', 'tailscale'],
                capture_output=True, text=True, timeout=2
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Error checking Tailscale installation: {e}")
            return False
    
    def get_status(self) -> Dict:
        """Get Tailscale connection status"""
        if not self.is_installed():
            return {
                'success': False,
                'installed': False,
                'error': 'Tailscale not installed'
            }
        
        try:
            # Get main status
            result = subprocess.run(
                ['tailscale', 'status', '--json'],
                capture_output=True, text=True, timeout=5
            )
            
            # Check if logged out
            if 'Logged out' in result.stderr or result.returncode != 0:
                stderr = result.stderr
                if 'Logged out' in stderr:
                    return {
                        'success': True,
                        'installed': True,
                        'connected': False,
                        'authenticated': False,
                        'message': 'Not authenticated'
                    }
                else:
                    return {
                        'success': True,
                        'installed': True,
                        'connected': False,
                        'authenticated': False,
                        'message': 'Tailscale daemon not running'
                    }
            
            # Parse JSON output if available
            import json
            try:
                status_data = json.loads(result.stdout)
                
                # Extract relevant information
                backend_state = status_data.get('BackendState', 'Unknown')
                self_node = status_data.get('Self', {})
                peers = status_data.get('Peer', {}) or {}  # Handle null Peer after logout
                auth_url = status_data.get('AuthURL', '')
                
                # Check if node is really online and active
                node_online = self_node.get('Online', False)
                node_active = self_node.get('Active', False)
                
                # Authenticated means has valid credentials and is not in login-required state
                # User is authenticated in these states: Stopped, Starting, Running
                # User is NOT authenticated in: NoState, NeedsLogin
                authenticated = backend_state not in ['NeedsLogin', 'NoState', 'Unknown', '']
                
                # Connected only if backend running AND node is online/active AND authenticated
                connected = (backend_state == 'Running' and 
                           (node_online or node_active) and 
                           authenticated)
                
                # Get Tailscale IP
                tailscale_ips = self_node.get('TailscaleIPs', [])
                ip_address = tailscale_ips[0] if tailscale_ips else None
                
                # Get hostname
                hostname = self_node.get('HostName', 'Unknown')
                
                # Get online peers count
                online_peers = sum(1 for peer in peers.values() if peer.get('Online', False))
                
                response = {
                    'success': True,
                    'installed': True,
                    'connected': connected,
                    'authenticated': authenticated,
                    'ip_address': ip_address,
                    'hostname': hostname,
                    'interface': self._get_interface(),
                    'peers_count': len(peers),
                    'online_peers': online_peers,
                    'backend_state': backend_state
                }
                
                # If there's an auth URL, include it for UI purposes but don't override authenticated
                # (auth_url can temporarily appear during reconnection)
                if auth_url:
                    response['needs_auth'] = True
                    response['auth_url'] = auth_url
                    response['message'] = 'Device needs re-authentication'
                    # Override authenticated only if we're actually in NeedsLogin state
                    if backend_state in ['NeedsLogin', 'NoState']:
                        response['authenticated'] = False
                
                return response
                
            except json.JSONDecodeError:
                # Fallback to text parsing
                return self._parse_text_status()
                
        except Exception as e:
            logger.error(f"Error getting Tailscale status: {e}")
            return {
                'success': False,
                'installed': True,
                'error': str(e)
            }
    
    def _parse_text_status(self) -> Dict:
        """Fallback text parsing for older Tailscale versions"""
        try:
            result = subprocess.run(
                ['tailscale', 'status'],
                capture_output=True, text=True, timeout=5
            )
            
            connected = len(result.stdout.strip()) > 0 and 'Logged out' not in result.stdout
            
            # Get IP
            ip_result = subprocess.run(
                ['tailscale', 'ip', '-4'],
                capture_output=True, text=True, timeout=2
            )
            ip_address = ip_result.stdout.strip() if ip_result.returncode == 0 else None
            
            return {
                'success': True,
                'installed': True,
                'connected': connected,
                'authenticated': connected,
                'ip_address': ip_address,
                'interface': self._get_interface(),
                'status_output': result.stdout if connected else None
            }
        except Exception as e:
            logger.error(f"Error in text status parsing: {e}")
            return {
                'success': False,
                'installed': True,
                'error': str(e)
            }
    
    def _get_interface(self) -> Optional[str]:
        """Get Tailscale interface name"""
        try:
            result = subprocess.run(
                ['ip', 'link', 'show'],
                capture_output=True, text=True, timeout=2
            )
            for line in result.stdout.split('\n'):
                if 'tailscale' in line:
                    match = re.search(r'\d+:\s+(tailscale\d+):', line)
                    if match:
                        return match.group(1)
        except Exception as e:
            logger.error(f"Error getting Tailscale interface: {e}")
        return None
    
    def connect(self) -> Dict:
        """Connect to Tailscale"""
        try:
            # Check if already connected
            status = self.get_status()
            if status.get('connected') and status.get('authenticated'):
                return {
                    'success': True,
                    'message': 'Already connected',
                    'already_connected': True
                }
            
            # First, check if we need a login URL by checking current state
            # If backend_state is NeedsLogin, we need to get an auth URL
            backend_state = status.get('backend_state', '')
            
            if backend_state == 'NeedsLogin' or not status.get('authenticated'):
                # Use 'timeout' OUTSIDE sudo to prevent tailscale up from blocking forever
                # timeout wraps sudo so it can kill it without needing sudoers entry for timeout
                cmd = ['timeout', '5', 'sudo', '-n', 'tailscale', 'up']
                
                logger.info(f"Executing: {' '.join(cmd)}")
                
                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=10  # Python-level safety timeout
                    )
                    combined_output = result.stdout + result.stderr
                    logger.info(f"Tailscale up result: returncode={result.returncode}, output={combined_output[:200]}")
                except subprocess.TimeoutExpired:
                    # If Python timeout fires, try to get partial output
                    combined_output = ''
                    logger.warning("Tailscale up timed out at Python level")
                
                # Extract auth URL from output
                auth_url = self._extract_auth_url(combined_output)
                
                if auth_url:
                    return {
                        'success': True,
                        'needs_auth': True,
                        'auth_url': auth_url,
                        'message': 'Authentication required'
                    }
                
                # If no URL in output, check status for auth URL
                check_status = self.get_status()
                if check_status.get('needs_auth') and check_status.get('auth_url'):
                    return {
                        'success': True,
                        'needs_auth': True,
                        'auth_url': check_status.get('auth_url'),
                        'message': 'Authentication required'
                    }
                
                # If now connected (was already authenticated but just needed 'up')
                if check_status.get('connected'):
                    return {
                        'success': True,
                        'message': 'Connected successfully'
                    }
                
                return {
                    'success': False,
                    'error': 'Could not get authentication URL. Try again.'
                }
            
            # Already authenticated, just need to bring it up
            cmd = ['timeout', '10', 'sudo', '-n', 'tailscale', 'up']
            logger.info(f"Executing (already authenticated): {' '.join(cmd)}")
            
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=15
                )
            except subprocess.TimeoutExpired:
                logger.warning("Tailscale up timed out for authenticated connect")
            
            import time
            time.sleep(2)
            
            verify_status = self.get_status()
            
            if verify_status.get('connected'):
                return {
                    'success': True,
                    'message': 'Connected successfully'
                }
            
            # Check if device was deleted from admin panel
            if verify_status.get('backend_state') != 'NeedsLogin' and not verify_status.get('needs_auth'):
                logger.warning("Device appears deleted from admin panel")
                return {
                    'success': False,
                    'needs_logout': True,
                    'error': 'Device was deleted from admin panel. Please click the "Logout" button and try again.'
                }
            
            return {
                'success': False,
                'error': 'Connection status unclear'
            }
            
        except Exception as e:
            logger.error(f"Error connecting Tailscale: {e}")
            return {'success': False, 'error': str(e)}
    
    def _extract_auth_url(self, output: str) -> Optional[str]:
        """Extract authentication URL from output"""
        match = re.search(
            r'https://login\.tailscale\.com/a/[a-zA-Z0-9]+',
            output,
            re.MULTILINE | re.DOTALL
        )
        return match.group(0) if match else None
    
    def disconnect(self) -> Dict:
        """Disconnect from Tailscale"""
        try:
            result = subprocess.run(
                ['sudo', 'tailscale', 'down'],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode != 0:
                return {'success': False, 'error': result.stderr}
            
            return {
                'success': True,
                'message': 'Disconnected successfully'
            }
            
        except Exception as e:
            logger.error(f"Error disconnecting Tailscale: {e}")
            return {'success': False, 'error': str(e)}
    
    def logout(self) -> Dict:
        """Logout from Tailscale (clears local credentials)"""
        try:
            result = subprocess.run(
                ['sudo', '-n', 'tailscale', 'logout'],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode != 0:
                error_msg = result.stderr.strip()
                if 'password is required' in error_msg or 'a password is required' in error_msg.lower():
                    return {
                        'success': False, 
                        'error': 'Logout requires sudo password. Please run "sudo tailscale logout" manually in terminal.'
                    }
                return {'success': False, 'error': error_msg or 'Logout failed'}
            
            return {
                'success': True,
                'message': 'Logged out successfully. You can now reconnect with a fresh authentication.'
            }
            
        except Exception as e:
            logger.error(f"Error logging out from Tailscale: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_info(self) -> Dict:
        """Get Tailscale provider information"""
        return {
            'name': self.name,
            'display_name': self.display_name,
            'description': 'Secure mesh VPN with easy setup',
            'features': [
                'Zero-config mesh networking',
                'Cross-platform support',
                'Built-in NAT traversal',
                'Free for personal use (up to 20 devices)',
                'Web-based authentication'
            ],
            'requires_auth': True,
            'auth_method': 'web',
            'install_url': 'https://tailscale.com/download'
        }
    
    def get_peers(self) -> List[Dict]:
        """Get list of Tailscale peers/nodes"""
        if not self.is_installed():
            return []
        
        try:
            result = subprocess.run(
                ['tailscale', 'status', '--json'],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode != 0:
                logger.error(f"Failed to get Tailscale peers: {result.stderr}")
                return []
            
            import json
            try:
                status_data = json.loads(result.stdout)
                peers_data = status_data.get('Peer', {}) or {}
                self_node = status_data.get('Self', {})
                
                peers = []
                
                # Add self node first
                if self_node:
                    # Prefer DNSName over HostName for display (extract hostname from FQDN)
                    dns_name = self_node.get('DNSName', '')
                    host_name = self_node.get('HostName', 'Unknown')
                    # Extract hostname from DNSName like "device.tailXXXX.ts.net."
                    display_name = dns_name.split('.')[0] if dns_name else host_name
                    
                    peers.append({
                        'id': self_node.get('ID', ''),
                        'hostname': display_name,
                        'ip_addresses': self_node.get('TailscaleIPs', []),
                        'os': self_node.get('OS', 'Unknown'),
                        'online': self_node.get('Online', False),
                        'active': self_node.get('Active', False),
                        'is_self': True,
                        'exit_node': self_node.get('ExitNode', False),
                        'exit_node_option': self_node.get('ExitNodeOption', False),
                        'relay': self_node.get('CurAddr', ''),
                        'last_seen': self_node.get('LastSeen', '')
                    })
                
                # Add other peers
                for peer_id, peer_data in peers_data.items():
                    # Prefer DNSName over HostName for display (extract hostname from FQDN)
                    dns_name = peer_data.get('DNSName', '')
                    host_name = peer_data.get('HostName', 'Unknown')
                    # Extract hostname from DNSName like "device.tailXXXX.ts.net."
                    display_name = dns_name.split('.')[0] if dns_name else host_name
                    
                    peers.append({
                        'id': peer_id,
                        'hostname': display_name,
                        'ip_addresses': peer_data.get('TailscaleIPs', []),
                        'os': peer_data.get('OS', 'Unknown'),
                        'online': peer_data.get('Online', False),
                        'active': peer_data.get('Active', False),
                        'is_self': False,
                        'exit_node': peer_data.get('ExitNode', False),
                        'exit_node_option': peer_data.get('ExitNodeOption', False),
                        'relay': peer_data.get('CurAddr', ''),
                        'last_seen': peer_data.get('LastSeen', ''),
                        'rx_bytes': peer_data.get('RxBytes', 0),
                        'tx_bytes': peer_data.get('TxBytes', 0)
                    })
                
                return peers
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Tailscale status JSON: {e}")
                return []
                
        except Exception as e:
            logger.error(f"Error getting Tailscale peers: {e}")
            return []


class VPNService:
    """Main VPN service managing multiple providers"""
    
    def __init__(self, websocket_manager=None, event_loop=None):
        self.websocket_manager = websocket_manager
        self.event_loop = event_loop
        
        # Initialize providers
        self.providers: Dict[str, VPNProvider] = {
            'tailscale': TailscaleProvider(),
            # Future providers can be added here:
            # 'zerotier': ZeroTierProvider(),
            # 'wireguard': WireGuardProvider(),
        }
        
        self.current_provider: Optional[str] = None
        self._detect_providers()
    
    def _detect_providers(self):
        """Detect installed VPN providers"""
        for name, provider in self.providers.items():
            if provider.is_installed():
                logger.info(f"{name} detected")
                if not self.current_provider:
                    self.current_provider = name
    
    def get_available_providers(self) -> List[Dict]:
        """Get list of available VPN providers"""
        providers_list = []
        for name, provider in self.providers.items():
            info = provider.get_info()
            info['installed'] = provider.is_installed()
            providers_list.append(info)
        return providers_list
    
    def get_status(self, provider: Optional[str] = None) -> Dict:
        """Get VPN status for a specific provider or current one"""
        provider_name = provider or self.current_provider
        
        if not provider_name or provider_name not in self.providers:
            return {
                'success': True,
                'current_provider': None,
                'installed': False,
                'connected': False,
                'message': 'No VPN provider selected or installed'
            }
        
        provider_obj = self.providers[provider_name]
        status = provider_obj.get_status()
        status['provider'] = provider_name
        status['provider_display_name'] = provider_obj.display_name
        
        return status
    
    def get_peers(self, provider: Optional[str] = None) -> List[Dict]:
        """Get list of VPN peers/nodes for a specific provider or current one"""
        provider_name = provider or self.current_provider
        
        if not provider_name or provider_name not in self.providers:
            return []
        
        provider_obj = self.providers[provider_name]
        
        if not provider_obj.is_installed():
            return []
        
        return provider_obj.get_peers()
    
    def connect(self, provider: Optional[str] = None) -> Dict:
        """Connect to VPN"""
        provider_name = provider or self.current_provider
        
        if not provider_name or provider_name not in self.providers:
            return {'success': False, 'error': 'Invalid VPN provider'}
        
        provider_obj = self.providers[provider_name]
        
        if not provider_obj.is_installed():
            return {
                'success': False,
                'error': f'{provider_obj.display_name} is not installed'
            }
        
        result = provider_obj.connect()
        
        if result.get('success') and not result.get('needs_auth'):
            self.current_provider = provider_name
            # Broadcast status update
            self._broadcast_status()
        
        return result
    
    def disconnect(self, provider: Optional[str] = None) -> Dict:
        """Disconnect from VPN"""
        provider_name = provider or self.current_provider
        
        if not provider_name or provider_name not in self.providers:
            return {'success': False, 'error': 'Invalid VPN provider'}
        
        provider_obj = self.providers[provider_name]
        result = provider_obj.disconnect()
        
        if result.get('success'):
            # Broadcast status update
            self._broadcast_status()
        
        return result
    
    def logout(self, provider: Optional[str] = None) -> Dict:
        """Logout from VPN (clears local credentials)"""
        provider_name = provider or self.current_provider
        
        if not provider_name or provider_name not in self.providers:
            return {'success': False, 'error': 'Invalid VPN provider'}
        
        provider_obj = self.providers[provider_name]
        result = provider_obj.logout()
        
        if result.get('success'):
            # Broadcast status update
            self._broadcast_status()
        
        return result
    
    def _broadcast_status(self):
        """Broadcast VPN status via WebSocket"""
        if self.websocket_manager and self.event_loop:
            try:
                import asyncio
                status = self.get_status()
                asyncio.run_coroutine_threadsafe(
                    self.websocket_manager.broadcast("vpn_status", status),
                    self.event_loop
                )
            except Exception as e:
                logger.error(f"Error broadcasting VPN status: {e}")


# Singleton instance
_vpn_service_instance = None


def init_vpn_service(websocket_manager=None, event_loop=None) -> VPNService:
    """Initialize VPN service singleton"""
    global _vpn_service_instance
    if _vpn_service_instance is None:
        _vpn_service_instance = VPNService(websocket_manager, event_loop)
    return _vpn_service_instance


def get_vpn_service() -> VPNService:
    """Get VPN service singleton"""
    global _vpn_service_instance
    if _vpn_service_instance is None:
        raise RuntimeError("VPN service not initialized")
    return _vpn_service_instance
