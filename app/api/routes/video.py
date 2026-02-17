"""
Video Streaming API Routes
Endpoints for controlling GStreamer video streaming
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
import ipaddress
from app.i18n import get_language_from_request, translate
from app.services.preferences import get_preferences

router = APIRouter(prefix="/api/video", tags=["video"])

# Service reference (will be set by main.py)
_video_service = None


def set_video_service(service):
    """Set the video service instance"""
    global _video_service
    _video_service = service


class VideoConfigRequest(BaseModel):
    """Video configuration request with validated ranges"""

    device: Optional[str] = None
    device_name: Optional[str] = None
    device_bus_info: Optional[str] = None
    width: Optional[int] = Field(None, ge=1, le=7680)
    height: Optional[int] = Field(None, ge=1, le=4320)
    framerate: Optional[int] = Field(None, ge=1, le=120)
    codec: Optional[str] = None
    quality: Optional[int] = Field(None, ge=1, le=100)
    h264_bitrate: Optional[int] = Field(None, ge=100, le=50000)
    gop_size: Optional[int] = Field(None, ge=1, le=300)

    @field_validator("codec")
    @classmethod
    def validate_codec(cls, v):
        if v is not None:
            # Build allowed set dynamically from registered encoders
            try:
                from app.providers.registry import get_provider_registry

                registry = get_provider_registry()
                encoders = registry.get_available_video_encoders()
                allowed = {e["codec_id"] for e in encoders if e.get("available")}
            except Exception:
                allowed = set()
            # Fallback: always accept well-known codec IDs
            allowed |= {
                "mjpeg",
                "h264",
                "h264_openh264",
                "h264_hardware",
                "h264_v4l2",
                "h264_passthrough",
            }
            if v not in allowed:
                raise ValueError(f"Invalid codec: {v}. Allowed: {allowed}")
        return v


class LivePropertyRequest(BaseModel):
    """Live property change request (no pipeline restart)"""

    property: Literal["quality", "bitrate", "h264_bitrate", "gop-size", "gop_size"]
    value: int = Field(ge=1, le=50000)


class StreamingConfigRequest(BaseModel):
    """Streaming configuration request with validated ranges"""

    # Streaming mode
    mode: Optional[Literal["udp", "multicast", "rtsp", "webrtc"]] = None

    # UDP unicast (mode='udp')
    udp_host: Optional[str] = None
    udp_port: Optional[int] = Field(None, ge=1024, le=65535)

    # UDP multicast (mode='multicast')
    multicast_group: Optional[str] = None
    multicast_port: Optional[int] = Field(None, ge=1024, le=65535)
    multicast_ttl: Optional[int] = Field(None, ge=1, le=255)

    # RTSP server (mode='rtsp')
    rtsp_enabled: Optional[bool] = None
    rtsp_url: Optional[str] = None
    rtsp_transport: Optional[Literal["tcp", "udp"]] = None

    # General settings
    enabled: Optional[bool] = None
    auto_start: Optional[bool] = None

    @field_validator("udp_host")
    @classmethod
    def validate_udp_host(cls, v):
        if v is not None:
            try:
                ipaddress.IPv4Address(v)
            except (ipaddress.AddressValueError, ValueError):
                raise ValueError(f"Invalid IPv4 address: {v}")
        return v

    @field_validator("multicast_group")
    @classmethod
    def validate_multicast_group(cls, v):
        if v is not None:
            try:
                addr = ipaddress.IPv4Address(v)
                if not addr.is_multicast:
                    raise ValueError(f"{v} is not a multicast address (must be 224.0.0.0 – 239.255.255.255)")
            except ipaddress.AddressValueError:
                raise ValueError(f"Invalid IPv4 address: {v}")
        return v

    @field_validator("rtsp_url")
    @classmethod
    def validate_rtsp_url(cls, v):
        if v is not None and v == "":
            return None
        if v is not None and not v.startswith("rtsp://"):
            raise ValueError("RTSP URL must start with rtsp://")
        return v


@router.get("/status")
async def get_status(request: Request):
    """Get video streaming status"""
    lang = get_language_from_request(request)
    if not _video_service:
        raise HTTPException(status_code=503, detail=translate("services.video_not_initialized", lang))

    return _video_service.get_status()


@router.get("/cameras")
async def get_cameras(request: Request):
    """Get available cameras from all video source providers"""
    lang = get_language_from_request(request)
    if not _video_service:
        raise HTTPException(status_code=503, detail=translate("services.video_not_initialized", lang))

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


@router.get("/codecs")
async def get_codecs(request: Request):
    """Get available video codecs/encoders"""
    lang = get_language_from_request(request)
    if not _video_service:
        raise HTTPException(status_code=503, detail=translate("services.video_not_initialized", lang))

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


@router.post("/start")
async def start_streaming(request: Request):
    """Start video streaming"""
    lang = get_language_from_request(request)
    if not _video_service:
        raise HTTPException(status_code=503, detail=translate("services.video_not_initialized", lang))

    result = _video_service.start()

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.post("/stop")
async def stop_streaming(request: Request):
    """Stop video streaming"""
    lang = get_language_from_request(request)
    if not _video_service:
        raise HTTPException(status_code=503, detail=translate("services.video_not_initialized", lang))

    result = _video_service.stop()

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.post("/restart")
async def restart_streaming(request: Request):
    """Restart video streaming with current configuration"""
    lang = get_language_from_request(request)
    if not _video_service:
        raise HTTPException(status_code=503, detail=translate("services.video_not_initialized", lang))

    result = _video_service.restart()

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.post("/config/video")
async def configure_video(config: VideoConfigRequest, request: Request):
    """Update video configuration"""
    lang = get_language_from_request(request)
    if not _video_service:
        raise HTTPException(status_code=503, detail=translate("services.video_not_initialized", lang))

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
        from app.services.preferences import get_preferences

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
                    print(f"📹 Saved camera identity: {identity.get('name')} ({identity.get('bus_info', 'N/A')})")
            except Exception as e:
                print(f"⚠️ Failed to detect camera identity: {e}")

        prefs.set_video_config(current)

        # Verify the save
        saved = prefs.get_video_config()
        if "device" in config_dict and saved.get("device") == config_dict["device"]:
            print(f"✅ Video device preference verified: {saved.get('device')}")
        elif "width" in config_dict and saved.get("width") == config_dict["width"]:
            print(f"✅ Video config preference verified: {config_dict['width']}x{config_dict.get('height')}")
    except Exception as e:
        print(f"⚠️ Failed to save video config: {e}")

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
        raise HTTPException(status_code=503, detail=translate("services.video_not_initialized", lang))

    # Convert to dict, excluding None values
    config_dict = {k: v for k, v in config.model_dump().items() if v is not None}

    if not config_dict:
        raise HTTPException(status_code=400, detail="No configuration provided")

    # Update video service
    _video_service.configure(streaming_config=config_dict)

    # Save to preferences
    try:
        from app.services.preferences import get_preferences

        prefs = get_preferences()
        current = prefs.get_streaming_config()
        current.update(config_dict)
        prefs.set_streaming_config(current)

        # Verify the save
        saved = prefs.get_streaming_config()
        if saved.get("auto_start") == config_dict.get("auto_start", saved.get("auto_start")):
            print(f"✅ Streaming auto_start preference verified: {saved.get('auto_start')}")
        else:
            print("⚠️ Streaming preference save verification failed")
    except Exception as e:
        print(f"⚠️ Failed to save streaming config: {e}")

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
        raise HTTPException(status_code=503, detail=translate("services.video_not_initialized", lang))

    result = _video_service.update_live_property(req.property, req.value)

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    # Save to preferences
    try:
        from app.services.preferences import get_preferences

        prefs = get_preferences()
        current = prefs.get_video_config()
        current[req.property] = req.value
        prefs.set_video_config(current)
    except Exception as e:
        print(f"⚠️ Failed to save live update: {e}")

    return result


@router.get("/pipeline-string")
async def get_pipeline_string(request: Request):
    """Get GStreamer pipeline string for Mission Planner"""
    lang = get_language_from_request(request)
    if not _video_service:
        raise HTTPException(status_code=503, detail=translate("services.video_not_initialized", lang))

    return {
        "pipeline": _video_service.get_pipeline_string(),
        "codec": _video_service.video_config.codec,
        "port": _video_service.streaming_config.udp_port,
        "mode": _video_service.streaming_config.mode,
    }


@router.get("/network/ip")
async def get_network_ip(request: Request):
    """Get current network IP address for streaming"""
    if not _video_service:
        raise HTTPException(status_code=503, detail="Video service not initialized")

    ip = _video_service._get_streaming_ip()

    return {
        "ip": ip,
        "rtsp_url": f"rtsp://{ip}:8554/fpv",
    }


@router.get("/config/auto-adaptive-bitrate")
async def get_auto_adaptive_bitrate():
    """Get auto-adaptive bitrate configuration"""
    prefs = get_preferences()
    enabled = prefs.get_auto_adaptive_bitrate()

    return {
        "enabled": enabled,
        "description": (
            "Auto-adaptive bitrate adjusts video quality based on network conditions (SINR, RTT, jitter, packet loss). "
            "Recommended for 4G/LTE connections. Disable for manual control on stable networks (WiFi/Ethernet)."
        ),
    }


@router.post("/config/auto-adaptive-bitrate")
async def set_auto_adaptive_bitrate(request: Request):
    """Enable or disable auto-adaptive bitrate"""
    try:
        body = await request.json()
        enabled = body.get("enabled", True)

        prefs = get_preferences()
        prefs.set_auto_adaptive_bitrate(enabled)

        # If enabling, start the Network Event Bridge
        # If disabling, stop it
        from app.services.network_event_bridge import get_network_event_bridge

        bridge = get_network_event_bridge()

        if enabled:
            await bridge.start()
            message = "Auto-adaptive bitrate enabled. Network Event Bridge started."
        else:
            await bridge.stop()
            message = "Auto-adaptive bitrate disabled. You can now control bitrate manually."

        return {
            "success": True,
            "enabled": enabled,
            "message": message,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
