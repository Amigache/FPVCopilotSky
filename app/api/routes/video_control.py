"""Video streaming control routes"""

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


@router.post("/start")
async def start_streaming(request: Request):
    """Start video streaming"""
    lang = get_language_from_request(request)
    if not _video_service:
        raise HTTPException(
            status_code=503,
            detail=translate("services.video_not_initialized", lang),
        )

    try:
        result = _video_service.start()
    except (AttributeError, TypeError, RuntimeError, ValueError, KeyError) as e:
        logger.error(
            f"Video service error in start_streaming: {type(e).__name__}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to start video streaming")

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.post("/stop")
async def stop_streaming(request: Request):
    """Stop video streaming"""
    lang = get_language_from_request(request)
    if not _video_service:
        raise HTTPException(
            status_code=503,
            detail=translate("services.video_not_initialized", lang),
        )

    try:
        result = _video_service.stop()
    except (AttributeError, TypeError, RuntimeError, ValueError, KeyError) as e:
        logger.error(
            f"Video service error in stop_streaming: {type(e).__name__}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to stop video streaming")

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.post("/restart")
async def restart_streaming(request: Request):
    """Restart video streaming with current configuration"""
    lang = get_language_from_request(request)
    if not _video_service:
        raise HTTPException(
            status_code=503,
            detail=translate("services.video_not_initialized", lang),
        )

    try:
        result = _video_service.restart()
    except (AttributeError, TypeError, RuntimeError, ValueError, KeyError) as e:
        logger.error(
            f"Video service error in restart_streaming: {type(e).__name__}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to restart video streaming")

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return result
