"""
OpenH264 Encoder Provider
ARM-optimized H.264 encoding with low CPU usage
"""

import subprocess
import logging
from typing import Dict
from ..base.video_encoder_provider import VideoEncoderProvider

logger = logging.getLogger(__name__)


class OpenH264Encoder(VideoEncoderProvider):
    """OpenH264 encoder (software, ARM NEON optimized)"""
    
    def __init__(self):
        super().__init__()
        self.codec_id = "h264_openh264"
        self.display_name = "H.264 (OpenH264 - Bajo CPU)"
        self.codec_family = "h264"
        self.encoder_type = "software"
        self.gst_encoder_element = "openh264enc"
        self.rtp_payload_type = 96
        self.priority = 0  # Disabled: slower than x264 in software mode, needs hardware acceleration
    
    def is_available(self) -> bool:
        """Check if openh264enc is available in GStreamer"""
        try:
            result = subprocess.run(
                ['gst-inspect-1.0', 'openh264enc'],
                capture_output=True,
                timeout=2
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Failed to check openh264enc availability: {e}")
            return False
    
    def get_capabilities(self) -> Dict:
        """Get OpenH264 encoder capabilities"""
        return {
            'codec_id': self.codec_id,
            'display_name': self.display_name,
            'codec_family': self.codec_family,
            'encoder_type': self.encoder_type,
            'available': self.is_available(),
            'supported_resolutions': [
                (640, 480),
                (960, 720),
                (1280, 720),
                (1920, 1080)
            ],
            'supported_framerates': [15, 24, 25, 30, 60],
            'min_bitrate': 500,
            'max_bitrate': 8000,
            'default_bitrate': 2500,
            'quality_control': False,
            'live_quality_adjust': True,  # Can change bitrate and gop-size
            'latency_estimate': 'very-low',  # ~20-50ms with gop-size=2 (2 keyframes/sec at 30fps)
            'cpu_usage': 'low',  # ~25-35% on 720p30 (ARM NEON)
            'priority': self.priority,
            'description': 'Optimizado para FPV. Baja latencia (<50ms), menor CPU que x264. Gop-size ajustable: 1 (latencia mínima) a 15 (mayor compresión).'
        }
    
    def build_pipeline_elements(self, config: Dict) -> Dict:
        """
        Build OpenH264 pipeline elements.
        Pipeline: camera(MJPEG) → jpegdec → videoconvert → openh264enc → h264parse → rtph264pay
        """
        try:
            width = config.get('width', 960)
            height = config.get('height', 720)
            framerate = config.get('framerate', 30)
            bitrate = config.get('bitrate', 2500)
            gop_size = config.get('gop_size', 2)  # Keyframe interval in frames
            
            elements = [
                {
                    'name': 'decoder',
                    'element': 'jpegdec',
                    'properties': {}
                },
                {
                    'name': 'videoconvert',
                    'element': 'videoconvert',
                    'properties': {}
                },
                {
                    'name': 'videoscale',
                    'element': 'videoscale',
                    'properties': {}
                },
                {
                    'name': 'encoder_caps',
                    'element': 'capsfilter',
                    'properties': {
                        'caps': f'video/x-raw,format=I420,width={width},height={height},framerate={framerate}/1'
                    }
                },
                {
                    'name': 'queue_pre',
                    'element': 'queue',
                    'properties': {
                        'max-size-buffers': 2,
                        'max-size-time': 0,
                        'max-size-bytes': 0,
                        'leaky': 2
                    }
                },
                {
                    'name': 'encoder',
                    'element': 'openh264enc',
                    'properties': {
                        'bitrate': bitrate * 1000,  # OpenH264 expects bps (bits per second)
                        'rate-control': 1,  # CBR (Constant Bitrate) mode
                        'gop-size': gop_size  # Keyframe interval from config
                    }
                },
                {
                    'name': 'queue_post',
                    'element': 'queue',
                    'properties': {
                        'max-size-buffers': 3,
                        'max-size-time': 0,
                        'max-size-bytes': 0,
                        'leaky': 2
                    }
                },
                {
                    'name': 'h264parse',
                    'element': 'h264parse',
                    'properties': {
                        'config-interval': -1
                    }
                }
            ]
            
            return {
                'success': True,
                'elements': elements,
                'caps': [],
                'rtp_payload_type': self.rtp_payload_type,
                'rtp_payloader': 'rtph264pay',
                'rtp_payloader_properties': {
                    'pt': self.rtp_payload_type,
                    'mtu': 1400,
                    'config-interval': -1
                }
            }
        except Exception as e:
            logger.error(f"Failed to build OpenH264 pipeline: {e}")
            return {
                'success': False,
                'elements': [],
                'caps': [],
                'rtp_payload_type': 0,
                'rtp_payloader': '',
                'error': str(e)
            }
    
    def get_live_adjustable_properties(self) -> Dict[str, Dict]:
        """OpenH264 bitrate and gop-size can be adjusted live"""
        return {
            'bitrate': {
                'element': 'encoder',
                'property': 'bitrate',
                'min': 500,
                'max': 8000,
                'default': 2500,
                'description': 'Bitrate H.264 en kbps',
                'multiplier': 1000  # Convert kbps to bps for OpenH264
            },
            'gop-size': {
                'element': 'encoder',
                'property': 'gop-size',
                'min': 1,
                'max': 15,
                'default': 2,
                'description': 'Keyframe interval (frames). 1=menor latencia/+bitrate, 5=equilibrio, 15=+compresión/-latencia',
                'multiplier': 1  # Direct frame count
            }
        }
