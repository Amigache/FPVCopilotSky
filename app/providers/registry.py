"""
Provider Registry - Central registry for VPN, Modem, Network Interface, and Video Encoder providers
Enables dynamic provider discovery and instantiation
"""

import logging
import time
from typing import Dict, Type, Optional, List
from .base import (
    VPNProvider,
    ModemProvider,
    NetworkInterface,
    VideoEncoderProvider,
    VideoSourceProvider,
)

logger = logging.getLogger(__name__)

# Default TTL for cached discover_sources() results (seconds)
_SOURCE_CACHE_TTL = 30.0


class ProviderRegistry:
    """
    Central registry for all VPN, Modem, Network Interface, and Video Encoder providers.
    Allows dynamic registration and discovery of providers.
    """

    def __init__(self):
        self._vpn_providers: Dict[str, Type[VPNProvider]] = {}
        self._modem_providers: Dict[str, Type[ModemProvider]] = {}
        self._network_providers: Dict[str, Type[NetworkInterface]] = {}
        self._video_encoder_providers: Dict[str, Type[VideoEncoderProvider]] = {}
        self._video_source_providers: Dict[str, Type[VideoSourceProvider]] = {}
        self._vpn_instances: Dict[str, VPNProvider] = {}
        self._modem_instances: Dict[str, ModemProvider] = {}
        self._network_instances: Dict[str, NetworkInterface] = {}
        self._video_encoder_instances: Dict[str, VideoEncoderProvider] = {}
        self._video_source_instances: Dict[str, VideoSourceProvider] = {}

        # Cache for discover_sources() results: {source_type: (timestamp, results)}
        self._source_discovery_cache: Dict[str, tuple] = {}

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
                available.append(
                    {
                        "name": name,
                        "display_name": getattr(provider, "display_name", name),
                        "installed": provider.is_installed(),
                        "class": self._vpn_providers[name].__name__,
                    }
                )

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

                available.append(
                    {
                        "name": name,
                        "display_name": getattr(provider, "display_name", name),
                        "available": is_available,
                        "class": self._modem_providers[name].__name__,
                    }
                )

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

                available.append(
                    {
                        "name": name,
                        "type": getattr(provider, "interface_type", "unknown"),
                        "detected": detected,
                        "status": status,
                        "class": self._network_providers[name].__name__,
                    }
                )

        return available

    # ==================== VIDEO ENCODER PROVIDERS ====================

    def register_video_encoder(self, codec_id: str, provider_class: Type[VideoEncoderProvider]) -> None:
        """
        Register a Video Encoder provider class.

        Args:
            codec_id: Codec identifier (e.g., 'mjpeg', 'h264', 'h264_openh264')
            provider_class: Class inheriting from VideoEncoderProvider
        """
        if not issubclass(provider_class, VideoEncoderProvider):
            raise TypeError(f"{provider_class} must inherit from VideoEncoderProvider")

        self._video_encoder_providers[codec_id] = provider_class
        logger.info(f"Registered Video Encoder provider: {codec_id}")

    def get_video_encoder(self, codec_id: str) -> Optional[VideoEncoderProvider]:
        """
        Get a Video Encoder provider instance by codec ID.
        Caches instances for reuse.
        """
        if codec_id not in self._video_encoder_providers:
            logger.warning(f"Video Encoder provider '{codec_id}' not found")
            return None

        # Return cached instance if available
        if codec_id in self._video_encoder_instances:
            return self._video_encoder_instances[codec_id]

        # Create new instance
        try:
            provider = self._video_encoder_providers[codec_id]()
            self._video_encoder_instances[codec_id] = provider
            logger.info(f"Instantiated Video Encoder provider: {codec_id}")
            return provider
        except Exception as e:
            logger.error(f"Failed to instantiate Video Encoder provider '{codec_id}': {e}")
            return None

    def list_video_encoders(self) -> List[str]:
        """Get list of registered Video Encoder provider codec IDs"""
        return list(self._video_encoder_providers.keys())

    def get_available_video_encoders(self) -> List[Dict]:
        """
        Get list of available Video Encoder providers with capabilities.
        Only returns encoders that are actually available on the system.

        Returns:
            [
                {
                    'codec_id': str,
                    'display_name': str,
                    'codec_family': str,
                    'encoder_type': str,
                    'available': bool,
                    'capabilities': dict,
                    'class': str
                },
                ...
            ]
        """
        available = []

        for codec_id in self._video_encoder_providers:
            provider = self.get_video_encoder(codec_id)
            if provider:
                try:
                    is_available = provider.is_available()
                    capabilities = provider.get_capabilities()

                    available.append(
                        {
                            "codec_id": codec_id,
                            "display_name": provider.display_name,
                            "codec_family": provider.codec_family,
                            "encoder_type": provider.encoder_type,
                            "available": is_available,
                            "capabilities": capabilities,
                            "class": self._video_encoder_providers[codec_id].__name__,
                        }
                    )
                except Exception as e:
                    logger.error(f"Error getting capabilities for encoder '{codec_id}': {e}")

        # Sort by priority (higher first), then by availability
        available.sort(
            key=lambda x: (x["available"], x["capabilities"].get("priority", 0)),
            reverse=True,
        )

        return available

    def get_best_video_encoder(self, codec_family: Optional[str] = None) -> Optional[VideoEncoderProvider]:
        """
        Get the best available video encoder, optionally filtered by codec family.

        Args:
            codec_family: Optional filter ('mjpeg', 'h264', 'h265')

        Returns:
            VideoEncoderProvider instance with highest priority that is available
        """
        encoders = self.get_available_video_encoders()

        # Filter by codec family if specified
        if codec_family:
            encoders = [e for e in encoders if e["codec_family"] == codec_family]

        # Filter only available encoders
        encoders = [e for e in encoders if e["available"]]

        if not encoders:
            return None

        # Already sorted by priority in get_available_video_encoders
        best_codec_id = encoders[0]["codec_id"]
        return self.get_video_encoder(best_codec_id)

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
        if provider_type == "vpn":
            provider = self.get_vpn_provider(name)
            return provider.get_status() if provider else {"success": False, "error": "Not found"}

        elif provider_type == "modem":
            provider = self.get_modem_provider(name)
            return provider.get_status() if provider else {"success": False, "error": "Not found"}

        elif provider_type == "network":
            provider = self.get_network_interface(name)
            if provider:
                try:
                    detected = provider.detect()
                    if detected:
                        return provider.get_status()
                    return {"success": False, "error": "Interface not detected"}
                except Exception as e:
                    return {"success": False, "error": str(e)}
            return {"success": False, "error": "Not found"}

        return {"success": False, "error": "Invalid provider type"}

    # ==================== VIDEO SOURCE PROVIDERS ====================

    def register_video_source(self, source_type: str, provider_class: Type[VideoSourceProvider]) -> None:
        """
        Register a video source provider class.

        Args:
            source_type: Source type identifier (e.g., 'v4l2', 'libcamera', 'hdmi_capture')
            provider_class: Class inheriting from VideoSourceProvider
        """
        if not issubclass(provider_class, VideoSourceProvider):
            raise TypeError(f"{provider_class} must inherit from VideoSourceProvider")

        self._video_source_providers[source_type] = provider_class
        logger.info(f"Registered video source provider: {source_type}")

    def get_video_source(self, source_type: str) -> Optional[VideoSourceProvider]:
        """
        Get a video source provider instance by type.
        Caches instances for reuse.
        """
        if source_type not in self._video_source_providers:
            logger.warning(f"Video source provider '{source_type}' not found")
            return None

        # Return cached instance if available
        if source_type in self._video_source_instances:
            return self._video_source_instances[source_type]

        # Create new instance
        try:
            provider = self._video_source_providers[source_type]()
            self._video_source_instances[source_type] = provider
            logger.info(f"Instantiated video source provider: {source_type}")
            return provider
        except Exception as e:
            logger.error(f"Failed to instantiate video source provider '{source_type}': {e}")
            return None

    def list_video_source_providers(self) -> List[str]:
        """Get list of registered video source provider types"""
        return list(self._video_source_providers.keys())

    def discover_sources_cached(self, source_type: str, ttl: float = _SOURCE_CACHE_TTL) -> List[Dict]:
        """Return cached discover_sources() for *source_type*, refreshing after *ttl* seconds."""
        now = time.time()
        cached = self._source_discovery_cache.get(source_type)
        if cached and (now - cached[0]) < ttl:
            return cached[1]

        provider = self.get_video_source(source_type)
        if not provider or not provider.is_available():
            self._source_discovery_cache[source_type] = (now, [])
            return []

        try:
            sources = provider.discover_sources()
        except Exception as e:
            logger.error(f"Failed to discover sources from {source_type}: {e}")
            sources = []

        self._source_discovery_cache[source_type] = (now, sources)
        return sources

    def invalidate_source_cache(self, source_type: str = None) -> None:
        """Invalidate cached discover_sources() results.

        Args:
            source_type: Invalidate a single provider, or *None* to flush all.
        """
        if source_type:
            self._source_discovery_cache.pop(source_type, None)
        else:
            self._source_discovery_cache.clear()
        logger.debug(f"Source discovery cache invalidated: {source_type or 'all'}")

    def get_available_video_sources(self) -> List[Dict]:
        """
        Get list of all available video sources from all providers.
        Uses TTL-based cache to avoid expensive subprocess calls.

        Returns:
            [
                {
                    'source_id': str,
                    'name': str,
                    'type': str,  # 'v4l2', 'libcamera', etc.
                    'device': str,
                    'capabilities': dict,
                    'provider': str
                },
                ...
            ]
        """
        all_sources = []

        # Query each registered provider (with cache)
        for source_type in self._video_source_providers:
            sources = self.discover_sources_cached(source_type)
            all_sources.extend(sources)

        # Sort by provider priority (highest first)
        all_sources.sort(
            key=lambda s: (self.get_video_source(s["type"]).priority if self.get_video_source(s["type"]) else 0),
            reverse=True,
        )

        return all_sources

    def get_best_video_source(self) -> Optional[Dict]:
        """
        Get the best available video source based on provider priority.

        Returns first available source from highest priority provider.
        """
        sources = self.get_available_video_sources()
        return sources[0] if sources else None

    def find_video_source_by_identity(self, name: str, bus_info: str = "", driver: str = "") -> Optional[Dict]:
        """
        Find a video source by identity across all providers.

        Args:
            name: Device name
            bus_info: Bus info (optional)
            driver: Driver name (optional)

        Returns:
            Source dict if found, None otherwise
        """
        for source_type in self._video_source_providers:
            provider = self.get_video_source(source_type)
            if provider and provider.is_available():
                source_id = provider.find_source_by_identity(name, bus_info, driver)
                if source_id:
                    # Get full source info from cache
                    sources = self.discover_sources_cached(source_type)
                    for source in sources:
                        if source["source_id"] == source_id:
                            return source

        return None

    def clear_cache(self) -> None:
        """Clear cached provider instances and discovery results"""
        self._vpn_instances.clear()
        self._modem_instances.clear()
        self._network_instances.clear()
        self._video_encoder_instances.clear()
        self._video_source_instances.clear()
        self._source_discovery_cache.clear()
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
