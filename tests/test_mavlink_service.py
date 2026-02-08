"""
Tests for MAVLink Bridge Service

Unit tests for the MAVLink connection and message handling
"""

import pytest
from unittest.mock import Mock, patch
from app.services.mavlink_bridge import MAVLinkBridge


@pytest.mark.asyncio
class TestMAVLinkConnection:
    """Test MAVLink connection establishment"""

    async def test_connect_success(self, mock_serial_port, mock_mavlink_connection):
        """Test successful MAVLink connection"""
        bridge = MAVLinkBridge()

        result = await bridge.connect("/dev/ttyUSB0", 115200)

        assert result["success"] is True
        assert bridge.is_connected() is True
        assert "connected" in result.get("message", "").lower()

    async def test_connect_invalid_port(self, mock_serial_port):
        """Test connection with invalid port"""
        mock_serial_port.side_effect = Exception("Port not found")

        bridge = MAVLinkBridge()
        result = await bridge.connect("/dev/invalid", 115200)

        assert result["success"] is False
        assert bridge.is_connected() is False

    async def test_connect_no_heartbeat(self, mock_serial_port, mock_mavlink_connection):
        """Test connection fails without heartbeat"""
        mock_mavlink_connection.wait_heartbeat.side_effect = TimeoutError("No heartbeat")

        bridge = MAVLinkBridge()
        result = await bridge.connect("/dev/ttyUSB0", 115200)

        # Should handle timeout gracefully
        assert result["success"] is False or "timeout" in result.get("message", "").lower()

    async def test_disconnect(self, mock_mavlink_connection):
        """Test clean disconnection"""
        bridge = MAVLinkBridge()
        await bridge.connect("/dev/ttyUSB0", 115200)

        result = await bridge.disconnect()

        assert result["success"] is True
        assert bridge.is_connected() is False

    async def test_double_connect(self, mock_mavlink_connection):
        """Test that double connect is handled properly"""
        bridge = MAVLinkBridge()

        # First connection
        result1 = await bridge.connect("/dev/ttyUSB0", 115200)
        assert result1["success"] is True

        # Second connection should either succeed or return already connected
        result2 = await bridge.connect("/dev/ttyUSB0", 115200)
        assert isinstance(result2, dict)
        assert "success" in result2


@pytest.mark.asyncio
class TestMAVLinkStatus:
    """Test MAVLink status reporting"""

    async def test_get_status_disconnected(self):
        """Test status when disconnected"""
        bridge = MAVLinkBridge()

        status = bridge.get_status()

        assert status["connected"] is False
        assert status["system_id"] is None

    async def test_get_status_connected(self, mock_mavlink_connection):
        """Test status when connected"""
        bridge = MAVLinkBridge()
        await bridge.connect("/dev/ttyUSB0", 115200)

        status = bridge.get_status()

        assert status["connected"] is True
        assert "port" in status
        assert "baudrate" in status

    async def test_get_system_id(self, mock_mavlink_connection):
        """Test getting system ID"""
        bridge = MAVLinkBridge()
        await bridge.connect("/dev/ttyUSB0", 115200)

        system_id = bridge.get_system_id()

        assert system_id is not None
        assert isinstance(system_id, int)
        assert system_id > 0


@pytest.mark.asyncio
class TestMAVLinkMessages:
    """Test MAVLink message handling"""

    async def test_receive_heartbeat(self, mock_mavlink_connection, sample_mavlink_messages):
        """Test receiving heartbeat message"""
        # Setup mock to return heartbeat
        mock_heartbeat = Mock()
        mock_heartbeat.get_type.return_value = "HEARTBEAT"
        mock_heartbeat.custom_mode = sample_mavlink_messages["heartbeat"]["custom_mode"]
        mock_heartbeat.base_mode = sample_mavlink_messages["heartbeat"]["base_mode"]

        mock_mavlink_connection.recv_match.return_value = mock_heartbeat

        bridge = MAVLinkBridge()
        await bridge.connect("/dev/ttyUSB0", 115200)

        # Simulate receiving messages
        # This depends on your actual implementation

    async def test_message_callback(self, mock_mavlink_connection):
        """Test message callback mechanism"""
        bridge = MAVLinkBridge()
        await bridge.connect("/dev/ttyUSB0", 115200)

        received_messages = []

        def callback(msg):
            received_messages.append(msg)

        # Register callback (if your implementation supports it)
        # bridge.register_callback(callback)

        # This test structure depends on your actual implementation


@pytest.mark.asyncio
class TestMAVLinkParameters:
    """Test MAVLink parameter operations"""

    async def test_get_parameter(self, mock_mavlink_connection):
        """Test getting a parameter from FC"""
        bridge = MAVLinkBridge()
        await bridge.connect("/dev/ttyUSB0", 115200)

        # Mock parameter response
        mock_param = Mock()
        mock_param.get_type.return_value = "PARAM_VALUE"
        mock_param.param_id = "TEST_PARAM"
        mock_param.param_value = 1.5

        mock_mavlink_connection.recv_match.return_value = mock_param

        # This depends on your actual parameter implementation

    async def test_set_parameter(self, mock_mavlink_connection):
        """Test setting a parameter on FC"""
        bridge = MAVLinkBridge()
        await bridge.connect("/dev/ttyUSB0", 115200)

        # This depends on your actual parameter implementation


@pytest.mark.integration
class TestMAVLinkIntegration:
    """Integration tests for MAVLink bridge"""

    @pytest.mark.asyncio
    async def test_full_connection_cycle(self, mock_mavlink_connection):
        """Test complete connection lifecycle"""
        bridge = MAVLinkBridge()

        # Connect
        result = await bridge.connect("/dev/ttyUSB0", 115200)
        assert result["success"] is True

        # Check status
        status = bridge.get_status()
        assert status["connected"] is True

        # Disconnect
        result = await bridge.disconnect()
        assert result["success"] is True

        # Verify disconnected
        status = bridge.get_status()
        assert status["connected"] is False

    @pytest.mark.asyncio
    async def test_reconnection(self, mock_mavlink_connection):
        """Test reconnecting after disconnect"""
        bridge = MAVLinkBridge()

        # First connection
        await bridge.connect("/dev/ttyUSB0", 115200)
        await bridge.disconnect()

        # Reconnection should work
        result = await bridge.connect("/dev/ttyUSB0", 115200)
        assert result["success"] is True


class TestMAVLinkEdgeCases:
    """Test edge cases and error handling"""

    @pytest.mark.asyncio
    async def test_connect_with_invalid_baudrate(self, mock_serial_port):
        """Test connection with invalid baudrate"""
        bridge = MAVLinkBridge()

        # Should handle gracefully
        result = await bridge.connect("/dev/ttyUSB0", 9999999)

        # Depending on implementation, might fail or succeed with mock

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self):
        """Test disconnecting when not connected"""
        bridge = MAVLinkBridge()

        result = await bridge.disconnect()

        # Should not crash, might return success or already disconnected
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, mock_mavlink_connection):
        """Test concurrent bridge operations"""
        import asyncio

        bridge = MAVLinkBridge()
        await bridge.connect("/dev/ttyUSB0", 115200)

        # Multiple status checks concurrently
        tasks = [bridge.get_status() for _ in range(10)]
        results = await asyncio.gather(*[asyncio.create_task(asyncio.to_thread(lambda: bridge.get_status())) for _ in range(10)])

        # All should succeed
        assert all(isinstance(r, dict) for r in results)
