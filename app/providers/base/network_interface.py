"""
Network Interface abstraction
Represents physical/virtual network interfaces (WiFi, Ethernet, VPN, Modem, etc.)
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, List
from enum import Enum
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


class InterfaceStatus(Enum):
    """Network interface status"""

    UP = "up"
    DOWN = "down"
    CONNECTING = "connecting"
    NO_CARRIER = "no_carrier"
    ERROR = "error"


class InterfaceType(Enum):
    """Network interface type"""

    ETHERNET = "ethernet"
    WIFI = "wifi"
    VPN = "vpn"
    MODEM = "modem"
    LOOPBACK = "loopback"
    BRIDGE = "bridge"
    UNKNOWN = "unknown"


@dataclass
class InterfaceMetrics:
    """Network interface metrics"""

    status: InterfaceStatus
    ip_v4: Optional[str] = None
    ip_v6: Optional[str] = None
    gateway: Optional[str] = None
    metric: int = 100  # Route metric for policy routing
    mtu: int = 1500
    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_packets: int = 0
    tx_packets: int = 0


class NetworkInterface(ABC):
    """
    Abstract base class for network interfaces.
    Represents a logical network connection point.
    """

    def __init__(self):
        self.name: str = ""
        self.display_name: str = ""
        self.interface_type: InterfaceType = InterfaceType.UNKNOWN

    @abstractmethod
    def detect(self) -> bool:
        """
        Check if this interface is available on the system.
        Returns True if interface exists and is accessible.
        """
        pass

    @abstractmethod
    def get_status(self) -> InterfaceMetrics:
        """
        Get current interface status and metrics.
        """
        pass

    @abstractmethod
    def bring_up(self) -> Dict:
        """
        Activate the interface (if not already up).
        Returns:
            {'success': bool, 'message': str}
        """
        pass

    @abstractmethod
    def bring_down(self) -> Dict:
        """
        Deactivate the interface.
        Returns:
            {'success': bool, 'message': str}
        """
        pass

    @abstractmethod
    def get_ip_address(self) -> Optional[str]:
        """Get IPv4 address"""
        pass

    @abstractmethod
    def set_metric(self, metric: int) -> Dict:
        """
        Set interface metric for routing policy.
        Lower metric = higher priority.
        """
        pass

    def is_available(self) -> bool:
        """Check if interface is available"""
        metrics = self.get_status()
        return metrics.status in [InterfaceStatus.UP, InterfaceStatus.CONNECTING]

    def is_connected(self) -> bool:
        """Check if interface has active connection"""
        metrics = self.get_status()
        return metrics.status == InterfaceStatus.UP and metrics.ip_v4 is not None

    def get_capabilities(self) -> Dict[str, bool]:
        """Get interface capabilities"""
        return {
            "dhcp": False,
            "static_ip": False,
            "ipv6": False,
            "metric_configuration": True,
        }
