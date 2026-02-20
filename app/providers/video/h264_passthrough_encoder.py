"""
H.264 Passthrough Encoder Provider
Passes through native H.264 from camera without decode/re-encode (ultra low latency, minimal CPU)
"""

import logging
from typing import Dict
from ..base.video_encoder_provider import VideoEncoderProvider
from app.utils.gstreamer import is_gst_element_available

logger = logging.getLogger(__name__)


class H264PassthroughEncoder(VideoEncoderProvider):
    """H.264 passthrough (no transcoding, requires H.264 camera)"""

    def __init__(self):
        super().__init__()
        self.codec_id = "h264_passthrough"
        self.display_name = "H.264 Passthrough"
        self.codec_family = "h264"
        self.encoder_type = "passthrough"
        self.gst_encoder_element = None  # No encoder needed
        self.rtp_payload_type = 96
        self.priority = 85  # High priority for H.264 cameras (better than x264 software encoding)

    def is_available(self) -> bool:
        """Check if h264parse is available in GStreamer"""
        return is_gst_element_available("h264parse")

    def get_capabilities(self) -> Dict:
        """Get H.264 passthrough capabilities"""
        return {
            "codec_id": self.codec_id,
            "display_name": self.display_name,
            "codec_family": self.codec_family,
            "encoder_type": self.encoder_type,
            "available": self.is_available(),
            "requires_h264_source": True,  # IMPORTANT: Only works with H.264 cameras
            "supported_resolutions": [
                (640, 480),
                (960, 720),
                (1280, 720),
                (1920, 1080),
                (2560, 1440),
                (3840, 2160),
            ],
            "supported_framerates": [15, 24, 25, 30, 60, 120],
            "min_bitrate": None,  # Camera controls bitrate
            "max_bitrate": None,
            "default_bitrate": None,
            "quality_control": False,  # Camera controls quality
            "live_quality_adjust": False,  # Cannot adjust camera bitrate
            "latency_estimate": "ultra-low",  # ~5-15ms (no transcoding)
            "cpu_usage": "minimal",  # ~1-2% (parsing only)
            "priority": self.priority,
            "description": (
                "Modo passthrough para cámaras H.264 nativas (Firefly, etc). "
                "Ultra baja latencia, sin recodificación."
            ),
        }

    def validate_config(self, config: Dict) -> Dict:
        """
        Validate configuration for H.264 passthrough.

        Passthrough mode requires the source to be H.264.
        """
        errors = []
        warnings = []

        # Check if source is H.264
        source_format = config.get("source_format", "")
        if "video/x-h264" not in source_format:
            errors.append(f"H.264 passthrough requires H.264 camera. Source format: {source_format}")
            warnings.append("Use x264 encoder for non-H.264 cameras (MJPEG, YUYV, etc)")

        # Passthrough cannot adjust bitrate/quality
        if config.get("bitrate") or config.get("quality"):
            warnings.append("Bitrate/quality control not available in passthrough mode (camera controls encoding)")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    def build_pipeline_elements(self, config: Dict) -> Dict:
        """
        Build H.264 passthrough pipeline elements.

        Pipeline: camera(H.264) → h264parse → (no encoding needed)

        This is extremely efficient as we skip decode/encode cycles.
        Works only with cameras that output native H.264 (Firefly Split, etc).
        """
        try:
            source_format = config.get("source_format", "")

            # Verify source is H.264
            if "video/x-h264" not in source_format:
                return {
                    "success": False,
                    "elements": [],
                    "caps": [],
                    "rtp_payload_type": 0,
                    "rtp_payloader": "",
                    "error": f"H.264 passthrough requires H.264 camera (got {source_format})",
                }

            logger.info("📹 H.264 Passthrough: Camera outputs native H.264, no transcoding needed")

            # Pipeline: parse H.264 NAL stream → queue → RTP
            #
            # Key robustness settings for UVC H.264 cameras (Firefly Split, etc):
            # - h264parse config-interval=-1    : re-inject SPS/PPS before every IDR
            # - h264parse update-timecodes      : fix timestamp gaps from USB
            # - queue with leaky downstream      : drop stale frames, never block
            # - rtph264pay config-interval=-1   : send SPS/PPS with EVERY IDR in RTP
            #   (critical for UDP where any lost IDR = artifacts until next IDR)
            #
            # Intentionally NOT set:
            # - h264parse disable-passthrough   : re-timestamping a valid UVC H.264 stream
            #                                    creates PTS discontinuities that browsers
            #                                    decode as gray/corrupt frames
            # - rtph264pay aggregate-mode=1     : STAP-A aggregation is rejected by many
            #                                    decoders (Mission Planner, older browsers)
            #                                    causing systematic gray frames
            elements = [
                {
                    "name": "h264parse",
                    "element": "h264parse",
                    "properties": {
                        "config-interval": -1,  # Re-insert SPS/PPS on every IDR
                        "update-timecodes": True,  # Fix timestamp irregularities from USB
                    },
                },
                {
                    "name": "capsfilter_parsed",
                    "element": "capsfilter",
                    "properties": {
                        "caps": "video/x-h264,stream-format=byte-stream,alignment=au",
                    },
                },
                {
                    "name": "queue",
                    "element": "queue",
                    "properties": {
                        "max-size-buffers": 3,
                        "max-size-time": 100000000,  # 100ms — enough to absorb USB bursts
                        "max-size-bytes": 0,
                        "leaky": 2,  # Drop oldest if full
                    },
                },
            ]

            return {
                "success": True,
                "elements": elements,
                "caps": [],
                "rtp_payload_type": self.rtp_payload_type,
                "rtp_payloader": "rtph264pay",
                "rtp_payloader_properties": {
                    "pt": self.rtp_payload_type,
                    "mtu": 1300,  # Conservative MTU — DTLS/SRTP overhead leaves ~100 bytes
                    # config-interval=-1: send SPS/PPS in-band with EVERY IDR frame.
                    # Cameras like Firefly Split have long GOP (2-5s between IDRs);
                    # with -1 the browser decoder recovers from any packet loss at the
                    # very next IDR instead of waiting up to one second (config-interval=1)
                    # or remaining broken (config-interval=0).
                    "config-interval": -1,
                },
            }
        except Exception as e:
            logger.error(f"Failed to build H.264 passthrough pipeline: {e}")
            return {
                "success": False,
                "elements": [],
                "caps": [],
                "rtp_payload_type": 0,
                "rtp_payloader": "",
                "error": str(e),
            }

    def get_live_adjustable_properties(self) -> Dict[str, Dict]:
        """No live adjustable properties in passthrough mode (camera controls encoding)"""
        return {}
