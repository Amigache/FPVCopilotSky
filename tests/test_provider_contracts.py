"""Provider contract conformance tests for Issue #35.

Covers one concrete provider per required family:
- modem
- vpn
- video_source
- video_encoder

Use PROVIDER_TYPE env var to run a single family in CI matrix.
"""

import os

import pytest


def _is_selected(provider_type: str) -> bool:
    selected = os.getenv("PROVIDER_TYPE", "").strip().lower()
    return not selected or selected == provider_type


@pytest.mark.contract
def test_modem_provider_contract(monkeypatch):
    if not _is_selected("modem"):
        pytest.skip("Matrix filtered for another provider type")

    import app.providers.modem.router as router_modem_module
    from app.providers.base.modem_provider import ModemProvider

    def fake_run_cmd(cmd, timeout=10, check=False):
        if cmd[:2] == ["ping", "-c"]:
            return "", "", 0
        return "", "", 0

    monkeypatch.setattr(router_modem_module, "run_cmd", fake_run_cmd)

    provider = router_modem_module.RouterModemProvider()

    assert isinstance(provider, ModemProvider)
    assert provider.name
    assert provider.display_name

    status = provider.get_status()
    assert isinstance(status, dict)
    assert "available" in status
    assert "status" in status

    connect_result = provider.connect()
    disconnect_result = provider.disconnect()
    band_result = provider.configure_band(0x1)
    reboot_result = provider.reboot()

    for result in (connect_result, disconnect_result, band_result, reboot_result):
        assert isinstance(result, dict)
        assert "success" in result

    assert provider.get_modem_info() is not None
    assert provider.get_network_info() is not None


@pytest.mark.contract
def test_vpn_provider_contract(monkeypatch):
    if not _is_selected("vpn"):
        pytest.skip("Matrix filtered for another provider type")

    import app.providers.vpn.tailscale as tailscale_module
    from app.providers.base.vpn_provider import VPNProvider

    def fake_run_cmd(cmd, timeout=10, check=False):
        if cmd == ["which", "tailscale"]:
            return "/usr/bin/tailscale\n", "", 0
        if cmd == ["tailscale", "status", "--json"]:
            return (
                '{"BackendState":"Running","Self":{"Online":true,"Active":true,'
                '"TailscaleIPs":["100.64.0.10"],"HostName":"fpv"},"Peer":{}}',
                "",
                0,
            )
        if cmd == ["ip", "link", "show"]:
            return "1: lo\n10: tailscale0: <BROADCAST>\n", "", 0
        if cmd == ["systemctl", "is-active", "tailscaled"]:
            return "active\n", "", 0
        if cmd in (["sudo", "tailscale", "down"], ["timeout", "10", "sudo", "-n", "tailscale", "up"]):
            return "", "", 0
        return "", "", 0

    monkeypatch.setattr(tailscale_module, "run_cmd", fake_run_cmd)

    provider = tailscale_module.TailscaleProvider()

    assert isinstance(provider, VPNProvider)
    assert provider.name
    assert provider.display_name
    assert provider.is_installed() is True

    status = provider.get_status()
    assert isinstance(status, dict)
    assert "installed" in status

    connect_result = provider.connect()
    disconnect_result = provider.disconnect()
    info = provider.get_info()
    peers = provider.get_peers()

    assert isinstance(connect_result, dict)
    assert "success" in connect_result
    assert isinstance(disconnect_result, dict)
    assert "success" in disconnect_result
    assert isinstance(info, dict)
    assert "name" in info
    assert isinstance(peers, list)


@pytest.mark.contract
def test_video_source_provider_contract(monkeypatch):
    if not _is_selected("video_source"):
        pytest.skip("Matrix filtered for another provider type")

    import app.providers.video_source.v4l2_camera as v4l2_module
    from app.providers.base.video_source_provider import VideoSourceProvider

    def fake_glob(_pattern):
        return ["/dev/video0"]

    def fake_run_cmd(cmd, timeout=10, check=False):
        if cmd == ["which", "v4l2-ctl"]:
            return "/usr/bin/v4l2-ctl\n", "", 0
        if cmd[:4] == ["v4l2-ctl", "-d", "/dev/video0", "--info"]:
            return "Card type: USB Cam\nDriver name: uvcvideo\nBus info: usb-1\nCapabilities: Video Capture\n", "", 0
        if cmd[:4] == ["v4l2-ctl", "-d", "/dev/video0", "--list-formats-ext"]:
            return (
                "[0]: 'MJPG' (Motion-JPEG)\n"
                "  Size: Discrete 1280x720\n"
                "    Interval: Discrete 0.033s (30.000 fps)\n",
                "",
                0,
            )
        if cmd[:4] == ["v4l2-ctl", "-d", "/dev/video0", "--list-ctrls"]:
            return "brightness 0x00980900 (int) : min=0 max=200 step=1 default=100 value=100\n", "", 0
        if cmd[:3] == ["v4l2-ctl", "-d", "/dev/video0"]:
            return "", "", 0
        return "", "", 0

    monkeypatch.setattr(v4l2_module.glob, "glob", fake_glob)
    monkeypatch.setattr(v4l2_module, "run_cmd", fake_run_cmd)

    provider = v4l2_module.V4L2CameraSource()

    assert isinstance(provider, VideoSourceProvider)
    assert provider.source_type
    assert provider.display_name
    assert provider.gst_source_element
    assert provider.is_available() is True

    sources = provider.discover_sources()
    assert isinstance(sources, list)
    assert sources
    assert "source_id" in sources[0]

    source_id = sources[0]["source_id"]
    caps = provider.get_source_capabilities(source_id)
    assert isinstance(caps, dict)
    assert "supported_formats" in caps

    pipeline = provider.build_source_element(source_id, {"width": 1280, "height": 720, "framerate": 30})
    assert isinstance(pipeline, dict)
    assert "success" in pipeline

    validation = provider.validate_config(source_id, {"width": 1280, "height": 720, "framerate": 30})
    assert isinstance(validation, dict)
    assert "valid" in validation


@pytest.mark.contract
def test_video_encoder_provider_contract(monkeypatch):
    if not _is_selected("video_encoder"):
        pytest.skip("Matrix filtered for another provider type")

    import app.providers.video.x264_encoder as x264_module
    from app.providers.base.video_encoder_provider import VideoEncoderProvider

    monkeypatch.setattr(x264_module, "is_gst_element_available", lambda _name: True)
    x264_module._v4l2jpegdec_available = None

    provider = x264_module.X264Encoder()

    assert isinstance(provider, VideoEncoderProvider)
    assert provider.codec_id
    assert provider.display_name
    assert provider.gst_encoder_element

    assert provider.is_available() is True

    capabilities = provider.get_capabilities()
    assert isinstance(capabilities, dict)
    assert capabilities.get("available") is True

    pipeline = provider.build_pipeline_elements({"width": 1280, "height": 720, "framerate": 30, "bitrate": 2000})
    assert isinstance(pipeline, dict)
    assert pipeline.get("success") is True
    assert isinstance(pipeline.get("elements"), list)

    live_props = provider.get_live_adjustable_properties()
    assert isinstance(live_props, dict)
    assert "bitrate" in live_props
