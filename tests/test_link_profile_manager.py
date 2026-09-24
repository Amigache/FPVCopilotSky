"""Tests for the LinkProfileManager apply paths (services mocked)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.link_profile_manager import LinkProfileManager
from app.services.link_profiles import default_link_profiles


@pytest.fixture(autouse=True)
def mock_net_optimizer(monkeypatch):
    """Avoid touching the real NetworkOptimizer (runs ip/tc commands) in these tests."""
    optimizer = MagicMock()
    optimizer.apply_network_optimizations.return_value = {"success": True, "optimizations": ["mtu"]}
    optimizer.revert_network_optimizations.return_value = {"success": True}
    monkeypatch.setattr("app.services.network_optimizer.get_network_optimizer", lambda: optimizer)
    return optimizer


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
    svc.start.return_value = {"success": True, "message": "Streaming started"}
    return svc


def test_apply_same_mode_updates_bitrate_live():
    manager = LinkProfileManager()
    gst = make_gstreamer(mode="udp", width=1920, height=1080, framerate=30)
    manager.set_services(gstreamer_service=gst)
    manager._auto_apply_video = True  # streaming config is opt-in

    with patch("app.services.preferences.get_preferences", return_value=make_prefs()):
        result = asyncio.run(manager.apply_profile("lan"))

    assert result["success"] is True
    gst.update_live_property.assert_called_once_with("bitrate", 6000)
    gst.stop.assert_not_called()
    gst.start.assert_not_called()


def test_apply_different_mode_restarts_pipeline(monkeypatch):
    monkeypatch.setattr("app.services.link_profile_manager.time.sleep", lambda *_: None)
    manager = LinkProfileManager()
    gst = make_gstreamer(mode="udp", width=1920, height=1080, framerate=30)
    manager.set_services(gstreamer_service=gst)
    manager._auto_apply_video = True

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


def test_modem_profile_applies_network_optimization(monkeypatch, mock_net_optimizer):
    monkeypatch.setattr("app.services.link_profile_manager.time.sleep", lambda *_: None)
    manager = LinkProfileManager()
    manager.set_services(gstreamer_service=make_gstreamer())

    with patch("app.services.preferences.get_preferences", return_value=make_prefs()):
        asyncio.run(manager.apply_profile("modem"))

    mock_net_optimizer.apply_network_optimizations.assert_called_once()


def test_lan_profile_reverts_network_optimization_when_active(mock_net_optimizer):
    manager = LinkProfileManager()
    manager._net_optim_active = True
    manager.set_services(gstreamer_service=make_gstreamer(mode="udp"))

    with patch("app.services.preferences.get_preferences", return_value=make_prefs()):
        asyncio.run(manager.apply_profile("lan"))

    mock_net_optimizer.revert_network_optimizations.assert_called_once()


def test_restart_failure_is_reported_and_retried(monkeypatch):
    monkeypatch.setattr("app.services.link_profile_manager.time.sleep", lambda *_: None)
    manager = LinkProfileManager()
    gst = make_gstreamer(mode="udp")
    gst.start.return_value = {"success": False, "message": "boom"}
    manager.set_services(gstreamer_service=gst)
    manager._auto_apply_video = True

    with patch("app.services.preferences.get_preferences", return_value=make_prefs()):
        result = asyncio.run(manager.apply_profile("modem"))

    assert any("video-restart-failed" in action for action in result["actions"])
    assert gst.start.call_count == 3  # original + two retries


def test_profile_when_not_streaming_only_configures():
    manager = LinkProfileManager()
    gst = make_gstreamer()
    gst.is_streaming = False
    gst.set_udp_buffer_size.return_value = False  # no live pipeline
    manager.set_services(gstreamer_service=gst)
    manager._auto_apply_video = True

    with patch("app.services.preferences.get_preferences", return_value=make_prefs()):
        result = asyncio.run(manager.apply_profile("modem"))

    assert "video-config-only" in result["actions"]
    assert any(a.startswith("net-opt:applied") for a in result["actions"])
    gst.configure.assert_called_once()
    gst.start.assert_not_called()


def test_unsupported_resolution_keeps_current(monkeypatch):
    monkeypatch.setattr("app.services.link_profile_manager.time.sleep", lambda *_: None)
    manager = LinkProfileManager()
    gst = make_gstreamer(mode="udp", width=1920, height=1080, framerate=30)
    manager.set_services(gstreamer_service=gst)
    manager._auto_apply_video = True
    monkeypatch.setattr(manager, "_supported_resolutions", lambda device: {"3840x2160", "1920x1080"})

    with patch("app.services.preferences.get_preferences", return_value=make_prefs()):
        result = asyncio.run(manager.apply_profile("modem"))

    assert any(a.startswith("resolution-kept:1920x1080") for a in result["actions"])
    # It still switches mode (udp -> webrtc) but keeps 1080p capture
    assert gst.configure.call_args.kwargs["video_config"]["width"] == 1920
    assert gst.configure.call_args.kwargs["video_config"]["height"] == 1080


def test_video_is_user_managed_by_default():
    """By default the profile must NOT touch the user's streaming config."""
    manager = LinkProfileManager()
    gst = make_gstreamer(mode="udp", width=1920, height=1080, framerate=30)
    manager.set_services(gstreamer_service=gst)

    with patch("app.services.preferences.get_preferences", return_value=make_prefs()):
        result = asyncio.run(manager.apply_profile("modem"))

    assert "video:user-managed" in result["actions"]
    gst.update_live_property.assert_not_called()
    gst.configure.assert_not_called()
    gst.stop.assert_not_called()
    gst.start.assert_not_called()
