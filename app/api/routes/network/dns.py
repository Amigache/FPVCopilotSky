"""
DNS Caching - Local DNS Cache Management

This module provides endpoints for managing the local DNS cache (dnsmasq),
which reduces DNS lookup latency and improves overall network performance.

Features:
- Start/stop DNS caching service
- Cache statistics and status
- Manual cache clearing
- Package installation
"""

from fastapi import APIRouter, HTTPException
from app.services.dns_cache import get_dns_cache
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/dns/status")
async def get_dns_cache_status():
    """Get DNS cache status and statistics"""
    try:
        dns_cache = get_dns_cache()
        status = await dns_cache.get_status()

        return {"success": True, **status}

    except Exception as e:
        logger.error(f"Error getting DNS cache status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dns/start")
async def start_dns_cache():
    """Start DNS caching service (dnsmasq)"""
    try:
        dns_cache = get_dns_cache()
        success = await dns_cache.start()

        if success:
            return {"success": True, "message": "DNS caching started", "cache_size": dns_cache.config.cache_size}
        else:
            raise HTTPException(status_code=500, detail="Failed to start DNS cache")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting DNS cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dns/stop")
async def stop_dns_cache():
    """Stop DNS caching service"""
    try:
        dns_cache = get_dns_cache()
        success = await dns_cache.stop()

        if success:
            return {"success": True, "message": "DNS caching stopped"}
        else:
            raise HTTPException(status_code=500, detail="Failed to stop DNS cache")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping DNS cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dns/clear")
async def clear_dns_cache():
    """Clear DNS cache"""
    try:
        dns_cache = get_dns_cache()
        success = await dns_cache.clear_cache()

        if success:
            return {"success": True, "message": "DNS cache cleared"}
        else:
            raise HTTPException(status_code=500, detail="Failed to clear DNS cache")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing DNS cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dns/install")
async def install_dns_cache():
    """Install dnsmasq package"""
    try:
        dns_cache = get_dns_cache()

        # Check if already installed
        if await dns_cache.is_installed():
            return {"success": True, "message": "dnsmasq already installed", "already_installed": True}

        success = await dns_cache.install()

        if success:
            return {"success": True, "message": "dnsmasq installed successfully", "already_installed": False}
        else:
            raise HTTPException(status_code=500, detail="Failed to install dnsmasq")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error installing DNS cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))
