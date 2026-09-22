"""Tests for MAVLink telemetry stream-rate adaptation (SET_MESSAGE_INTERVAL)."""

from unittest.mock import MagicMock

from pymavlink.dialects.v20 import ardupilotmega as mavlink2

from app.services.mavlink_bridge import MAVLinkBridge


def make_bridge():
    bridge = MAVLinkBridge()
    bridge.connected = True
    bridge.serial_port = MagicMock()
    bridge.target_system = 1
    bridge.target_component = 1
    bridge.write_to_serial = MagicMock(return_value=True)
    return bridge


def test_apply_reduced_telemetry_sends_all_messages():
    bridge = make_bridge()
    result = bridge.apply_telemetry_profile("reduced")
    assert result["success"] is True
    assert result["profile"] == "reduced"
    assert bridge.write_to_serial.call_count == len(bridge._TELEMETRY_INTERVALS["reduced"])


def test_unknown_telemetry_profile_fails():
    bridge = make_bridge()
    result = bridge.apply_telemetry_profile("nope")
    assert result["success"] is False


def test_set_message_interval_requires_connection():
    bridge = MAVLinkBridge()
    bridge.connected = False
    assert bridge.set_message_interval(30, 100_000) is False


def test_set_message_interval_packs_set_message_interval_command():
    bridge = make_bridge()
    assert bridge.set_message_interval(30, 200_000) is True

    data = bridge.write_to_serial.call_args[0][0]
    parser = mavlink2.MAVLink(None)
    parser.robust_parsing = True
    commands = []
    for byte in data:
        msg = parser.parse_char(bytes([byte]))
        if msg is not None and msg.get_type() == "COMMAND_LONG":
            commands.append(msg)

    assert commands, "expected a COMMAND_LONG message"
    cmd = commands[-1]
    assert cmd.command == mavlink2.MAV_CMD_SET_MESSAGE_INTERVAL
    assert cmd.param1 == 30
    assert cmd.param2 == 200_000
