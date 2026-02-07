"""
x264 H.264 Encoder Provider
High-quality H.264 encoding with comprehensive tuning options
"""

import subprocess
import logging
from typing import Dict
from ..base.video_encoder_provider import VideoEncoderProvider

logger = logging.getLogger(__name__)


class X264Encoder(VideoEncoderProvider):
    """x264 H.264 encoder (software, high quality)"""
    
    def __init__(self):
        super().__init__()
        self.codec_id = "h264"
        self.display_name = "H.264 (x264)"
        self.codec_family = "h264"
        self.encoder_type = "software"
        self.gst_encoder_element = "x264enc"
        self.rtp_payload_type = 96
        self.priority = 60  # Medium-high priority
    
    def is_available(self) -> bool:
        """Check if x264enc is available in GStreamer"""
        try:
            result = subprocess.run(
                ['gst-inspect-1.0', 'x264enc'],
                capture_output=True,
                timeout=2
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Failed to check x264enc availability: {e}")
            return False
    
    def get_capabilities(self) -> Dict:
        """Get x264 encoder capabilities"""
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
            'min_bitrate': 100,
            'max_bitrate': 10000,
            'default_bitrate': 2000,
            'quality_control': False,
            'live_quality_adjust': True,  # Can change bitrate
            'latency_estimate': 'medium',  # ~60-80ms
            'cpu_usage': 'medium-high',  # ~40-60% on 720p30
            'priority': self.priority,
            'description': 'Balance entre calidad y latencia. Mejor compresión que MJPEG.'
        }
    
    def build_pipeline_elements(self, config: Dict) -> Dict:
        """
        Build x264 H.264 pipeline elements.
        Pipeline: camera(MJPEG) → jpegdec → videoconvert → x264enc → h264parse → rtph264pay
        """
        try:
            width = config.get('width', 960)
            height = config.get('height', 720)
            framerate = config.get('framerate', 30)
            bitrate = config.get('bitrate', 2000)
            
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
                    'element': 'x264enc',
                    'properties': {
                        'bitrate': bitrate,
                        'speed-preset': 'ultrafast',
                        'tune': 0x00000004,  # zerolatency
                        'key-int-max': framerate,
                        'bframes': 0,
                        'threads': 4,
                        'sliced-threads': True,
                        'rc-lookahead': 0,
                        'vbv-buf-capacity': 300
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
            logger.error(f"Failed to build x264 pipeline: {e}")
            return {
                'success': False,
                'elements': [],
                'caps': [],
                'rtp_payload_type': 0,
                'rtp_payloader': '',
                'error': str(e)
            }
    
    def get_live_adjustable_properties(self) -> Dict[str, Dict]:
        """x264 bitrate can be adjusted live"""
        return {
            'bitrate': {
                'element': 'encoder',
                'property': 'bitrate',
                'min': 100,
                'max': 10000,
                'default': 2000,
                'description': 'Bitrate H.264 en kbps'
            }
        }
