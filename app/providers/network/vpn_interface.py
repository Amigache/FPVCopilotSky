"""
VPN Network Interface Provider
Implementation for VPN tunnel interfaces (Tailscale, ZeroTier, WireGuard, etc.)
"""

from typing import Dict, Optional
from ..base import NetworkInterface, InterfaceStatus, InterfaceType
import re
import logging
from app.utils.cmd import run_cmd

logger = logging.getLogger(__name__)


class VPNInterface(NetworkInterface):
    """VPN network interface provider"""

    def __init__(self, interface_pattern: str = "tailscale", interface_name: Optional[str] = None):
        super().__init__()
        self.interface_pattern = interface_pattern  # Pattern to search for (e.g., "tailscale", "zt", "wg")
        self.interface_name = interface_name  # Actual interface name if known
        self.name = f"vpn_{interface_pattern}"
        self.display_name = f"VPN ({interface_pattern})"
        self.interface_type = InterfaceType.VPN

    def detect(self) -> bool:
        """Detect if VPN interface exists"""
        try:
            # If we don't have the interface name, search for it
            if not self.interface_name:
                self.interface_name = self._find_interface()

            if not self.interface_name:
                return False

            _, _, returncode = run_cmd(
                ["ip", "link", "show", self.interface_name],
                timeout=2,
                check=False,
            )
            return returncode == 0
        except Exception:
            return False

    def _find_interface(self) -> Optional[str]:
        """Find VPN interface by pattern"""
        try:
            output, _, returncode = run_cmd(["ip", "link", "show"], timeout=2, check=False)

            if returncode == 0:
                for line in output.split("\n"):
                    if self.interface_pattern in line.lower():
                        match = re.search(r"\d+:\s+(\S+):", line)
                        if match:
                            return match.group(1)
            return None
        except Exception:
            return None

    def get_status(self) -> Dict:
        """Get VPN interface status"""
        if not self.detect():
            return {
                "status": InterfaceStatus.DOWN,
                "interface": self.interface_name or f"{self.interface_pattern}*",
                "type": self.interface_type.value,
                "message": f"VPN interface not found (pattern: {self.interface_pattern})",
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

            # Determine status (VPN interfaces often show UNKNOWN state but have LOWER_UP when active)
            if "state UP" in output or "LOWER_UP" in output:
                status = InterfaceStatus.UP
            elif "state DOWN" in output:
                status = InterfaceStatus.DOWN
            else:
                # VPN interfaces might be in UNKNOWN state but still functional
                if "LOWER_UP" in output:
                    status = InterfaceStatus.UP
                else:
                    status = InterfaceStatus.DOWN

            # Extract IP address
            ip_match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", output)
            ip_address = ip_match.group(1) if ip_match else None

            # Extract MAC address (VPN interfaces might not have one)
            mac_match = re.search(r"link/(\S+)\s+([0-9a-f:]+)", output)
            mac_address = mac_match.group(2) if mac_match else None

            # Get gateway (VPN interfaces might not have traditional gateway)
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
                "vpn_type": self.interface_pattern,
            }
        except Exception as e:
            logger.error(f"Error getting VPN status: {e}")
            return {
                "status": InterfaceStatus.ERROR,
                "interface": self.interface_name or self.interface_pattern,
                "type": self.interface_type.value,
                "error": str(e),
            }

    def bring_up(self) -> Dict:
        """Bring VPN interface up (not typically used - VPN service manages this)"""
        return {
            "success": False,
            "error": "VPN interfaces are managed by their respective VPN services",
        }

    def bring_down(self) -> Dict:
        """Bring VPN interface down (not typically used - VPN service manages this)"""
        return {
            "success": False,
            "error": "VPN interfaces are managed by their respective VPN services",
        }

    def get_ip_address(self) -> Optional[str]:
        """Get IP address of interface"""
        status = self.get_status()
        return status.get("ip_address")

    def set_metric(self, metric: int) -> Dict:
        """Set route metric for interface"""
        try:
            if not self.interface_name:
                return {"success": False, "error": "Interface not detected"}

            gateway = self._get_gateway()
            if not gateway:
                # VPN interfaces might not have explicit gateway, use interface directly
                # Get all routes for this interface
                output, _, returncode = run_cmd(
                    ["ip", "route", "show", "dev", self.interface_name],
                    timeout=2,
                    check=False,
                )

                if returncode != 0 or "default" not in output:
                    return {
                        "success": False,
                        "error": "No default route found for VPN interface",
                    }

                # For VPN, modify existing routes with metric
                routes = []
                for line in output.split("\n"):
                    if line.strip():
                        routes.append(line.strip())

                for route in routes:
                    if "default" in route:
                        # Delete old default route
                        run_cmd(
                            ["sudo", "ip", "route", "del"] + route.split(),
                            timeout=2,
                            check=False,
                        )

                        # Add back with metric
                        route_parts = route.split()
                        # Remove old metric if present
                        if "metric" in route_parts:
                            idx = route_parts.index("metric")
                            route_parts = route_parts[:idx] + route_parts[idx + 2 :]

                        _, stderr, returncode = run_cmd(
                            ["sudo", "ip", "route", "add"] + route_parts + ["metric", str(metric)],
                            timeout=5,
                            check=False,
                        )

                        if returncode == 0:
                            return {
                                "success": True,
                                "message": f"Metric set to {metric} for {self.interface_name}",
                                "metric": metric,
                            }
                        return {
                            "success": False,
                            "error": stderr or "Failed to set metric",
                        }
            else:
                # Traditional approach with gateway
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
                return {
                    "success": False,
                    "error": stderr or "Failed to set metric",
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_gateway(self) -> Optional[str]:
        """Get gateway for interface (VPN might not have traditional gateway)"""
        try:
            if not self.interface_name:
                return None

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
            if not self.interface_name:
                return None

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
            "interface_name": self.interface_name or f"{self.interface_pattern}*",
            "type": self.interface_type.value,
            "description": f"VPN tunnel interface ({self.interface_pattern})",
            "features": [
                "Encrypted tunnel",
                "Managed by VPN service",
                "Virtual interface",
                f"Pattern: {self.interface_pattern}",
            ],
        }
