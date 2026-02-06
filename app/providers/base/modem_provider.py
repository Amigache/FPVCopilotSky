"""
Modem Provider - Abstract base class for modem integration
Supports multiple modes: HiLink, Router gateway, USB dongle
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, List
from enum import Enum
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class ModemStatus(Enum):
    """Modem operational status"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    UNAVAILABLE = "unavailable"


@dataclass
class ModemInfo:
    """Modem information"""
    name: str
    model: str
    imei: str
    imsi: str
    manufacturer: str


@dataclass
class NetworkInfo:
    """Network connection information"""
    status: ModemStatus
    signal_strength: int  # 0-100
    network_type: str  # 4G, LTE, 5G, 3G, 2G
    operator: str
    ip_address: Optional[str] = None
    dns_servers: List[str] = None
    data_uploaded: int = 0  # bytes
    data_downloaded: int = 0  # bytes


class ModemProvider(ABC):
    """
    Abstract base class for modem providers.
    Each implementation handles a specific modem type/mode.
    """
    
    def __init__(self):
        self.name: str = ""
        self.display_name: str = ""
        self.is_available: bool = False
    
    @abstractmethod
    def detect(self) -> bool:
        """
        Auto-detect if this modem is available/connected.
        Returns True if modem is found and operational.
        """
        pass
    
    @abstractmethod
    def get_status(self) -> Dict:
        """
        Get current modem status.
        Returns:
            {
                'available': bool,
                'status': ModemStatus,
                'modem_info': Optional[ModemInfo],
                'network_info': Optional[NetworkInfo],
                'error': Optional[str]
            }
        """
        pass
    
    @abstractmethod
    def connect(self) -> Dict:
        """
        Activate modem connection.
        Returns:
            {
                'success': bool,
                'message': str,
                'network_info': Optional[NetworkInfo]
            }
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> Dict:
        """
        Deactivate modem connection.
        Returns:
            {
                'success': bool,
                'message': str
            }
        """
        pass
    
    @abstractmethod
    def get_modem_info(self) -> Optional[ModemInfo]:
        """Get modem hardware information"""
        pass
    
    @abstractmethod
    def get_network_info(self) -> Optional[NetworkInfo]:
        """Get network connection information"""
        pass
    
    @abstractmethod
    def configure_band(self, band_mask: int) -> Dict:
        """
        Configure LTE band preference (if supported).
        Args:
            band_mask: Bitmask of bands to use
        Returns:
            {'success': bool, 'message': str}
        """
        pass
    
    @abstractmethod
    def reboot(self) -> Dict:
        """
        Reboot the modem (if supported).
        Returns:
            {'success': bool, 'message': str}
        """
        pass
    
    def get_capabilities(self) -> Dict[str, bool]:
        """
        Get provider capabilities.
        Default: minimal set, override in subclasses.
        """
        return {
            'band_configuration': False,
            'signal_monitoring': True,
            'remote_reboot': False,
            'dns_configuration': False,
            'apn_configuration': False,
        }
