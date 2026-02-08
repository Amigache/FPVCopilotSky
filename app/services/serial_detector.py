"""
Serial Detector - Auto-detect flight controllers on serial ports
Scans hardware serial ports and USB devices for MAVLink heartbeats
"""

import serial
import time
import os
from typing import Optional, Tuple, List, Dict, Any

# MAVLink environment
os.environ["MAVLINK20"] = "1"
from pymavlink.dialects.v20 import ardupilotmega as mavlink2


class SerialDetector:
    """
    Detect flight controllers on serial ports.
    Tries to establish MAVLink connection and receive heartbeat.
    """

    # Timeout for heartbeat detection (seconds)
    HEARTBEAT_TIMEOUT = 3

    # Radxa Zero hardware serial ports (priority order)
    HARDWARE_PORTS = [
        "/dev/ttyAML0",  # Main UART on GPIO (pins 8/10)
        "/dev/ttyS0",  # Secondary UART
        "/dev/ttyS1",
        "/dev/ttyS2",
    ]

    # USB serial patterns
    USB_PATTERNS = [
        "/dev/ttyUSB",
        "/dev/ttyACM",
    ]

    # Common baudrates (most common first)
    BAUDRATES = [115200, 57600, 921600, 460800, 230400]

    def __init__(self):
        self.last_detection: Optional[Dict[str, Any]] = None

    def detect_flight_controller(
        self,
        preferred_port: str = "",
        preferred_baudrate: int = 0,
        timeout_per_port: float = 3.0,
    ) -> Optional[Dict[str, Any]]:
        """
        Auto-detect flight controller.

        Args:
            preferred_port: Port to try first (from saved config)
            preferred_baudrate: Baudrate to try first (from saved config)
            timeout_per_port: Timeout for each port attempt

        Returns:
            Dict with port, baudrate, system_id if found, None otherwise
        """
        ports = self._get_ports_to_scan(preferred_port)
        baudrates = self._get_baudrates_to_try(preferred_baudrate)

        print(f"🔍 Auto-detecting flight controller...")
        print(f"   Ports: {ports[:5]}...")  # Show first 5
        print(f"   Baudrates: {baudrates}")

        for port in ports:
            # Try preferred baudrate first for this port
            for baudrate in baudrates:
                result = self._try_connect(port, baudrate, timeout_per_port)
                if result:
                    self.last_detection = result
                    return result

        print("❌ No flight controller detected")
        return None

    def _get_ports_to_scan(self, preferred_port: str = "") -> List[str]:
        """Build list of ports to scan in priority order."""
        import glob

        ports = []

        # First: preferred port if exists
        if preferred_port and os.path.exists(preferred_port):
            ports.append(preferred_port)

        # Second: hardware ports
        for port in self.HARDWARE_PORTS:
            if os.path.exists(port) and port not in ports:
                ports.append(port)

        # Third: USB devices
        for pattern in self.USB_PATTERNS:
            for port in sorted(glob.glob(f"{pattern}*")):
                if port not in ports:
                    ports.append(port)

        return ports

    def _get_baudrates_to_try(self, preferred_baudrate: int = 0) -> List[int]:
        """Build list of baudrates to try in priority order."""
        baudrates = []

        if preferred_baudrate and preferred_baudrate > 0:
            baudrates.append(preferred_baudrate)

        for br in self.BAUDRATES:
            if br not in baudrates:
                baudrates.append(br)

        return baudrates

    def _try_connect(
        self, port: str, baudrate: int, timeout: float
    ) -> Optional[Dict[str, Any]]:
        """
        Try to connect to a specific port/baudrate.

        Returns:
            Dict with connection info if successful, None otherwise
        """
        try:
            print(f"   Trying {port} @ {baudrate}...", end=" ", flush=True)

            ser = serial.Serial(
                port=port, baudrate=baudrate, timeout=0.1, write_timeout=1
            )

            # Create parser
            mav = mavlink2.MAVLink(None)
            mav.robust_parsing = True

            start_time = time.time()
            buffer = b""

            while time.time() - start_time < timeout:
                if ser.in_waiting > 0:
                    data = ser.read(ser.in_waiting)
                    buffer += data

                    try:
                        msgs = mav.parse_buffer(buffer)
                        if msgs:
                            for msg in msgs:
                                if msg.get_type() == "HEARTBEAT":
                                    # Found a flight controller!
                                    system_id = msg.get_srcSystem()
                                    component_id = msg.get_srcComponent()
                                    mav_type = msg.type
                                    autopilot = msg.autopilot

                                    ser.close()

                                    result = {
                                        "port": port,
                                        "baudrate": baudrate,
                                        "system_id": system_id,
                                        "component_id": component_id,
                                        "mav_type": mav_type,
                                        "autopilot": autopilot,
                                    }

                                    print(f"✅ Found! (System {system_id})")
                                    return result
                    except Exception:
                        pass

                time.sleep(0.01)

            ser.close()
            print("❌")

        except serial.SerialException as e:
            print(f"⚠️ ({e})")
        except Exception as e:
            print(f"⚠️ ({e})")

        return None

    def quick_probe(self, port: str, baudrate: int = 115200) -> bool:
        """
        Quick probe to check if a port has a flight controller.
        Faster than full detect - just checks for any data.

        Returns:
            True if port appears to have MAVLink traffic
        """
        try:
            ser = serial.Serial(port=port, baudrate=baudrate, timeout=0.5)

            # Wait for some data
            time.sleep(0.3)

            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                ser.close()

                # Check for MAVLink magic bytes (0xFD for MAVLink 2, 0xFE for MAVLink 1)
                return b"\xfd" in data or b"\xfe" in data

            ser.close()

        except Exception:
            pass

        return False


# Singleton instance
_detector: Optional[SerialDetector] = None


def get_detector() -> SerialDetector:
    """Get the singleton detector instance."""
    global _detector
    if _detector is None:
        _detector = SerialDetector()
    return _detector
