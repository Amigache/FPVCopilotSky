"""Tests for the LinkProfileManager apply paths (services mocked)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.link_profile_manager import LinkProfileManager
from app.services.link_profiles import default_link_profiles


def make_prefs(settings=None):
    prefs = MagicMock()
    prefs.get_link_profiles.return_value = default_link_profiles()
    prefs.get_link_profile_settings.return_value = settings or {"mode": "auto", "forced": "", "auto_apply": True}
    prefs.get_all_preferences.return_value = {"network": {"link_profile_telemetry_apply": False}}
    return prefs


def make_gstreamer(mode="udp", width=1920, height=1080, framerate=30):
    svc = MagicMock()
    svc.is_streaming = True
    svc.video_config = SimpleNamespace(width=width, height=height, framerate=framerate, quality=85, h264_bitrate=2000)
    svc.streaming_config = SimpleNamespace(mode=mode)
    svc.update_live_property.return_value = {"success": True}
    svc.set_udp_buffer_size.return_value = True
    return svc


def test_apply_same_mode_updates_bitrate_live():
    manager = LinkProfileManager()
    gst = make_gstreamer(mode="udp", width=1920, height=1080, framerate=30)
    manager.set_services(gstreamer_service=gst)

    with patch("app.services.preferences.get_preferences", return_value=make_prefs()):
        result = asyncio.run(manager.apply_profile("lan"))

    assert result["success"] is True
    gst.update_live_property.assert_called_once_with("bitrate", 6000)
    gst.stop.assert_not_called()
    gst.start.assert_not_called()


def test_apply_different_mode_restarts_pipeline():
    manager = LinkProfileManager()
    gst = make_gstreamer(mode="udp", width=1920, height=1080, framerate=30)
    manager.set_services(gstreamer_service=gst)

    with patch("app.services.preferences.get_preferences", return_value=make_prefs()):
        result = asyncio.run(manager.apply_profile("modem"))

    assert result["success"] is True
    gst.configure.assert_called_once()
    gst.stop.assert_called_once()
    gst.start.assert_called_once()
    # Mode moved to webrtc in the configure call
    assert gst.configure.call_args.kwargs["streaming_config"] == {"mode": "webrtc"}


def test_telemetry_apply_calls_mavlink_when_enabled():
    manager = LinkProfileManager()
    gst = make_gstreamer()
    mav = MagicMock()
    mav.apply_telemetry_profile.return_value = {"success": True}
    manager.set_services(gstreamer_service=gst, mavlink_service=mav)
    manager._telemetry_apply = True

    with patch("app.services.preferences.get_preferences", return_value=make_prefs()):
        result = asyncio.run(manager.apply_profile("modem"))

    assert result["success"] is True
    mav.apply_telemetry_profile.assert_called_once_with("reduced")


def test_override_rejects_unknown_profile():
    manager = LinkProfileManager()
    result = asyncio.run(manager.set_override("bogus"))
    assert result["success"] is False
    assert "bogus" in result["message"]


def test_desired_profile_respects_manual_forced():
    manager = LinkProfileManager()
    manager._detected_link = "lan"
    assert manager._desired_profile({"mode": "auto", "forced": ""}) == "lan"
    assert manager._desired_profile({"mode": "manual", "forced": "modem"}) == "modem"
    # manual without forced falls back to detection
    assert manager._desired_profile({"mode": "manual", "forced": ""}) == "lan"
