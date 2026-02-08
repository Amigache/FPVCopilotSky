"""
MAVLink Bridge - Simple Serial <-> TCP bidirectional bridge
Based on the working test_mavlink_bridge.py approach
"""

import os

os.environ["MAVLINK20"] = "1"

import socket
import serial
import threading
import time
import asyncio
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from pymavlink.dialects.v20 import ardupilotmega as mavlink2
from .mavlink_dialect import MAVLinkDialect

if TYPE_CHECKING:
    from .mavlink_router import MAVLinkRouter


class MAVLinkBridge:
    """
    Simple MAVLink bridge between serial port and TCP server.
    Uses direct pyserial and socket operations without complex pymavlink connection objects.
    """

    def __init__(self, websocket_manager=None, event_loop=None):
        # Serial
        self.serial_port: Optional[serial.Serial] = None
        self.serial_lock = threading.Lock()  # Lock for serial writes
        self.port: str = ""
        self.baudrate: int = 115200

        # TCP Server (built-in) - DISABLED by default, use router instead
        self.tcp_server: Optional[socket.socket] = None
        self.tcp_port: int = 0  # 0 = disabled, all outputs via router
        self.tcp_clients: List[socket.socket] = []
        self.tcp_clients_lock = threading.Lock()

        # Router for outputs (required)
        self.router: Optional["MAVLinkRouter"] = None

        # State
        self.running: bool = False
        self.connected: bool = False
        self._disconnecting: bool = False

        # Threads
        self.serial_reader_thread: Optional[threading.Thread] = None
        self.tcp_accept_thread: Optional[threading.Thread] = None
        self.tcp_reader_threads: List[threading.Thread] = []

        # MAVLink parser (for telemetry only)
        self.mav_parser = mavlink2.MAVLink(None)
        self.mav_parser.robust_parsing = True

        # Our identity as companion computer
        self.source_system_id: int = 1  # Same as autopilot (part of same vehicle)
        self.source_component_id: int = 191  # MAV_COMP_ID_ONBOARD_COMPUTER

        # MAVLink sender for heartbeats/video (same system as FC for camera identity)
        self.mav_sender = mavlink2.MAVLink(None)
        self.mav_sender.srcSystem = self.source_system_id
        self.mav_sender.srcComponent = self.source_component_id

        # Separate sender for GCS-like operations (params, commands)
        # Uses sysid=255 (standard GCS ID) so ArduPilot treats it as a GCS link
        self.gcs_sender = mavlink2.MAVLink(None)
        self.gcs_sender.srcSystem = 255
        self.gcs_sender.srcComponent = 0  # MAV_COMP_ID_ALL

        # Target system (from heartbeat)
        self.target_system: int = 0
        self.target_component: int = 0
        self.last_heartbeat: float = 0

        # HEARTBEAT thread
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.heartbeat_interval: float = 1.0  # Send every 1 second
        self.heartbeat_timeout: float = 15.0
        self._connect_time: float = 0  # Track connection start for grace period

        # WebSocket manager for UI updates
        self.websocket_manager = websocket_manager
        self.event_loop = event_loop

        # Statistics
        self.stats = {
            "serial_rx": 0,
            "serial_tx": 0,
            "tcp_rx": 0,
            "tcp_tx": 0,
        }

        # Telemetry data
        self.telemetry_data: Dict[str, Any] = {
            "attitude": {"roll": 0, "pitch": 0, "yaw": 0},
            "gps": {"lat": 0, "lon": 0, "alt": 0, "satellites": 0},
            "battery": {"voltage": 0, "current": 0, "remaining": 100},
            "speed": {"ground_speed": 0, "air_speed": 0, "climb_rate": 0},
            "system": {
                "mode": "UNKNOWN",
                "armed": False,
                "vehicle_type": "UNKNOWN",
                "autopilot_type": "UNKNOWN",
                "state": "UNKNOWN",
                # Raw values
                "mav_type": 0,
                "autopilot": 0,
                "system_status": 0,
                "custom_mode": 0,
            },
            "messages": [],  # STATUSTEXT messages
        }
        self.max_messages = 20  # Keep last 20 messages

        # Parameter handling
        self._param_callbacks: Dict[str, threading.Event] = {}
        self._param_values: Dict[str, Any] = {}
        self._param_lock = threading.Lock()

    def set_router(self, router: "MAVLinkRouter"):
        """Set the router for additional outputs."""
        self.router = router
        # Set callback so router can send to serial
        router.set_serial_callback(self.write_to_serial)
        print("🔗 Router connected to bridge")

    def write_to_serial(self, data: bytes) -> bool:
        """Thread-safe write to serial port."""
        if not self.connected or not self.serial_port:
            return False

        try:
            with self.serial_lock:
                self.serial_port.write(data)
                self.stats["serial_tx"] += 1
            return True
        except Exception as e:
            print(f"⚠️ Serial write error: {e}")
            return False

    def connect(self, port: str, baudrate: int = 115200, tcp_port: int = 0) -> Dict[str, Any]:
        """Connect to serial port. TCP server disabled by default (tcp_port=0), use router instead."""
        if self.connected:
            return {"success": False, "message": "Already connected"}

        try:
            print(f"🔌 Connecting to {port} @ {baudrate}...")

            # Open serial port
            self.serial_port = serial.Serial(port=port, baudrate=baudrate, timeout=0.1, write_timeout=1)
            self.port = port
            self.baudrate = baudrate

            # Wait for heartbeat
            print("⏳ Waiting for heartbeat...")
            heartbeat = self._wait_for_heartbeat(timeout=10)
            if not heartbeat:
                self.serial_port.close()
                self.serial_port = None
                return {"success": False, "message": "No heartbeat received"}

            print(f"✅ Heartbeat received from system {self.target_system}")

            # Reset parser for serial reader (clean state after heartbeat detection)
            self.mav_parser = mavlink2.MAVLink(None)
            self.mav_parser.robust_parsing = True
            self._parse_error_count = 0
            self._serial_heartbeat_count = 0
            self._parsed_msg_count = 0
            self._unparsed_msg_count = 0

            # Drain any stale data from serial buffer so reader starts clean
            try:
                stale = self.serial_port.in_waiting
                if stale > 0:
                    self.serial_port.read(stale)
                    print(f"🧹 Drained {stale} stale bytes from serial buffer")
            except Exception:
                pass

            self._connect_time = time.time()

            # Start TCP server only if port > 0 (disabled by default)
            self.tcp_port = tcp_port
            if tcp_port > 0:
                self._start_tcp_server()

            self.connected = True
            self.running = True

            # Start serial reader thread
            self.serial_reader_thread = threading.Thread(
                target=self._serial_reader_loop, daemon=True, name="SerialReader"
            )
            self.serial_reader_thread.start()

            # Start HEARTBEAT sender thread
            self.heartbeat_thread = threading.Thread(target=self._heartbeat_sender, daemon=True, name="HeartbeatSender")
            self.heartbeat_thread.start()
            print(
                f"✅ Started HEARTBEAT transmitter (SysID={self.source_system_id}, CompID={self.source_component_id})"
            )

            # Start TCP accept thread only if TCP server is enabled
            if self.tcp_server:
                self.tcp_accept_thread = threading.Thread(target=self._tcp_accept_loop, daemon=True, name="TCPAccept")
                self.tcp_accept_thread.start()

            if tcp_port > 0:
                print(f"✅ MAVLink Bridge started (Serial: {port}, TCP: {tcp_port})")
            else:
                print(f"✅ MAVLink Bridge started (Serial: {port}, outputs via router)")

            self._broadcast_status()

            return {
                "success": True,
                "message": "Connected successfully",
                "system_id": self.target_system,
                "component_id": self.target_component,
            }

        except Exception as e:
            print(f"❌ Connection error: {e}")
            if self.serial_port:
                try:
                    self.serial_port.close()
                except:
                    pass
                self.serial_port = None
            return {"success": False, "message": str(e)}

    def disconnect(self) -> Dict[str, Any]:
        """Stop the bridge and disconnect."""
        if self._disconnecting:
            return {"success": False, "message": "Disconnect already in progress"}
        if not self.connected:
            return {"success": False, "message": "Not connected"}
        self._disconnecting = True
        try:
            print("🔌 Disconnecting...")

            self.running = False

            # Close TCP clients
            with self.tcp_clients_lock:
                for client in self.tcp_clients:
                    try:
                        client.close()
                    except:
                        pass
                self.tcp_clients.clear()

            # Close TCP server
            if self.tcp_server:
                try:
                    self.tcp_server.close()
                except:
                    pass
                self.tcp_server = None

            # Close serial
            if self.serial_port:
                try:
                    self.serial_port.close()
                except:
                    pass
                self.serial_port = None

            self.connected = False
            self.last_heartbeat = 0

            print(
                f"📊 Final stats: Serial RX={self.stats['serial_rx']}, TX={self.stats['serial_tx']}, "
                f"TCP RX={self.stats['tcp_rx']}, TX={self.stats['tcp_tx']}, "
                f"parsed={getattr(self, '_parsed_msg_count', 0)}, unparsed={getattr(self, '_unparsed_msg_count', 0)}, "
                f"heartbeats={getattr(self, '_serial_heartbeat_count', 0)}"
            )
            print("✅ Disconnected")

            # Reset stats for next connection
            self.stats = {"serial_rx": 0, "serial_tx": 0, "tcp_rx": 0, "tcp_tx": 0}

            self._broadcast_status()

            return {"success": True, "message": "Disconnected"}
        finally:
            self._disconnecting = False

    def _handle_serial_failure(self, reason: str):
        """Handle unexpected serial failures and update status."""
        if not self.connected:
            return
        print(f"❌ Serial connection lost: {reason}")
        try:
            self.disconnect()
        except Exception as e:
            print(f"⚠️ Error during disconnect after serial failure: {e}")

    def _wait_for_heartbeat(self, timeout: float = 10) -> bool:
        """Wait for first heartbeat from autopilot."""
        start = time.time()

        while time.time() - start < timeout:
            if self.serial_port.in_waiting > 0:
                data = self.serial_port.read(self.serial_port.in_waiting)

                # Feed only newly-read bytes to the parser (never re-feed)
                for byte_val in data:
                    try:
                        msg = self.mav_parser.parse_char(bytes([byte_val]))
                        if msg and msg.get_type() == "HEARTBEAT":
                            self.target_system = msg.get_srcSystem()
                            self.target_component = msg.get_srcComponent()
                            self.last_heartbeat = time.time()

                            self.telemetry_data["system"]["mav_type"] = msg.type
                            self.telemetry_data["system"]["autopilot"] = msg.autopilot

                            print(f"   MAV Type: {msg.type}, Autopilot: {msg.autopilot}")
                            return True
                    except Exception:
                        pass

            time.sleep(0.01)

        return False

    def _start_tcp_server(self):
        """Start TCP server for GCS connections."""
        self.tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp_server.settimeout(1.0)
        self.tcp_server.bind(("0.0.0.0", self.tcp_port))
        self.tcp_server.listen(5)
        print(f"🌐 TCP Server listening on 0.0.0.0:{self.tcp_port}")

    def _tcp_accept_loop(self):
        """Accept incoming TCP connections."""
        print("🔄 TCP accept thread started")

        while self.running:
            try:
                client, addr = self.tcp_server.accept()
                print(f"✅ TCP Client connected from {addr}")

                # Keep socket in blocking mode with timeout for reads
                client.settimeout(0.1)
                # But send should be non-blocking to not block serial
                client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

                with self.tcp_clients_lock:
                    self.tcp_clients.append(client)
                    print(f"   Total clients: {len(self.tcp_clients)}")

                # Start reader thread for this client
                reader = threading.Thread(
                    target=self._tcp_client_reader, args=(client, addr), daemon=True, name=f"TCPReader-{addr[1]}"
                )
                reader.start()
                self.tcp_reader_threads.append(reader)

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"⚠️ TCP accept error: {e}")

        print("🛑 TCP accept thread stopped")

    def _tcp_client_reader(self, client: socket.socket, addr):
        """Read data from TCP client and forward to serial."""
        print(f"📥 TCP reader started for {addr}")
        first_data = True

        while self.running:
            try:
                data = client.recv(4096)
                if not data:
                    print(f"📤 Client {addr} disconnected (EOF)")
                    break

                if first_data:
                    print(f"📥 First data from {addr}: {len(data)} bytes")
                    first_data = False

                # Forward to serial using thread-safe method
                if self.write_to_serial(data):
                    self.stats["tcp_rx"] += 1

                    if self.stats["tcp_rx"] == 1:
                        print(f"📡 First message forwarded to serial ({len(data)} bytes)")
                    elif self.stats["tcp_rx"] % 50 == 0:
                        print(f"📡 TCP→Serial: {self.stats['tcp_rx']} messages")

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"⚠️ TCP reader error {addr}: {e}")
                break

        # Cleanup
        with self.tcp_clients_lock:
            if client in self.tcp_clients:
                self.tcp_clients.remove(client)
                print(f"   Remaining clients: {len(self.tcp_clients)}")

        try:
            client.close()
        except:
            pass

        print(f"📥 TCP reader stopped for {addr}")

    def _heartbeat_sender(self):
        """Send HEARTBEAT messages periodically to identify as companion computer/camera."""
        print("💓 HEARTBEAT sender started")

        while self.running:
            try:
                if not self.serial_port or not self.serial_port.is_open or not self.connected:
                    time.sleep(0.5)
                    continue

                # Build HEARTBEAT messages
                # Camera heartbeat (SysID=1, CompID=191) for video stream identity
                camera_hb = self.mav_sender.heartbeat_encode(
                    type=30,  # MAV_TYPE_CAMERA
                    autopilot=8,  # MAV_AUTOPILOT_INVALID
                    base_mode=0,
                    custom_mode=0,
                    system_status=4,  # MAV_STATE_ACTIVE
                )
                # GCS heartbeat (SysID=255) to establish GCS link for param operations
                gcs_hb = self.gcs_sender.heartbeat_encode(
                    type=6,  # MAV_TYPE_GCS
                    autopilot=8,  # MAV_AUTOPILOT_INVALID
                    base_mode=0,
                    custom_mode=0,
                    system_status=4,  # MAV_STATE_ACTIVE
                )

                # Send both heartbeats via serial AND router
                packed_camera = camera_hb.pack(self.mav_sender)
                packed_gcs = gcs_hb.pack(self.gcs_sender)

                try:
                    acquired = self.serial_lock.acquire(timeout=0.1)
                    if acquired:
                        try:
                            if self.serial_port and self.serial_port.is_open:
                                self.serial_port.write(packed_camera)
                                self.serial_port.write(packed_gcs)
                                # Also broadcast to router so UDP clients receive them
                                if self.router:
                                    self.router.forward_to_outputs(packed_camera)
                                    self.router.forward_to_outputs(packed_gcs)
                                    # Debug log (first heartbeat of each session)
                                    if not hasattr(self, "_heartbeat_logged"):
                                        print(
                                            f"💓 Sending HEARTBEATs: Camera(SysID={self.mav_sender.srcSystem}, CompID={self.mav_sender.srcComponent}), GCS(SysID={self.gcs_sender.srcSystem})"
                                        )
                                        self._heartbeat_logged = True
                        finally:
                            self.serial_lock.release()
                except Exception as e:
                    print(f"❌ HEARTBEAT send error: {e}")
                    pass

                # Wait for next heartbeat
                time.sleep(self.heartbeat_interval)

            except Exception as e:
                print(f"⚠️ HEARTBEAT sender error: {e}")
                time.sleep(1)

        print("💓 HEARTBEAT sender stopped")

    def _serial_reader_loop(self):
        """Read from serial, forward raw bytes, and parse for telemetry."""
        print("🔄 Serial reader started")

        while self.running:
            try:
                if self.connected and (not self.serial_port or not self.serial_port.is_open):
                    self._handle_serial_failure("serial port closed")
                    break

                if self.connected and self.last_heartbeat:
                    elapsed = time.time() - self.last_heartbeat
                    # Use longer timeout (30s) during first 30 seconds after connect
                    effective_timeout = 30.0 if (time.time() - self._connect_time < 30.0) else self.heartbeat_timeout
                    if elapsed > effective_timeout:
                        print(
                            f"⏱️ Heartbeat elapsed: {elapsed:.1f}s > {effective_timeout:.1f}s (parsed HBs: {getattr(self, '_serial_heartbeat_count', 0)}, msgs: {self.stats['serial_rx']})"
                        )
                        self._handle_serial_failure("heartbeat timeout")
                        break

                if not self.serial_port or not self.serial_port.is_open:
                    time.sleep(0.1)
                    continue

                # Read available data
                bytes_waiting = self.serial_port.in_waiting
                if bytes_waiting > 0:
                    data = self.serial_port.read(bytes_waiting)
                else:
                    data = self.serial_port.read(256)

                if data:
                    # Forward ALL raw bytes immediately to TCP clients and router
                    self._forward_to_tcp_clients(data)

                    # Feed bytes to parser one at a time for telemetry processing
                    for byte_val in data:
                        try:
                            parsed_msg = self.mav_parser.parse_char(bytes([byte_val]))
                            if parsed_msg:
                                self.stats["serial_rx"] += 1
                                msg_type = parsed_msg.get_type()

                                # Track message types
                                if not hasattr(self, "_msg_type_counts"):
                                    self._msg_type_counts = {}
                                self._msg_type_counts[msg_type] = self._msg_type_counts.get(msg_type, 0) + 1

                                self._process_telemetry(parsed_msg)

                                # Log first message and periodic stats
                                if self.stats["serial_rx"] == 1:
                                    print(f"📡 First serial message: {msg_type}")
                                elif self.stats["serial_rx"] == 100:
                                    types_summary = ", ".join(sorted(self._msg_type_counts.keys()))
                                    print(f"📊 Serial: {self.stats['serial_rx']} msgs, types: {types_summary}")
                        except Exception as e:
                            if not hasattr(self, "_parse_error_count"):
                                self._parse_error_count = 0
                            self._parse_error_count += 1
                            if self._parse_error_count <= 3:
                                print(f"⚠️ MAVLink parse error #{self._parse_error_count}: {e}")

            except serial.SerialException as e:
                print(f"⚠️ Serial error: {e}")
                self._handle_serial_failure(str(e))
                break
            except Exception as e:
                print(f"⚠️ Serial reader error: {e}")
                time.sleep(0.1)

        print("🛑 Serial reader stopped")

    def _forward_to_tcp_clients(self, data: bytes):
        """Forward data to all connected TCP clients and router outputs."""
        # Forward to built-in TCP server clients
        with self.tcp_clients_lock:
            if self.tcp_clients:
                dead_clients = []

                for client in self.tcp_clients:
                    try:
                        client.sendall(data)
                        self.stats["tcp_tx"] += 1

                        # Log first successful send
                        if self.stats["tcp_tx"] == 1:
                            print(f"📡 First message sent to TCP client ({len(data)} bytes)")

                    except (BrokenPipeError, ConnectionResetError, OSError) as e:
                        print(f"⚠️ TCP send error: {e}")
                        dead_clients.append(client)

                # Remove dead clients
                for dead in dead_clients:
                    if dead in self.tcp_clients:
                        self.tcp_clients.remove(dead)
                        try:
                            dead.close()
                        except:
                            pass
                        print(f"❌ TCP client disconnected, {len(self.tcp_clients)} remaining")

        # Forward to router outputs (UDP, additional TCP servers/clients)
        if self.router:
            self.router.forward_to_outputs(data)

    def _process_telemetry(self, msg):
        """Process parsed message for telemetry updates."""
        msg_type = msg.get_type()

        if msg_type == "HEARTBEAT":
            # Track heartbeat count for debugging
            if not hasattr(self, "_serial_heartbeat_count"):
                self._serial_heartbeat_count = 0
            self._serial_heartbeat_count += 1
            if self._serial_heartbeat_count == 1:
                print(f"💓 First HEARTBEAT parsed in serial reader (system {msg.get_srcSystem()})")

            self.last_heartbeat = time.time()
            mav_type = msg.type
            custom_mode = msg.custom_mode

            # Convert numeric values to readable strings using MAVLinkDialect
            self.telemetry_data["system"]["armed"] = (msg.base_mode & 128) != 0
            self.telemetry_data["system"]["mode"] = MAVLinkDialect.get_mode_string(mav_type, custom_mode)
            self.telemetry_data["system"]["vehicle_type"] = MAVLinkDialect.get_type_string(mav_type)
            self.telemetry_data["system"]["autopilot_type"] = MAVLinkDialect.get_autopilot_string(msg.autopilot)
            self.telemetry_data["system"]["state"] = MAVLinkDialect.get_state_string(msg.system_status)

            # Also keep raw values for reference
            self.telemetry_data["system"]["mav_type"] = mav_type
            self.telemetry_data["system"]["autopilot"] = msg.autopilot
            self.telemetry_data["system"]["system_status"] = msg.system_status
            self.telemetry_data["system"]["custom_mode"] = custom_mode

            self._broadcast_telemetry()

        elif msg_type == "ATTITUDE":
            self.telemetry_data["attitude"]["roll"] = msg.roll
            self.telemetry_data["attitude"]["pitch"] = msg.pitch
            self.telemetry_data["attitude"]["yaw"] = msg.yaw
            self._broadcast_telemetry()

        elif msg_type == "GLOBAL_POSITION_INT":
            self.telemetry_data["gps"]["lat"] = msg.lat / 1e7
            self.telemetry_data["gps"]["lon"] = msg.lon / 1e7
            self.telemetry_data["gps"]["alt"] = msg.alt / 1000.0
            self._broadcast_telemetry()

        elif msg_type == "SYS_STATUS":
            self.telemetry_data["battery"]["voltage"] = msg.voltage_battery / 1000.0
            self.telemetry_data["battery"]["current"] = msg.current_battery / 100.0
            self.telemetry_data["battery"]["remaining"] = msg.battery_remaining
            self._broadcast_telemetry()

        elif msg_type == "STATUSTEXT":
            # Decode severity: 0=EMERGENCY, 1=ALERT, 2=CRITICAL, 3=ERROR, 4=WARNING, 5=NOTICE, 6=INFO, 7=DEBUG
            severity_map = {
                0: "EMERGENCY",
                1: "ALERT",
                2: "CRITICAL",
                3: "ERROR",
                4: "WARNING",
                5: "NOTICE",
                6: "INFO",
                7: "DEBUG",
            }
            severity = severity_map.get(msg.severity, "UNKNOWN")

            # Decode text (may be bytes or string)
            text = msg.text
            if isinstance(text, bytes):
                text = text.decode("utf-8", errors="ignore").rstrip("\x00")
            else:
                text = str(text).rstrip("\x00")

            # Add message to list with timestamp
            message_entry = {"text": text, "severity": severity, "timestamp": time.time()}
            self.telemetry_data["messages"].insert(0, message_entry)

            # Keep only last N messages
            if len(self.telemetry_data["messages"]) > self.max_messages:
                self.telemetry_data["messages"] = self.telemetry_data["messages"][: self.max_messages]

            print(f"📨 STATUSTEXT [{severity}]: {text}")
            self._broadcast_telemetry()

        elif msg_type == "VFR_HUD":
            self.telemetry_data["speed"]["ground_speed"] = msg.groundspeed
            self.telemetry_data["speed"]["air_speed"] = msg.airspeed
            self.telemetry_data["speed"]["climb_rate"] = msg.climb
            self._broadcast_telemetry()

        elif msg_type == "GPS_RAW_INT":
            self.telemetry_data["gps"]["satellites"] = msg.satellites_visible
            self._broadcast_telemetry()

        elif msg_type == "PARAM_VALUE":
            # Handle parameter response
            try:
                param_id = msg.param_id
                if isinstance(param_id, bytes):
                    param_id = param_id.decode("utf-8").rstrip("\x00")
                else:
                    param_id = str(param_id).rstrip("\x00")

                param_value = msg.param_value
                param_type = msg.param_type

                print(f"📥 PARAM_VALUE received: {param_id} = {param_value}")

                # Store the value and signal any waiting threads
                with self._param_lock:
                    if param_id in self._param_callbacks:
                        self._param_values[param_id] = {
                            "value": param_value,
                            "param_type": param_type,
                            "param_index": msg.param_index,
                            "param_count": msg.param_count,
                        }
                        self._param_callbacks[param_id].set()
            except Exception as e:
                print(f"⚠️ Error processing PARAM_VALUE: {e}")

    def is_connected(self) -> bool:
        return self.connected

    def get_status(self) -> Dict[str, Any]:
        """Get current status."""
        with self.tcp_clients_lock:
            num_clients = len(self.tcp_clients)

        return {
            "connected": self.connected,
            "port": self.port,
            "baudrate": self.baudrate,
            "tcp_port": self.tcp_port,
            "tcp_clients": num_clients,
            "last_heartbeat": self.last_heartbeat,
            "stats": self.stats,
        }

    def get_telemetry(self) -> Dict[str, Any]:
        """Get telemetry data."""
        if not self.connected:
            return {"connected": False}
        return {"connected": True, **self.telemetry_data}

    def get_parameter(self, param_name: str, timeout: float = 3.0) -> Dict[str, Any]:
        """
        Request and wait for a parameter value from the flight controller.

        Args:
            param_name: Parameter name (e.g., 'FS_THR_ENABLE')
            timeout: Timeout in seconds

        Returns:
            Dict with success, value, param_type, etc.
        """
        if not self.connected or not self.serial_port:
            return {"success": False, "error": "Not connected"}

        # Create event for this parameter
        event = threading.Event()
        with self._param_lock:
            self._param_callbacks[param_name] = event
            self._param_values[param_name] = None

        try:
            # Build PARAM_REQUEST_READ message
            # Encode param name as bytes (16 chars max, null-padded)
            param_id = param_name.encode("utf-8")[:16].ljust(16, b"\x00")

            msg = self.gcs_sender.param_request_read_encode(
                target_system=self.target_system,
                target_component=self.target_component,
                param_id=param_id,
                param_index=-1,  # Use name, not index
            )

            # Send message
            with self.serial_lock:
                packed = msg.pack(self.gcs_sender)
                self.serial_port.write(packed)
            if event.wait(timeout):
                with self._param_lock:
                    result = self._param_values.get(param_name)
                    if result is not None:
                        return {
                            "success": True,
                            "param_id": param_name,
                            "value": result["value"],
                            "param_type": result["param_type"],
                        }

            return {"success": False, "error": f"Timeout waiting for {param_name}"}

        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            # Cleanup
            with self._param_lock:
                self._param_callbacks.pop(param_name, None)

    def set_parameter(self, param_name: str, value: float, param_type: int = 9, timeout: float = 3.0) -> Dict[str, Any]:
        """
        Set a parameter on the flight controller and verify it was saved.

        Args:
            param_name: Parameter name (e.g., 'FS_THR_ENABLE')
            value: New value (float, will be converted as needed)
            param_type: MAV_PARAM_TYPE (9 = REAL32 is most common)
            timeout: Timeout in seconds

        Returns:
            Dict with success status and verified value
        """
        if not self.connected or not self.serial_port:
            return {"success": False, "error": "Not connected"}

        # Create event for this parameter
        event = threading.Event()
        with self._param_lock:
            self._param_callbacks[param_name] = event
            self._param_values[param_name] = None

        try:
            # Encode param name as bytes (16 chars max, null-padded)
            param_id = param_name.encode("utf-8")[:16].ljust(16, b"\x00")

            # Build PARAM_SET message
            msg = self.gcs_sender.param_set_encode(
                target_system=self.target_system,
                target_component=self.target_component,
                param_id=param_id,
                param_value=float(value),
                param_type=param_type,
            )

            # Send message
            with self.serial_lock:
                self.serial_port.write(msg.pack(self.gcs_sender))

            # Wait for PARAM_VALUE response (confirmation)
            if event.wait(timeout):
                with self._param_lock:
                    result = self._param_values.get(param_name)
                    if result is not None:
                        # Verify the value was set correctly
                        set_value = result["value"]
                        # For integer params, compare as int
                        if param_type in [1, 2, 3, 4, 5, 6, 7, 8]:  # Integer types
                            success = int(set_value) == int(value)
                        else:
                            success = abs(set_value - value) < 0.001

                        return {
                            "success": success,
                            "param_id": param_name,
                            "requested_value": value,
                            "actual_value": set_value,
                            "verified": success,
                        }

            return {"success": False, "error": f"Timeout waiting for {param_name} confirmation"}

        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            # Cleanup
            with self._param_lock:
                self._param_callbacks.pop(param_name, None)

    def get_parameters_batch(self, param_names: List[str], timeout: float = 5.0) -> Dict[str, Any]:
        """
        Get multiple parameters in sequence.

        Args:
            param_names: List of parameter names
            timeout: Timeout per parameter

        Returns:
            Dict with parameters and their values
        """
        results = {}
        errors = []

        for param_name in param_names:
            result = self.get_parameter(param_name, timeout=timeout)
            if result["success"]:
                results[param_name] = result["value"]
            else:
                errors.append(f"{param_name}: {result.get('error', 'Unknown error')}")

        return {"success": len(errors) == 0, "parameters": results, "errors": errors if errors else None}

    def set_parameters_batch(self, params: Dict[str, float], timeout: float = 3.0) -> Dict[str, Any]:
        """
        Set multiple parameters in sequence.

        Args:
            params: Dict of param_name -> value
            timeout: Timeout per parameter

        Returns:
            Dict with results for each parameter
        """
        results = {}
        errors = []

        for param_name, value in params.items():
            result = self.set_parameter(param_name, value, timeout=timeout)
            results[param_name] = {"success": result["success"], "value": result.get("actual_value", value)}
            if not result["success"]:
                errors.append(f"{param_name}: {result.get('error', 'Failed')}")
            else:
                print(f"✅ Parameter {param_name} = {result.get('actual_value')}")

        return {"success": len(errors) == 0, "results": results, "errors": errors if errors else None}

    def _broadcast_status(self):
        """Broadcast status via WebSocket."""
        if not self.websocket_manager or not self.event_loop:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self.websocket_manager.broadcast("mavlink_status", self.get_status()), self.event_loop
            )
        except:
            pass

    def _broadcast_telemetry(self):
        """Broadcast telemetry via WebSocket.

        OPTIMIZATION: Skip if no clients connected to save CPU.
        """
        if not self.websocket_manager or not self.event_loop:
            return
        # Skip broadcast if no clients (save CPU for video encoding)
        if not self.websocket_manager.has_clients:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self.websocket_manager.broadcast("telemetry", self.get_telemetry()), self.event_loop
            )
        except:
            pass
