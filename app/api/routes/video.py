"""
Video Streaming API Routes
Endpoints for controlling GStreamer video streaming
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/video", tags=["video"])

# Service reference (will be set by main.py)
_video_service = None


def set_video_service(service):
    """Set the video service instance"""
    global _video_service
    _video_service = service


class VideoConfigRequest(BaseModel):
    """Video configuration request"""
    device: Optional[str] = None
    device_name: Optional[str] = None
    device_bus_info: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    framerate: Optional[int] = None
    codec: Optional[str] = None
    quality: Optional[int] = None
    h264_bitrate: Optional[int] = None


class LivePropertyRequest(BaseModel):
    """Live property change request (no pipeline restart)"""
    property: str
    value: int


class StreamingConfigRequest(BaseModel):
    """Streaming configuration request"""
    udp_host: Optional[str] = None
    udp_port: Optional[int] = None
    enabled: Optional[bool] = None
    auto_start: Optional[bool] = None


@router.get("/status")
async def get_status():
    """Get video streaming status"""
    if not _video_service:
        raise HTTPException(status_code=503, detail="Video service not initialized")
    
    return _video_service.get_status()


@router.get("/cameras")
async def get_cameras():
    """Get available cameras"""
    if not _video_service:
        raise HTTPException(status_code=503, detail="Video service not initialized")
    
    return {"cameras": _video_service.get_cameras()}


@router.post("/start")
async def start_streaming():
    """Start video streaming"""
    if not _video_service:
        raise HTTPException(status_code=503, detail="Video service not initialized")
    
    result = _video_service.start()
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    
    return result


@router.post("/stop")
async def stop_streaming():
    """Stop video streaming"""
    if not _video_service:
        raise HTTPException(status_code=503, detail="Video service not initialized")
    
    result = _video_service.stop()
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    
    return result


@router.post("/restart")
async def restart_streaming():
    """Restart video streaming with current configuration"""
    if not _video_service:
        raise HTTPException(status_code=503, detail="Video service not initialized")
    
    result = _video_service.restart()
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    
    return result


@router.post("/config/video")
async def configure_video(config: VideoConfigRequest):
    """Update video configuration"""
    if not _video_service:
        raise HTTPException(status_code=503, detail="Video service not initialized")
    
    # Convert to dict, excluding None values
    config_dict = {k: v for k, v in config.model_dump().items() if v is not None}
    
    if not config_dict:
        raise HTTPException(status_code=400, detail="No configuration provided")
    
    # Separate identity fields from GStreamer config
    identity_fields = {}
    for field in ("device_name", "device_bus_info"):
        if field in config_dict:
            identity_fields[field] = config_dict.pop(field)
    
    _video_service.configure(video_config=config_dict)
    
    # Save to preferences (including identity fields for smart matching)
    try:
        from services.preferences import get_preferences
        prefs = get_preferences()
        current = prefs.get_video_config()
        current.update(config_dict)
        
        # If identity fields were provided, save them
        if identity_fields:
            current.update(identity_fields)
        elif "device" in config_dict:
            # Auto-detect identity from the device path if not provided by frontend
            try:
                from services.video_config import get_device_identity
                identity = get_device_identity(config_dict["device"])
                if identity:
                    current["device_name"] = identity.get("name", "")
                    current["device_bus_info"] = identity.get("bus_info", "")
                    print(f"📹 Saved camera identity: {identity.get('name')} ({identity.get('bus_info', 'N/A')})")
            except Exception as e:
                print(f"⚠️ Failed to detect camera identity: {e}")
        
        prefs.set_video_config(current)
    except Exception as e:
        print(f"⚠️ Failed to save video config: {e}")
    
    return {"success": True, "message": "Video configuration updated", "config": config_dict}


@router.post("/config/streaming")
async def configure_streaming(config: StreamingConfigRequest):
    """Update streaming configuration"""
    if not _video_service:
        raise HTTPException(status_code=503, detail="Video service not initialized")
    
    # Convert to dict, excluding None values
    config_dict = {k: v for k, v in config.model_dump().items() if v is not None}
    
    if not config_dict:
        raise HTTPException(status_code=400, detail="No configuration provided")
    
    _video_service.configure(streaming_config=config_dict)
    
    # Save to preferences
    try:
        from services.preferences import get_preferences
        prefs = get_preferences()
        current = prefs.get_streaming_config()
        current.update(config_dict)
        prefs.set_streaming_config(current)
    except Exception as e:
        print(f"⚠️ Failed to save streaming config: {e}")
    
    return {"success": True, "message": "Streaming configuration updated", "config": config_dict}


@router.post("/live-update")
async def live_update(req: LivePropertyRequest):
    """Update a pipeline property on-the-fly without restarting.
    Only quality (MJPEG) or h264_bitrate (H.264) are allowed."""
    if not _video_service:
        raise HTTPException(status_code=503, detail="Video service not initialized")
    
    result = _video_service.update_live_property(req.property, req.value)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    
    # Save to preferences
    try:
        from services.preferences import get_preferences
        prefs = get_preferences()
        current = prefs.get_video_config()
        current[req.property] = req.value
        prefs.set_video_config(current)
    except Exception as e:
        print(f"⚠️ Failed to save live update: {e}")
    
    return result


@router.get("/pipeline-string")
async def get_pipeline_string():
    """Get GStreamer pipeline string for Mission Planner"""
    if not _video_service:
        raise HTTPException(status_code=503, detail="Video service not initialized")
    
    return {
        "pipeline": _video_service.get_pipeline_string(),
        "codec": _video_service.video_config.codec,
        "port": _video_service.streaming_config.udp_port
    }
