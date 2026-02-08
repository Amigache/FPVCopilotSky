"""
Video Encoder Provider abstract base class
Enables dynamic encoder discovery based on hardware/software capabilities
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


class VideoEncoderProvider(ABC):
    """Abstract base class for video encoder providers"""

    def __init__(self):
        self.codec_id: str = ""  # e.g., 'mjpeg', 'h264', 'h264_openh264'
        self.display_name: str = ""  # e.g., 'MJPEG', 'H.264 (x264)', 'H.264 Low CPU (OpenH264)'
        self.codec_family: str = ""  # e.g., 'mjpeg', 'h264', 'h265'
        self.encoder_type: str = ""  # 'hardware', 'software', 'hybrid'
        self.gst_encoder_element: str = ""  # GStreamer element name
        self.rtp_payload_type: int = 96  # Default RTP payload type
        self.priority: int = 50  # Higher = preferred (for auto-selection)

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if encoder is available on the system.
        Should check for GStreamer plugin availability.
        """
        pass

    @abstractmethod
    def get_capabilities(self) -> Dict:
        """
        Get encoder capabilities and constraints.
        Returns:
            {
                'codec_id': str,
                'display_name': str,
                'codec_family': str,
                'encoder_type': str,
                'available': bool,
                'supported_resolutions': List[tuple],  # [(width, height), ...]
                'supported_framerates': List[int],
                'min_bitrate': int,  # kbps
                'max_bitrate': int,  # kbps
                'default_bitrate': int,  # kbps
                'quality_control': bool,  # True if supports quality parameter
                'live_quality_adjust': bool,  # True if can change quality without restart
                'latency_estimate': str,  # 'low', 'medium', 'high'
                'cpu_usage': str,  # 'low', 'medium', 'high'
                'priority': int
            }
        """
        pass

    @abstractmethod
    def build_pipeline_elements(self, config: Dict) -> Dict:
        """
        Build GStreamer pipeline configuration for this encoder.

        Args:
            config: Video configuration dict with:
                - width: int
                - height: int
                - framerate: int
                - bitrate: int (for H.264/H.265)
                - quality: int (for MJPEG)

        Returns:
            {
                'success': bool,
                'elements': List[Dict],  # List of GStreamer elements with properties
                'caps': List[str],  # List of caps filters
                'rtp_payload_type': int,
                'rtp_payloader': str,  # RTP payloader element name
                'error': Optional[str]
            }

        Example:
            {
                'success': True,
                'elements': [
                    {'name': 'encoder', 'element': 'x264enc', 'properties': {'bitrate': 2000, ...}},
                    {'name': 'h264parse', 'element': 'h264parse', 'properties': {...}},
                ],
                'caps': [],
                'rtp_payload_type': 96,
                'rtp_payloader': 'rtph264pay'
            }
        """
        pass

    @abstractmethod
    def get_live_adjustable_properties(self) -> Dict[str, Dict]:
        """
        Get properties that can be adjusted without pipeline restart.

        Returns:
            {
                'property_name': {
                    'element': str,  # Element name to adjust
                    'property': str,  # Element property name
                    'min': int,
                    'max': int,
                    'default': int,
                    'description': str
                }
            }
        """
        pass

    def validate_config(self, config: Dict) -> Dict:
        """
        Validate encoder configuration.
        Can be overridden for specific validation logic.

        Returns:
            {
                'valid': bool,
                'errors': List[str],
                'warnings': List[str]
            }
        """
        errors = []
        warnings = []

        caps = self.get_capabilities()

        # Basic validation
        if config.get("width", 0) <= 0:
            errors.append("Width must be positive")
        if config.get("height", 0) <= 0:
            errors.append("Height must be positive")
        if config.get("framerate", 0) <= 0:
            errors.append("Framerate must be positive")

        # Bitrate validation for H.264/H.265
        if self.codec_family in ["h264", "h265"]:
            bitrate = config.get("bitrate", 0)
            if bitrate < caps.get("min_bitrate", 0):
                warnings.append(f"Bitrate below minimum ({caps.get('min_bitrate')} kbps)")
            if bitrate > caps.get("max_bitrate", 10000):
                warnings.append(f"Bitrate above maximum ({caps.get('max_bitrate')} kbps)")

        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

    def get_pipeline_string_for_client(self, port: int) -> str:
        """
        Get GStreamer pipeline string for client (Mission Planner, QGC, etc).
        Can be overridden for specific requirements.
        """
        if self.codec_family == "h264":
            return (
                f'udpsrc port={port} caps="application/x-rtp, media=(string)video, '
                f'clock-rate=(int)90000, encoding-name=(string)H264, payload=(int){self.rtp_payload_type}" ! '
                f"rtph264depay ! avdec_h264 ! videoconvert ! "
                f"video/x-raw,format=BGRA ! appsink name=outsink sync=false"
            )
        elif self.codec_family == "h265":
            return (
                f'udpsrc port={port} caps="application/x-rtp, media=(string)video, '
                f'clock-rate=(int)90000, encoding-name=(string)H265, payload=(int){self.rtp_payload_type}" ! '
                f"rtph265depay ! avdec_h265 ! videoconvert ! "
                f"video/x-raw,format=BGRA ! appsink name=outsink sync=false"
            )
        elif self.codec_family == "mjpeg":
            return (
                f'udpsrc port={port} caps="application/x-rtp, media=(string)video, '
                f'clock-rate=(int)90000, encoding-name=(string)JPEG, payload=(int){self.rtp_payload_type}" ! '
                f"rtpjpegdepay ! jpegdec ! videoconvert ! "
                f"video/x-raw,format=BGRA ! appsink name=outsink sync=false"
            )
        else:
            return ""
