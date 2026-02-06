"""
Provider Registry - Central registry for VPN, Modem, and Network Interface providers
Enables dynamic provider discovery and instantiation
"""

import logging
from typing import Dict, Type, Optional, List
from .base import VPNProvider, ModemProvider, NetworkInterface

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """
    Central registry for all VPN, Modem, and Network Interface providers.
    Allows dynamic registration and discovery of providers.
    """
    
    def __init__(self):
        self._vpn_providers: Dict[str, Type[VPNProvider]] = {}
        self._modem_providers: Dict[str, Type[ModemProvider]] = {}
        self._network_providers: Dict[str, Type[NetworkInterface]] = {}
        self._vpn_instances: Dict[str, VPNProvider] = {}
        self._modem_instances: Dict[str, ModemProvider] = {}
        self._network_instances: Dict[str, NetworkInterface] = {}
    
    # ==================== VPN PROVIDERS ====================
    
    def register_vpn_provider(self, name: str, provider_class: Type[VPNProvider]) -> None:
        """
        Register a VPN provider class.
        
        Args:
            name: Provider identifier (e.g., 'tailscale', 'zerotier')
            provider_class: Class inheriting from VPNProvider
        """
        if not issubclass(provider_class, VPNProvider):
            raise TypeError(f"{provider_class} must inherit from VPNProvider")
        
        self._vpn_providers[name] = provider_class
        logger.info(f"Registered VPN provider: {name}")
    
    def get_vpn_provider(self, name: str) -> Optional[VPNProvider]:
        """
        Get a VPN provider instance by name.
        Caches instances for reuse.
        """
        if name not in self._vpn_providers:
            logger.warning(f"VPN provider '{name}' not found")
            return None
        
        # Return cached instance if available
        if name in self._vpn_instances:
            return self._vpn_instances[name]
        
        # Create new instance
        try:
            provider = self._vpn_providers[name]()
            self._vpn_instances[name] = provider
            logger.info(f"Instantiated VPN provider: {name}")
            return provider
        except Exception as e:
            logger.error(f"Failed to instantiate VPN provider '{name}': {e}")
            return None
    
    def list_vpn_providers(self) -> List[str]:
        """Get list of registered VPN provider names"""
        return list(self._vpn_providers.keys())
    
    def get_available_vpn_providers(self) -> List[Dict]:
        """
        Get list of available VPN providers with status.
        Returns:
            [
                {
                    'name': str,
                    'display_name': str,
                    'installed': bool,
                    'class': str
                },
                ...
            ]
        """
        available = []
        
        for name in self._vpn_providers:
            provider = self.get_vpn_provider(name)
            if provider:
                available.append({
                    'name': name,
                    'display_name': getattr(provider, 'display_name', name),
                    'installed': provider.is_installed(),
                    'class': self._vpn_providers[name].__name__
                })
        
        return available
    
    # ==================== MODEM PROVIDERS ====================
    
    def register_modem_provider(self, name: str, provider_class: Type[ModemProvider]) -> None:
        """
        Register a Modem provider class.
        
        Args:
            name: Provider identifier (e.g., 'hilink', 'router', 'dongle')
            provider_class: Class inheriting from ModemProvider
        """
        if not issubclass(provider_class, ModemProvider):
            raise TypeError(f"{provider_class} must inherit from ModemProvider")
        
        self._modem_providers[name] = provider_class
        logger.info(f"Registered Modem provider: {name}")
    
    def get_modem_provider(self, name: str) -> Optional[ModemProvider]:
        """
        Get a Modem provider instance by name.
        Caches instances for reuse.
        """
        if name not in self._modem_providers:
            logger.warning(f"Modem provider '{name}' not found")
            return None
        
        # Return cached instance if available
        if name in self._modem_instances:
            return self._modem_instances[name]
        
        # Create new instance
        try:
            provider = self._modem_providers[name]()
            self._modem_instances[name] = provider
            logger.info(f"Instantiated Modem provider: {name}")
            return provider
        except Exception as e:
            logger.error(f"Failed to instantiate Modem provider '{name}': {e}")
            return None
    
    def list_modem_providers(self) -> List[str]:
        """Get list of registered Modem provider names"""
        return list(self._modem_providers.keys())
    
    def get_available_modem_providers(self) -> List[Dict]:
        """
        Get list of available Modem providers with status.
        Returns:
            [
                {
                    'name': str,
                    'display_name': str,
                    'available': bool,
                    'class': str
                },
                ...
            ]
        """
        available = []
        
        for name in self._modem_providers:
            provider = self.get_modem_provider(name)
            if provider:
                # Try to detect if available
                try:
                    is_available = provider.detect()
                except Exception as e:
                    logger.warning(f"Error detecting modem provider '{name}': {e}")
                    is_available = False
                
                available.append({
                    'name': name,
                    'display_name': getattr(provider, 'display_name', name),
                    'available': is_available,
                    'class': self._modem_providers[name].__name__
                })
        
        return available
    
    # ==================== NETWORK INTERFACE PROVIDERS ====================
    
    def register_network_interface(self, name: str, provider_class: Type[NetworkInterface]) -> None:
        """
        Register a Network Interface provider class.
        
        Args:
            name: Provider identifier (e.g., 'ethernet', 'wifi', 'vpn', 'modem')
            provider_class: Class inheriting from NetworkInterface
        """
        if not issubclass(provider_class, NetworkInterface):
            raise TypeError(f"{provider_class} must inherit from NetworkInterface")
        
        self._network_providers[name] = provider_class
        logger.info(f"Registered Network Interface provider: {name}")
    
    def get_network_interface(self, name: str) -> Optional[NetworkInterface]:
        """
        Get a Network Interface provider instance by name.
        Caches instances for reuse.
        """
        if name not in self._network_providers:
            logger.warning(f"Network Interface provider '{name}' not found")
            return None
        
        # Return cached instance if available
        if name in self._network_instances:
            return self._network_instances[name]
        
        # Create new instance
        try:
            provider = self._network_providers[name]()
            self._network_instances[name] = provider
            logger.info(f"Instantiated Network Interface provider: {name}")
            return provider
        except Exception as e:
            logger.error(f"Failed to instantiate Network Interface provider '{name}': {e}")
            return None
    
    def list_network_interfaces(self) -> List[str]:
        """Get list of registered Network Interface provider names"""
        return list(self._network_providers.keys())
    
    def get_available_network_interfaces(self) -> List[Dict]:
        """
        Get list of available Network Interface providers with detection status.
        Returns:
            [
                {
                    'name': str,
                    'type': str,
                    'detected': bool,
                    'status': dict,
                    'class': str
                },
                ...
            ]
        """
        available = []
        
        for name in self._network_providers:
            provider = self.get_network_interface(name)
            if provider:
                # Try to detect interface
                try:
                    detected = provider.detect()
                    status = provider.get_status() if detected else {}
                except Exception as e:
                    logger.warning(f"Error detecting network interface '{name}': {e}")
                    detected = False
                    status = {}
                
                available.append({
                    'name': name,
                    'type': getattr(provider, 'interface_type', 'unknown'),
                    'detected': detected,
                    'status': status,
                    'class': self._network_providers[name].__name__
                })
        
        return available
    
    # ==================== UTILITIES ====================
    
    def get_provider_status(self, provider_type: str, name: str) -> Dict:
        """
        Get status of a specific provider.
        
        Args:
            provider_type: 'vpn', 'modem', or 'network'
            name: Provider name
        
        Returns:
            Status dictionary from the provider
        """
        if provider_type == 'vpn':
            provider = self.get_vpn_provider(name)
            return provider.get_status() if provider else {'success': False, 'error': 'Not found'}
        
        elif provider_type == 'modem':
            provider = self.get_modem_provider(name)
            return provider.get_status() if provider else {'success': False, 'error': 'Not found'}
        
        elif provider_type == 'network':
            provider = self.get_network_interface(name)
            if provider:
                try:
                    detected = provider.detect()
                    if detected:
                        return provider.get_status()
                    return {'success': False, 'error': 'Interface not detected'}
                except Exception as e:
                    return {'success': False, 'error': str(e)}
            return {'success': False, 'error': 'Not found'}
        
        return {'success': False, 'error': 'Invalid provider type'}
    
    def clear_cache(self) -> None:
        """Clear cached provider instances"""
        self._vpn_instances.clear()
        self._modem_instances.clear()
        self._network_instances.clear()
        logger.info("Provider cache cleared")


# Global registry instance
_registry: Optional[ProviderRegistry] = None


def get_provider_registry() -> ProviderRegistry:
    """Get the global provider registry"""
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry


def init_provider_registry() -> ProviderRegistry:
    """Initialize the global provider registry"""
    global _registry
    _registry = ProviderRegistry()
    return _registry
