"""
Modem Network Interface Provider
Implementation for USB/HiLink modem interfaces
"""

from typing import Dict, Optional
from ..base import NetworkInterface, InterfaceStatus, InterfaceType
import subprocess
import re
import logging

logger = logging.getLogger(__name__)


class ModemInterface(NetworkInterface):
    """Modem network interface provider (USB/HiLink)"""

    def __init__(self, interface_name: Optional[str] = None, subnet_pattern: str = "192.168.8"):
        super().__init__()
        self.interface_name = interface_name
        self.subnet_pattern = subnet_pattern  # HiLink modems typically use 192.168.8.x
        self.name = "modem_interface"
        self.display_name = "4G/LTE Modem"
        self.interface_type = InterfaceType.MODEM

    def detect(self) -> bool:
        """Detect if modem interface exists"""
        try:
            # If no specific interface name, search for modem by subnet pattern
            if not self.interface_name:
                self.interface_name = self._find_modem_interface()

            if not self.interface_name:
                return False

            result = subprocess.run(
                ["ip", "link", "show", self.interface_name],
                capture_output=True,
                text=True,
                timeout=2,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _find_modem_interface(self) -> Optional[str]:
        """Find modem interface by subnet pattern"""
        try:
            result = subprocess.run(["ip", "-o", "addr", "show"], capture_output=True, text=True, timeout=2)

            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    # Look for interface with modem subnet (e.g., 192.168.8.x)
                    if self.subnet_pattern in line:
                        match = re.search(
                            r"^\d+:\s+(\S+)\s+inet\s+" + self.subnet_pattern.replace(".", r"\."),
                            line,
                        )
                        if match:
                            return match.group(1)
            return None
        except Exception:
            return None

    def get_status(self) -> Dict:
        """Get modem interface status"""
        if not self.detect():
            return {
                "status": InterfaceStatus.DOWN,
                "interface": self.interface_name or "unknown",
                "type": self.interface_type.value,
                "message": f"Modem interface not found (subnet: {self.subnet_pattern}.x)",
            }

        try:
            # Get interface state
            result = subprocess.run(
                ["ip", "addr", "show", self.interface_name],
                capture_output=True,
                text=True,
                timeout=2,
            )

            if result.returncode != 0:
                return {
                    "status": InterfaceStatus.ERROR,
                    "interface": self.interface_name,
                    "type": self.interface_type.value,
                    "error": "Failed to get interface status",
                }

            output = result.stdout

            # Determine status
            if "state UP" in output:
                status = InterfaceStatus.UP
            elif "state DOWN" in output:
                status = InterfaceStatus.DOWN
            else:
                status = InterfaceStatus.ERROR

            # Extract IP address
            ip_match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", output)
            ip_address = ip_match.group(1) if ip_match else None

            # Extract MAC address
            mac_match = re.search(r"link/ether ([0-9a-f:]+)", output)
            mac_address = mac_match.group(1) if mac_match else None

            # Get gateway
            gateway = self._get_gateway()

            # Get metric
            metric = self._get_metric()

            return {
                "status": status,
                "interface": self.interface_name,
                "type": self.interface_type.value,
                "ip_address": ip_address,
                "mac_address": mac_address,
                "gateway": gateway,
                "metric": metric,
                "subnet_pattern": self.subnet_pattern,
            }
        except Exception as e:
            logger.error(f"Error getting modem status: {e}")
            return {
                "status": InterfaceStatus.ERROR,
                "interface": self.interface_name or "unknown",
                "type": self.interface_type.value,
                "error": str(e),
            }

    def bring_up(self) -> Dict:
        """Bring modem interface up"""
        if not self.interface_name:
            return {"success": False, "error": "Interface not detected"}

        try:
            result = subprocess.run(
                ["sudo", "ip", "link", "set", self.interface_name, "up"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "message": f"Interface {self.interface_name} brought up",
                }
            return {
                "success": False,
                "error": result.stderr or "Failed to bring interface up",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def bring_down(self) -> Dict:
        """Bring modem interface down"""
        if not self.interface_name:
            return {"success": False, "error": "Interface not detected"}

        try:
            result = subprocess.run(
                ["sudo", "ip", "link", "set", self.interface_name, "down"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "message": f"Interface {self.interface_name} brought down",
                }
            return {
                "success": False,
                "error": result.stderr or "Failed to bring interface down",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_ip_address(self) -> Optional[str]:
        """Get IP address of interface"""
        status = self.get_status()
        return status.get("ip_address")

    def set_metric(self, metric: int) -> Dict:
        """Set route metric for interface"""
        if not self.interface_name:
            return {"success": False, "error": "Interface not detected"}

        try:
            gateway = self._get_gateway()
            if not gateway:
                return {"success": False, "error": "No gateway found for interface"}

            # Delete old route
            subprocess.run(
                [
                    "sudo",
                    "ip",
                    "route",
                    "del",
                    "default",
                    "via",
                    gateway,
                    "dev",
                    self.interface_name,
                ],
                capture_output=True,
                timeout=2,
            )

            # Add route with new metric
            result = subprocess.run(
                [
                    "sudo",
                    "ip",
                    "route",
                    "add",
                    "default",
                    "via",
                    gateway,
                    "dev",
                    self.interface_name,
                    "metric",
                    str(metric),
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "message": f"Metric set to {metric} for {self.interface_name}",
                    "metric": metric,
                }
            return {"success": False, "error": result.stderr or "Failed to set metric"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_gateway(self) -> Optional[str]:
        """Get gateway for interface"""
        if not self.interface_name:
            return None

        try:
            result = subprocess.run(
                ["ip", "route", "show", "dev", self.interface_name],
                capture_output=True,
                text=True,
                timeout=2,
            )

            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if "default via" in line:
                        match = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", line)
                        if match:
                            return match.group(1)
            return None
        except Exception:
            return None

    def _get_metric(self) -> Optional[int]:
        """Get current route metric"""
        if not self.interface_name:
            return None

        try:
            result = subprocess.run(
                ["ip", "route", "show", "dev", self.interface_name],
                capture_output=True,
                text=True,
                timeout=2,
            )

            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if "default" in line and "metric" in line:
                        match = re.search(r"metric (\d+)", line)
                        if match:
                            return int(match.group(1))
            return None
        except Exception:
            return None

    def get_info(self) -> Dict:
        """Get interface information"""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "interface_name": self.interface_name or "auto-detect",
            "type": self.interface_type.value,
            "description": "USB/HiLink 4G/LTE modem interface",
            "features": [
                "4G/LTE connectivity",
                "Auto-detection via subnet pattern",
                "USB connection",
                f"Subnet: {self.subnet_pattern}.x",
            ],
        }
