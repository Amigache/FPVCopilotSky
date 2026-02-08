"""
MJPEG Encoder Provider
Ultra-low latency encoder using JPEG compression
"""

import subprocess
import logging
from typing import Dict
from ..base.video_encoder_provider import VideoEncoderProvider

logger = logging.getLogger(__name__)


class MJPEGEncoder(VideoEncoderProvider):
    """MJPEG encoder using jpegenc (software)"""

    def __init__(self):
        super().__init__()
        self.codec_id = "mjpeg"
        self.display_name = "MJPEG"
        self.codec_family = "mjpeg"
        self.encoder_type = "software"
        self.gst_encoder_element = "jpegenc"
        self.rtp_payload_type = 26  # Standard MJPEG RTP payload
        self.priority = 70  # High priority for low latency

    def is_available(self) -> bool:
        """Check if jpegenc is available in GStreamer"""
        try:
            result = subprocess.run(["gst-inspect-1.0", "jpegenc"], capture_output=True, timeout=2)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Failed to check jpegenc availability: {e}")
            return False

    def get_capabilities(self) -> Dict:
        """Get MJPEG encoder capabilities"""
        return {
            "codec_id": self.codec_id,
            "display_name": self.display_name,
            "codec_family": self.codec_family,
            "encoder_type": self.encoder_type,
            "available": self.is_available(),
            "supported_resolutions": [
                (640, 480),
                (960, 720),
                (1280, 720),
                (1920, 1080),
            ],
            "supported_framerates": [15, 24, 25, 30, 60],
            "min_bitrate": 0,  # Quality-based, not bitrate
            "max_bitrate": 0,
            "default_bitrate": 0,
            "quality_control": True,
            "live_quality_adjust": True,
            "latency_estimate": "low",  # ~30ms
            "cpu_usage": "low",  # Camera does MJPEG, we just re-encode
            "priority": self.priority,
            "description": "Ultra-baja latencia (~30ms), alto bitrate. Ideal para FPV con buena conexión.",
        }

    def build_pipeline_elements(self, config: Dict) -> Dict:
        """
        Build MJPEG pipeline elements.
        Pipeline: camera(MJPEG) → jpegdec → jpegenc → rtpjpegpay
        """
        try:
            quality = config.get("quality", 85)

            elements = [
                {"name": "decoder", "element": "jpegdec", "properties": {}},
                {
                    "name": "queue_pre",
                    "element": "queue",
                    "properties": {
                        "max-size-buffers": 2,
                        "max-size-time": 0,
                        "max-size-bytes": 0,
                        "leaky": 2,  # Drop old frames
                    },
                },
                {"name": "videoconvert", "element": "videoconvert", "properties": {}},
                {
                    "name": "encoder",
                    "element": "jpegenc",
                    "properties": {"quality": quality},
                },
                {
                    "name": "queue_udp",
                    "element": "queue",
                    "properties": {
                        "max-size-buffers": 3,
                        "max-size-time": 0,
                        "max-size-bytes": 0,
                        "leaky": 2,
                    },
                },
            ]

            return {
                "success": True,
                "elements": elements,
                "caps": [],
                "rtp_payload_type": self.rtp_payload_type,
                "rtp_payloader": "rtpjpegpay",
                "rtp_payloader_properties": {"pt": self.rtp_payload_type, "mtu": 1400},
            }
        except Exception as e:
            logger.error(f"Failed to build MJPEG pipeline: {e}")
            return {
                "success": False,
                "elements": [],
                "caps": [],
                "rtp_payload_type": 0,
                "rtp_payloader": "",
                "error": str(e),
            }

    def get_live_adjustable_properties(self) -> Dict[str, Dict]:
        """MJPEG quality can be adjusted live"""
        return {
            "quality": {
                "element": "encoder",
                "property": "quality",
                "min": 10,
                "max": 100,
                "default": 85,
                "description": "Calidad JPEG (10=baja, 100=máxima)",
            }
        }
