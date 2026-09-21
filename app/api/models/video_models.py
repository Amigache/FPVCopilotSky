"""Pydantic models for video API endpoints"""

import ipaddress
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


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
            except (AttributeError, KeyError, TypeError, RuntimeError, ValueError):
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
