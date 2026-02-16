"""
MAVLink Router - Manage multiple outputs (UDP, TCP) for message distribution
Uses simplified approach: direct sockets without complex pymavlink connections
"""

import socket as socket_module
import threading
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum


class OutputType(Enum):
    TCP_SERVER = "tcp_server"
    TCP_CLIENT = "tcp_client"
    UDP = "udp"


@dataclass
class OutputConfig:
    """Configuration for a router output."""

    id: str
    type: OutputType
    host: str
    port: int
    enabled: bool = True
    auto_start: bool = False
    name: str = ""


@dataclass
class OutputState:
    """Runtime state for an output."""

    config: OutputConfig
    running: bool = False
    sock: Optional[socket_module.socket] = None
    clients: List[socket_module.socket] = field(default_factory=list)
    threads: List[threading.Thread] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=lambda: {"tx": 0, "rx": 0, "errors": 0})


class MAVLinkRouter:
    """
    Router for distributing MAVLink messages to multiple outputs.
    Works alongside MAVLinkBridge to add additional outputs.
    """

    CONFIG_FILE = "mavlink_router_config.json"

    def __init__(self):
        self.outputs: Dict[str, OutputState] = {}
        self.lock = threading.RLock()  # Reentrant lock to avoid deadlocks
        self.running = True

        # Callback to send data back to serial (set by bridge)
        self.on_data_received: Optional[Callable[[bytes], None]] = None

        # Callback to notify status changes (set by main.py for WebSocket updates)
        self.on_status_change: Optional[Callable[[], None]] = None

        # Load saved configuration
        self._load_config()

    def set_status_callback(self, callback: Callable[[], None]):
        """Set callback for notifying status changes."""
        self.on_status_change = callback

    def _notify_status_change(self):
        """Notify that router status has changed."""
        if self.on_status_change:
            try:
                self.on_status_change()
            except Exception:
                pass

    def set_serial_callback(self, callback: Callable[[bytes], None]):
        """Set callback for forwarding received data to serial."""
        self.on_data_received = callback
        print("🔗 Router linked to serial bridge")

    def _get_type_value(self, config_type) -> str:
        """Get type value string, handling both enum and string."""
        return config_type.value if hasattr(config_type, "value") else config_type

    def forward_to_outputs(self, data: bytes):
        """Forward data from serial to all active outputs."""
        with self.lock:
            for output_id, state in list(self.outputs.items()):
                if not state.running:
                    continue

                try:
                    output_type = self._get_type_value(state.config.type)
                    if output_type == "tcp_server":
                        self._send_to_tcp_clients(state, data)
                    elif output_type == "tcp_client":
                        self._send_to_tcp_client(state, data)
                    elif output_type == "udp":
                        self._send_to_udp(state, data)
                except Exception:
                    state.stats["errors"] += 1

    def _send_to_tcp_clients(self, state: OutputState, data: bytes):
        """Send to all connected TCP server clients."""
        dead_clients = []
        for client in state.clients:
            try:
                client.sendall(data)
                state.stats["tx"] += 1
            except (BrokenPipeError, ConnectionResetError, OSError):
                dead_clients.append(client)

        for dead in dead_clients:
            if dead in state.clients:
                state.clients.remove(dead)
                try:
                    dead.close()
                except Exception:
                    pass

    def _send_to_tcp_client(self, state: OutputState, data: bytes):
        """Send to TCP client connection."""
        if state.sock:
            try:
                state.sock.sendall(data)
                state.stats["tx"] += 1
            except (BrokenPipeError, ConnectionResetError, OSError):
                state.stats["errors"] += 1

    def _send_to_udp(self, state: OutputState, data: bytes):
        """Send to UDP endpoint."""
        if state.sock:
            try:
                state.sock.sendto(data, (state.config.host, state.config.port))
                state.stats["tx"] += 1
            except OSError:
                state.stats["errors"] += 1

    # ==================== Output Management ====================

    def add_output(self, config: OutputConfig) -> tuple[bool, str]:
        """Add a new output configuration."""
        with self.lock:
            if config.id in self.outputs:
                return False, f"Output {config.id} already exists"

            self.outputs[config.id] = OutputState(config=config)
            self._save_config()

            print(f"✅ Added output: {config.id} ({config.type.value} {config.host}:{config.port})")

            # Auto-start if configured
            if config.auto_start and config.enabled:
                return self.start_output(config.id)

            return True, "Output added"

    def remove_output(self, output_id: str) -> tuple[bool, str]:
        """Remove an output."""
        with self.lock:
            if output_id not in self.outputs:
                return False, f"Output {output_id} not found"

            state = self.outputs[output_id]
            if state.running:
                self._stop_output_internal(state)

            del self.outputs[output_id]
            self._save_config()
            self._notify_status_change()  # Notify WebSocket

            print(f"🗑️ Removed output: {output_id}")
            return True, "Output removed"

    def update_output(self, output_id: str, updated_data: dict) -> tuple[bool, str]:
        """Update an existing output configuration."""
        with self.lock:
            if output_id not in self.outputs:
                return False, f"Output {output_id} not found"

            state = self.outputs[output_id]
            was_running = state.running

            # Stop output if running for safe update
            if was_running:
                self._stop_output_internal(state)
                print(f"🔄 Stopping output {output_id} for update")

            # Update configuration
            if "type" in updated_data:
                # Ensure type is properly converted to enum
                type_value = updated_data["type"]
                if isinstance(type_value, str):
                    state.config.type = OutputType(type_value)
                else:
                    state.config.type = type_value
            if "host" in updated_data:
                state.config.host = updated_data["host"]
            if "port" in updated_data:
                state.config.port = updated_data["port"]
            if "name" in updated_data:
                state.config.name = updated_data["name"]
            if "enabled" in updated_data:
                state.config.enabled = updated_data["enabled"]
            if "auto_start" in updated_data:
                state.config.auto_start = updated_data["auto_start"]

            self._save_config()

            # Restart if it was running and still enabled
            if was_running and state.config.enabled:
                success, message = self.start_output(output_id)
                if success:
                    print(f"🔄 Restarted output {output_id} after update")
                    self._notify_status_change()
                    return True, "Output updated and restarted"
                else:
                    print(f"⚠️ Output {output_id} updated but failed to restart: {message}")
                    self._notify_status_change()
                    return True, f"Output updated but restart failed: {message}"

            self._notify_status_change()
            print(f"✅ Updated output: {output_id}")
            return True, "Output updated"

    def start_output(self, output_id: str) -> tuple[bool, str]:
        """Start an output."""
        with self.lock:
            if output_id not in self.outputs:
                return False, f"Output {output_id} not found"

            state = self.outputs[output_id]
            if state.running:
                return False, "Output already running"

            try:
                output_type = self._get_type_value(state.config.type)

                if output_type == "tcp_server":
                    success, message = self._start_tcp_server(state)
                elif output_type == "tcp_client":
                    success, message = self._start_tcp_client(state)
                elif output_type == "udp":
                    success, message = self._start_udp(state)
                else:
                    return False, f"Unknown output type: {output_type}"

                if success:
                    self._notify_status_change()  # Notify WebSocket

                return success, message
            except Exception as e:
                return False, str(e)

    def stop_output(self, output_id: str) -> tuple[bool, str]:
        """Stop an output."""
        with self.lock:
            if output_id not in self.outputs:
                return False, f"Output {output_id} not found"

            state = self.outputs[output_id]
            if not state.running:
                return False, "Output not running"

            self._stop_output_internal(state)
            self._notify_status_change()  # Notify WebSocket
            print(f"🛑 Stopped output: {output_id}")
            return True, "Output stopped"

    def restart_output(self, output_id: str) -> tuple[bool, str]:
        """Restart an output (stop then start)."""
        with self.lock:
            if output_id not in self.outputs:
                return False, f"Output {output_id} not found"

            state = self.outputs[output_id]

            # Stop the output if running
            if state.running:
                self._stop_output_internal(state)
                print(f"🔄 Stopping output for restart: {output_id}")

            # Start the output
            try:
                output_type = self._get_type_value(state.config.type)

                if output_type == "tcp_server":
                    success, message = self._start_tcp_server(state)
                elif output_type == "tcp_client":
                    success, message = self._start_tcp_client(state)
                elif output_type == "udp":
                    success, message = self._start_udp(state)
                else:
                    return False, f"Unknown output type: {output_type}"

                if success:
                    print(f"🔄 Restarted output: {output_id}")
                    self._notify_status_change()  # Notify WebSocket

                return success, message

            except Exception as e:
                return False, str(e)

    def _stop_output_internal(self, state: OutputState):
        """Internal method to stop an output."""
        state.running = False

        # Close clients
        for client in state.clients:
            try:
                client.close()
            except Exception:
                pass
        state.clients.clear()

        # Close main socket
        if state.sock:
            try:
                state.sock.close()
            except Exception:
                pass
            state.sock = None

        # Wait for threads
        for thread in state.threads:
            thread.join(timeout=1)
        state.threads.clear()

    # ==================== TCP Server ====================

    def _start_tcp_server(self, state: OutputState) -> tuple[bool, str]:
        """Start a TCP server output."""
        try:
            server = socket_module.socket(socket_module.AF_INET, socket_module.SOCK_STREAM)
            server.setsockopt(socket_module.SOL_SOCKET, socket_module.SO_REUSEADDR, 1)
            server.settimeout(1.0)
            server.bind((state.config.host, state.config.port))
            server.listen(5)

            state.sock = server
            state.running = True

            # Start accept thread
            accept_thread = threading.Thread(
                target=self._tcp_server_accept_loop,
                args=(state,),
                daemon=True,
                name=f"TCPAccept-{state.config.id}",
            )
            accept_thread.start()
            state.threads.append(accept_thread)

            print(f"🌐 TCP Server started on {state.config.host}:{state.config.port} (ID: {state.config.id})")
            return True, "TCP Server started"

        except Exception as e:
            return False, f"Failed to start TCP server: {e}"

    def _tcp_server_accept_loop(self, state: OutputState):
        """Accept loop for TCP server."""
        while state.running and self.running:
            try:
                client, addr = state.sock.accept()
                print(f"✅ Router: TCP client connected from {addr} (output: {state.config.id})")

                client.settimeout(0.1)
                client.setsockopt(socket_module.IPPROTO_TCP, socket_module.TCP_NODELAY, 1)

                with self.lock:
                    state.clients.append(client)

                # Notify status change
                self._notify_status_change()

                # Start reader thread
                reader = threading.Thread(
                    target=self._tcp_client_reader,
                    args=(state, client, addr),
                    daemon=True,
                    name=f"TCPReader-{addr[1]}",
                )
                reader.start()
                state.threads.append(reader)

            except socket_module.timeout:
                continue
            except Exception as e:
                if state.running:
                    print(f"⚠️ Router: TCP accept error: {e}")

    def _tcp_client_reader(self, state: OutputState, client: socket_module.socket, addr):
        """Read from TCP client and forward to serial."""
        while state.running and self.running:
            try:
                data = client.recv(4096)
                if not data:
                    break

                state.stats["rx"] += 1

                # Forward to serial via callback
                if self.on_data_received:
                    self.on_data_received(data)

            except socket_module.timeout:
                continue
            except Exception:
                break

        # Cleanup
        with self.lock:
            if client in state.clients:
                state.clients.remove(client)
        try:
            client.close()
        except Exception:
            pass
        print(f"📤 Router: TCP client {addr} disconnected (output: {state.config.id})")

        # Notify status change
        self._notify_status_change()

    # ==================== TCP Client ====================

    def _start_tcp_client(self, state: OutputState) -> tuple[bool, str]:
        """Start a TCP client output (connect to remote server)."""
        try:
            sock = socket_module.socket(socket_module.AF_INET, socket_module.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((state.config.host, state.config.port))
            sock.settimeout(0.1)
            sock.setsockopt(socket_module.IPPROTO_TCP, socket_module.TCP_NODELAY, 1)

            state.sock = sock
            state.running = True

            # Start reader thread
            reader = threading.Thread(
                target=self._tcp_client_connection_reader,
                args=(state,),
                daemon=True,
                name=f"TCPClient-{state.config.id}",
            )
            reader.start()
            state.threads.append(reader)

            print(f"🔗 TCP Client connected to {state.config.host}:{state.config.port} (ID: {state.config.id})")
            return True, "TCP Client connected"

        except ConnectionRefusedError:
            return (
                False,
                f"No hay servidor TCP en {state.config.host}:{state.config.port}. "
                "Verifica que el destino esté disponible.",
            )
        except socket_module.timeout:
            return (
                False,
                f"Timeout conectando a {state.config.host}:{state.config.port}. Verifica la conectividad de red.",
            )
        except Exception as e:
            return False, f"Error de conexión: {e}"

    def _tcp_client_connection_reader(self, state: OutputState):
        """Read from TCP client connection and forward to serial."""
        while state.running and self.running:
            try:
                data = state.sock.recv(4096)
                if not data:
                    break

                state.stats["rx"] += 1

                if self.on_data_received:
                    self.on_data_received(data)

            except socket_module.timeout:
                continue
            except Exception:
                break

        print(f"📤 Router: TCP client disconnected (output: {state.config.id})")
        state.running = False

    # ==================== UDP ====================

    def _start_udp(self, state: OutputState) -> tuple[bool, str]:
        """Start a UDP output."""
        try:
            sock = socket_module.socket(socket_module.AF_INET, socket_module.SOCK_DGRAM)
            sock.setsockopt(socket_module.SOL_SOCKET, socket_module.SO_REUSEADDR, 1)

            # Bind to receive responses
            sock.bind(("0.0.0.0", 0))
            sock.settimeout(0.1)

            state.sock = sock
            state.running = True

            # Start reader thread for incoming UDP
            reader = threading.Thread(
                target=self._udp_reader,
                args=(state,),
                daemon=True,
                name=f"UDPReader-{state.config.id}",
            )
            reader.start()
            state.threads.append(reader)

            print(f"📡 UDP output started for {state.config.host}:{state.config.port} (ID: {state.config.id})")
            return True, "UDP output started"

        except Exception as e:
            return False, f"Failed to start UDP: {e}"

    def _udp_reader(self, state: OutputState):
        """Read incoming UDP packets and forward to serial."""
        while state.running and self.running:
            try:
                data, addr = state.sock.recvfrom(4096)
                if data:
                    state.stats["rx"] += 1

                    if self.on_data_received:
                        self.on_data_received(data)

            except socket_module.timeout:
                continue
            except Exception:
                if state.running:
                    continue

    # ==================== Status & Config ====================

    def get_status(self) -> Dict[str, Any]:
        """Get router status."""
        with self.lock:
            outputs = []
            for output_id, state in self.outputs.items():
                outputs.append(
                    {
                        "id": output_id,
                        "type": state.config.type.value,
                        "host": state.config.host,
                        "port": state.config.port,
                        "name": state.config.name,
                        "enabled": state.config.enabled,
                        "auto_start": state.config.auto_start,
                        "running": state.running,
                        "clients": (
                            len(state.clients) if self._get_type_value(state.config.type) == "tcp_server" else 0
                        ),
                        "stats": state.stats.copy(),
                    }
                )

            return {
                "outputs": outputs,
                "total_outputs": len(self.outputs),
                "active_outputs": sum(1 for s in self.outputs.values() if s.running),
            }

    def get_outputs_list(self) -> List[Dict[str, Any]]:
        """Get list of all outputs."""
        return self.get_status()["outputs"]

    def _save_config(self):
        """Save configuration to preferences service."""
        configs = []
        for output_id, state in self.outputs.items():
            configs.append(
                {
                    "id": state.config.id,
                    "type": state.config.type.value,
                    "host": state.config.host,
                    "port": state.config.port,
                    "name": state.config.name,
                    "enabled": state.config.enabled,
                    "auto_start": state.config.auto_start,
                }
            )

        try:
            from app.services.preferences import get_preferences

            prefs = get_preferences()
            prefs.set_router_outputs(configs)
        except Exception as e:
            print(f"⚠️ Failed to save router config: {e}")

    def _load_config(self):
        """Load configuration from preferences service."""
        try:
            from app.services.preferences import get_preferences

            prefs = get_preferences()
            configs = prefs.get_router_outputs()

            if not configs:
                return

            for cfg in configs:
                output_config = OutputConfig(
                    id=cfg["id"],
                    type=OutputType(cfg["type"]),
                    host=cfg["host"],
                    port=cfg["port"],
                    name=cfg.get("name", ""),
                    enabled=cfg.get("enabled", True),
                    auto_start=cfg.get("auto_start", True),
                )
                self.outputs[output_config.id] = OutputState(config=output_config)

            print(f"✅ Loaded {len(configs)} router outputs from preferences")

            # Auto-start enabled outputs
            for output_id, state in self.outputs.items():
                if state.config.auto_start and state.config.enabled:
                    success, msg = self.start_output(output_id)
                    if success:
                        print(f"🔄 Auto-started output: {output_id}")
                    else:
                        print(f"⚠️ Failed to auto-start {output_id}: {msg}")

        except Exception as e:
            print(f"⚠️ Failed to load router config: {e}")

    def shutdown(self):
        """Shutdown all outputs."""
        self.running = False

        with self.lock:
            for output_id, state in list(self.outputs.items()):
                if state.running:
                    self._stop_output_internal(state)

        print("🛑 Router shutdown complete")


# Global instance
_router_instance: Optional[MAVLinkRouter] = None


def get_router() -> MAVLinkRouter:
    """Get or create the global router instance."""
    global _router_instance
    if _router_instance is None:
        _router_instance = MAVLinkRouter()
    return _router_instance
