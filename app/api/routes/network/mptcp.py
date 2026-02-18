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

import subprocess
from fastapi import APIRouter, HTTPException
from app.utils.logger import get_logger

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
            proc = subprocess.run(["sysctl", "-n", "net.mptcp.enabled"], capture_output=True, text=True, timeout=5)
            if proc.returncode == 0:
                result["kernel_support"] = True
                result["enabled"] = proc.stdout.strip() == "1"
                result["available"] = True
        except Exception:
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
                    proc = subprocess.run(
                        ["sysctl", "-n", f"net.mptcp.{param}"], capture_output=True, text=True, timeout=5
                    )
                    if proc.returncode == 0:
                        result[param] = proc.stdout.strip()
                except Exception:
                    pass

            # Check number of subflows
            try:
                proc = subprocess.run(["ip", "mptcp", "limits", "show"], capture_output=True, text=True, timeout=5)
                if proc.returncode == 0:
                    result["subflow_limits"] = proc.stdout.strip()
            except Exception:
                pass

        return {"success": True, **result}

    except Exception as e:
        logger.error(f"Error getting MPTCP status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mptcp/enable")
async def enable_mptcp():
    """
    Enable MPTCP in the kernel.

    Sets net.mptcp.enabled=1 and configures default subflow limits.
    Requires kernel 5.6+ with MPTCP support.
    """
    try:
        # Enable MPTCP
        proc = subprocess.run(["sysctl", "-w", "net.mptcp.enabled=1"], capture_output=True, text=True, timeout=5)
        if proc.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Failed to enable MPTCP: {proc.stderr}")

        # Set reasonable defaults for streaming
        limits_proc = subprocess.run(
            ["ip", "mptcp", "limits", "set", "subflow", "2", "add_addr_accepted", "2"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if limits_proc.returncode != 0:
            logger.warning(f"Failed to set MPTCP limits: {limits_proc.stderr}")

        return {"success": True, "message": "MPTCP enabled"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enabling MPTCP: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mptcp/disable")
async def disable_mptcp():
    """Disable MPTCP"""
    try:
        proc = subprocess.run(["sysctl", "-w", "net.mptcp.enabled=0"], capture_output=True, text=True, timeout=5)
        if proc.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Failed to disable MPTCP: {proc.stderr}")

        return {"success": True, "message": "MPTCP disabled"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disabling MPTCP: {e}")
        raise HTTPException(status_code=500, detail=str(e))
