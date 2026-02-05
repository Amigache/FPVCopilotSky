"""
MAVLink Bridge - Simple Serial <-> TCP bidirectional bridge
Based on the working test_mavlink_bridge.py approach
"""

import os
os.environ['MAVLINK20'] = '1'

import socket
import serial
import threading
import time
import asyncio
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from pymavlink.dialects.v20 import ardupilotmega as mavlink2
from services.mavlink_dialect import MAVLinkDialect

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
        self.router: Optional['MAVLinkRouter'] = None
        
        # State
        self.running: bool = False
        self.connected: bool = False
        
        # Threads
        self.serial_reader_thread: Optional[threading.Thread] = None
        self.tcp_accept_thread: Optional[threading.Thread] = None
        self.tcp_reader_threads: List[threading.Thread] = []
        
        # MAVLink parser (for telemetry only)
        self.mav_parser = mavlink2.MAVLink(None)
        self.mav_parser.robust_parsing = True
        
        # Target system (from heartbeat)
        self.target_system: int = 0
        self.target_component: int = 0
        self.last_heartbeat: float = 0
        
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
            "messages": []  # STATUSTEXT messages
        }
        self.max_messages = 20  # Keep last 20 messages
        
        # Parameter handling
        self._param_callbacks: Dict[str, threading.Event] = {}
        self._param_values: Dict[str, Any] = {}
        self._param_lock = threading.Lock()
    
    def set_router(self, router: 'MAVLinkRouter'):
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
            self.serial_port = serial.Serial(
                port=port,
                baudrate=baudrate,
                timeout=0.1,
                write_timeout=1
            )
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
            
            # Start TCP server only if port > 0 (disabled by default)
            self.tcp_port = tcp_port
            if tcp_port > 0:
                self._start_tcp_server()
            
            self.connected = True
            self.running = True
            
            # Start serial reader thread
            self.serial_reader_thread = threading.Thread(
                target=self._serial_reader_loop,
                daemon=True,
                name="SerialReader"
            )
            self.serial_reader_thread.start()
            
            # Start TCP accept thread only if TCP server is enabled
            if self.tcp_server:
                self.tcp_accept_thread = threading.Thread(
                    target=self._tcp_accept_loop,
                    daemon=True,
                    name="TCPAccept"
                )
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
                "component_id": self.target_component
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
        if not self.connected:
            return {"success": False, "message": "Not connected"}
        
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
        
        print(f"📊 Final stats: Serial RX={self.stats['serial_rx']}, TX={self.stats['serial_tx']}, "
              f"TCP RX={self.stats['tcp_rx']}, TX={self.stats['tcp_tx']}")
        print("✅ Disconnected")
        
        self._broadcast_status()
        
        return {"success": True, "message": "Disconnected"}
    
    def _wait_for_heartbeat(self, timeout: float = 10) -> bool:
        """Wait for first heartbeat from autopilot."""
        start = time.time()
        buffer = b''
        
        while time.time() - start < timeout:
            if self.serial_port.in_waiting > 0:
                data = self.serial_port.read(self.serial_port.in_waiting)
                buffer += data
                
                # Try to parse heartbeat
                for i, byte in enumerate(buffer):
                    try:
                        msg = self.mav_parser.parse_char(bytes([byte]))
                        if msg and msg.get_type() == 'HEARTBEAT':
                            self.target_system = msg.get_srcSystem()
                            self.target_component = msg.get_srcComponent()
                            self.last_heartbeat = time.time()
                            
                            self.telemetry_data["system"]["mav_type"] = msg.type
                            self.telemetry_data["system"]["autopilot"] = msg.autopilot
                            
                            print(f"   MAV Type: {msg.type}, Autopilot: {msg.autopilot}")
                            return True
                    except Exception:
                        pass
                
                # Keep only last 1KB in buffer
                if len(buffer) > 1024:
                    buffer = buffer[-1024:]
            
            time.sleep(0.01)
        
        return False
    
    def _start_tcp_server(self):
        """Start TCP server for GCS connections."""
        self.tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp_server.settimeout(1.0)
        self.tcp_server.bind(('0.0.0.0', self.tcp_port))
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
                    target=self._tcp_client_reader,
                    args=(client, addr),
                    daemon=True,
                    name=f"TCPReader-{addr[1]}"
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
    
    def _serial_reader_loop(self):
        """Read from serial and forward to all TCP clients."""
        print("🔄 Serial reader started")
        
        buffer = b''
        
        while self.running:
            try:
                if not self.serial_port or not self.serial_port.is_open:
                    time.sleep(0.1)
                    continue
                
                # Read available data - use larger read with timeout to reduce CPU usage
                # The serial port has timeout=0.1, so this blocks up to 100ms if no data
                bytes_waiting = self.serial_port.in_waiting
                if bytes_waiting > 0:
                    # Data available, read it immediately
                    data = self.serial_port.read(bytes_waiting)
                else:
                    # No data, do a blocking read with timeout (more CPU efficient than polling)
                    data = self.serial_port.read(256)
                
                if data:
                    buffer += data
                    
                    # Extract and forward complete messages
                    while True:
                        msg_bytes, remaining, parsed_msg = self._extract_mavlink_message(buffer)
                        if msg_bytes is None:
                            break
                        
                        buffer = remaining
                        self.stats["serial_rx"] += 1
                        
                        # Forward to all TCP clients
                        self._forward_to_tcp_clients(msg_bytes)
                        
                        # Process for telemetry
                        if parsed_msg:
                            self._process_telemetry(parsed_msg)
                        
                        # Log only first message
                        if self.stats["serial_rx"] == 1:
                            print(f"📡 First serial message ({len(msg_bytes)} bytes)")
                    
            except serial.SerialException as e:
                print(f"⚠️ Serial error: {e}")
                time.sleep(0.1)
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
    
    def _extract_mavlink_message(self, buffer: bytes):
        """
        Extract one complete MAVLink message from buffer.
        Returns (message_bytes, remaining_buffer, parsed_message) or (None, buffer, None).
        """
        if len(buffer) < 2:
            return None, buffer, None
        
        # Find MAVLink start byte
        start_idx = -1
        for i, b in enumerate(buffer):
            if b == 0xFD or b == 0xFE:
                start_idx = i
                break
        
        if start_idx == -1:
            return None, b'', None
        
        # Remove garbage before start
        if start_idx > 0:
            buffer = buffer[start_idx:]
        
        if len(buffer) < 2:
            return None, buffer, None
        
        # Determine message length
        if buffer[0] == 0xFD:  # MAVLink v2
            if len(buffer) < 10:
                return None, buffer, None
            
            payload_len = buffer[1]
            incompat_flags = buffer[2]
            has_signature = (incompat_flags & 0x01) != 0
            msg_len = 12 + payload_len + (13 if has_signature else 0)
        else:  # MAVLink v1
            if len(buffer) < 6:
                return None, buffer, None
            
            payload_len = buffer[1]
            msg_len = 8 + payload_len
        
        if len(buffer) < msg_len:
            return None, buffer, None
        
        # Extract message
        msg_bytes = buffer[:msg_len]
        remaining = buffer[msg_len:]
        
        # Try to parse
        parsed = None
        try:
            for byte in msg_bytes:
                result = self.mav_parser.parse_char(bytes([byte]))
                if result:
                    parsed = result
        except Exception:
            pass
        
        return msg_bytes, remaining, parsed
    
    def _process_telemetry(self, msg):
        """Process parsed message for telemetry updates."""
        msg_type = msg.get_type()
        
        if msg_type == 'HEARTBEAT':
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
            
        elif msg_type == 'ATTITUDE':
            self.telemetry_data["attitude"]["roll"] = msg.roll
            self.telemetry_data["attitude"]["pitch"] = msg.pitch
            self.telemetry_data["attitude"]["yaw"] = msg.yaw
            self._broadcast_telemetry()
            
        elif msg_type == 'GLOBAL_POSITION_INT':
            self.telemetry_data["gps"]["lat"] = msg.lat / 1e7
            self.telemetry_data["gps"]["lon"] = msg.lon / 1e7
            self.telemetry_data["gps"]["alt"] = msg.alt / 1000.0
            self._broadcast_telemetry()
            
        elif msg_type == 'SYS_STATUS':
            self.telemetry_data["battery"]["voltage"] = msg.voltage_battery / 1000.0
            self.telemetry_data["battery"]["current"] = msg.current_battery / 100.0
            self.telemetry_data["battery"]["remaining"] = msg.battery_remaining
            self._broadcast_telemetry()
        
        elif msg_type == 'STATUSTEXT':
            # Decode severity: 0=EMERGENCY, 1=ALERT, 2=CRITICAL, 3=ERROR, 4=WARNING, 5=NOTICE, 6=INFO, 7=DEBUG
            severity_map = {
                0: "EMERGENCY", 1: "ALERT", 2: "CRITICAL", 3: "ERROR",
                4: "WARNING", 5: "NOTICE", 6: "INFO", 7: "DEBUG"
            }
            severity = severity_map.get(msg.severity, "UNKNOWN")
            
            # Decode text (may be bytes or string)
            text = msg.text
            if isinstance(text, bytes):
                text = text.decode('utf-8', errors='ignore').rstrip('\x00')
            else:
                text = str(text).rstrip('\x00')
            
            # Add message to list with timestamp
            message_entry = {
                "text": text,
                "severity": severity,
                "timestamp": time.time()
            }
            self.telemetry_data["messages"].insert(0, message_entry)
            
            # Keep only last N messages
            if len(self.telemetry_data["messages"]) > self.max_messages:
                self.telemetry_data["messages"] = self.telemetry_data["messages"][:self.max_messages]
            
            print(f"📨 STATUSTEXT [{severity}]: {text}")
            self._broadcast_telemetry()
        
        elif msg_type == 'VFR_HUD':
            self.telemetry_data["speed"]["ground_speed"] = msg.groundspeed
            self.telemetry_data["speed"]["air_speed"] = msg.airspeed
            self.telemetry_data["speed"]["climb_rate"] = msg.climb
            self._broadcast_telemetry()
        
        elif msg_type == 'GPS_RAW_INT':
            self.telemetry_data["gps"]["satellites"] = msg.satellites_visible
            self._broadcast_telemetry()
        
        elif msg_type == 'PARAM_VALUE':
            # Handle parameter response
            try:
                param_id = msg.param_id
                if isinstance(param_id, bytes):
                    param_id = param_id.decode('utf-8').rstrip('\x00')
                else:
                    param_id = str(param_id).rstrip('\x00')
                
                param_value = msg.param_value
                param_type = msg.param_type
                
                # Store the value and signal any waiting threads
                with self._param_lock:
                    if param_id in self._param_callbacks:
                        self._param_values[param_id] = {
                            "value": param_value,
                            "param_type": param_type,
                            "param_index": msg.param_index,
                            "param_count": msg.param_count
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
            "stats": self.stats
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
            param_id = param_name.encode('utf-8')[:16].ljust(16, b'\x00')
            
            msg = self.mav_parser.param_request_read_encode(
                target_system=self.target_system,
                target_component=self.target_component,
                param_id=param_id,
                param_index=-1  # Use name, not index
            )
            
            # Send message
            with self.serial_lock:
                self.serial_port.write(msg.pack(self.mav_parser))
            
            # Wait for response
            if event.wait(timeout):
                with self._param_lock:
                    result = self._param_values.get(param_name)
                    if result is not None:
                        return {
                            "success": True,
                            "param_id": param_name,
                            "value": result["value"],
                            "param_type": result["param_type"]
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
            param_id = param_name.encode('utf-8')[:16].ljust(16, b'\x00')
            
            # Build PARAM_SET message
            msg = self.mav_parser.param_set_encode(
                target_system=self.target_system,
                target_component=self.target_component,
                param_id=param_id,
                param_value=float(value),
                param_type=param_type
            )
            
            # Send message
            with self.serial_lock:
                self.serial_port.write(msg.pack(self.mav_parser))
            
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
                            "verified": success
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
        
        return {
            "success": len(errors) == 0,
            "parameters": results,
            "errors": errors if errors else None
        }
    
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
            results[param_name] = {
                "success": result["success"],
                "value": result.get("actual_value", value)
            }
            if not result["success"]:
                errors.append(f"{param_name}: {result.get('error', 'Failed')}")
            else:
                print(f"✅ Parameter {param_name} = {result.get('actual_value')}")
        
        return {
            "success": len(errors) == 0,
            "results": results,
            "errors": errors if errors else None
        }
    
    def _broadcast_status(self):
        """Broadcast status via WebSocket."""
        if not self.websocket_manager or not self.event_loop:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self.websocket_manager.broadcast("mavlink_status", self.get_status()),
                self.event_loop
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
                self.websocket_manager.broadcast("telemetry", self.get_telemetry()),
                self.event_loop
            )
        except:
            pass
