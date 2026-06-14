"""Tests for typed exception handling in critical routes."""

import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, Mock

from app.api.routes import modem as modem_routes
from app.api.routes import video as video_routes
from app.api.routes import vpn as vpn_routes


class MockRequest:
    def __init__(self, lang="en"):
        self.headers = {"accept-language": lang}
        self.query_params = {}
        self.cookies = {}


@pytest.mark.asyncio
async def test_get_available_providers_handles_registry_errors(monkeypatch):
    """Verify get_available_providers catches and sanitizes registry errors."""

    def raise_attribute_error():
        raise AttributeError("Registry misconfigured")

    monkeypatch.setattr("app.api.routes.modem.get_provider_registry", raise_attribute_error)

    with pytest.raises(HTTPException) as excinfo:
        await modem_routes.get_available_providers()

    assert excinfo.value.status_code == 500
    assert "Failed to retrieve" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_get_modem_status_handles_provider_errors(monkeypatch):
    """Verify get_modem_status catches provider-specific errors."""
    mock_registry = Mock()
    mock_registry.get_modem_provider.side_effect = TypeError("Invalid provider type")

    monkeypatch.setattr("app.api.routes.modem.get_provider_registry", lambda: mock_registry)

    with pytest.raises(HTTPException) as excinfo:
        await modem_routes.get_modem_status("huawei", MockRequest())

    assert excinfo.value.status_code == 500
    assert "Failed to get modem status" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_get_cameras_sanitizes_discovery_errors(monkeypatch):
    """Verify get_cameras hides internal errors from clients."""
    mock_registry = Mock()
    mock_registry.get_available_video_sources.side_effect = KeyError("missing_field")

    # Patch at the point of import within the function
    monkeypatch.setattr("app.providers.registry.get_provider_registry", lambda: mock_registry)

    # Mock the video service as present
    monkeypatch.setattr(video_routes, "_video_service", Mock())

    with pytest.raises(HTTPException) as excinfo:
        await video_routes.get_cameras(MockRequest())

    assert excinfo.value.status_code == 500
    assert "Failed to enumerate cameras" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_get_codecs_sanitizes_encoder_errors(monkeypatch):
    """Verify get_codecs hides internal errors from clients."""
    mock_registry = Mock()
    mock_registry.get_available_video_encoders.side_effect = AttributeError("encoder_list missing")

    # Patch at the point of import within the function
    monkeypatch.setattr("app.providers.registry.get_provider_registry", lambda: mock_registry)

    # Mock the video service as present
    monkeypatch.setattr(video_routes, "_video_service", Mock())

    with pytest.raises(HTTPException) as excinfo:
        await video_routes.get_codecs(MockRequest())

    assert excinfo.value.status_code == 500
    assert "Failed to enumerate codecs" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_get_vpn_providers_sanitizes_registry_errors(monkeypatch):
    """Verify VPN providers endpoint sanitizes registry failures."""

    def raise_registry_error():
        raise AttributeError("registry not initialized")

    monkeypatch.setattr("app.api.routes.vpn.get_provider_registry", raise_registry_error)

    with pytest.raises(HTTPException) as excinfo:
        await vpn_routes.get_providers()

    assert excinfo.value.status_code == 500
    assert "Failed to retrieve VPN providers" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_get_vpn_status_sanitizes_provider_errors(monkeypatch):
    """Verify VPN status endpoint hides provider internal errors."""
    mock_provider = Mock()
    mock_provider.get_status.side_effect = RuntimeError("status call failed")

    monkeypatch.setattr("app.api.routes.vpn._get_vpn_provider", lambda _provider, _lang: mock_provider)

    with pytest.raises(HTTPException) as excinfo:
        await vpn_routes.get_status(MockRequest(), provider="tailscale")

    assert excinfo.value.status_code == 500
    assert "Failed to retrieve VPN status" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_get_vpn_peers_sanitizes_provider_errors(monkeypatch):
    """Verify VPN peers endpoint hides provider internal errors."""
    mock_provider = Mock()
    mock_provider.get_peers.side_effect = TypeError("peer payload invalid")

    monkeypatch.setattr("app.api.routes.vpn._get_vpn_provider", lambda _provider, _lang: mock_provider)

    with pytest.raises(HTTPException) as excinfo:
        await vpn_routes.get_peers(MockRequest(), provider="tailscale")

    assert excinfo.value.status_code == 500
    assert "Failed to retrieve VPN peers" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_get_vpn_status_returns_neutral_payload_on_missing_provider(monkeypatch):
    """Verify VPN status returns neutral payload for 400/503 provider errors."""
    monkeypatch.setattr(
        "app.api.routes.vpn._get_vpn_provider",
        lambda _provider, _lang: (_ for _ in ()).throw(HTTPException(status_code=400, detail="no provider")),
    )

    response = await vpn_routes.get_status(MockRequest(), provider=None)

    assert response["success"] is False
    assert response["installed"] is False
    assert response["connected"] is False
    assert response["authenticated"] is False
    assert response["provider"] is None


