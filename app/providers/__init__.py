"""
Providers module - Modular VPN, Modem, and Network Interface provider system
"""

from .base import (
    ModemProvider,
    ModemStatus,
    ModemInfo,
    NetworkInfo as ModemNetworkInfo,
    VPNProvider,
    NetworkInterface,
    InterfaceStatus,
)

from .registry import (
    ProviderRegistry,
    get_provider_registry,
    init_provider_registry,
)

# Import concrete implementations
from .vpn.tailscale import TailscaleProvider
from .modem.hilink.huawei import HuaweiE3372hProvider
from .network import (
    EthernetInterface,
    WiFiInterface,
    VPNInterface,
    ModemInterface,
)

__all__ = [
    # Base abstractions
    'ModemProvider',
    'ModemStatus',
    'ModemInfo',
    'ModemNetworkInfo',
    'VPNProvider',
    'NetworkInterface',
    'InterfaceStatus',
    
    # Registry
    'ProviderRegistry',
    'get_provider_registry',
    'init_provider_registry',
    
    # VPN providers
    'TailscaleProvider',
    
    # Modem providers
    'HuaweiE3372hProvider',
    
    # Network Interface providers
    'EthernetInterface',
    'WiFiInterface',
    'VPNInterface',
    'ModemInterface',
]
