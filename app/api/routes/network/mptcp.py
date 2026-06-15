"""
MPTCP Configuration - Multi-Path TCP Management

This module provides endpoints for managing Multi-Path TCP (MPTCP),
which allows using multiple network interfaces simultaneously for
improved throughput and reliability.

Features:
- Kernel support detection
- Enable/disable MPTCP
- Configure subflow limits
- Status monitoring
"""

from fastapi import APIRouter, HTTPException
from app.utils.logger import get_logger
from app.utils.cmd import run_cmd
from app.exceptions import NetworkCommandError

logger = get_logger(__name__)
router = APIRouter()


@router.get("/mptcp/status")
async def get_mptcp_status():
    """
    Get MPTCP (Multi-Path TCP) status.

    Checks if kernel supports MPTCP, current enabled state,
    and available subflow configuration.
    """
    try:
        result = {"available": False, "enabled": False, "kernel_support": False}

        # Check kernel support
        try:
            stdout, _, returncode = run_cmd(["sysctl", "-n", "net.mptcp.enabled"], timeout=5, check=False)
            if returncode == 0:
                result["kernel_support"] = True
                result["enabled"] = stdout.strip() == "1"
                result["available"] = True
        except NetworkCommandError:
            # Kernel doesn't support MPTCP
            pass

        # Get MPTCP settings
        if result["kernel_support"]:
            for param in [
                "add_addr_timeout",
                "allow_join_initial_addr_once",
                "checksum_enabled",
                "pm_type",
                "stale_loss_cnt",
            ]:
                try:
                    stdout, _, returncode = run_cmd(["sysctl", "-n", f"net.mptcp.{param}"], timeout=5, check=False)
                    if returncode == 0:
                        result[param] = stdout.strip()
                except NetworkCommandError:
                    pass

            # Check number of subflows
            try:
                stdout, _, returncode = run_cmd(["ip", "mptcp", "limits", "show"], timeout=5, check=False)
                if returncode == 0:
                    result["subflow_limits"] = stdout.strip()
            except NetworkCommandError:
                pass

        return {"success": True, **result}

    except NetworkCommandError as e:
        logger.warning("MPTCP not available on this kernel", extra=e.to_dict())
        return {"success": True, "available": False, "enabled": False, "kernel_support": False}


@router.post("/mptcp/enable")
async def enable_mptcp():
    """
    Enable MPTCP in the kernel.

    Sets net.mptcp.enabled=1 and configures default subflow limits.
    Requires kernel 5.6+ with MPTCP support.
    """
    try:
        # Enable MPTCP
        _, stderr, returncode = run_cmd(["sysctl", "-w", "net.mptcp.enabled=1"], timeout=5, check=False)
        if returncode != 0:
            raise NetworkCommandError("sysctl", returncode, stderr)

        # Set reasonable defaults for streaming
        _, limits_stderr, limits_returncode = run_cmd(
            ["ip", "mptcp", "limits", "set", "subflow", "2", "add_addr_accepted", "2"],
            timeout=5,
            check=False,
        )
        if limits_returncode != 0:
            logger.warning(
                "MPTCP limits may not be optimal", extra={"command": "ip mptcp limits", "stderr": limits_stderr}
            )

        return {"success": True, "message": "MPTCP enabled"}

    except NetworkCommandError as e:
        logger.error("Failed to enable MPTCP", extra=e.to_dict())
        raise HTTPException(status_code=500, detail="Could not enable MPTCP")


@router.post("/mptcp/disable")
async def disable_mptcp():
    """Disable MPTCP"""
    try:
        _, stderr, returncode = run_cmd(["sysctl", "-w", "net.mptcp.enabled=0"], timeout=5, check=False)
        if returncode != 0:
            raise NetworkCommandError("sysctl", returncode, stderr)

        return {"success": True, "message": "MPTCP disabled"}

    except NetworkCommandError as e:
        logger.error("Failed to disable MPTCP", extra=e.to_dict())
        raise HTTPException(status_code=500, detail="Could not disable MPTCP")
