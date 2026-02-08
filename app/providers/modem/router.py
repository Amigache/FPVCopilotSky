"""
Router Gateway Modem Provider
Implementation for modems in router/gateway mode (e.g., TP-Link M7200)
"""

from typing import Dict, Optional
from ..base import ModemProvider, ModemStatus, ModemInfo, NetworkInfo
import logging
import subprocess

logger = logging.getLogger(__name__)


class RouterModemProvider(ModemProvider):
    """
    Generic router/gateway modem provider.
    Communicates with modem via its web interface or API.

    Example: TP-Link M7200 in router mode (typically 192.168.0.1)
    """

    def __init__(
        self,
        router_ip: str = "192.168.0.1",
        username: str = "admin",
        password: str = "admin",
    ):
        super().__init__()
        self.name = "router_modem"
        self.display_name = "Router Gateway Modem"
        self.router_ip = router_ip
        self.username = username
        self.password = password
        self.is_available = self.detect()

    def detect(self) -> bool:
        """Detect if router is accessible"""
        try:
            # Try ping to router
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "2", self.router_ip],
                capture_output=True,
                timeout=3,
            )
            return result.returncode == 0
        except:
            return False

    def get_status(self) -> Dict:
        """Get modem status"""
        if not self.is_available:
            return {
                "available": False,
                "status": ModemStatus.UNAVAILABLE,
                "modem_info": None,
                "network_info": None,
                "error": f"Router not accessible at {self.router_ip}",
            }

        return {
            "available": True,
            "status": ModemStatus.CONNECTED,
            "modem_info": self.get_modem_info(),
            "network_info": self.get_network_info(),
            "error": None,
            "note": "Router gateway modem - limited information available",
        }

    def connect(self) -> Dict:
        """Activate modem connection"""
        return {
            "success": False,
            "message": "Manual connection control not supported for router modems",
            "network_info": None,
        }

    def disconnect(self) -> Dict:
        """Deactivate modem connection"""
        return {
            "success": False,
            "message": "Manual disconnection not supported for router modems",
        }

    def get_modem_info(self) -> Optional[ModemInfo]:
        """Get modem hardware information"""
        # Router modems typically don't expose detailed info
        return ModemInfo(
            name="Router Gateway Modem",
            model="Unknown",
            imei="N/A",
            imsi="N/A",
            manufacturer="Unknown",
        )

    def get_network_info(self) -> Optional[NetworkInfo]:
        """Get network connection information"""
        # Router modems typically provide limited network info
        return NetworkInfo(
            status=ModemStatus.CONNECTED,
            signal_strength=0,  # Not available
            network_type="Unknown",
            operator="Unknown",
            ip_address=self.router_ip,
            dns_servers=[],
            data_uploaded=0,
            data_downloaded=0,
        )

    def configure_band(self, band_mask: int) -> Dict:
        """Configure LTE band preference"""
        return {
            "success": False,
            "message": "Band configuration not supported via router gateway mode",
        }

    def reboot(self) -> Dict:
        """Reboot the modem"""
        return {
            "success": False,
            "message": "Reboot not supported via API (use web interface)",
        }

    def get_info(self) -> Dict:
        """Get provider information"""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": "Generic router/gateway modem provider (limited functionality)",
            "features": [
                "Basic connectivity detection",
                "Router IP: " + self.router_ip,
            ],
            "modes": ["Router/Gateway mode"],
            "note": "For full features, use direct modem API (e.g., HiLink mode)",
        }


class TPLinkM7200Provider(RouterModemProvider):
    """TP-Link M7200 specific provider"""

    def __init__(self):
        super().__init__(router_ip="192.168.0.1", username="admin", password="admin")
        self.name = "tplink_m7200"
        self.display_name = "TP-Link M7200"

    def get_info(self) -> Dict:
        """Get provider information"""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": "TP-Link M7200 4G LTE mobile WiFi router",
            "features": [
                "LTE Cat 4",
                "WiFi hotspot",
                "Up to 10 devices",
                "Router mode: " + self.router_ip,
            ],
            "modes": ["Router mode"],
            "note": "Advanced features require web interface at " + self.router_ip,
        }
