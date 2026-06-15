"""Video status and discovery routes (read-only)"""

import logging
import time

from fastapi import APIRouter, HTTPException, Request

from app.i18n import get_language_from_request, translate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video", tags=["video"])

# Service reference (set by main module)
_video_service = None


def set_video_service(service):
    """Set the video service instance"""
    global _video_service
    _video_service = service


@router.get("/status")
async def get_status(request: Request):
    """Get video streaming status"""
    lang = get_language_from_request(request)
    if not _video_service:
        raise HTTPException(
            status_code=503,
            detail=translate("services.video_not_initialized", lang),
        )

    return _video_service.get_status()


@router.get("/stats")
async def get_stats(request: Request):
    """Get detailed video streaming statistics.

    Returns pipeline counters, encoder-specific metrics (encode time,
    keyframe ratio, frame sizes), and stream health indicators.
    More detailed than the stats section in /status.
    """
    lang = get_language_from_request(request)
    if not _video_service:
        raise HTTPException(
            status_code=503,
            detail=translate("services.video_not_initialized", lang),
        )

    # Thread-safe copy of counters
    with _video_service.stats_lock:
        stats_copy = dict(_video_service.stats)
    encoder_copy = _video_service.encoder_stats.copy()

    uptime = None
    if stats_copy.get("start_time") and _video_service.is_streaming:
        uptime = int(time.time() - stats_copy["start_time"])

    # Derived metrics
    frames_encoded = encoder_copy.get("frames_encoded", 0)
    keyframes = encoder_copy.get("keyframes_sent", 0)
    pframes = encoder_copy.get("pframes_sent", 0)
    keyframe_ratio = round(keyframes / frames_encoded, 4) if frames_encoded > 0 else 0.0
    target_fps = _video_service.video_config.framerate or 30
    fps = stats_copy.get("current_fps", 0)
    fps_pct = round(fps / target_fps * 100, 1) if target_fps else 0

    return {
        "streaming": _video_service.is_streaming,
        "uptime": uptime,
        "pipeline": {
            "frames_sent": stats_copy.get("frames_sent", 0),
            "bytes_sent": stats_copy.get("bytes_sent", 0),
            "bytes_sent_mb": round(stats_copy.get("bytes_sent", 0) / (1024 * 1024), 2),
            "current_fps": fps,
            "target_fps": target_fps,
            "fps_percent": fps_pct,
            "current_bitrate_kbps": stats_copy.get("current_bitrate", 0),
            "errors": stats_copy.get("errors", 0),
        },
        "encoder": {
            "frames_encoded": frames_encoded,
            "avg_encode_time_ms": encoder_copy.get("avg_encode_time_ms", 0.0),
            "max_encode_time_ms": encoder_copy.get("max_encode_time_ms", 0.0),
            "last_frame_size_bytes": encoder_copy.get("last_frame_size_bytes", 0),
            "avg_frame_size_bytes": encoder_copy.get("avg_frame_size_bytes", 0),
            "keyframes_sent": keyframes,
            "pframes_sent": pframes,
            "keyframe_ratio": keyframe_ratio,
            "frames_dropped_pre_encoder": encoder_copy.get("frames_dropped_pre_encoder", 0),
            "frames_dropped_post_encoder": encoder_copy.get("frames_dropped_post_encoder", 0),
        },
        "health": _video_service._calculate_health(stats_copy.get("errors", 0), fps, target_fps),
    }


@router.get("/cameras")
async def get_cameras(request: Request):
    """Get available cameras from all video source providers"""
    lang = get_language_from_request(request)
    if not _video_service:
        raise HTTPException(
            status_code=503,
            detail=translate("services.video_not_initialized", lang),
        )

    try:
        # Import here to avoid circular dependency
        from app.providers.registry import get_provider_registry

        registry = get_provider_registry()
        sources = registry.get_available_video_sources()

        # Format for frontend consumption (maintain compatibility)
        cameras = []
        for source in sources:
            caps = source.get("capabilities", {})
            cameras.append(
                {
                    "device": source["device"],
                    "name": source["name"],
                    "type": caps.get("identity", {}).get("driver", source["type"]),
                    "driver": caps.get("identity", {}).get("driver", "unknown"),
                    "bus_info": caps.get("identity", {}).get("bus_info", ""),
                    "is_usb": caps.get("is_usb", False),
                    "resolutions": caps.get("supported_resolutions", []),
                    "resolutions_fps": caps.get("supported_framerates", {}),
                    "provider": source["provider"],
                }
            )

        return {"cameras": cameras}
    except (AttributeError, KeyError, TypeError) as e:
        logger.error(f"Camera discovery error: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to enumerate cameras")


@router.get("/codecs")
async def get_codecs(request: Request):
    """Get available video codecs/encoders"""
    lang = get_language_from_request(request)
    if not _video_service:
        raise HTTPException(
            status_code=503,
            detail=translate("services.video_not_initialized", lang),
        )

    try:
        # Import here to avoid circular dependency
        from app.providers.registry import get_provider_registry

        registry = get_provider_registry()
        available_encoders = registry.get_available_video_encoders()

        # Format for frontend consumption
        codecs = []
        for encoder in available_encoders:
            if encoder["available"]:  # Only return actually available codecs
                caps = encoder["capabilities"]
                codecs.append(
                    {
                        "id": encoder["codec_id"],
                        "name": encoder["display_name"],
                        "family": encoder["codec_family"],
                        "type": encoder["encoder_type"],
                        "description": caps.get("description", ""),
                        "latency": caps.get("latency_estimate", "medium"),
                        "cpu_usage": caps.get("cpu_usage", "medium"),
                        "default_bitrate": caps.get("default_bitrate", 2000),
                        "min_bitrate": caps.get("min_bitrate", 0),
                        "max_bitrate": caps.get("max_bitrate", 10000),
                        "quality_control": caps.get("quality_control", False),
                        "priority": caps.get("priority", 50),
                    }
                )

        return {"codecs": codecs}
    except (AttributeError, KeyError, TypeError) as e:
        logger.error(f"Encoder discovery error: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to enumerate codecs")
