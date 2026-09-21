"""
Experimental API Routes
Endpoints for testing experimental features like OpenCV video processing
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import logging

from app.exceptions import ServiceInitError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/experimental", tags=["experimental"])

# Service instance (injected from main.py)
_opencv_service = None


def set_opencv_service(service):
    """Inject OpenCV service instance"""
    global _opencv_service
    _opencv_service = service


class ToggleRequest(BaseModel):
    enabled: bool


class ConfigUpdateRequest(BaseModel):
    filter: str = "none"
    osd_enabled: bool = False
    edgeThreshold1: int = 100
    edgeThreshold2: int = 200
    blurKernel: int = 15
    thresholdValue: int = 127


@router.get("/config")
async def get_config():
    """Get current OpenCV configuration"""
    try:
        if _opencv_service is None:
            return JSONResponse(
                content={
                    "success": False,
                    "message": "OpenCV service not initialized",
                    "opencv_enabled": False,
                    "config": {},
                },
                status_code=503,
            )

        status = _opencv_service.get_status()
        return {"success": True, "opencv_enabled": status["opencv_enabled"], "config": status["config"]}
    except (KeyError, TypeError, ValueError) as e:
        logger.error("Error getting OpenCV config (%s): %s", type(e).__name__, e)
        raise HTTPException(status_code=500, detail="Could not retrieve OpenCV configuration")
    except ServiceInitError as e:
        logger.error("OpenCV service error", extra=e.to_dict())
        raise HTTPException(status_code=503, detail="OpenCV service unavailable")


@router.post("/toggle")
async def toggle_opencv(request: ToggleRequest):
    """Enable or disable OpenCV processing"""
    try:
        if _opencv_service is None:
            return JSONResponse(
                content={"success": False, "message": "OpenCV service not initialized"}, status_code=503
            )

        enabled = _opencv_service.set_enabled(request.enabled)

        return {
            "success": True,
            "opencv_enabled": enabled,
            "message": f"OpenCV processing {'enabled' if enabled else 'disabled'}",
        }
    except (KeyError, TypeError, ValueError) as e:
        logger.error("Error toggling OpenCV (%s): %s", type(e).__name__, e)
        raise HTTPException(status_code=500, detail="Could not toggle OpenCV")
    except ServiceInitError as e:
        logger.error("OpenCV service error", extra=e.to_dict())
        raise HTTPException(status_code=503, detail="OpenCV service unavailable")


@router.post("/config")
async def update_config(request: ConfigUpdateRequest):
    """Update OpenCV configuration"""
    try:
        if _opencv_service is None:
            return JSONResponse(
                content={"success": False, "message": "OpenCV service not initialized"}, status_code=503
            )

        config_dict = request.model_dump()
        updated_config = _opencv_service.update_config(config_dict)

        return {"success": True, "config": updated_config, "message": "Configuration updated successfully"}
    except (KeyError, TypeError, ValueError) as e:
        logger.error("Error updating OpenCV config (%s): %s", type(e).__name__, e)
        raise HTTPException(status_code=500, detail="Could not update OpenCV configuration")
    except ServiceInitError as e:
        logger.error("OpenCV service error", extra=e.to_dict())
        raise HTTPException(status_code=503, detail="OpenCV service unavailable")


@router.get("/status")
async def get_status():
    """Get OpenCV processing status and info"""
    try:
        if _opencv_service is None:
            return {"success": False, "message": "OpenCV service not initialized", "opencv_available": False}

        status = _opencv_service.get_status()
        return {"success": True, "opencv_available": True, **status}
    except (KeyError, TypeError, ValueError) as e:
        logger.error("Error getting OpenCV status (%s): %s", type(e).__name__, e)
        raise HTTPException(status_code=500, detail="Could not retrieve OpenCV status")
    except ServiceInitError as e:
        logger.error("OpenCV service error", extra=e.to_dict())
        raise HTTPException(status_code=503, detail="OpenCV service unavailable")
