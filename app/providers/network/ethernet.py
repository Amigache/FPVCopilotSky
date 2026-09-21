"""
Ethernet Network Interface Provider
Implementation for wired Ethernet connections
"""

from typing import Dict, Optional
from ..base import NetworkInterface, InterfaceStatus, InterfaceType
import re
import logging
from app.utils.cmd import run_cmd

logger = logging.getLogger(__name__)


class EthernetInterface(NetworkInterface):
    """Ethernet network interface provider"""

    def __init__(self, interface_name: str = "eth0"):
        super().__init__()
        self.interface_name = interface_name
        self.name = f"ethernet_{interface_name}"
        self.display_name = f"Ethernet ({interface_name})"
        self.interface_type = InterfaceType.ETHERNET

    def detect(self) -> bool:
        """Detect if Ethernet interface exists"""
        try:
            _, _, returncode = run_cmd(
                ["ip", "link", "show", self.interface_name],
                timeout=2,
                check=False,
            )
            return returncode == 0
        except Exception:
            return False

    def get_status(self) -> Dict:
        """Get Ethernet interface status"""
        if not self.detect():
            return {
                "status": InterfaceStatus.ERROR,
                "interface": self.interface_name,
                "type": self.interface_type.value,
                "error": f"Interface {self.interface_name} not found",
            }

        try:
            # Get interface state
            output, _, returncode = run_cmd(
                ["ip", "addr", "show", self.interface_name],
                timeout=2,
                check=False,
            )

            if returncode != 0:
                return {
                    "status": InterfaceStatus.ERROR,
                    "interface": self.interface_name,
                    "type": self.interface_type.value,
                    "error": "Failed to get interface status",
                }

            # Determine status
            if "state UP" in output:
                if "NO-CARRIER" in output:
                    status = InterfaceStatus.NO_CARRIER
                else:
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
                "carrier": status != InterfaceStatus.NO_CARRIER,
            }
        except Exception as e:
            logger.error(f"Error getting Ethernet status: {e}")
            return {
                "status": InterfaceStatus.ERROR,
                "interface": self.interface_name,
                "type": self.interface_type.value,
                "error": str(e),
            }

    def bring_up(self) -> Dict:
        """Bring Ethernet interface up"""
        try:
            _, stderr, returncode = run_cmd(
                ["sudo", "ip", "link", "set", self.interface_name, "up"],
                timeout=5,
                check=False,
            )

            if returncode == 0:
                return {
                    "success": True,
                    "message": f"Interface {self.interface_name} brought up",
                }
            return {
                "success": False,
                "error": stderr or "Failed to bring interface up",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def bring_down(self) -> Dict:
        """Bring Ethernet interface down"""
        try:
            _, stderr, returncode = run_cmd(
                ["sudo", "ip", "link", "set", self.interface_name, "down"],
                timeout=5,
                check=False,
            )

            if returncode == 0:
                return {
                    "success": True,
                    "message": f"Interface {self.interface_name} brought down",
                }
            return {
                "success": False,
                "error": stderr or "Failed to bring interface down",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_ip_address(self) -> Optional[str]:
        """Get IP address of interface"""
        status = self.get_status()
        return status.get("ip_address")

    def set_metric(self, metric: int) -> Dict:
        """Set route metric for interface"""
        try:
            gateway = self._get_gateway()
            if not gateway:
                return {"success": False, "error": "No gateway found for interface"}

            # Delete old route
            run_cmd(
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
                timeout=2,
                check=False,
            )

            # Add route with new metric
            _, stderr, returncode = run_cmd(
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
                timeout=5,
                check=False,
            )

            if returncode == 0:
                return {
                    "success": True,
                    "message": f"Metric set to {metric} for {self.interface_name}",
                    "metric": metric,
                }
            return {"success": False, "error": stderr or "Failed to set metric"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_gateway(self) -> Optional[str]:
        """Get gateway for interface"""
        try:
            output, _, returncode = run_cmd(
                ["ip", "route", "show", "dev", self.interface_name],
                timeout=2,
                check=False,
            )

            if returncode == 0:
                for line in output.split("\n"):
                    if "default via" in line:
                        match = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", line)
                        if match:
                            return match.group(1)
            return None
        except Exception:
            return None

    def _get_metric(self) -> Optional[int]:
        """Get current route metric"""
        try:
            output, _, returncode = run_cmd(
                ["ip", "route", "show", "dev", self.interface_name],
                timeout=2,
                check=False,
            )

            if returncode == 0:
                for line in output.split("\n"):
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
            "interface_name": self.interface_name,
            "type": self.interface_type.value,
            "description": f"Wired Ethernet interface {self.interface_name}",
            "features": ["Wired connection", "High speed", "Low latency", "Reliable"],
        }
