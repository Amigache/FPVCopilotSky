"""
Video Source Provider Base Class
Abstract interface for video input sources (cameras, capture cards, network streams)
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class VideoSourceProvider(ABC):
    """
    Abstract base class for video source providers.
    
    A video source provider handles detection, configuration, and GStreamer
    pipeline construction for a specific type of video input.
    
    Examples:
    - V4L2 cameras (USB, CSI via video4linux2)
    - libcamera sources (CSI via libcamera)
    - HDMI capture cards
    - Network streams (RTSP, HTTP)
    """
    
    def __init__(self):
        self.source_type = "unknown"  # 'v4l2', 'libcamera', 'hdmi_capture', 'network'
        self.display_name = "Generic Video Source"
        self.priority = 50  # Higher = preferred when multiple sources available
        self.gst_source_element = ""  # GStreamer element name (e.g., 'v4l2src', 'libcamerasrc')
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if this source type is available on the system.
        
        Returns:
            bool: True if the source type can be used (e.g., v4l2-ctl exists, libcamera installed)
        """
        pass
    
    @abstractmethod
    def discover_sources(self) -> List[Dict[str, Any]]:
        """
        Discover and list all available sources of this type.
        
        Each source dict should contain:
        - source_id: Unique identifier (e.g., '/dev/video0', 'camera-module-1')
        - name: Human-readable name
        - type: Source type (matches self.source_type)
        - device: Device path or identifier for GStreamer
        - capabilities: Dict with supported resolutions, fps, formats, etc.
        
        Returns:
            List[Dict]: List of discovered sources with their capabilities
        """
        pass
    
    @abstractmethod
    def get_source_capabilities(self, source_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed capabilities for a specific source.
        
        Args:
            source_id: Unique identifier of the source
            
        Returns:
            Dict with:
            - supported_resolutions: List of (width, height) tuples
            - supported_framerates: Dict mapping resolution to fps list
            - supported_formats: List of pixel formats (e.g., ['MJPEG', 'YUYV', 'H264'])
            - default_format: Preferred format
            - hardware_encoding: Bool, true if source provides compressed format
            - identity: Dict with name, driver, bus_info for stable matching
        """
        pass
    
    @abstractmethod
    def build_source_element(self, source_id: str, config: Dict) -> Dict:
        """
        Build GStreamer source element and initial pipeline elements.
        
        Args:
            source_id: Identifier of the source to use
            config: Dict with width, height, framerate, format, etc.
            
        Returns:
            Dict with:
            - success: bool
            - source_element: GStreamer element configuration
            - caps_filter: Capability filter string or None
            - post_elements: List of additional elements after source (e.g., converters)
            - output_format: Format leaving the source chain ('video/x-raw', 'image/jpeg', etc.)
            - error: Error message if success=False
        """
        pass
    
    @abstractmethod
    def validate_config(self, source_id: str, config: Dict) -> Dict[str, Any]:
        """
        Validate configuration for a source before building pipeline.
        
        Args:
            source_id: Identifier of the source
            config: Configuration to validate
            
        Returns:
            Dict with:
            - valid: bool
            - errors: List of error messages
            - warnings: List of warning messages
            - adjusted_config: Dict with adjusted/corrected config if needed
        """
        pass
    
    def find_source_by_identity(self, name: str, bus_info: str = "", driver: str = "") -> Optional[str]:
        """
        Find a source by its identity information (for stable device matching).
        
        Args:
            name: Device name (Card type)
            bus_info: Bus information (optional)
            driver: Driver name (optional)
            
        Returns:
            source_id if found, None otherwise
        """
        # Default implementation scans all sources
        sources = self.discover_sources()
        
        name_match = None
        for source in sources:
            identity = source.get('identity', {})
            source_name = identity.get('name', '')
            source_bus = identity.get('bus_info', '')
            source_driver = identity.get('driver', '')
            
            if source_name == name:
                # Exact match on all provided fields
                if (not bus_info or source_bus == bus_info) and \
                   (not driver or source_driver == driver):
                    return source['source_id']
                    
                # Partial match (name only)
                if name_match is None:
                    name_match = source['source_id']
        
        return name_match
    
    def get_default_source(self) -> Optional[str]:
        """
        Get the default/preferred source for this provider.
        
        Returns:
            source_id of the default source, or None if none available
        """
        sources = self.discover_sources()
        return sources[0]['source_id'] if sources else None
    
    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.display_name} (priority={self.priority})>"
