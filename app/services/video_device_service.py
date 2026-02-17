"""
Video Device Service
Inventory and discovery of all video devices across all source providers.
Provides a unified view of detected video hardware with capabilities.
"""

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class VideoDeviceService:
    """
    Service that scans all registered video source providers and builds
    a unified inventory of detected video devices with their capabilities.

    This is a read-only discovery layer that does NOT modify providers,
    registry, or the streaming pipeline.
    """

    def __init__(self):
        self._devices: List[Dict[str, Any]] = []
        self._scan_timestamp: Optional[float] = None
        self._scanning = False

    def scan_devices(self) -> List[Dict[str, Any]]:
        """
        Scan all video source providers and build a unified device inventory.

        Returns:
            List of discovered video devices with capabilities.
        """
        if self._scanning:
            logger.warning("Device scan already in progress, returning cached results")
            return self._devices

        self._scanning = True
        devices = []
        seen_bus_info: dict[str, bool] = {}

        try:
            from app.providers.registry import get_provider_registry

            registry = get_provider_registry()

            # Get the currently active device from preferences
            active_device = self._get_active_device()

            # Iterate over all registered video source providers
            for source_type in registry.list_video_source_providers():
                provider = registry.get_video_source(source_type)
                if not provider:
                    continue

                available = False
                try:
                    available = provider.is_available()
                except Exception as e:
                    logger.debug(f"Provider {source_type} availability check failed: {e}")

                if not available:
                    logger.debug(f"Provider {source_type} not available, skipping")
                    continue

                try:
                    sources = provider.discover_sources()
                except Exception as e:
                    logger.error(f"Failed to discover sources from {source_type}: {e}")
                    continue

                for source in sources:
                    caps = source.get("capabilities", {})
                    identity = caps.get("identity", {})
                    bus_info = identity.get("bus_info", "")

                    # Deduplicate by bus_info (same physical device detected by multiple providers)
                    dedup_key = f"{bus_info}:{identity.get('name', '')}"
                    if dedup_key and dedup_key in seen_bus_info:
                        continue
                    if dedup_key:
                        seen_bus_info[dedup_key] = True

                    device_id = f"{source_type}:{source.get('device', source.get('source_id', 'unknown'))}"

                    # Determine formats and resolutions per format
                    format_resolutions = caps.get("format_resolutions", {})
                    supported_formats = caps.get("supported_formats", [])

                    # Build resolutions list (flat, unique)
                    all_resolutions = caps.get("supported_resolutions", [])

                    # FPS by resolution
                    fps_by_resolution = caps.get("supported_framerates", {})

                    # Determine compatible codecs for this device
                    compatible_codecs = self._get_compatible_codecs(supported_formats)

                    device_entry = {
                        "device_id": device_id,
                        "source_id": source.get("source_id", ""),
                        "name": source.get("name", "Unknown Device"),
                        "source_type": source_type,
                        "device_path": source.get("device", ""),
                        "driver": identity.get("driver", "unknown"),
                        "bus_info": bus_info,
                        "provider": source.get("provider", provider.display_name),
                        "status": "connected",
                        "formats": supported_formats,
                        "format_resolutions": format_resolutions,
                        "resolutions": all_resolutions,
                        "fps_by_resolution": fps_by_resolution,
                        "hardware_encoding": caps.get("hardware_encoding", False),
                        "is_usb": caps.get("is_usb", False),
                        "is_csi": caps.get("is_csi", False),
                        "is_network": caps.get("is_network_stream", False),
                        "is_active": (
                            source.get("device", "") == active_device or source.get("source_id", "") == active_device
                        ),
                        "compatible_codecs": compatible_codecs,
                    }

                    devices.append(device_entry)

            self._devices = devices
            self._scan_timestamp = time.time()

            logger.info(f"Video device scan complete: {len(devices)} device(s) found")

        except Exception as e:
            logger.error(f"Video device scan failed: {e}")
        finally:
            self._scanning = False

        return self._devices

    def get_devices(self) -> List[Dict[str, Any]]:
        """
        Get cached device list. Performs initial scan if never scanned.

        Returns:
            List of video devices.
        """
        if self._scan_timestamp is None:
            return self.scan_devices()
        return self._devices

    def get_device_by_id(self, device_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific device by its device_id.

        Args:
            device_id: Unique device identifier (e.g., 'v4l2:/dev/video0')

        Returns:
            Device dict or None.
        """
        devices = self.get_devices()
        for device in devices:
            if device["device_id"] == device_id:
                return device
        return None

    def get_scan_info(self) -> Dict[str, Any]:
        """
        Get full device inventory with metadata.

        Returns:
            Dict with devices list, count, and scan timestamp.
        """
        devices = self.get_devices()
        return {
            "devices": devices,
            "count": len(devices),
            "scan_timestamp": self._scan_timestamp,
            "scanning": self._scanning,
        }

    def _get_active_device(self) -> str:
        """Get the currently active video device from preferences."""
        try:
            from app.services.preferences import get_preferences

            prefs = get_preferences()
            video_config = prefs.get_all_preferences().get("video", {})
            return video_config.get("device", "")
        except Exception:
            return ""

    def _get_compatible_codecs(self, device_formats: List[str]) -> List[Dict[str, Any]]:
        """
        Determine which codecs are compatible with a device based on its formats.

        - All devices support software encoders (MJPEG, x264, OpenH264)
          as long as raw video (YUYV, NV12, RGB, etc.) or MJPEG is available.
        - Devices with native H264 format support h264_passthrough.
        - Hardware encoders depend on system availability.

        Returns:
            List of compatible codec dicts with id, name, type, and reason.
        """
        codecs = []

        try:
            from app.providers.registry import get_provider_registry

            registry = get_provider_registry()
            available_encoders = registry.get_available_video_encoders()

            formats_upper = [f.upper() for f in device_formats]

            has_h264 = "H264" in formats_upper or "H.264" in formats_upper
            has_mjpeg = "MJPG" in formats_upper or "MJPEG" in formats_upper
            has_raw = any(f in formats_upper for f in ["YUYV", "NV12", "RGB", "BGR", "YUY2", "I420", "UYVY"])
            # Any format that can be decoded/converted is usable
            has_decodable = has_raw or has_mjpeg

            for encoder in available_encoders:
                if not encoder.get("available"):
                    continue

                codec_id = encoder["codec_id"]
                caps = encoder.get("capabilities", {})
                encoder_type = encoder.get("encoder_type", "software")
                requires_h264 = caps.get("requires_h264_source", False)

                compatible = False
                reason = ""

                if requires_h264:
                    # Passthrough: requires native H264 from device
                    if has_h264:
                        compatible = True
                        reason = "passthrough"
                    else:
                        reason = "requires_h264"
                elif has_decodable or has_h264:
                    # Software/hardware encoders work with any decodable format
                    compatible = True
                    if encoder_type == "hardware":
                        reason = "hardware"
                    elif encoder_type == "software":
                        reason = "software"
                    else:
                        reason = "encode"

                codecs.append(
                    {
                        "codec_id": codec_id,
                        "display_name": encoder.get("display_name", codec_id),
                        "codec_family": encoder.get("codec_family", ""),
                        "encoder_type": encoder_type,
                        "compatible": compatible,
                        "reason": reason,
                    }
                )
        except Exception as e:
            logger.error(f"Error determining compatible codecs: {e}")

        return codecs


# Singleton
_video_device_service: Optional[VideoDeviceService] = None


def get_video_device_service() -> VideoDeviceService:
    """Get the global VideoDeviceService singleton."""
    global _video_device_service
    if _video_device_service is None:
        _video_device_service = VideoDeviceService()
    return _video_device_service
