"""
Network Stream Source Provider
Handles remote video streams (RTSP, HTTP, HLS)
"""

import subprocess
import logging
from typing import Dict, List, Optional, Any
from ..base.video_source_provider import VideoSourceProvider

logger = logging.getLogger(__name__)


class NetworkStreamSource(VideoSourceProvider):
    """
    Network stream source provider for remote video feeds.

    Supports:
    - RTSP streams (IP cameras, drones, video servers)
    - HTTP/HTTPS streams
    - HLS streams
    - RTMP streams

    Common use cases:
    - IP camera integration
    - Remote drone video feed
    - Re-streaming from another server
    - Network video surveillance integration
    """

    def __init__(self):
        super().__init__()
        self.source_type = "network_stream"
        self.display_name = "Network Stream"
        self.priority = 50  # Lower priority than local sources
        self.gst_source_element = "rtspsrc"  # Can vary (urisourcebin for auto-detect)

    def is_available(self) -> bool:
        """Check if GStreamer network source elements are available"""
        try:
            # Check for rtspsrc (most common)
            result = subprocess.run(
                ["gst-inspect-1.0", "rtspsrc"], capture_output=True, timeout=2
            )

            if result.returncode != 0:
                return False

            # Check for urisourcebin (universal URI handler)
            result2 = subprocess.run(
                ["gst-inspect-1.0", "urisourcebin"], capture_output=True, timeout=2
            )

            return result2.returncode == 0

        except Exception as e:
            logger.debug(f"Network stream elements not available: {e}")
            return False

    def discover_sources(self) -> List[Dict[str, Any]]:
        """
        Discover network streams.

        Note: Network streams cannot be auto-discovered.
        They must be configured manually by the user.

        This method returns empty list, but streams can be added
        via configuration with explicit URIs.
        """
        # Network streams are not auto-discoverable
        # User must provide URI explicitly
        return []

    def get_source_capabilities(self, source_id: str) -> Optional[Dict[str, Any]]:
        """
        Get capabilities for network stream.

        Args:
            source_id: URI of the stream (e.g., "rtsp://192.168.1.100:554/stream")

        Returns generic capabilities since actual stream properties
        are determined at runtime.
        """
        try:
            # Parse URI to determine stream type
            uri = source_id.lower()

            stream_type = "unknown"
            if uri.startswith("rtsp://"):
                stream_type = "RTSP"
            elif uri.startswith("http://") or uri.startswith("https://"):
                if ".m3u8" in uri:
                    stream_type = "HLS"
                else:
                    stream_type = "HTTP"
            elif uri.startswith("rtmp://"):
                stream_type = "RTMP"

            # Generic capabilities (actual stream determines real values)
            return {
                "is_capture_device": False,
                "is_network_stream": True,
                "stream_type": stream_type,
                "identity": {
                    "name": f"{stream_type} Stream",
                    "driver": "network",
                    "bus_info": uri,
                },
                "is_usb": False,
                "supported_formats": ["auto"],  # Determined by stream
                "default_format": "auto",
                "supported_resolutions": ["auto"],  # Determined by stream
                "supported_framerates": {},
                "hardware_encoding": False,  # Stream provides encoded data
                "device_path": source_id,
                "uri": source_id,
                "requires_network": True,
                "latency": "variable",  # Depends on network conditions
            }

        except Exception as e:
            logger.error(f"Failed to get capabilities for network stream: {e}")
            return None

    def build_source_element(self, source_id: str, config: Dict) -> Dict:
        """
        Build network stream source element.

        Uses urisourcebin for automatic protocol detection and handling.
        For RTSP, uses rtspsrc with latency optimization.
        """
        try:
            uri = source_id

            # Determine which source element to use based on protocol
            if uri.lower().startswith("rtsp://"):
                # Use rtspsrc for better RTSP control
                return {
                    "success": True,
                    "source_element": {
                        "name": "source",
                        "element": "rtspsrc",
                        "properties": {
                            "location": uri,
                            "latency": 100,  # 100ms buffer (adjust as needed)
                            "drop-on-latency": True,  # Drop old frames
                            "protocols": "tcp",  # TCP for reliability (can use 'udp' for lower latency)
                            "do-timestamp": True,
                        },
                    },
                    "caps_filter": None,  # RTSP provides its own caps
                    "post_elements": [
                        # rtspsrc outputs encoded stream, need depayloader
                        {
                            "name": "depay",
                            "element": "rtph264depay",  # Assumes H264, TODO: auto-detect
                            "properties": {},
                        },
                        {"name": "parse", "element": "h264parse", "properties": {}},
                        {
                            "name": "decode",
                            "element": "avdec_h264",
                            "properties": {"max-threads": 2},
                        },
                    ],
                    "output_format": "video/x-raw",  # After decoding
                    "error": None,
                }
            else:
                # Use urisourcebin for other protocols (HTTP, HLS, RTMP)
                return {
                    "success": True,
                    "source_element": {
                        "name": "source",
                        "element": "urisourcebin",
                        "properties": {
                            "uri": uri,
                            "use-buffering": True,
                            "buffer-duration": 100000000,  # 100ms in nanoseconds
                        },
                    },
                    "caps_filter": None,  # Auto-negotiated
                    "post_elements": [],  # urisourcebin handles decoding
                    "output_format": "video/x-raw",
                    "error": None,
                }

        except Exception as e:
            logger.error(f"Failed to build network stream source element: {e}")
            return {"success": False, "error": str(e)}

    def validate_config(self, source_id: str, config: Dict) -> Dict[str, Any]:
        """
        Validate configuration for network stream.

        Basic validation since stream properties are determined at runtime.
        """
        errors = []
        warnings = []

        uri = source_id

        # Check URI format
        if not any(
            uri.lower().startswith(proto)
            for proto in ["rtsp://", "http://", "https://", "rtmp://"]
        ):
            errors.append(
                "Invalid stream URI. Must start with rtsp://, http://, https://, or rtmp://"
            )

        # Warn about network dependency
        warnings.append("Network stream requires stable network connection")
        warnings.append("Latency and quality depend on network conditions")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "adjusted_config": config,
        }

    def add_stream(self, uri: str, name: str = None) -> Optional[Dict]:
        """
        Helper method to add a network stream configuration.

        Args:
            uri: Stream URI (rtsp://..., http://..., etc.)
            name: Friendly name for the stream

        Returns:
            Source dict that can be used with the provider
        """
        if not name:
            name = f"Stream: {uri}"

        caps = self.get_source_capabilities(uri)
        if caps:
            return {
                "source_id": uri,
                "name": name,
                "type": self.source_type,
                "device": uri,
                "capabilities": caps,
                "provider": self.display_name,
            }
        return None
