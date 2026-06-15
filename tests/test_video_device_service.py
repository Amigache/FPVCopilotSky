import types
from unittest.mock import MagicMock

import pytest

from app.services.video_device_service import VideoDeviceService
import app.services.video_device_service as video_device_module


class _Provider:
    def __init__(self, name: str, available: bool = True):
        self.display_name = name
        self._available = available

    def is_available(self):
        return self._available


def _patch_preferences(monkeypatch, active_device: str = ""):
    prefs_module = __import__("app.services.preferences", fromlist=["get_preferences"])
    prefs = types.SimpleNamespace(get_all_preferences=lambda: {"video": {"device": active_device}})
    monkeypatch.setattr(prefs_module, "get_preferences", lambda: prefs)


def _patch_registry(monkeypatch, registry):
    registry_module = __import__("app.providers.registry", fromlist=["get_provider_registry"])
    monkeypatch.setattr(registry_module, "get_provider_registry", lambda: registry)


def test_scan_devices_builds_inventory_and_marks_active(monkeypatch):
    _patch_preferences(monkeypatch, active_device="/dev/video0")

    registry = types.SimpleNamespace(
        list_video_source_providers=lambda: ["v4l2", "libcamera"],
        get_video_source=lambda source_type: _Provider(source_type.upper(), available=True),
        discover_sources_cached=lambda source_type: [
            {
                "source_id": f"{source_type}-0",
                "name": "Camera 0",
                "device": "/dev/video0",
                "provider": source_type,
                "capabilities": {
                    "identity": {"bus_info": "usb-1", "driver": "uvcvideo", "name": "Camera 0"},
                    "supported_formats": ["YUYV", "MJPG"],
                    "format_resolutions": {"YUYV": ["1280x720"]},
                    "supported_resolutions": ["1280x720"],
                    "supported_framerates": {"1280x720": [30]},
                    "hardware_encoding": False,
                    "is_usb": True,
                },
            }
        ],
        get_available_video_encoders=lambda: [
            {
                "codec_id": "x264",
                "display_name": "x264",
                "codec_family": "h264",
                "encoder_type": "software",
                "available": True,
                "capabilities": {},
            }
        ],
    )
    _patch_registry(monkeypatch, registry)

    service = VideoDeviceService()
    devices = service.scan_devices()

    # Second provider reports same physical device and is deduplicated by bus_info+name.
    assert len(devices) == 1
    assert devices[0]["device_id"].startswith("v4l2:")
    assert devices[0]["is_active"] is True
    assert devices[0]["compatible_codecs"][0]["compatible"] is True


def test_scan_devices_returns_cached_when_scan_in_progress():
    service = VideoDeviceService()
    service._scanning = True
    service._devices = [{"device_id": "cached"}]

    assert service.scan_devices() == [{"device_id": "cached"}]


def test_scan_devices_handles_provider_unavailable_and_discovery_errors(monkeypatch):
    _patch_preferences(monkeypatch, active_device="")

    provider_ok = _Provider("OK", available=True)
    provider_down = _Provider("DOWN", available=False)

    def discover(source_type):
        if source_type == "ok":
            return [
                {
                    "source_id": "ok-1",
                    "name": "Cam",
                    "device": "/dev/video1",
                    "capabilities": {"identity": {}, "supported_formats": ["H264"]},
                }
            ]
        raise RuntimeError("scan failed")

    registry = types.SimpleNamespace(
        list_video_source_providers=lambda: ["ok", "bad", "down"],
        get_video_source=lambda source_type: {"ok": provider_ok, "bad": provider_ok, "down": provider_down}.get(
            source_type
        ),
        discover_sources_cached=discover,
        get_available_video_encoders=lambda: [],
    )
    _patch_registry(monkeypatch, registry)

    service = VideoDeviceService()
    devices = service.scan_devices()

    assert len(devices) == 1
    assert devices[0]["source_id"] == "ok-1"


def test_get_devices_scans_first_time_and_respects_ttl(monkeypatch):
    service = VideoDeviceService()

    call_counter = {"count": 0}
    fake_now = {"value": 0.0}

    monkeypatch.setattr("time.time", lambda: fake_now["value"])

    def fake_scan():
        call_counter["count"] += 1
        service._devices = [{"device_id": f"cam-{call_counter['count']}"}]
        service._scan_timestamp = call_counter["count"] * 10.0
        return service._devices

    monkeypatch.setattr(service, "scan_devices", fake_scan)

    assert service.get_devices() == [{"device_id": "cam-1"}]
    assert service.get_devices() == [{"device_id": "cam-1"}]

    fake_now["value"] = 100.0
    service._scan_timestamp = 0.0
    service._cache_ttl = 30.0

    assert service.get_devices() == [{"device_id": "cam-2"}]


def test_invalidate_cache_resets_timestamp_and_registry_cache(monkeypatch):
    registry = types.SimpleNamespace(invalidate_source_cache=MagicMock())
    _patch_registry(monkeypatch, registry)

    service = VideoDeviceService()
    service._scan_timestamp = 123.0

    service.invalidate_cache()

    assert service._scan_timestamp is None
    registry.invalidate_source_cache.assert_called_once()


