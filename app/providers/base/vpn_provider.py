"""
VPN Provider abstract base class
Compatible with existing vpn_service.py VPNProvider
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)


class VPNProvider(ABC):
    """Abstract base class for VPN providers"""

    def __init__(self):
        self.name: str = ""
        self.display_name: str = ""

    @abstractmethod
    def is_installed(self) -> bool:
        """Check if VPN provider is installed on the system"""
        pass

    @abstractmethod
    def get_status(self) -> Dict:
        """
        Get connection status.
        Returns:
            {
                'success': bool,
                'installed': bool,
                'connected': bool,
                'ip_address': Optional[str],
                'interface': Optional[str],
                'peers': Optional[int],
                'message': str,
                'error': Optional[str]
            }
        """
        pass

    @abstractmethod
    def connect(self) -> Dict:
        """
        Establish VPN connection.
        Returns:
            {
                'success': bool,
                'message': str,
                'ip_address': Optional[str],
                'interface': Optional[str]
            }
        """
        pass

    @abstractmethod
    def disconnect(self) -> Dict:
        """
        Terminate VPN connection.
        Returns:
            {
                'success': bool,
                'message': str
            }
        """
        pass

    @abstractmethod
    def get_info(self) -> Dict:
        """
        Get provider information and capabilities.
        Returns:
            {
                'name': str,
                'version': str,
                'capabilities': [str],
                'settings': Dict
            }
        """
        pass

    @abstractmethod
    def get_peers(self) -> List[Dict]:
        """
        Get list of peers/nodes in the VPN network.
        Returns:
            [
                {
                    'id': str,
                    'name': str,
                    'ip': str,
                    'status': 'online'|'offline',
                    'last_seen': Optional[datetime]
                },
                ...
            ]
        """
        pass

    def get_interface_name(self) -> Optional[str]:
        """Get the VPN interface name (e.g., 'tailscale0', 'tun0')"""
        status = self.get_status()
        return status.get("interface")

    def get_capabilities(self) -> Dict[str, bool]:
        """Get provider capabilities"""
        return {
            "exit_node_selection": False,
            "subnet_routes": False,
            "split_tunnel": False,
            "dns_override": False,
            "peer_management": False,
        }
