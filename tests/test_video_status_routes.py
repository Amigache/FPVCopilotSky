"""Tests for video status routes (read-only endpoints)"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import HTTPException

from app.api.routes import video_status


@pytest.fixture
def mock_video_service():
    """Create a mock video service"""
    service = MagicMock()
    service.get_status = MagicMock(
        return_value={
            "streaming": True,
            "device": "/dev/video0",
            "codec": "h264",
        }
    )
    service.stats_lock = MagicMock()
    service.stats = {"frames_sent": 100, "current_fps": 30}
    service.encoder_stats = {"frames_encoded": 100, "keyframes_sent": 3}
    service.video_config = MagicMock(framerate=30)
    service.is_streaming = True
    service._calculate_health = MagicMock(return_value={"status": "healthy"})
    return service


def test_set_video_service(mock_video_service):
    """Test setting video service"""
    video_status.set_video_service(mock_video_service)
    assert video_status._video_service == mock_video_service


@pytest.mark.asyncio
async def test_get_status_with_service(mock_video_service):
    """Test GET /status endpoint with service"""
    video_status.set_video_service(mock_video_service)

    mock_request = MagicMock()
    result = await video_status.get_status(mock_request)

    assert result["streaming"] is True
    mock_video_service.get_status.assert_called_once()


@pytest.mark.asyncio
async def test_get_status_without_service():
    """Test GET /status endpoint without service"""
    video_status._video_service = None

    mock_request = MagicMock()
    with pytest.raises(HTTPException) as exc_info:
        await video_status.get_status(mock_request)

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_get_stats_with_service(mock_video_service):
    """Test GET /stats endpoint with service"""
    video_status.set_video_service(mock_video_service)

    # Mock context manager for stats_lock
    video_status._video_service.stats_lock.__enter__ = MagicMock()
    video_status._video_service.stats_lock.__exit__ = MagicMock(return_value=False)

    mock_request = MagicMock()
    result = await video_status.get_stats(mock_request)

    assert "streaming" in result
    assert "pipeline" in result
    assert "encoder" in result
    assert "health" in result
    assert result["streaming"] is True


@pytest.mark.asyncio
async def test_get_stats_without_service():
    """Test GET /stats endpoint without service"""
    video_status._video_service = None

    mock_request = MagicMock()
    with pytest.raises(HTTPException) as exc_info:
        await video_status.get_stats(mock_request)

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_get_cameras_with_service(mock_video_service):
    """Test GET /cameras endpoint with service"""
    video_status.set_video_service(mock_video_service)

    with patch("app.providers.registry.get_provider_registry") as mock_registry_fn:
        mock_registry = MagicMock()
        mock_registry.get_available_video_sources = MagicMock(
            return_value=[
                {
                    "device": "/dev/video0",
                    "name": "Camera 1",
                    "type": "v4l2",
                    "provider": "v4l2_camera",
                    "capabilities": {
                        "identity": {"driver": "uvcvideo", "bus_info": "usb-0000:00:14.0-1"},
                        "is_usb": True,
                        "supported_resolutions": [(1920, 1080), (1280, 720)],
                        "supported_framerates": {
                            "(1920, 1080)": [30, 24],
                            "(1280, 720)": [60, 30],
                        },
                    },
                }
            ]
        )
        mock_registry_fn.return_value = mock_registry

        mock_request = MagicMock()
        result = await video_status.get_cameras(mock_request)

        assert "cameras" in result
        assert len(result["cameras"]) == 1
        assert result["cameras"][0]["device"] == "/dev/video0"
        assert result["cameras"][0]["name"] == "Camera 1"


@pytest.mark.asyncio
async def test_get_cameras_without_service():
    """Test GET /cameras endpoint without service"""
    video_status._video_service = None

    mock_request = MagicMock()
    with pytest.raises(HTTPException) as exc_info:
        await video_status.get_cameras(mock_request)

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_get_cameras_discovery_error(mock_video_service):
    """Test GET /cameras endpoint with discovery error"""
    video_status.set_video_service(mock_video_service)

    with patch("app.providers.registry.get_provider_registry") as mock_registry_fn:
        mock_registry_fn.side_effect = KeyError("Registry error")

        mock_request = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            await video_status.get_cameras(mock_request)

        assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_get_codecs_with_service(mock_video_service):
    """Test GET /codecs endpoint with service"""
    video_status.set_video_service(mock_video_service)

    with patch("app.providers.registry.get_provider_registry") as mock_registry_fn:
        mock_registry = MagicMock()
        mock_registry.get_available_video_encoders = MagicMock(
            return_value=[
                {
                    "codec_id": "h264",
                    "display_name": "H.264 Hardware",
                    "codec_family": "h264",
                    "encoder_type": "hardware",
                    "available": True,
                    "capabilities": {
                        "description": "Hardware H.264 encoder",
                        "latency_estimate": "low",
                        "cpu_usage": "low",
                        "default_bitrate": 2000,
                        "min_bitrate": 500,
                        "max_bitrate": 10000,
                        "quality_control": True,
                        "priority": 100,
                    },
                }
            ]
        )
        mock_registry_fn.return_value = mock_registry

        mock_request = MagicMock()
        result = await video_status.get_codecs(mock_request)

        assert "codecs" in result
        assert len(result["codecs"]) == 1
        assert result["codecs"][0]["id"] == "h264"
        assert result["codecs"][0]["name"] == "H.264 Hardware"


@pytest.mark.asyncio
async def test_get_codecs_without_service():
    """Test GET /codecs endpoint without service"""
    video_status._video_service = None

    mock_request = MagicMock()
    with pytest.raises(HTTPException) as exc_info:
        await video_status.get_codecs(mock_request)

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_get_codecs_only_available(mock_video_service):
    """Test that only available codecs are returned"""
    video_status.set_video_service(mock_video_service)

    with patch("app.providers.registry.get_provider_registry") as mock_registry_fn:
        mock_registry = MagicMock()
        mock_registry.get_available_video_encoders = MagicMock(
            return_value=[
                {
                    "codec_id": "h264",
                    "display_name": "H.264",
                    "codec_family": "h264",
                    "encoder_type": "hardware",
                    "available": True,
                    "capabilities": {"description": "Available encoder"},
                },
                {
                    "codec_id": "h265",
                    "display_name": "H.265",
                    "codec_family": "h265",
                    "encoder_type": "hardware",
                    "available": False,  # Not available
                    "capabilities": {"description": "Unavailable encoder"},
                },
            ]
        )
        mock_registry_fn.return_value = mock_registry

        mock_request = MagicMock()
        result = await video_status.get_codecs(mock_request)

        # Only h264 should be in result (available=True)
        assert len(result["codecs"]) == 1
        assert result["codecs"][0]["id"] == "h264"
