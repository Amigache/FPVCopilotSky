"""
Common utilities and models for network routes
Shared helper functions and Pydantic models
"""

from pydantic import BaseModel
from typing import Optional, List
import asyncio
import logging
import re

logger = logging.getLogger(__name__)


# =============================
# Pydantic Models
# =============================


class WiFiConnectRequest(BaseModel):
    """WiFi connection request model"""

    ssid: str
    password: Optional[str] = None


class PriorityModeRequest(BaseModel):
    """Network priority mode request"""

    mode: str  # 'wifi', 'modem', or 'auto'


class ForgetConnectionRequest(BaseModel):
    """Forget connection request"""

    name: str


# =============================
# Helper Functions
# =============================


async def run_command(cmd: List[str], timeout: float = 30) -> tuple:
    """Run a command asynchronously and return stdout, stderr, returncode

    Args:
        cmd: Command and arguments to execute
        timeout: Maximum seconds to wait for the command (default: 30)
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return stdout.decode().strip(), stderr.decode().strip(), proc.returncode
    except asyncio.TimeoutError:
        logger.error(f"Command {cmd} timed out after {timeout}s")
        try:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass
        return "", f"Command timed out after {timeout}s", -1
    except Exception as e:
        logger.error(f"Error running command {cmd}: {e}")
        return "", str(e), -1


async def detect_wifi_interface() -> Optional[str]:
    """Detect WiFi interface using nmcli"""
    stdout, _, returncode = await run_command(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device"])
    if returncode == 0:
        for line in stdout.split("\n"):
            if ":wifi:" in line:
                parts = line.split(":")
                if len(parts) >= 1:
                    return parts[0]
    return None


async def detect_modem_interfaces() -> List[str]:
    """Detect ALL USB 4G modem interfaces (looks for 192.168.8.x IP)"""
    modems = []
    stdout, _, returncode = await run_command(["ip", "-o", "addr", "show"])
    if returncode == 0:
        for line in stdout.split("\n"):
            if "192.168.8." in line:
                match = re.search(r"^\d+:\s+(\S+)\s+inet\s+192\.168\.8\.", line)
                if match:
                    iface = match.group(1)
                    if iface not in modems:
                        modems.append(iface)
    return modems


async def detect_modem_interface() -> Optional[str]:
    """Detect first USB 4G modem interface (backward compatibility)"""
    modems = await detect_modem_interfaces()
    return modems[0] if modems else None


async def get_gateway_for_interface(interface: str) -> Optional[str]:
    """Get gateway for a specific interface"""
    stdout, _, returncode = await run_command(["ip", "route", "show", "dev", interface])
    if returncode == 0:
        for line in stdout.split("\n"):
            if "default" in line or line.startswith("default"):
                match = re.search(r"via\s+(\d+\.\d+\.\d+\.\d+)", line)
                if match:
                    return match.group(1)
        # Fallback: try to infer gateway from interface IP
        match = re.search(r"inet\s+(\d+\.\d+\.\d+)\.\d+", stdout)
        if match:
            return f"{match.group(1)}.1"
    return None