@pytest.mark.asyncio
async def test_connect_vpn_sanitizes_provider_errors(monkeypatch):
    """Verify connect endpoint hides provider internal errors."""
    mock_provider = Mock()
    mock_provider.connect.side_effect = RuntimeError("connect pipeline crashed")

    monkeypatch.setattr("app.api.routes.vpn._get_vpn_provider", lambda _provider, _lang: mock_provider)

    with pytest.raises(HTTPException) as excinfo:
        await vpn_routes.connect_vpn(vpn_routes.VPNConnectRequest(provider="tailscale"), MockRequest())

    assert excinfo.value.status_code == 500
    assert "Failed to connect VPN" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_disconnect_vpn_sanitizes_provider_errors(monkeypatch):
    """Verify disconnect endpoint hides provider internal errors."""
    mock_provider = Mock()
    mock_provider.disconnect.side_effect = TypeError("disconnect payload invalid")

    monkeypatch.setattr("app.api.routes.vpn._get_vpn_provider", lambda _provider, _lang: mock_provider)

    with pytest.raises(HTTPException) as excinfo:
        await vpn_routes.disconnect_vpn(vpn_routes.VPNDisconnectRequest(provider="tailscale"), MockRequest())

    assert excinfo.value.status_code == 500
    assert "Failed to disconnect VPN" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_logout_vpn_sanitizes_provider_errors(monkeypatch):
    """Verify logout endpoint hides provider internal errors."""
    mock_provider = Mock()
    mock_provider.logout.side_effect = AttributeError("logout handler missing")

    monkeypatch.setattr("app.api.routes.vpn._get_vpn_provider", lambda _provider, _lang: mock_provider)

    with pytest.raises(HTTPException) as excinfo:
        await vpn_routes.logout_vpn(vpn_routes.VPNDisconnectRequest(provider="tailscale"), MockRequest())

    assert excinfo.value.status_code == 500
    assert "Failed to logout VPN" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_configure_streaming_sanitizes_service_errors(monkeypatch):
    """Verify configure_streaming hides internal service errors."""
    mock_video_service = Mock()
    mock_video_service.configure.side_effect = RuntimeError("pipeline reconfigure failed")

    monkeypatch.setattr(video_routes, "_video_service", mock_video_service)

    req = video_routes.StreamingConfigRequest(mode="udp")
    with pytest.raises(HTTPException) as excinfo:
        await video_routes.configure_streaming(req, MockRequest())

    assert excinfo.value.status_code == 500
    assert "Failed to update streaming configuration" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_live_update_sanitizes_service_errors(monkeypatch):
    """Verify live_update hides internal service errors."""
    mock_video_service = Mock()
    mock_video_service.update_live_property.side_effect = TypeError("invalid live property payload")

    monkeypatch.setattr(video_routes, "_video_service", mock_video_service)

    req = video_routes.LivePropertyRequest(property="h264_bitrate", value=2500)
    with pytest.raises(HTTPException) as excinfo:
        await video_routes.live_update(req, MockRequest())

    assert excinfo.value.status_code == 500
    assert "Failed to apply live update" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_connect_modem_sanitizes_provider_errors(monkeypatch):
    """Verify connect_modem hides provider internal errors."""
    mock_provider = Mock()
    mock_provider.connect.side_effect = RuntimeError("connect failed internally")

    mock_registry = Mock()
    mock_registry.get_modem_provider.return_value = mock_provider

    monkeypatch.setattr("app.api.routes.modem.get_provider_registry", lambda: mock_registry)

    with pytest.raises(HTTPException) as excinfo:
        await modem_routes.connect_modem("huawei", MockRequest())

    assert excinfo.value.status_code == 500
    assert "Failed to connect modem" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_disconnect_modem_sanitizes_provider_errors(monkeypatch):
    """Verify disconnect_modem hides provider internal errors."""
    mock_provider = Mock()
    mock_provider.disconnect.side_effect = TypeError("disconnect internal type error")

    mock_registry = Mock()
    mock_registry.get_modem_provider.return_value = mock_provider

    monkeypatch.setattr("app.api.routes.modem.get_provider_registry", lambda: mock_registry)

    with pytest.raises(HTTPException) as excinfo:
        await modem_routes.disconnect_modem("huawei", MockRequest())

    assert excinfo.value.status_code == 500
    assert "Failed to disconnect modem" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_get_modem_info_sanitizes_provider_errors(monkeypatch):
    """Verify get_modem_info hides provider internal errors."""
    mock_provider = Mock()
    mock_provider.get_info.side_effect = AttributeError("info adapter missing")

    mock_registry = Mock()
    mock_registry.get_modem_provider.return_value = mock_provider

    monkeypatch.setattr("app.api.routes.modem.get_provider_registry", lambda: mock_registry)

    with pytest.raises(HTTPException) as excinfo:
        await modem_routes.get_modem_info("huawei", MockRequest())

    assert excinfo.value.status_code == 500
    assert "Failed to get modem info" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_get_modem_signal_sanitizes_provider_errors(monkeypatch):
    """Verify get_modem_signal hides provider internal errors."""
    mock_provider = Mock()
    mock_provider.async_get_signal_info = AsyncMock(side_effect=RuntimeError("signal probe failed"))

    mock_registry = Mock()
    mock_registry.get_modem_provider.return_value = mock_provider

    monkeypatch.setattr("app.api.routes.modem.get_provider_registry", lambda: mock_registry)

    with pytest.raises(HTTPException) as excinfo:
        await modem_routes.get_modem_signal("huawei", MockRequest())

    assert excinfo.value.status_code == 500
    assert "Failed to get signal info" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_get_modem_network_sanitizes_provider_errors(monkeypatch):
    """Verify get_modem_network hides provider internal errors."""
    mock_provider = Mock()
    mock_provider.async_get_network_info = AsyncMock(side_effect=TypeError("network payload invalid"))

    mock_registry = Mock()
    mock_registry.get_modem_provider.return_value = mock_provider

    monkeypatch.setattr("app.api.routes.modem.get_provider_registry", lambda: mock_registry)

    with pytest.raises(HTTPException) as excinfo:
        await modem_routes.get_modem_network("huawei", MockRequest())

    assert excinfo.value.status_code == 500
    assert "Failed to get network info" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_get_modem_traffic_sanitizes_provider_errors(monkeypatch):
    """Verify get_modem_traffic hides provider internal errors."""
    mock_provider = Mock()
    mock_provider.async_get_traffic_stats = AsyncMock(side_effect=AttributeError("traffic collector missing"))

    mock_registry = Mock()
    mock_registry.get_modem_provider.return_value = mock_provider

    monkeypatch.setattr("app.api.routes.modem.get_provider_registry", lambda: mock_registry)

    with pytest.raises(HTTPException) as excinfo:
        await modem_routes.get_modem_traffic("huawei", MockRequest())

    assert excinfo.value.status_code == 500
    assert "Failed to get traffic stats" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_get_modem_mode_sanitizes_provider_errors(monkeypatch):
    """Verify get_modem_mode hides provider internal errors."""
    mock_provider = Mock()
    mock_provider.get_network_mode = Mock(side_effect=RuntimeError("mode query failed"))

    mock_registry = Mock()
    mock_registry.get_modem_provider.return_value = mock_provider

    monkeypatch.setattr("app.api.routes.modem.get_provider_registry", lambda: mock_registry)

    with pytest.raises(HTTPException) as excinfo:
        await modem_routes.get_modem_mode("huawei", MockRequest())

    assert excinfo.value.status_code == 500
    assert "Failed to get network mode" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_get_current_band_sanitizes_provider_errors(monkeypatch):
    """Verify get_current_band hides provider internal errors."""
    mock_provider = Mock()
    mock_provider.get_current_band = Mock(side_effect=TypeError("band data invalid"))

    mock_registry = Mock()
    mock_registry.get_modem_provider.return_value = mock_provider

    monkeypatch.setattr("app.api.routes.modem.get_provider_registry", lambda: mock_registry)

    with pytest.raises(HTTPException) as excinfo:
        await modem_routes.get_current_band("huawei", MockRequest())

    assert excinfo.value.status_code == 500
    assert "Failed to get band info" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_get_band_presets_sanitizes_provider_errors(monkeypatch):
    """Verify get_band_presets hides provider internal errors."""
    mock_provider = Mock()
    mock_provider.get_band_presets = Mock(side_effect=AttributeError("presets adapter missing"))

    mock_registry = Mock()
    mock_registry.get_modem_provider.return_value = mock_provider

    monkeypatch.setattr("app.api.routes.modem.get_provider_registry", lambda: mock_registry)

    with pytest.raises(HTTPException) as excinfo:
        await modem_routes.get_band_presets("huawei", MockRequest())

    assert excinfo.value.status_code == 500
    assert "Failed to get band presets" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_set_modem_mode_sanitizes_provider_errors(monkeypatch):
    """Verify set_modem_mode hides provider internal errors."""
    from app.api.routes.modem import NetworkModeRequest

    mock_provider = Mock()
    mock_provider.set_network_mode = Mock(side_effect=ValueError("invalid mode value"))

    mock_registry = Mock()
    mock_registry.get_modem_provider.return_value = mock_provider

    monkeypatch.setattr("app.api.routes.modem.get_provider_registry", lambda: mock_registry)

    mode_request = NetworkModeRequest(mode="00")
    with pytest.raises(HTTPException) as excinfo:
        await modem_routes.set_modem_mode("huawei", mode_request, MockRequest())

    assert excinfo.value.status_code == 500
    assert "Failed to set network mode" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_set_lte_band_sanitizes_provider_errors(monkeypatch):
    """Verify set_lte_band hides provider internal errors."""
    from app.api.routes.modem import LTEBandRequest

    mock_provider = Mock()
    mock_provider.set_lte_band = Mock(side_effect=RuntimeError("band config failed"))

    mock_registry = Mock()
    mock_registry.get_modem_provider.return_value = mock_provider

    monkeypatch.setattr("app.api.routes.modem.get_provider_registry", lambda: mock_registry)

    band_request = LTEBandRequest(preset="all", custom_mask=None)
    with pytest.raises(HTTPException) as excinfo:
        await modem_routes.set_lte_band("huawei", band_request, MockRequest())

    assert excinfo.value.status_code == 500
    assert "Failed to set band" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_set_apn_sanitizes_provider_errors(monkeypatch):
    """Verify set_apn hides provider internal errors."""
    from app.api.routes.modem import APNRequest

    mock_provider = Mock()
    mock_provider.set_apn = Mock(side_effect=TypeError("apn type mismatch"))

    mock_registry = Mock()
    mock_registry.get_modem_provider.return_value = mock_provider

    monkeypatch.setattr("app.api.routes.modem.get_provider_registry", lambda: mock_registry)

    apn_request = APNRequest(preset="orange", custom_apn=None)
    with pytest.raises(HTTPException) as excinfo:
        await modem_routes.set_apn("huawei", apn_request, MockRequest())

    assert excinfo.value.status_code == 500
    assert "Failed to set APN" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_reconnect_network_sanitizes_provider_errors(monkeypatch):
    """Verify reconnect_network hides provider internal errors."""
    mock_provider = Mock()
    mock_provider.reconnect_network = Mock(side_effect=AttributeError("reconnect method missing"))

    mock_registry = Mock()
    mock_registry.get_modem_provider.return_value = mock_provider

    monkeypatch.setattr("app.api.routes.modem.get_provider_registry", lambda: mock_registry)

    with pytest.raises(HTTPException) as excinfo:
        await modem_routes.reconnect_network("huawei", MockRequest())

    assert excinfo.value.status_code == 500
    assert "Failed to reconnect network" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_start_streaming_sanitizes_service_errors(monkeypatch):
    """Verify start_streaming hides service internal errors."""
    mock_service = Mock()
    mock_service.start = Mock(side_effect=RuntimeError("GStreamer initialization failed"))

    monkeypatch.setattr("app.api.routes.video._video_service", mock_service)

    with pytest.raises(HTTPException) as excinfo:
        await video_routes.start_streaming(MockRequest())

    assert excinfo.value.status_code == 500
    assert "Failed to start video streaming" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_stop_streaming_sanitizes_service_errors(monkeypatch):
    """Verify stop_streaming hides service internal errors."""
    mock_service = Mock()
    mock_service.stop = Mock(side_effect=TypeError("pipeline cleanup type error"))

    monkeypatch.setattr("app.api.routes.video._video_service", mock_service)

    with pytest.raises(HTTPException) as excinfo:
        await video_routes.stop_streaming(MockRequest())

    assert excinfo.value.status_code == 500
    assert "Failed to stop video streaming" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_restart_streaming_sanitizes_service_errors(monkeypatch):
    """Verify restart_streaming hides service internal errors."""
    mock_service = Mock()
    mock_service.restart = Mock(side_effect=AttributeError("restart method missing"))

    monkeypatch.setattr("app.api.routes.video._video_service", mock_service)

    with pytest.raises(HTTPException) as excinfo:
        await video_routes.restart_streaming(MockRequest())

    assert excinfo.value.status_code == 500
    assert "Failed to restart video streaming" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_configure_video_sanitizes_service_errors(monkeypatch):
    """Verify configure_video hides service internal errors."""
    from app.api.routes.video import VideoConfigRequest

    mock_service = Mock()
    mock_service.configure = Mock(side_effect=ValueError("invalid config parameter"))

    monkeypatch.setattr("app.api.routes.video._video_service", mock_service)

    config = VideoConfigRequest(width=1280, height=720)
    with pytest.raises(HTTPException) as excinfo:
        await video_routes.configure_video(config, MockRequest())

    assert excinfo.value.status_code == 500
    assert "Failed to update video configuration" in str(excinfo.value.detail)
