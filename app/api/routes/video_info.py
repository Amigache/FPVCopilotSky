"""Video streaming information routes"""

import logging

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


@router.get("/pipeline-string")
async def get_pipeline_string(request: Request):
    """Get GStreamer pipeline string for Mission Planner"""
    lang = get_language_from_request(request)
    if not _video_service:
        raise HTTPException(
            status_code=503,
            detail=translate("services.video_not_initialized", lang),
        )

    return {
        "pipeline": _video_service.get_pipeline_string(),
        "codec": _video_service.video_config.codec,
        "port": _video_service.streaming_config.udp_port,
        "mode": _video_service.streaming_config.mode,
    }


@router.get("/pipeline-strings")
async def get_pipeline_strings(request: Request):
    """Get GStreamer receive pipeline strings for every supported client mode.

    Returns ready-to-paste pipeline strings for UDP unicast, multicast, and
    RTSP so that Mission Planner / QGC users can quickly connect regardless
    of the active streaming mode.
    """
    lang = get_language_from_request(request)
    if not _video_service:
        raise HTTPException(
            status_code=503,
            detail=translate("services.video_not_initialized", lang),
        )

    return _video_service.get_client_pipeline_strings()


@router.get("/network/ip")
async def get_network_ip(request: Request):
    """Get current network IP address for streaming"""
    lang = get_language_from_request(request)
    if not _video_service:
        raise HTTPException(
            status_code=503,
            detail=translate("services.video_not_initialized", lang),
        )

    ip = _video_service._get_streaming_ip()

    return {
        "ip": ip,
        "rtsp_url": f"rtsp://{ip}:8554/fpv",
    }