def test_get_device_by_id_returns_match(monkeypatch):
    service = VideoDeviceService()
    monkeypatch.setattr(service, "get_devices", lambda: [{"device_id": "v4l2:/dev/video0"}])

    assert service.get_device_by_id("v4l2:/dev/video0") == {"device_id": "v4l2:/dev/video0"}
    assert service.get_device_by_id("missing") is None


def test_get_scan_info_returns_metadata(monkeypatch):
    service = VideoDeviceService()
    service._scan_timestamp = 42.0
    service._scanning = False
    monkeypatch.setattr(service, "get_devices", lambda: [{"device_id": "cam"}])

    info = service.get_scan_info()

    assert info["count"] == 1
    assert info["scan_timestamp"] == 42.0
    assert info["scanning"] is False


def test_get_active_device_handles_preferences_errors(monkeypatch):
    prefs_module = __import__("app.services.preferences", fromlist=["get_preferences"])
    monkeypatch.setattr(prefs_module, "get_preferences", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    service = VideoDeviceService()

    assert service._get_active_device() == ""


def test_get_compatible_codecs_covers_reason_paths(monkeypatch):
    registry = types.SimpleNamespace(
        get_available_video_encoders=lambda: [
            {
                "codec_id": "h264_passthrough",
                "display_name": "H264 passthrough",
                "codec_family": "h264",
                "encoder_type": "passthrough",
                "available": True,
                "capabilities": {"requires_h264_source": True},
            },
            {
                "codec_id": "h264_hw",
                "display_name": "H264 HW",
                "codec_family": "h264",
                "encoder_type": "hardware",
                "available": True,
                "capabilities": {},
            },
            {
                "codec_id": "x264",
                "display_name": "x264",
                "codec_family": "h264",
                "encoder_type": "software",
                "available": True,
                "capabilities": {},
            },
            {
                "codec_id": "disabled",
                "display_name": "disabled",
                "codec_family": "h264",
                "encoder_type": "software",
                "available": False,
                "capabilities": {},
            },
        ]
    )
    _patch_registry(monkeypatch, registry)

    service = VideoDeviceService()
    codecs_no_h264 = service._get_compatible_codecs(["YUYV"])
    codecs_h264 = service._get_compatible_codecs(["H264"])

    passthrough_no_h264 = [c for c in codecs_no_h264 if c["codec_id"] == "h264_passthrough"][0]
    passthrough_h264 = [c for c in codecs_h264 if c["codec_id"] == "h264_passthrough"][0]

    assert passthrough_no_h264["compatible"] is False
    assert passthrough_no_h264["reason"] == "requires_h264"
    assert passthrough_h264["compatible"] is True
    assert passthrough_h264["reason"] == "passthrough"
    assert any(c["reason"] == "hardware" for c in codecs_no_h264 if c["codec_id"] == "h264_hw")
    assert any(c["reason"] == "software" for c in codecs_no_h264 if c["codec_id"] == "x264")


def test_get_compatible_codecs_returns_empty_on_registry_error(monkeypatch):
    registry_module = __import__("app.providers.registry", fromlist=["get_provider_registry"])
    monkeypatch.setattr(registry_module, "get_provider_registry", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    service = VideoDeviceService()

    assert service._get_compatible_codecs(["YUYV"]) == []


def test_scan_devices_skips_missing_and_handles_availability_exception(monkeypatch):
    _patch_preferences(monkeypatch, active_device="")

    class _ExplodingProvider:
        display_name = "boom"

        def is_available(self):
            raise RuntimeError("not ready")

    registry = types.SimpleNamespace(
        list_video_source_providers=lambda: ["missing", "exploding"],
        get_video_source=lambda source_type: None if source_type == "missing" else _ExplodingProvider(),
        discover_sources_cached=lambda _source_type: [],
        get_available_video_encoders=lambda: [],
    )
    _patch_registry(monkeypatch, registry)

    service = VideoDeviceService()
    assert service.scan_devices() == []


def test_scan_devices_handles_outer_exception(monkeypatch):
    _patch_preferences(monkeypatch, active_device="")

    registry = types.SimpleNamespace(
        list_video_source_providers=lambda: (_ for _ in ()).throw(RuntimeError("registry down")),
    )
    _patch_registry(monkeypatch, registry)

    service = VideoDeviceService()
    assert service.scan_devices() == []


def test_invalidate_cache_swallows_registry_errors(monkeypatch):
    registry = types.SimpleNamespace(
        invalidate_source_cache=MagicMock(side_effect=RuntimeError("boom")),
    )
    _patch_registry(monkeypatch, registry)

    service = VideoDeviceService()
    service.invalidate_cache()


def test_get_compatible_codecs_uses_encode_reason_for_custom_encoder(monkeypatch):
    registry = types.SimpleNamespace(
        get_available_video_encoders=lambda: [
            {
                "codec_id": "custom",
                "display_name": "Custom",
                "codec_family": "h264",
                "encoder_type": "fpga",
                "available": True,
                "capabilities": {},
            }
        ]
    )
    _patch_registry(monkeypatch, registry)

    service = VideoDeviceService()
    codecs = service._get_compatible_codecs(["YUYV"])

    assert codecs[0]["reason"] == "encode"


def test_get_video_device_service_singleton_instance():
    video_device_module._video_device_service = None

    instance_a = video_device_module.get_video_device_service()
    instance_b = video_device_module.get_video_device_service()

    assert instance_a is instance_b
