"""
V4L2 Camera Source Provider
Handles USB cameras and CSI cameras exposed through video4linux2
"""

import subprocess
import glob
import os
import re
import logging
from typing import Dict, List, Optional, Any
from ..base.video_source_provider import VideoSourceProvider

logger = logging.getLogger(__name__)


class V4L2CameraSource(VideoSourceProvider):
    """
    Video4Linux2 camera source provider.
    
    Supports:
    - USB cameras (uvcvideo driver)
    - CSI cameras exposed as /dev/video* (if supported by v4l2)
    - Other video capture devices
    """
    
    def __init__(self):
        super().__init__()
        self.source_type = "v4l2"
        self.display_name = "V4L2 Camera"
        self.priority = 70  # High priority, widely compatible
        self.gst_source_element = "v4l2src"
    
    def is_available(self) -> bool:
        """Check if v4l2-ctl is available"""
        try:
            result = subprocess.run(
                ['which', 'v4l2-ctl'],
                capture_output=True,
                timeout=2
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Failed to check v4l2-ctl availability: {e}")
            return False
    
    def discover_sources(self) -> List[Dict[str, Any]]:
        """
        Discover all V4L2 video capture devices.
        
        Filters out duplicate device entris (same physical camera exposed 
        as multiple /dev/video*) by grouping on bus_info.
        
        Returns list of unique cameras with full capabilities.
        """
        if not self.is_available():
            return []
        
        cameras = []
        devices_by_identity = {}  # Group by bus_info to detect duplicates
        devices = sorted(glob.glob('/dev/video*'))
        
        for device in devices:
            try:
                caps = self.get_source_capabilities(device)
                if not caps or not caps.get('is_capture_device'):
                    continue
                
                # Get identity info
                identity = caps.get('identity', {})
                bus_info = identity.get('bus_info', device)  # Fallback to device if no bus_info
                
                # Group by bus_info - only keep the first device for each physical camera
                if bus_info not in devices_by_identity:
                    devices_by_identity[bus_info] = {
                        'source_id': device,
                        'name': identity.get('name', device),
                        'type': self.source_type,
                        'device': device,
                        'capabilities': caps,
                        'provider': self.display_name,
                        'all_devices': [device]  # Track all /dev/video* for this camera
                    }
                else:
                    # Same physical camera, just track the device path
                    devices_by_identity[bus_info]['all_devices'].append(device)
            
            except Exception as e:
                logger.debug(f"Skipping {device}: {e}")
                continue
        
        # Convert to list, removing the tracking info
        for identity_group in devices_by_identity.values():
            identity_group.pop('all_devices', None)  # Remove internal tracking
            cameras.append(identity_group)
        
        logger.info(f"Discovered {len(cameras)} physical cameras (filtered {len(devices) - len(cameras)} duplicate device paths)")
        return cameras
    
    def get_source_capabilities(self, source_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed capabilities for a V4L2 device.
        
        Queries v4l2-ctl for:
        - Device info (name, driver, bus_info)
        - Supported resolutions and framerates
        - Available pixel formats
        """
        try:
            device = source_id
            
            # Get device identity info
            info_result = subprocess.run(
                ["v4l2-ctl", "-d", device, "--info"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if info_result.returncode != 0:
                return None
            
            # Parse device info
            device_name = os.path.basename(device)
            device_type = "Camera"
            driver = "unknown"
            bus_info = ""
            is_capture = False
            
            for line in info_result.stdout.split('\n'):
                if 'Card type' in line:
                    parts = line.split(':', 1)
                    if len(parts) > 1:
                        device_name = parts[1].strip()
                elif 'Driver name' in line:
                    parts = line.split(':', 1)
                    if len(parts) > 1:
                        driver = parts[1].strip()
                elif 'Bus info' in line:
                    parts = line.split(':', 1)
                    if len(parts) > 1:
                        bus_info = parts[1].strip()
                elif 'Video Capture' in line:
                    is_capture = True
            
            # Skip if not a capture device
            if not is_capture:
                return None
            
            # Get formats and resolutions with FPS
            formats_result = subprocess.run(
                ["v4l2-ctl", "-d", device, "--list-formats-ext"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # Parse formats and resolutions
            formats = []
            resolutions_fps = {}  # {resolution: [fps list]}
            format_resolutions = {}  # {format: [resolutions]}
            
            current_format = None
            current_resolution = None
            
            for line in formats_result.stdout.split('\n'):
                # Parse format line (e.g., "[0]: 'MJPG' (Motion-JPEG)")
                if "'" in line and "'" in line.split("'")[1:]:
                    parts = line.split("'")
                    if len(parts) >= 2:
                        current_format = parts[1]
                        if current_format not in formats:
                            formats.append(current_format)
                            format_resolutions[current_format] = []
                
                # Parse resolution line
                if 'Size: Discrete' in line and current_format:
                    parts = line.split()
                    for part in parts:
                        if 'x' in part and part[0].isdigit():
                            current_resolution = part
                            if current_resolution not in resolutions_fps:
                                resolutions_fps[current_resolution] = []
                            if current_resolution not in format_resolutions[current_format]:
                                format_resolutions[current_format].append(current_resolution)
                
                # Parse FPS line
                if 'Interval: Discrete' in line and current_resolution:
                    fps_match = re.search(r'\(([0-9.]+)\s*fps\)', line)
                    if fps_match:
                        fps = float(fps_match.group(1))
                        fps_int = int(fps)
                        if fps_int not in resolutions_fps[current_resolution]:
                            resolutions_fps[current_resolution].append(fps_int)
            
            # Sort FPS for each resolution (highest first)
            for res in resolutions_fps:
                resolutions_fps[res].sort(reverse=True)
            
            # Sort resolutions by pixel count (highest first)
            sorted_resolutions = sorted(
                resolutions_fps.keys(),
                key=lambda x: tuple(map(int, x.split('x'))) if 'x' in x else (0, 0),
                reverse=True
            )
            
            # Determine default format (prefer MJPEG for compatibility)
            default_format = None
            if 'MJPG' in formats or 'MJPEG' in formats:
                default_format = 'MJPEG'
            elif 'YUYV' in formats:
                default_format = 'YUYV'
            elif formats:
                default_format = formats[0]
            
            # Check for hardware encoding capability
            hardware_encoding = any(fmt in ['H264', 'HEVC', 'VP8', 'VP9'] for fmt in formats)
            
            return {
                'is_capture_device': True,
                'identity': {
                    'name': device_name,
                    'driver': driver,
                    'bus_info': bus_info
                },
                'is_usb': driver == "uvcvideo",
                'supported_formats': formats,
                'default_format': default_format,
                'format_resolutions': format_resolutions,
                'supported_resolutions': sorted_resolutions,
                'supported_framerates': resolutions_fps,
                'hardware_encoding': hardware_encoding,
                'device_path': device
            }
            
        except Exception as e:
            logger.error(f"Failed to get capabilities for {source_id}: {e}")
            return None
    
    def build_source_element(self, source_id: str, config: Dict) -> Dict:
        """
        Build V4L2 source element configuration.
        
        Args:
            source_id: Device path (e.g., '/dev/video0')
            config: Dict with width, height, framerate, format (optional)
            
        Returns pipeline config with source element and caps filter
        """
        try:
            caps = self.get_source_capabilities(source_id)
            if not caps:
                return {
                    'success': False,
                    'error': f"Device {source_id} not available or not a capture device"
                }
            
            width = config.get('width', 960)
            height = config.get('height', 720)
            framerate = config.get('framerate', 30)
            
            # Use MJPEG by default (best for USB cameras, low CPU)
            pixel_format = config.get('format', caps.get('default_format', 'MJPEG'))
            
            # Map common format names to GStreamer caps format
            format_mapping = {
                'MJPEG': 'image/jpeg',
                'MJPG': 'image/jpeg',
                'YUYV': 'video/x-raw,format=YUY2',
                'H264': 'video/x-h264',
                'HEVC': 'video/x-h265'
            }
            
            gst_format = format_mapping.get(pixel_format, 'image/jpeg')
            
            # Build caps filter string
            caps_str = f"{gst_format},width={width},height={height},framerate={framerate}/1"
            
            return {
                'success': True,
                'source_element': {
                    'name': 'source',
                    'element': 'v4l2src',
                    'properties': {
                        'device': source_id,
                        'do-timestamp': True
                    }
                },
                'caps_filter': caps_str,
                'post_elements': [],  # No additional elements needed after source
                'output_format': gst_format,
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Failed to build source element for {source_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def validate_config(self, source_id: str, config: Dict) -> Dict[str, Any]:
        """
        Validate configuration for V4L2 source.
        
        Checks if requested resolution, framerate, and format are supported.
        """
        caps = self.get_source_capabilities(source_id)
        if not caps:
            return {
                'valid': False,
                'errors': [f"Device {source_id} not available"],
                'warnings': [],
                'adjusted_config': config
            }
        
        errors = []
        warnings = []
        adjusted = dict(config)
        
        width = config.get('width')
        height = config.get('height')
        framerate = config.get('framerate')
        pixel_format = config.get('format')
        
        # Check resolution
        if width and height:
            resolution = f"{width}x{height}"
            if resolution not in caps['supported_resolutions']:
                errors.append(f"Resolution {resolution} not supported")
                # Suggest closest resolution
                if caps['supported_resolutions']:
                    suggested = caps['supported_resolutions'][0]
                    warnings.append(f"Consider using {suggested} instead")
        
        # Check framerate
        if framerate and width and height:
            resolution = f"{width}x{height}"
            if resolution in caps['supported_framerates']:
                supported_fps = caps['supported_framerates'][resolution]
                if framerate not in supported_fps:
                    warnings.append(f"Framerate {framerate} may not be supported. Available: {supported_fps}")
        
        # Check format
        if pixel_format and pixel_format not in caps['supported_formats']:
            errors.append(f"Format {pixel_format} not supported")
            warnings.append(f"Available formats: {caps['supported_formats']}")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'adjusted_config': adjusted
        }
