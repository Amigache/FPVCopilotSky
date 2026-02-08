"""
Pytest configuration and shared fixtures for FPV Copilot Sky tests

This module provides mock objects for hardware dependencies that are not available
in CI environments (serial ports, modems, cameras, etc.)
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path


@pytest.fixture
def mock_serial_port():
    """
    Mock pyserial.Serial for tests without hardware

    Returns a mock serial port with MAVLink-like behavior
    """
    with patch("serial.Serial") as mock:
        mock_port = Mock()
        mock_port.is_open = True
        mock_port.in_waiting = 0
        mock_port.baudrate = 115200
        mock_port.port = "/dev/ttyUSB0"

        # Mock MAVLink heartbeat packet (minimal valid packet)
        mock_port.read.return_value = b"\xfe\x09\x00\x01\x01\x00\x00\x00\x00\x00\x06\x08\x00\x00\x00\x03"

        mock.return_value = mock_port
        yield mock_port


@pytest.fixture
def mock_mavlink_connection():
    """
    Mock pymavlink.mavutil.mavlink_connection

    Provides mock MAVLink connection with heartbeat and basic message support
    """
    with patch("pymavlink.mavutil.mavlink_connection") as mock:
        mock_conn = Mock()
        mock_conn.target_system = 1
        mock_conn.target_component = 1

        # Mock heartbeat message
        mock_heartbeat = Mock()
        mock_heartbeat.get_type.return_value = "HEARTBEAT"
        mock_heartbeat.custom_mode = 0
        mock_heartbeat.base_mode = 81  # Armed + manual
        mock_heartbeat.system_status = 4  # Active

        mock_conn.recv_match.return_value = mock_heartbeat
        mock_conn.wait_heartbeat.return_value = True
        mock_conn.mav = Mock()

        mock.return_value = mock_conn
        yield mock_conn


@pytest.fixture
def mock_hilink_modem():
    """
    Mock Huawei HiLink API for modem tests

    Provides realistic modem responses without physical hardware
    """
    with patch("huawei_lte_api.Connection") as mock:
        mock_conn = Mock()

        # Mock device information
        mock_conn.device.information.return_value = {
            "DeviceName": "E3372h-320",
            "Imei": "123456789012345",
            "HardwareVersion": "CL2E3372HM",
            "SoftwareVersion": "22.333.01.00.00",
        }

        # Mock signal information
        mock_conn.device.signal.return_value = {
            "rssi": "-65",
            "rsrp": "-95",
            "rsrq": "-10",
            "sinr": "15",
            "cell_id": "12345678",
            "rscp": "-75",
        }

        # Mock network information
        mock_conn.net.current_plmn.return_value = {
            "FullName": "Orange Spain",
            "ShortName": "Orange",
            "Numeric": "21407",
        }

        # Mock connection status
        mock_conn.monitoring.status.return_value = {
            "ConnectionStatus": "901",  # Connected
            "CurrentNetworkType": "19",  # LTE
        }

        # Mock traffic statistics
        mock_conn.monitoring.traffic_statistics.return_value = {
            "CurrentUploadRate": "1024000",
            "CurrentDownloadRate": "5120000",
            "TotalUpload": "1073741824",
            "TotalDownload": "10737418240",
        }

        mock.return_value = mock_conn
        yield mock_conn


@pytest.fixture
def mock_gstreamer():
    """
    Mock GStreamer (gi.repository.Gst) for video tests

    Provides mock GStreamer pipeline without camera hardware
    """
    with patch("gi.repository.Gst") as mock_gst:
        # Mock pipeline
        mock_pipeline = MagicMock()
        mock_pipeline.set_state.return_value = (True, 0, 0)
        mock_pipeline.get_state.return_value = (1, 4, 0)  # SUCCESS, PLAYING, VOID_PENDING

        mock_gst.Pipeline.return_value = mock_pipeline
        mock_gst.State.PLAYING = 4
        mock_gst.State.PAUSED = 3
        mock_gst.State.READY = 2
        mock_gst.State.NULL = 1
        mock_gst.StateChangeReturn.SUCCESS = 1
        mock_gst.StateChangeReturn.ASYNC = 2
        mock_gst.StateChangeReturn.FAILURE = 0

        # Mock element creation
        mock_gst.ElementFactory.make.return_value = MagicMock()

        yield mock_gst


@pytest.fixture
def mock_subprocess():
    """
    Mock subprocess.run for system command tests

    Returns successful execution by default
    """
    with patch("subprocess.run") as mock:
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Mock command output"
        mock_result.stderr = ""
        mock.return_value = mock_result
        yield mock


@pytest.fixture
def temp_preferences(tmp_path):
    """
    Create temporary preferences.json file for testing

    Args:
        tmp_path: pytest's temporary directory fixture

    Returns:
        Path to temporary preferences file
    """
    prefs_file = tmp_path / "preferences.json"
    prefs_data = {
        "serial": {"port": "/dev/ttyUSB0", "baudrate": 115200, "auto_connect": False},
        "router": {"outputs": []},
        "video": {
            "source": "libcamera",
            "codec": "h264",
            "width": 1280,
            "height": 720,
            "fps": 30,
            "bitrate": 2000,
            "auto_start": False,
        },
        "vpn": {"provider": "tailscale", "auto_connect": False},
        "network": {"priority": "wifi"},
    }
    prefs_file.write_text(json.dumps(prefs_data, indent=2))
    return prefs_file


@pytest.fixture
def mock_network_manager():
    """
    Mock NetworkManager D-Bus interface

    Provides mock network management without system access
    """
    with patch("subprocess.run") as mock_subprocess:
        # Mock nmcli commands
        def side_effect(*args, **kwargs):
            cmd = args[0] if args else []
            result = Mock()
            result.returncode = 0
            result.stderr = ""

            if "connection" in cmd and "show" in cmd:
                result.stdout = "NAME\nWiFi Connection\nEthernet"
            elif "device" in cmd and "status" in cmd:
                result.stdout = "DEVICE  TYPE      STATE\nwlan0   wifi      connected\neth0    ethernet  unavailable"
            else:
                result.stdout = "Success"

            return result

        mock_subprocess.side_effect = side_effect
        yield mock_subprocess


@pytest.fixture
def mock_tailscale():
    """
    Mock Tailscale CLI commands

    Provides mock VPN functionality for testing
    """
    with patch("subprocess.run") as mock_subprocess:

        def side_effect(*args, **kwargs):
            cmd = args[0] if args else []
            result = Mock()
            result.returncode = 0
            result.stderr = ""

            if "status" in cmd:
                result.stdout = json.dumps(
                    {
                        "BackendState": "Running",
                        "Self": {
                            "HostName": "fpvcopilot-test",
                            "TailscaleIPs": ["100.64.0.1"],
                        },
                    }
                )
            elif "up" in cmd:
                result.stdout = "Success"
            elif "down" in cmd:
                result.stdout = "Success"
            else:
                result.stdout = "Mock tailscale output"

            return result

        mock_subprocess.side_effect = side_effect
        yield mock_subprocess


@pytest.fixture
def sample_mavlink_messages():
    """
    Provide sample MAVLink messages for testing

    Returns dict with common message types
    """
    return {
        "heartbeat": {
            "type": "HEARTBEAT",
            "custom_mode": 0,
            "base_mode": 81,
            "system_status": 4,
            "mavlink_version": 3,
        },
        "attitude": {
            "type": "ATTITUDE",
            "time_boot_ms": 1000,
            "roll": 0.1,
            "pitch": -0.05,
            "yaw": 1.57,
            "rollspeed": 0.01,
            "pitchspeed": 0.02,
            "yawspeed": 0.01,
        },
        "gps": {
            "type": "GPS_RAW_INT",
            "time_usec": 1000000,
            "lat": 40416775,  # Madrid
            "lon": -3703790,
            "alt": 65700,
            "satellites_visible": 12,
            "fix_type": 3,  # 3D fix
        },
    }


@pytest.fixture
def mock_api_services(monkeypatch):
    """
    Mock all API service dependencies for endpoint testing

    Provides mocked PreferencesService, MAVLinkService, VideoConfig, etc.
    """
    # Mock PreferencesService
    mock_prefs = Mock()
    mock_prefs.get_serial_config.return_value = Mock(
        port="/dev/ttyUSB0", baudrate=115200, auto_connect=True, last_successful=True
    )
    mock_prefs.get_video_config.return_value = {
        "device": "/dev/video0",
        "codec": "h264",
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "bitrate": 2000,
        "auto_start": True,
    }
    mock_prefs.get_vpn_config.return_value = {"provider": "tailscale", "auto_connect": True}
    mock_prefs.get_router_outputs.return_value = [
        {"id": "test-tcp", "type": "tcp_server", "host": "0.0.0.0", "port": 5760, "enabled": True}
    ]
    monkeypatch.setattr("app.services.preferences.PreferencesService", lambda *args, **kwargs: mock_prefs)

    # Mock MAVLinkService
    mock_mavlink = Mock()
    mock_mavlink.is_connected.return_value = True
    mock_mavlink.get_status.return_value = {
        "connected": True,
        "system_id": 1,
        "component_id": 1,
        "message_count": 150,
        "last_heartbeat": 0.5,
    }
    monkeypatch.setattr("app.services.mavlink_bridge.MAVLinkBridge", lambda *args, **kwargs: mock_mavlink)

    # Mock VideoConfig
    mock_video_config = Mock()
    mock_video_config.get_available_sources.return_value = [
        {"id": "/dev/video0", "name": "USB Camera", "type": "usbcamera"}
    ]
    mock_video_config.get_available_encoders.return_value = ["h264", "h265", "mjpeg"]
    monkeypatch.setattr("app.services.video_config.VideoConfig", lambda *args, **kwargs: mock_video_config)

    return {
        "preferences": mock_prefs,
        "mavlink": mock_mavlink,
        "video_config": mock_video_config,
    }


# Pytest configuration hooks
def pytest_configure(config):
    """
    Pytest configuration hook

    Add custom markers and configuration
    """
    config.addinivalue_line("markers", "hardware: tests requiring physical hardware (deselect in CI)")
    config.addinivalue_line("markers", "slow: slow running tests")
    config.addinivalue_line("markers", "integration: integration tests")
