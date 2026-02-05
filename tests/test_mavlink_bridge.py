#!/usr/bin/env python3
"""
Test MAVLink Bridge/Router functionality step by step.

Este script ayuda a depurar el puente MAVLink entre serial y TCP.
Ejecutar con: python3 -m tests.test_mavlink_bridge

Pruebas:
1. Conexión serial directa
2. Servidor TCP standalone
3. Bridge bidireccional
"""

import os
# Habilitar MAVLink 2.0
os.environ['MAVLINK20'] = '1'

import socket
import threading
import time
import sys
import argparse
from pymavlink import mavutil


class Colors:
    """ANSI colors for terminal output."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'


def log_info(msg):
    print(f"{Colors.BLUE}[INFO]{Colors.RESET} {msg}")


def log_success(msg):
    print(f"{Colors.GREEN}[OK]{Colors.RESET} {msg}")


def log_error(msg):
    print(f"{Colors.RED}[ERROR]{Colors.RESET} {msg}")


def log_warning(msg):
    print(f"{Colors.YELLOW}[WARN]{Colors.RESET} {msg}")


def log_data(direction, msg):
    print(f"{Colors.CYAN}[{direction}]{Colors.RESET} {msg}")


# ============================================================
# TEST 1: Conexión serial directa
# ============================================================
def test_serial_connection(port: str, baudrate: int):
    """Prueba la conexión serial directa con MAVLink."""
    print("\n" + "="*60)
    print("TEST 1: Conexión serial directa")
    print("="*60)
    
    log_info(f"Conectando a {port} @ {baudrate}...")
    
    try:
        conn = mavutil.mavlink_connection(
            port, 
            baud=baudrate, 
            source_system=255,
            dialect='ardupilotmega'
        )
        log_success(f"Puerto abierto: {port}")
    except Exception as e:
        log_error(f"No se puede abrir el puerto: {e}")
        return False
    
    log_info("Esperando heartbeat...")
    msg = conn.wait_heartbeat(timeout=10)
    
    if msg:
        log_success(f"Heartbeat recibido!")
        log_info(f"  System ID: {conn.target_system}")
        log_info(f"  Component ID: {conn.target_component}")
        log_info(f"  MAV Type: {msg.type}")
        log_info(f"  Autopilot: {msg.autopilot}")
        
        # Leer algunos mensajes más
        log_info("Leyendo mensajes (5 segundos)...")
        count = 0
        start_time = time.time()
        while time.time() - start_time < 5:
            msg = conn.recv_match(blocking=True, timeout=1)
            if msg:
                count += 1
                msg_type = msg.get_type()
                if count <= 10:  # Solo mostrar primeros 10
                    log_data("RX", f"{msg_type}")
        
        log_success(f"Recibidos {count} mensajes en 5 segundos ({count/5:.1f} msg/s)")
        conn.close()
        return True
    else:
        log_error("No se recibió heartbeat")
        conn.close()
        return False


# ============================================================
# TEST 2: Servidor TCP standalone
# ============================================================
def test_tcp_server(port: int):
    """Prueba un servidor TCP simple."""
    print("\n" + "="*60)
    print("TEST 2: Servidor TCP standalone")
    print("="*60)
    
    log_info(f"Iniciando servidor TCP en 0.0.0.0:{port}...")
    
    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('0.0.0.0', port))
        server.listen(5)
        server.settimeout(30)  # 30 segundos timeout
        log_success(f"Servidor escuchando en puerto {port}")
    except OSError as e:
        if e.errno == 98:
            log_error(f"Puerto {port} ya está en uso")
        else:
            log_error(f"Error: {e}")
        return False
    
    log_info("Esperando conexión de cliente (30s timeout)...")
    log_info("Conecta con: nc localhost {port}")
    
    try:
        client, addr = server.accept()
        log_success(f"Cliente conectado desde {addr}")
        
        # Enviar mensaje de prueba
        test_msg = b"Hello from FPVCopilotSky!\n"
        client.send(test_msg)
        log_info("Mensaje de prueba enviado")
        
        # Esperar respuesta
        client.settimeout(5)
        try:
            data = client.recv(1024)
            if data:
                log_success(f"Respuesta recibida: {data.decode().strip()}")
        except socket.timeout:
            log_warning("No se recibió respuesta del cliente (normal si usas nc)")
        
        client.close()
        server.close()
        return True
        
    except socket.timeout:
        log_error("Timeout esperando cliente")
        server.close()
        return False


# ============================================================
# TEST 3: Bridge MAVLink bidireccional
# ============================================================
class MAVLinkBridge:
    """
    Bridge MAVLink simple y funcional.
    Conecta serial <-> TCP con comunicación bidireccional.
    """
    
    def __init__(self, serial_port: str, baudrate: int, tcp_port: int):
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.tcp_port = tcp_port
        
        self.serial_conn = None
        self.tcp_server = None
        self.tcp_clients = []
        self.running = False
        self.lock = threading.Lock()
        
        # Statistics
        self.stats = {
            "serial_to_tcp": 0,
            "tcp_to_serial": 0,
            "errors": 0
        }
    
    def start(self):
        """Inicia el bridge."""
        log_info(f"Iniciando bridge: {self.serial_port} <-> TCP:{self.tcp_port}")
        
        # 1. Conectar al serial
        log_info(f"Conectando a serial {self.serial_port}...")
        try:
            self.serial_conn = mavutil.mavlink_connection(
                self.serial_port, 
                baud=self.baudrate,
                source_system=255,
                source_component=0,
                dialect='ardupilotmega'
            )
            log_success("Puerto serial abierto")
        except Exception as e:
            log_error(f"Error abriendo serial: {e}")
            return False
        
        # Esperar heartbeat
        log_info("Esperando heartbeat...")
        msg = self.serial_conn.wait_heartbeat(timeout=10)
        if not msg:
            log_error("No se recibió heartbeat")
            return False
        log_success(f"Heartbeat de system {self.serial_conn.target_system}")
        
        # 2. Iniciar servidor TCP
        log_info(f"Iniciando servidor TCP en puerto {self.tcp_port}...")
        try:
            self.tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.tcp_server.bind(('0.0.0.0', self.tcp_port))
            self.tcp_server.listen(5)
            self.tcp_server.settimeout(1.0)
            log_success(f"Servidor TCP escuchando en puerto {self.tcp_port}")
        except Exception as e:
            log_error(f"Error iniciando servidor TCP: {e}")
            return False
        
        self.running = True
        
        # 3. Iniciar threads
        # Thread para aceptar conexiones TCP
        self.accept_thread = threading.Thread(target=self._accept_clients, daemon=True)
        self.accept_thread.start()
        
        # Thread para leer del serial y enviar a TCP
        self.serial_rx_thread = threading.Thread(target=self._serial_to_tcp, daemon=True)
        self.serial_rx_thread.start()
        
        log_success("Bridge iniciado correctamente")
        log_info("Conecta Mission Planner a: tcp:IP_RASPBERRY:" + str(self.tcp_port))
        
        return True
    
    def stop(self):
        """Detiene el bridge."""
        log_info("Deteniendo bridge...")
        self.running = False
        
        # Cerrar clientes
        with self.lock:
            for client in self.tcp_clients:
                try:
                    client.close()
                except:
                    pass
            self.tcp_clients = []
        
        # Cerrar servidor
        if self.tcp_server:
            try:
                self.tcp_server.close()
            except:
                pass
        
        # Cerrar serial
        if self.serial_conn:
            try:
                self.serial_conn.close()
            except:
                pass
        
        log_success("Bridge detenido")
        self._print_stats()
    
    def _accept_clients(self):
        """Thread para aceptar conexiones TCP."""
        log_info("Thread de aceptación iniciado")
        while self.running:
            try:
                client, addr = self.tcp_server.accept()
                log_success(f"Cliente TCP conectado desde {addr}")
                
                # Configurar socket
                client.setblocking(False)
                
                with self.lock:
                    self.tcp_clients.append(client)
                
                # Iniciar thread para leer de este cliente
                client_thread = threading.Thread(
                    target=self._tcp_to_serial,
                    args=(client, addr),
                    daemon=True
                )
                client_thread.start()
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    log_error(f"Error aceptando cliente: {e}")
    
    def _serial_to_tcp(self):
        """Lee mensajes del serial y los envía a todos los clientes TCP."""
        log_info("Thread Serial→TCP iniciado")
        
        while self.running:
            try:
                # Leer mensaje MAVLink del serial
                msg = self.serial_conn.recv_match(blocking=True, timeout=1)
                
                if msg:
                    # Obtener bytes raw del mensaje
                    raw_bytes = msg.get_msgbuf()
                    msg_type = msg.get_type()
                    
                    # Enviar a todos los clientes TCP
                    with self.lock:
                        dead_clients = []
                        
                        for client in self.tcp_clients:
                            try:
                                client.send(raw_bytes)
                                self.stats["serial_to_tcp"] += 1
                            except (BlockingIOError, socket.error):
                                # Buffer lleno o cliente desconectado
                                pass
                            except (BrokenPipeError, ConnectionResetError) as e:
                                log_warning(f"Cliente desconectado: {e}")
                                dead_clients.append(client)
                            except Exception as e:
                                log_error(f"Error enviando a cliente: {e}")
                                dead_clients.append(client)
                        
                        # Limpiar clientes muertos
                        for dead in dead_clients:
                            try:
                                dead.close()
                            except:
                                pass
                            self.tcp_clients.remove(dead)
                    
                    # Log periódico
                    if self.stats["serial_to_tcp"] % 100 == 0:
                        log_data("S→T", f"{self.stats['serial_to_tcp']} mensajes enviados a {len(self.tcp_clients)} clientes")
                        
            except Exception as e:
                if self.running:
                    log_error(f"Error leyendo serial: {e}")
                    self.stats["errors"] += 1
                time.sleep(0.1)
    
    def _tcp_to_serial(self, client: socket.socket, addr):
        """Lee mensajes de un cliente TCP y los envía al serial."""
        log_info(f"Thread TCP→Serial iniciado para {addr}")
        
        # Buffer para acumular datos parciales
        buffer = b''
        
        # Crear un parser MAVLink para este cliente
        mav = mavutil.mavlink.MAVLink(None)
        
        while self.running:
            try:
                # Intentar leer datos del cliente
                try:
                    data = client.recv(1024)
                except BlockingIOError:
                    # No hay datos disponibles, esperar un poco
                    time.sleep(0.01)
                    continue
                
                if not data:
                    # Cliente cerró conexión
                    log_warning(f"Cliente {addr} cerró conexión")
                    break
                
                buffer += data
                
                # Procesar mensajes MAVLink del buffer
                while len(buffer) > 0:
                    try:
                        # Buscar inicio de mensaje MAVLink (0xFD para v2, 0xFE para v1)
                        if buffer[0] not in [0xFD, 0xFE]:
                            # Descartar byte inválido
                            buffer = buffer[1:]
                            continue
                        
                        # Determinar longitud del mensaje
                        if len(buffer) < 2:
                            break  # Necesitamos más datos
                        
                        if buffer[0] == 0xFD:  # MAVLink v2
                            if len(buffer) < 10:
                                break  # Header incompleto
                            payload_len = buffer[1]
                            msg_len = 12 + payload_len  # Header(10) + payload + CRC(2)
                        else:  # MAVLink v1 (0xFE)
                            if len(buffer) < 6:
                                break
                            payload_len = buffer[1]
                            msg_len = 8 + payload_len  # Header(6) + payload + CRC(2)
                        
                        if len(buffer) < msg_len:
                            break  # Mensaje incompleto
                        
                        # Extraer mensaje completo
                        msg_bytes = buffer[:msg_len]
                        buffer = buffer[msg_len:]
                        
                        # Enviar al serial (raw bytes)
                        if self.serial_conn:
                            # Usar port.write directamente para enviar bytes raw
                            self.serial_conn.port.write(msg_bytes)
                            self.stats["tcp_to_serial"] += 1
                            
                            # Log periódico
                            if self.stats["tcp_to_serial"] % 10 == 0:
                                log_data("T→S", f"{self.stats['tcp_to_serial']} mensajes de TCP a serial")
                                
                    except Exception as e:
                        log_error(f"Error procesando mensaje: {e}")
                        self.stats["errors"] += 1
                        # Descartar un byte e intentar continuar
                        if len(buffer) > 0:
                            buffer = buffer[1:]
                        break
                        
            except (ConnectionResetError, BrokenPipeError):
                log_warning(f"Cliente {addr} desconectado")
                break
            except Exception as e:
                if self.running:
                    log_error(f"Error en TCP→Serial: {e}")
                    self.stats["errors"] += 1
                time.sleep(0.1)
        
        # Limpiar cliente
        with self.lock:
            if client in self.tcp_clients:
                self.tcp_clients.remove(client)
        try:
            client.close()
        except:
            pass
        log_info(f"Thread para {addr} terminado")
    
    def _print_stats(self):
        """Imprime estadísticas."""
        print("\n" + "-"*40)
        print("Estadísticas del Bridge:")
        print(f"  Serial → TCP: {self.stats['serial_to_tcp']} mensajes")
        print(f"  TCP → Serial: {self.stats['tcp_to_serial']} mensajes")
        print(f"  Errores: {self.stats['errors']}")
        print("-"*40)


def test_bridge(serial_port: str, baudrate: int, tcp_port: int):
    """Prueba el bridge MAVLink completo."""
    print("\n" + "="*60)
    print("TEST 3: Bridge MAVLink bidireccional")
    print("="*60)
    
    bridge = MAVLinkBridge(serial_port, baudrate, tcp_port)
    
    if not bridge.start():
        log_error("Error iniciando bridge")
        return False
    
    print("\n" + "-"*40)
    print(f"Bridge activo en puerto TCP {tcp_port}")
    print("Conecta Mission Planner con: tcp:IP:{tcp_port}")
    print("Presiona Ctrl+C para detener")
    print("-"*40 + "\n")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n")
        log_info("Interrupción recibida, deteniendo...")
    
    bridge.stop()
    return True


# ============================================================
# MAIN
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="Test MAVLink Bridge functionality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Test 1: Probar conexión serial
  python3 test_mavlink_bridge.py --test serial --port /dev/ttyAML0
  
  # Test 2: Probar servidor TCP
  python3 test_mavlink_bridge.py --test tcp --tcp-port 5760
  
  # Test 3: Bridge completo (Serial <-> TCP)
  python3 test_mavlink_bridge.py --test bridge --port /dev/ttyAML0 --tcp-port 5760
        """
    )
    
    parser.add_argument('--test', choices=['serial', 'tcp', 'bridge'], 
                        default='bridge', help='Tipo de test a ejecutar')
    parser.add_argument('--port', default='/dev/ttyAML0', 
                        help='Puerto serial (default: /dev/ttyAML0)')
    parser.add_argument('--baudrate', type=int, default=115200, 
                        help='Baudrate (default: 115200)')
    parser.add_argument('--tcp-port', type=int, default=5760, 
                        help='Puerto TCP (default: 5760)')
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("FPVCopilotSky - MAVLink Bridge Test")
    print("="*60)
    
    success = False
    
    if args.test == 'serial':
        success = test_serial_connection(args.port, args.baudrate)
    elif args.test == 'tcp':
        success = test_tcp_server(args.tcp_port)
    elif args.test == 'bridge':
        success = test_bridge(args.port, args.baudrate, args.tcp_port)
    
    print("\n" + "="*60)
    if success:
        log_success(f"Test '{args.test}' completado exitosamente")
    else:
        log_error(f"Test '{args.test}' falló")
    print("="*60 + "\n")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
