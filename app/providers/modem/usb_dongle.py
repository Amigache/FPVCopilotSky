"""
USB Dongle Modem Provider
Implementation for generic USB dongle modems (e.g., via ModemManager/NetworkManager)
"""

from typing import Dict, Optional
from ..base import ModemProvider, ModemStatus, ModemInfo, NetworkInfo
import logging
import subprocess
import re

logger = logging.getLogger(__name__)


class USBDongleProvider(ModemProvider):
    """
    Generic USB dongle modem provider.
    Uses system tools like ModemManager (mmcli) or NetworkManager to communicate.

    This provider works with any USB modem that's detected by the Linux system.
    """

    def __init__(self):
        super().__init__()
        self.name = "usb_dongle"
        self.display_name = "USB Dongle Modem"
        self._modem_path = None
        self.is_available = self.detect()

    def detect(self) -> bool:
        """Detect if USB modem is available via ModemManager"""
        try:
            # Check if ModemManager is available
            result = subprocess.run(["which", "mmcli"], capture_output=True, timeout=2)
            if result.returncode != 0:
                logger.info("ModemManager (mmcli) not found")
                return False

            # List modems
            result = subprocess.run(["mmcli", "-L"], capture_output=True, text=True, timeout=5)

            if result.returncode == 0 and "Modem/" in result.stdout:
                # Extract modem path (e.g., /org/freedesktop/ModemManager1/Modem/0)
                match = re.search(r"/org/freedesktop/ModemManager1/Modem/\d+", result.stdout)
                if match:
                    self._modem_path = match.group(0)
                    logger.info(f"USB modem detected at {self._modem_path}")
                    return True

            return False
        except Exception as e:
            logger.debug(f"USB modem detection failed: {e}")
            return False

    def _run_mmcli(self, args: list) -> Optional[str]:
        """Run mmcli command and return output"""
        try:
            result = subprocess.run(["mmcli"] + args, capture_output=True, text=True, timeout=10)
            return result.stdout if result.returncode == 0 else None
        except Exception as e:
            logger.error(f"mmcli command failed: {e}")
            return None

    def get_status(self) -> Dict:
        """Get modem status"""
        if not self.is_available or not self._modem_path:
            return {
                "available": False,
                "status": ModemStatus.UNAVAILABLE,
                "modem_info": None,
                "network_info": None,
                "error": "USB modem not detected or ModemManager not available",
            }

        modem_info = self.get_modem_info()
        network_info = self.get_network_info()

        return {
            "available": True,
            "status": ModemStatus.CONNECTED if network_info else ModemStatus.DISCONNECTED,
            "modem_info": modem_info,
            "network_info": network_info,
            "error": None,
        }

    def connect(self) -> Dict:
        """Activate modem connection"""
        if not self._modem_path:
            return {"success": False, "message": "Modem not detected", "network_info": None}

        try:
            # Enable modem
            output = self._run_mmcli(["-m", self._modem_path.split("/")[-1], "--enable"])
            if output:
                return {"success": True, "message": "Modem enabled", "network_info": self.get_network_info()}
            return {"success": False, "message": "Failed to enable modem", "network_info": None}
        except Exception as e:
            return {"success": False, "message": str(e), "network_info": None}

    def disconnect(self) -> Dict:
        """Deactivate modem connection"""
        if not self._modem_path:
            return {"success": False, "message": "Modem not detected"}

        try:
            # Disable modem
            output = self._run_mmcli(["-m", self._modem_path.split("/")[-1], "--disable"])
            if output:
                return {"success": True, "message": "Modem disabled"}
            return {"success": False, "message": "Failed to disable modem"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_modem_info(self) -> Optional[ModemInfo]:
        """Get modem hardware information"""
        if not self._modem_path:
            return None

        try:
            modem_id = self._modem_path.split("/")[-1]
            output = self._run_mmcli(["-m", modem_id])
            if not output:
                return None

            # Parse mmcli output
            manufacturer = ""
            model = ""
            imei = ""
            imsi = ""

            for line in output.split("\n"):
                if "manufacturer:" in line.lower():
                    manufacturer = line.split(":", 1)[1].strip()
                elif "model:" in line.lower():
                    model = line.split(":", 1)[1].strip()
                elif "imei:" in line.lower():
                    imei = line.split(":", 1)[1].strip()
                elif "imsi:" in line.lower():
                    imsi = line.split(":", 1)[1].strip()

            return ModemInfo(
                name=f"{manufacturer} {model}", model=model, imei=imei, imsi=imsi, manufacturer=manufacturer
            )
        except Exception as e:
            logger.error(f"Failed to get modem info: {e}")
            return None

    def get_network_info(self) -> Optional[NetworkInfo]:
        """Get network connection information"""
        if not self._modem_path:
            return None

        try:
            modem_id = self._modem_path.split("/")[-1]
            output = self._run_mmcli(["-m", modem_id])
            if not output:
                return None

            # Parse modem status
            status = ModemStatus.DISCONNECTED
            signal_strength = 0
            network_type = ""
            operator = ""

            for line in output.split("\n"):
                if "state:" in line.lower():
                    if "connected" in line.lower():
                        status = ModemStatus.CONNECTED
                    elif "connecting" in line.lower():
                        status = ModemStatus.CONNECTING

                if "signal quality:" in line.lower():
                    match = re.search(r"(\d+)%", line)
                    if match:
                        signal_strength = int(match.group(1))

                if "access tech:" in line.lower():
                    network_type = line.split(":", 1)[1].strip()

                if "operator name:" in line.lower():
                    operator = line.split(":", 1)[1].strip()

            return NetworkInfo(
                status=status,
                signal_strength=signal_strength,
                network_type=network_type,
                operator=operator,
                ip_address=None,
                dns_servers=[],
                data_uploaded=0,
                data_downloaded=0,
            )
        except Exception as e:
            logger.error(f"Failed to get network info: {e}")
            return None

    def configure_band(self, band_mask: int) -> Dict:
        """Configure LTE band preference"""
        return {"success": False, "message": "Band configuration via ModemManager not implemented yet"}

    def reboot(self) -> Dict:
        """Reboot the modem"""
        if not self._modem_path:
            return {"success": False, "message": "Modem not detected"}

        try:
            modem_id = self._modem_path.split("/")[-1]
            output = self._run_mmcli(["-m", modem_id, "--reset"])
            if output:
                return {"success": True, "message": "Modem reset initiated"}
            return {"success": False, "message": "Failed to reset modem"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_info(self) -> Dict:
        """Get provider information"""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": "Generic USB dongle modem via ModemManager",
            "features": [
                "ModemManager integration",
                "Works with most USB modems",
                "Basic modem control",
                "Signal monitoring",
            ],
            "modes": ["USB dongle"],
            "requirements": ["ModemManager (mmcli)"],
        }
