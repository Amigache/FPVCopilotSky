"""
Board Provider System

Allows FPVCopilot to adapt to different hardware platforms and distros.
Each board provider declares supported features, hardware specs, and capabilities.
"""

from .board_registry import BoardRegistry
from .detected_board import DetectedBoard

__all__ = ['BoardRegistry', 'DetectedBoard']
