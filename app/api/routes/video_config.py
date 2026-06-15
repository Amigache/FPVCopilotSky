"""Video configuration routes"""

import logging

from fastapi import APIRouter, HTTPException, Request

from app.api.models.video_models import (
    LivePropertyRequest,
    StreamingConfigRequest,
    VideoConfigRequest,
)
from app.i18n import get_language_from_request, translate
from app.services.preferences import get_preferences

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video", tags=["video"])

# Service reference (set by main module)
_video_service = None


def set_video_service(service):
    """Set the video service instance"""
    global _video_service
    _video_service = service


@router.post("/config/video")
async def configure_video(config: VideoConfigRequest, request: Request):
    """Update video configuration"""
    lang = get_language_from_request(request)
    if not _video_service:
        raise HTTPException(
            status_code=503,
            detail=translate("services.video_not_initialized", lang),
        )

    # Convert to dict, excluding None values
    config_dict = {k: v for k, v in config.model_dump().items() if v is not None}

    if not config_dict:
        raise HTTPException(status_code=400, detail="No configuration provided")

    # Separate identity fields from GStreamer config
    identity_fields = {}
    for field in ("device_name", "device_bus_info"):
        if field in config_dict:
            identity_fields[field] = config_dict.pop(field)

    try:
        _video_service.configure(video_config=config_dict)
    except (AttributeError, TypeError, RuntimeError, ValueError, KeyError) as e:
        logger.error(
            f"Video service error in configure_video: {type(e).__name__}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to update video configuration")

    # Save to preferences (including identity fields for smart matching)
    try:
        prefs = get_preferences()
        current = prefs.get_video_config()
        current.update(config_dict)

        # If identity fields were provided, save them
        if identity_fields:
            current.update(identity_fields)
        elif "device" in config_dict:
            # Auto-detect identity from the device path if not provided by frontend
            try:
                from app.services.video_config import get_device_identity

                identity = get_device_identity(config_dict["device"])
                if identity:
                    current["device_name"] = identity.get("name", "")
                    current["device_bus_info"] = identity.get("bus_info", "")
                    logger.info(
                        "Camera identity saved",
                        extra={
                            "camera_name": identity.get("name"),
                            "bus_info": identity.get("bus_info"),
                        },
                    )
            except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as e:
                logger.warning("Failed to detect camera identity", extra={"error": str(e)})

        prefs.set_video_config(current)

        # Verify the save
        saved = prefs.get_video_config()
        if "device" in config_dict and saved.get("device") == config_dict["device"]:
            logger.debug(
                "Video device preference verified",
                extra={"device": saved.get("device")},
            )
        elif "width" in config_dict and saved.get("width") == config_dict["width"]:
            logger.debug(
                "Video config preference verified",
                extra={
                    "width": config_dict["width"],
                    "height": config_dict.get("height"),
                },
            )
    except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as e:
        logger.error("Failed to save video config", extra={"error": str(e)})

    return {
        "success": True,
        "message": translate("video.configuration_updated", lang),
        "config": config_dict,
    }


@router.post("/config/streaming")
async def configure_streaming(config: StreamingConfigRequest, request: Request):
    """Update streaming configuration"""
    lang = get_language_from_request(request)
    if not _video_service:
        raise HTTPException(
            status_code=503,
            detail=translate("services.video_not_initialized", lang),
        )

    # Convert to dict, excluding None values
    config_dict = {k: v for k, v in config.model_dump().items() if v is not None}

    if not config_dict:
        raise HTTPException(status_code=400, detail="No configuration provided")

    # Update video service
    try:
        _video_service.configure(streaming_config=config_dict)
    except (AttributeError, TypeError, ValueError, RuntimeError, KeyError) as e:
        logger.error(
            "Error updating streaming config (%s): %s",
            type(e).__name__,
            e,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to update streaming configuration")

    # Save to preferences
    try:
        prefs = get_preferences()
        current = prefs.get_streaming_config()
        current.update(config_dict)
        prefs.set_streaming_config(current)

        # Verify the save
        saved = prefs.get_streaming_config()
        if saved.get("auto_start") == config_dict.get("auto_start", saved.get("auto_start")):
            logger.debug(
                "Streaming auto_start preference verified",
                extra={"auto_start": saved.get("auto_start")},
            )
        else:
            logger.warning("Streaming preference save verification failed")
    except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as e:
        logger.error("Failed to save streaming config", extra={"error": str(e)})

    return {
        "success": True,
        "message": translate("video.streaming_configuration_updated", lang),
        "config": config_dict,
    }


@router.post("/live-update")
async def live_update(req: LivePropertyRequest, request: Request):
    """Update a pipeline property on-the-fly without restarting.
    Only quality (MJPEG) or h264_bitrate (H.264) are allowed."""
    lang = get_language_from_request(request)
    if not _video_service:
        raise HTTPException(
            status_code=503,
            detail=translate("services.video_not_initialized", lang),
        )

    try:
        result = _video_service.update_live_property(req.property, req.value)
    except (AttributeError, TypeError, ValueError, RuntimeError, KeyError) as e:
        logger.error("Error applying live update (%s): %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to apply live update")

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    # Save to preferences
    try:
        prefs = get_preferences()
        current = prefs.get_video_config()
        current[req.property] = req.value
        prefs.set_video_config(current)
    except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as e:
        logger.warning(
            "Failed to save live update preference",
            extra={"property": req.property, "error": str(e)},
        )

    return result
