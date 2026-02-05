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
                
                # Connected only if backend running AND node is online/active AND no auth needed
                connected = (backend_state == 'Running' and 
                           (node_online or node_active) and 
                           not auth_url)
                
                # Authenticated means has valid credentials (not needs login)
                # User is authenticated even when disconnected (Stopped state)
                authenticated = (backend_state not in ['NeedsLogin', 'NoState'] and 
                               not auth_url)
                
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
                
                # If there's an auth URL, include it and mark as needs auth
                if auth_url:
                    response['needs_auth'] = True
                    response['auth_url'] = auth_url
                    response['message'] = 'Device needs re-authentication'
                
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
            
            # Execute tailscale up
            cmd = ['sudo', '-n', 'tailscale', 'up']
            
            logger.info(f"Executing: {' '.join(cmd)}")
            
            # Use Popen to capture output with timeout
            import subprocess
            from threading import Timer
            import time
            
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Kill after 5 seconds to capture auth URL
            def kill_proc():
                try:
                    proc.kill()
                except:
                    pass
            
            timer = Timer(5.0, kill_proc)
            timer.start()
            
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
            finally:
                timer.cancel()
            
            returncode = proc.returncode
            combined_output = stdout + stderr
            
            logger.info(f"Tailscale up result: returncode={returncode}")
            logger.debug(f"Output: {combined_output}")
            
            # Check for authentication URL
            auth_url = self._extract_auth_url(combined_output)
            
            if auth_url or 'login.tailscale.com' in combined_output.lower():
                return {
                    'success': True,
                    'needs_auth': True,
                    'auth_url': auth_url,
                    'message': 'Authentication required'
                }
            
            # Wait a moment for Tailscale to establish connection
            time.sleep(2)
            
            # Verify actual connection status
            verify_status = self.get_status()
            
            # Check if really connected (node online or active)
            if verify_status.get('connected'):
                return {
                    'success': True,
                    'message': 'Connected successfully'
                }
            
            # If has auth_url after connection attempt, needs re-authentication
            if verify_status.get('needs_auth') and verify_status.get('auth_url'):
                return {
                    'success': True,
                    'needs_auth': True,
                    'auth_url': verify_status.get('auth_url'),
                    'message': 'Device needs re-authentication'
                }
            
            # Connection failed - device might be deleted from admin panel
            # Inform user to use the Logout button
            if returncode == 0 and not verify_status.get('connected'):
                # Check if node is not online/active despite being "authenticated"
                # This indicates device was deleted from admin panel
                if verify_status.get('backend_state') != 'NeedsLogin' and not verify_status.get('needs_auth'):
                    logger.warning("Device appears deleted from admin panel. User needs to logout first.")
                    
                    return {
                        'success': False,
                        'needs_logout': True,
                        'error': 'Device was deleted from admin panel. Please click the "Logout" button and try again.'
                    }
            
            # Other errors
            if returncode != 0:
                return {
                    'success': False,
                    'error': stderr or stdout or 'Unknown error'
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
