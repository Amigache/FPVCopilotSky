"""Tests for link profiles: classification, defaults and overrides."""

from app.services.link_profiles import (
    classify_link_type,
    default_link_profiles,
    merge_profile_overrides,
    LINK_LAN,
    LINK_MODEM,
    LINK_VPN,
)


class TestClassifyLinkType:
    def test_tailscale_is_vpn(self):
        assert classify_link_type("tailscale0", "unknown") == LINK_VPN

    def test_wireguard_is_vpn(self):
        assert classify_link_type("wg0", "") == LINK_VPN

    def test_wifi_is_lan(self):
        assert classify_link_type("wlan0", "wifi") == LINK_LAN

    def test_ethernet_is_lan(self):
        assert classify_link_type("eth0", "ethernet") == LINK_LAN

    def test_modem_by_type(self):
        assert classify_link_type("eth1", "modem") == LINK_MODEM

    def test_wwan_is_modem(self):
        assert classify_link_type("wwan0", "") == LINK_MODEM

    def test_unknown_defaults_to_lan(self):
        assert classify_link_type("", "unknown") == LINK_LAN


class TestDefaultProfiles:
    def test_contains_expected_profiles(self):
        profiles = default_link_profiles()
        assert set(profiles.keys()) == {LINK_LAN, LINK_MODEM, LINK_VPN}

    def test_modem_uses_reduced_telemetry_and_webrtc(self):
        modem = default_link_profiles()[LINK_MODEM]
        assert modem["telemetry"] == "reduced"
        assert modem["video_mode"] == "webrtc"
        assert modem["h264_bitrate"] <= 3000

    def test_vpn_mtu_is_small(self):
        assert default_link_profiles()[LINK_VPN]["mtu"] == 1280


class TestMergeOverrides:
    def test_override_known_key(self):
        merged = merge_profile_overrides({"lan": {"h264_bitrate": 1234}})
        assert merged["lan"]["h264_bitrate"] == 1234
        # Other keys keep their default
        assert merged["lan"]["video_mode"] == "udp"

    def test_unknown_keys_ignored(self):
        merged = merge_profile_overrides({"lan": {"does_not_exist": 1}, "bogus": {"a": 1}})
        assert "does_not_exist" not in merged["lan"]
        assert "bogus" not in merged

    def test_non_dict_input_returns_defaults(self):
        assert merge_profile_overrides(None) == default_link_profiles()
