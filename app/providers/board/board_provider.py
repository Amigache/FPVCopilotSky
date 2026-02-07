"""
Abstract base class for board providers
"""

from abc import ABC, abstractmethod
from typing import Optional, List
from .detected_board import DetectedBoard
from .board_definitions import DetectionCriteria, VariantInfo


class BoardProvider(ABC):
    """
    Abstract base for board providers.
    
    Each physical board (Radxa Zero, Jetson Nano, etc.) implements this
    to declare its hardware specs and supported features.
    """
    
    @property
    @abstractmethod
    def board_name(self) -> str:
        """Human-readable board name. e.g., "Radxa Zero" """
        pass
    
    @property
    @abstractmethod
    def board_identifier(self) -> str:
        """Unique identifier. e.g., "radxa_zero" """
        pass
    
    @abstractmethod
    def get_detection_criteria(self) -> DetectionCriteria:
        """
        Returns detection criteria to identify this board at runtime.
        Used by BoardRegistry to auto-detect hardware.
        
        Returns:
            DetectionCriteria with checks for CPU model, device tree, etc.
        """
        pass
    
    @abstractmethod
    def get_variants(self) -> List[VariantInfo]:
        """
        Returns all variants (configurations) of this board.
        
        E.g., Radxa Zero could have:
        - eMMC storage variant
        - SD Card variant
        - Different distro/kernel combinations
        
        Returns:
            List of VariantInfo objects
        """
        pass
    
    @abstractmethod
    def detect_running_variant(self) -> Optional[VariantInfo]:
        """
        Detect which variant is currently running.
        
        Analyzes /proc/cpuinfo, /etc/os-release, mounted storage, etc.
        
        Returns:
            VariantInfo if detected, None if unable to determine
        """
        pass
    
    def detect_board(self) -> Optional[DetectedBoard]:
        """
        Attempt to detect if system matches this board.
        Default implementation: check detection criteria + running variant.
        
        Can be overridden for complex detection logic.
        
        Returns:
            DetectedBoard if detection successful, None otherwise
        """
        # Check if detection criteria match
        criteria = self.get_detection_criteria()
        if not self._check_detection_criteria(criteria):
            return None
        
        # Try to detect running variant
        variant = self.detect_running_variant()
        if variant is None:
            return None
        
        # Get first available variant as reference for hardware
        variants = self.get_variants()
        if not variants:
            return None
        
        # Hardware is same for all variants of same board
        hardware = self._get_hardware_info()
        
        return DetectedBoard(
            board_name=self.board_name,
            board_model=f"{self.board_name} ({self._get_cpu_model()})",
            variant=variant,
            hardware=hardware,
            is_detected=True,
            detection_confidence=1.0
        )
    
    @abstractmethod
    def _get_hardware_info(self):
        """
        Return HardwareInfo for this board. Used internally.
        
        Should auto-detect at runtime where possible:
        - CPU cores: /proc/cpuinfo or os.cpu_count()
        - RAM: /proc/meminfo
        - Storage: df, lsblk, or /sys/class/mmc
        - GPU: /proc/device-tree or lspci
        
        Only use hardcoded fallbacks for immutable specs (CPU model, arch).
        """
        pass
    
    @abstractmethod
    def _get_cpu_model(self) -> str:
        """Return CPU model string. e.g., "Amlogic S905Y2" """
        pass
    
    def _check_detection_criteria(self, criteria: DetectionCriteria) -> bool:
        """
        Check if system matches detection criteria.
        
        Default implementation checks files and cpuinfo.
        Can be overridden for custom detection logic.
        """
        import os
        
        # Check required files exist
        if criteria.check_files:
            for filepath in criteria.check_files:
                if not os.path.exists(filepath):
                    return False
        
        # Check CPU model in /proc/cpuinfo
        if criteria.cpu_model_contains:
            try:
                with open('/proc/cpuinfo', 'r') as f:
                    content = f.read()
                    if criteria.cpu_model_contains not in content:
                        return False
            except:
                return False
        
        # TODO: Check device tree, dmesg, etc.
        return True
