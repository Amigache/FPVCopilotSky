"""Link profiles: adapt video + telemetry to the active connection type.

A *link profile* describes the desired streaming/telemetry behaviour for a
connection class (LAN/WiFi, 4G/LTE, VPN). Profiles are auto-selected from the
detected primary interface and can be overridden manually.
"""

import logging
from dataclasses import dataclass, asdict
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Stable profile identifiers
LINK_LAN = "lan"
LINK_MODEM = "modem"
LINK_VPN = "vpn"

TELEMETRY_FULL = "full"
TELEMETRY_REDUCED = "reduced"


@dataclass
class LinkProfile:
    """Desired settings for one connection class."""

    name: str
    label: str
    video_mode: str = "udp"  # udp | multicast | rtsp | webrtc
    width: int = 1920
    height: int = 1080
    framerate: int = 30
    h264_bitrate: int = 6000  # kbps
    quality: int = 85
    telemetry: str = TELEMETRY_FULL  # full | reduced
    mtu: int = 1500
    udp_buffer_size: int = 0  # bytes; 0 = leave GStreamer default

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def default_link_profiles() -> Dict[str, Dict[str, Any]]:
    """Sensible defaults per connection type."""
    profiles = {
        LINK_LAN: LinkProfile(
            name=LINK_LAN,
            label="LAN/WiFi",
            video_mode="udp",
            width=1920,
            height=1080,
            framerate=30,
            h264_bitrate=6000,
            telemetry=TELEMETRY_FULL,
            mtu=1500,
            udp_buffer_size=0,
        ),
        LINK_MODEM: LinkProfile(
            name=LINK_MODEM,
            label="4G/LTE",
            video_mode="webrtc",
            width=1280,
            height=720,
            framerate=30,
            h264_bitrate=2500,
            telemetry=TELEMETRY_REDUCED,
            mtu=1400,
            udp_buffer_size=2 * 1024 * 1024,
        ),
        LINK_VPN: LinkProfile(
            name=LINK_VPN,
            label="VPN/Tailscale",
            video_mode="udp",
            width=1920,
            height=1080,
            framerate=30,
            h264_bitrate=4000,
            telemetry=TELEMETRY_FULL,
            mtu=1280,
            udp_buffer_size=2 * 1024 * 1024,
        ),
    }
    return {name: profile.to_dict() for name, profile in profiles.items()}


def classify_link_type(interface: str, interface_type: str = "") -> str:
    """Map a primary interface to a link profile identifier.

    ``interface_type`` is the coarse classification from
    ``network_event_bridge.detect_primary_interface`` ("modem", "wifi",
    "ethernet", "unknown"). VPN interfaces take precedence.
    """
    iface = (interface or "").lower()

    # VPN/tunnel interfaces (Tailscale, WireGuard, OpenVPN, PPP)
    if iface.startswith(("tailscale", "tun", "wg", "ppp", "zt")):
        return LINK_VPN

    if interface_type == "modem" or iface.startswith(("wwan", "usb", "enx", "eth1")):
        # Heuristic: cellular modems present as usb/wwan/enx or the Huawei eth1
        if interface_type == "modem":
            return LINK_MODEM
        if iface.startswith(("wwan", "enx")):
            return LINK_MODEM

    if interface_type in ("wifi", "ethernet") or iface.startswith(("wlan", "wl", "eth", "enp")):
        return LINK_LAN

    return LINK_LAN


def merge_profile_overrides(overrides: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Merge user overrides onto the defaults, keeping only known keys."""
    profiles = default_link_profiles()
    if not isinstance(overrides, dict):
        return profiles

    for name, values in overrides.items():
        if name not in profiles or not isinstance(values, dict):
            continue
        for key in profiles[name].keys():
            if key in ("name", "label"):
                continue
            if key in values:
                profiles[name][key] = values[key]
    return profiles
