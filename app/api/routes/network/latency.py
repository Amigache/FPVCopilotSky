"""
Latency Monitoring - Real-time Network Performance Tracking

This module provides endpoints for continuous latency monitoring across
multiple network interfaces and targets, enabling network quality assessment
and failover decisions.

Features:
- Continuous monitoring with configurable targets
- Per-interface latency statistics
- Historical data tracking
- Manual latency testing
"""

import time
from typing import Optional
from fastapi import APIRouter, HTTPException
from app.services.latency_monitor import get_latency_monitor, start_latency_monitoring, stop_latency_monitoring
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post("/latency/start")
async def start_latency_monitor():
    """Start continuous latency monitoring"""
    try:
        await start_latency_monitoring()
        return {"success": True, "message": "Latency monitoring started"}
    except Exception as e:
        logger.error(f"Error starting latency monitor: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/latency/stop")
async def stop_latency_monitor():
    """Stop continuous latency monitoring"""
    try:
        await stop_latency_monitoring()
        return {"success": True, "message": "Latency monitoring stopped"}
    except Exception as e:
        logger.error(f"Error stopping latency monitor: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latency/current")
async def get_current_latency():
    """
    Get current latency statistics for all monitored targets

    Returns average, min, max latency and packet loss for each target
    """
    try:
        monitor = get_latency_monitor()
        stats = await monitor.get_current_latency()

        # Convert LatencyStats objects to dicts
        stats_dict = {}
        for target, stat in stats.items():
            stats_dict[target] = {
                "target": stat.target,
                "interface": stat.interface,
                "avg_latency_ms": round(stat.avg_latency, 2),
                "min_latency_ms": round(stat.min_latency, 2),
                "max_latency_ms": round(stat.max_latency, 2),
                "packet_loss_percent": round(stat.packet_loss, 2),
                "sample_count": stat.sample_count,
                "last_update": stat.last_update,
            }

        return {"success": True, "latency": stats_dict, "timestamp": time.time()}

    except Exception as e:
        logger.error(f"Error getting current latency: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latency/history")
async def get_latency_history(target: Optional[str] = None, last_n: int = 30):
    """
    Get historical latency data

    Args:
        target: Specific target to query (None for all)
        last_n: Number of recent samples to return
    """
    try:
        monitor = get_latency_monitor()
        history = monitor.get_history(target=target, last_n=last_n)

        # Convert to serializable format
        history_dict = {}
        for t, results in history.items():
            history_dict[t] = [
                {
                    "target": r.target,
                    "latency_ms": r.latency_ms,
                    "timestamp": r.timestamp,
                    "success": r.success,
                    "interface": r.interface,
                }
                for r in results
            ]

        return {"success": True, "history": history_dict, "sample_count": sum(len(v) for v in history_dict.values())}

    except Exception as e:
        logger.error(f"Error getting latency history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latency/interface/{interface}")
async def get_interface_latency(interface: str):
    """
    Get latency statistics for a specific network interface

    Args:
        interface: Network interface name (e.g., wlan0, enx...)
    """
    try:
        monitor = get_latency_monitor()
        stat = await monitor.get_interface_latency(interface)

        if not stat:
            return {"success": True, "available": False, "message": "No latency data available for this interface"}

        return {
            "success": True,
            "available": True,
            "interface": interface,
            "latency": {
                "avg_ms": round(stat.avg_latency, 2),
                "min_ms": round(stat.min_latency, 2),
                "max_ms": round(stat.max_latency, 2),
                "packet_loss_percent": round(stat.packet_loss, 2),
                "sample_count": stat.sample_count,
                "last_update": stat.last_update,
            },
        }

    except Exception as e:
        logger.error(f"Error getting interface latency: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/latency/test/{interface}")
async def test_interface_latency(interface: str, count: int = 3):
    """
    Perform one-time latency test for an interface

    Args:
        interface: Network interface to test
        count: Number of pings per target (default: 3)
    """
    try:
        monitor = get_latency_monitor()
        stat = await monitor.test_interface_latency(interface, count)

        return {
            "success": True,
            "interface": interface,
            "test_results": {
                "avg_ms": round(stat.avg_latency, 2),
                "min_ms": round(stat.min_latency, 2),
                "max_ms": round(stat.max_latency, 2),
                "packet_loss_percent": round(stat.packet_loss, 2),
                "samples": stat.sample_count,
                "targets_tested": len(monitor.targets),
            },
        }

    except Exception as e:
        logger.error(f"Error testing interface latency: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/latency/history")
async def clear_latency_history():
    """Clear all latency history"""
    try:
        monitor = get_latency_monitor()
        monitor.clear_history()
        return {"success": True, "message": "Latency history cleared"}
    except Exception as e:
        logger.error(f"Error clearing latency history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
