"""
Base abstractions for modular providers
"""

from .modem_provider import ModemProvider, ModemStatus, ModemInfo, NetworkInfo
from .vpn_provider import VPNProvider
from .network_interface import NetworkInterface, InterfaceStatus, InterfaceType
from .video_encoder_provider import VideoEncoderProvider
from .video_source_provider import VideoSourceProvider

__all__ = [
    # Modem
    "ModemProvider",
    "ModemStatus",
    "ModemInfo",
    "NetworkInfo",
    # VPN
    "VPNProvider",
    # Network
    "NetworkInterface",
    "InterfaceStatus",
    "InterfaceType",
    # Video
    "VideoEncoderProvider",
    "VideoSourceProvider",
]
