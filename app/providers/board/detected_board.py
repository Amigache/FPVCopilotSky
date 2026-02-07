"""
Data structure representing a detected board with its current configuration
"""

from dataclasses import dataclass
from typing import Optional, List
from .board_definitions import HardwareInfo, VariantInfo, VideoSourceFeature, VideoEncoderFeature, ConnectivityFeature, SystemFeature


@dataclass
class DetectedBoard:
    """
    Represents the current detected board and its configuration.
    This is what the application sees at runtime.
    """
    
    board_name: str                 # e.g., "Radxa Zero"
    board_model: str                # e.g., "Radxa Zero S905Y2"
    variant: VariantInfo            # Active variant config
    hardware: HardwareInfo          # Hardware specs
    
    # Current status
    is_detected: bool = True
    detection_confidence: float = 1.0  # 0.0 to 1.0
    
    @property
    def supports_video_source(self, feature: VideoSourceFeature) -> bool:
        """Check if board variant supports video source"""
        return feature in self.variant.video_sources
    
    @property
    def supports_video_encoder(self, feature: VideoEncoderFeature) -> bool:
        """Check if board variant supports video encoder"""
        return feature in self.variant.video_encoders
    
    @property
    def supports_connectivity(self, feature: ConnectivityFeature) -> bool:
        """Check if board variant has this connectivity option"""
        return feature in self.variant.connectivity
    
    @property
    def supports_system_feature(self, feature: SystemFeature) -> bool:
        """Check if board variant has this system feature"""
        return feature in self.variant.system_features
    
    def to_dict(self) -> dict:
        """Serialize to JSON for API responses"""
        return {
            "board_name": self.board_name,
            "board_model": self.board_model,
            "hardware": {
                "cpu_model": self.hardware.cpu_model,
                "cpu_cores": self.hardware.cpu_cores,
                "cpu_arch": self.hardware.cpu_arch.value,
                "ram_gb": self.hardware.ram_gb,
                "storage_gb": self.hardware.storage_gb,
                "has_gpu": self.hardware.has_gpu,
                "gpu_model": self.hardware.gpu_model,
            },
            "variant": {
                "name": self.variant.name,
                "storage_type": self.variant.storage_type.value,
                "distro": f"{self.variant.distro_family.value} {self.variant.distro_version}",
                "kernel": self.variant.kernel_version,
            },
            "features": {
                "video_sources": [f.value for f in self.variant.video_sources],
                "video_encoders": [f.value for f in self.variant.video_encoders],
                "connectivity": [f.value for f in self.variant.connectivity],
                "system_features": [f.value for f in self.variant.system_features],
            },
            "detection": {
                "detected": self.is_detected,
                "confidence": self.detection_confidence,
            }
        }
