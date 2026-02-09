"""
Network Optimizer Service
Optimizes network configuration for FPV video streaming over 4G/LTE

Features:
- Flight Mode: Optimizes all network parameters for low-latency streaming
- QoS management: DSCP marking for video traffic priority
- MTU optimization: Sets optimal MTU for LTE (1420 bytes)
- TCP tuning: Optimizes kernel parameters for streaming
- Interface optimization: Disables power saving, optimizes buffers
"""

import subprocess
import logging
from typing import Dict, Optional, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class FlightModeConfig:
    """Configuration for Flight Mode optimization"""

    # Network Mode
    force_4g_only: bool = True
    lte_band_preset: str = "urban"  # B3+B7 for lowest latency

    # Interface optimization
    mtu: int = 1420  # Optimal for LTE (1500 - 80 bytes overhead)
    disable_power_save: bool = True

    # QoS settings
    enable_qos: bool = True
    video_ports: List[int] = field(default_factory=lambda: [5600, 5601, 8554])  # WebRTC, RTSP
    dscp_class: str = "EF"  # Expedited Forwarding (46)

    # TCP optimization
    tcp_congestion_control: str = "bbr"  # Bottleneck Bandwidth and RTT
    tcp_window_scaling: bool = True
    tcp_timestamps: bool = True

    # Buffer optimization
    net_core_rmem_max: int = 26214400  # 25MB
    net_core_wmem_max: int = 26214400  # 25MB

    # DNS caching
    enable_dns_cache: bool = True


class NetworkOptimizer:
    """Service for optimizing network for FPV video streaming"""

    def __init__(self):
        self.flight_mode_active = False
        self.original_settings = {}
        self.config = FlightModeConfig()

    def _run_command(self, cmd: List[str], check: bool = True) -> tuple[str, str, int]:
        """Execute command and return (stdout, stderr, returncode)"""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if check and result.returncode != 0:
                logger.error(f"Command failed: {' '.join(cmd)}")
                logger.error(f"stderr: {result.stderr}")

            return result.stdout.strip(), result.stderr.strip(), result.returncode
        except subprocess.TimeoutExpired:
            logger.error(f"Command timeout: {' '.join(cmd)}")
            return "", "Timeout", -1
        except Exception as e:
            logger.error(f"Error running command {cmd}: {e}")
            return "", str(e), -1

    def _get_modem_interface(self) -> Optional[str]:
        """Detect 4G modem interface (192.168.8.x subnet)"""
        stdout, _, returncode = self._run_command(["ip", "-o", "addr", "show"])

        if returncode == 0:
            for line in stdout.split("\n"):
                if "192.168.8." in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        return parts[1]
        return None

    def _save_current_settings(self, interface: str):
        """Save current network settings before optimization"""
        settings = {}

        # Get current MTU
        stdout, _, _ = self._run_command(["ip", "link", "show", interface])
        if "mtu" in stdout:
            mtu_parts = stdout.split("mtu")
            if len(mtu_parts) > 1:
                try:
                    settings["mtu"] = int(mtu_parts[1].split()[0])
                except (ValueError, IndexError):
                    settings["mtu"] = 1500

        # Get current TCP congestion control
        stdout, _, _ = self._run_command(["sysctl", "-n", "net.ipv4.tcp_congestion_control"], check=False)
        settings["tcp_congestion"] = stdout if stdout else "cubic"

        # Get current buffer sizes
        stdout, _, _ = self._run_command(["sysctl", "-n", "net.core.rmem_max"], check=False)
        settings["rmem_max"] = stdout if stdout else "212992"

        stdout, _, _ = self._run_command(["sysctl", "-n", "net.core.wmem_max"], check=False)
        settings["wmem_max"] = stdout if stdout else "212992"

        self.original_settings = settings
        logger.info(f"Saved original settings: {settings}")

    def _set_mtu(self, interface: str, mtu: int) -> bool:
        """Set MTU for interface"""
        _, _, returncode = self._run_command(["sudo", "ip", "link", "set", interface, "mtu", str(mtu)])

        if returncode == 0:
            logger.info(f"Set MTU to {mtu} on {interface}")
            return True
        return False

    def _configure_qos(self, enable: bool = True) -> bool:
        """Configure QoS with iptables DSCP marking"""
        try:
            if enable:
                # Mark video traffic with DSCP EF (46) for highest priority
                for port in self.config.video_ports:
                    # Mark outgoing UDP traffic on video ports
                    self._run_command(
                        [
                            "sudo",
                            "iptables",
                            "-t",
                            "mangle",
                            "-A",
                            "OUTPUT",
                            "-p",
                            "udp",
                            "--dport",
                            str(port),
                            "-j",
                            "DSCP",
                            "--set-dscp",
                            "46",
                        ],
                        check=False,
                    )

                    # Mark incoming UDP traffic on video ports
                    self._run_command(
                        [
                            "sudo",
                            "iptables",
                            "-t",
                            "mangle",
                            "-A",
                            "INPUT",
                            "-p",
                            "udp",
                            "--sport",
                            str(port),
                            "-j",
                            "DSCP",
                            "--set-dscp",
                            "46",
                        ],
                        check=False,
                    )

                logger.info(f"QoS enabled: DSCP marking on ports {self.config.video_ports}")
                return True
            else:
                # Remove QoS rules
                for port in self.config.video_ports:
                    self._run_command(
                        [
                            "sudo",
                            "iptables",
                            "-t",
                            "mangle",
                            "-D",
                            "OUTPUT",
                            "-p",
                            "udp",
                            "--dport",
                            str(port),
                            "-j",
                            "DSCP",
                            "--set-dscp",
                            "46",
                        ],
                        check=False,
                    )

                    self._run_command(
                        [
                            "sudo",
                            "iptables",
                            "-t",
                            "mangle",
                            "-D",
                            "INPUT",
                            "-p",
                            "udp",
                            "--sport",
                            str(port),
                            "-j",
                            "DSCP",
                            "--set-dscp",
                            "46",
                        ],
                        check=False,
                    )

                logger.info("QoS disabled: DSCP rules removed")
                return True

        except Exception as e:
            logger.error(f"Error configuring QoS: {e}")
            return False

    def _optimize_tcp(self, enable: bool = True) -> bool:
        """Optimize TCP parameters for streaming"""
        try:
            if enable:
                # Enable BBR congestion control (best for variable bandwidth like LTE)
                self._run_command(
                    ["sudo", "sysctl", "-w", f"net.ipv4.tcp_congestion_control={self.config.tcp_congestion_control}"]
                )

                # Increase buffer sizes
                self._run_command(["sudo", "sysctl", "-w", f"net.core.rmem_max={self.config.net_core_rmem_max}"])

                self._run_command(["sudo", "sysctl", "-w", f"net.core.wmem_max={self.config.net_core_wmem_max}"])

                # Enable TCP window scaling
                self._run_command(["sudo", "sysctl", "-w", "net.ipv4.tcp_window_scaling=1"])

                # Enable TCP timestamps for better RTT estimation
                self._run_command(["sudo", "sysctl", "-w", "net.ipv4.tcp_timestamps=1"])

                # Reduce TCP retransmission timeout min (faster recovery)
                self._run_command(["sudo", "sysctl", "-w", "net.ipv4.tcp_rto_min=200"])

                logger.info("TCP optimizations enabled")
                return True
            else:
                # Restore original settings
                if "tcp_congestion" in self.original_settings:
                    self._run_command(
                        [
                            "sudo",
                            "sysctl",
                            "-w",
                            f"net.ipv4.tcp_congestion_control={self.original_settings['tcp_congestion']}",
                        ]
                    )

                if "rmem_max" in self.original_settings:
                    self._run_command(
                        ["sudo", "sysctl", "-w", f"net.core.rmem_max={self.original_settings['rmem_max']}"]
                    )

                if "wmem_max" in self.original_settings:
                    self._run_command(
                        ["sudo", "sysctl", "-w", f"net.core.wmem_max={self.original_settings['wmem_max']}"]
                    )

                logger.info("TCP settings restored")
                return True

        except Exception as e:
            logger.error(f"Error optimizing TCP: {e}")
            return False

    def _disable_power_save(self, interface: str, disable: bool = True) -> bool:
        """Disable power saving modes on network interface"""
        try:
            if disable:
                # Disable power management (if supported)
                self._run_command(["sudo", "ethtool", "-s", interface, "wol", "d"], check=False)

                # Set TX queue length to max
                self._run_command(["sudo", "ip", "link", "set", interface, "txqueuelen", "10000"])

                logger.info(f"Power save disabled on {interface}")
                return True
            else:
                # Restore defaults
                self._run_command(["sudo", "ip", "link", "set", interface, "txqueuelen", "1000"])
                logger.info(f"Power save settings restored on {interface}")
                return True

        except Exception as e:
            logger.error(f"Error configuring power save: {e}")
            return False

    def enable_flight_mode(self) -> Dict:
        """
        Enable Flight Mode - Full network optimization for FPV streaming

        Returns:
            Dict with success status and details of optimizations applied
        """
        if self.flight_mode_active:
            return {"success": True, "message": "Flight Mode already active", "active": True}

        try:
            # Detect modem interface
            modem_interface = self._get_modem_interface()
            if not modem_interface:
                return {"success": False, "message": "No modem interface detected (192.168.8.x)", "active": False}

            logger.info(f"Enabling Flight Mode on interface {modem_interface}")

            # Save current settings
            self._save_current_settings(modem_interface)

            optimizations = []

            # 1. Set optimal MTU for LTE
            if self._set_mtu(modem_interface, self.config.mtu):
                optimizations.append(f"MTU set to {self.config.mtu}")

            # 2. Configure QoS (DSCP marking)
            if self.config.enable_qos and self._configure_qos(enable=True):
                optimizations.append(f"QoS enabled on ports {self.config.video_ports}")

            # 3. Optimize TCP parameters
            if self._optimize_tcp(enable=True):
                optimizations.append("TCP optimized (BBR, increased buffers)")

            # 4. Disable power saving
            if self.config.disable_power_save and self._disable_power_save(modem_interface, disable=True):
                optimizations.append("Power saving disabled")

            self.flight_mode_active = True

            logger.info(f"Flight Mode enabled: {', '.join(optimizations)}")

            return {
                "success": True,
                "message": "Flight Mode enabled",
                "active": True,
                "interface": modem_interface,
                "optimizations": optimizations,
                "config": {
                    "mtu": self.config.mtu,
                    "qos_enabled": self.config.enable_qos,
                    "tcp_congestion": self.config.tcp_congestion_control,
                    "video_ports": self.config.video_ports,
                },
            }

        except Exception as e:
            logger.error(f"Error enabling Flight Mode: {e}")
            return {"success": False, "message": f"Error: {str(e)}", "active": False}

    def disable_flight_mode(self) -> Dict:
        """
        Disable Flight Mode and restore original network settings

        Returns:
            Dict with success status
        """
        if not self.flight_mode_active:
            return {"success": True, "message": "Flight Mode not active", "active": False}

        try:
            modem_interface = self._get_modem_interface()
            if not modem_interface:
                logger.warning("Modem interface not found during disable")
                # Still try to clean up

            logger.info(f"Disabling Flight Mode on interface {modem_interface}")

            # Restore original MTU
            if modem_interface and "mtu" in self.original_settings:
                self._set_mtu(modem_interface, self.original_settings["mtu"])

            # Remove QoS rules
            if self.config.enable_qos:
                self._configure_qos(enable=False)

            # Restore TCP settings
            self._optimize_tcp(enable=False)

            # Restore power save settings
            if modem_interface and self.config.disable_power_save:
                self._disable_power_save(modem_interface, disable=False)

            self.flight_mode_active = False
            self.original_settings = {}

            logger.info("Flight Mode disabled: settings restored")

            return {"success": True, "message": "Flight Mode disabled, settings restored", "active": False}

        except Exception as e:
            logger.error(f"Error disabling Flight Mode: {e}")
            return {"success": False, "message": f"Error: {str(e)}", "active": self.flight_mode_active}

    def get_status(self) -> Dict:
        """Get current Flight Mode status"""
        modem_interface = self._get_modem_interface()

        return {
            "active": self.flight_mode_active,
            "interface": modem_interface,
            "config": {
                "mtu": self.config.mtu,
                "qos_enabled": self.config.enable_qos,
                "tcp_congestion": self.config.tcp_congestion_control,
                "video_ports": self.config.video_ports,
                "dscp_class": self.config.dscp_class,
            },
            "original_settings": self.original_settings if self.flight_mode_active else {},
        }

    def get_network_metrics(self) -> Dict:
        """Get current network performance metrics"""
        try:
            metrics = {}

            # Get TCP congestion control
            stdout, _, _ = self._run_command(["sysctl", "-n", "net.ipv4.tcp_congestion_control"], check=False)
            metrics["tcp_congestion"] = stdout

            # Get buffer sizes
            stdout, _, _ = self._run_command(["sysctl", "-n", "net.core.rmem_max"], check=False)
            metrics["rmem_max"] = stdout

            stdout, _, _ = self._run_command(["sysctl", "-n", "net.core.wmem_max"], check=False)
            metrics["wmem_max"] = stdout

            # Get interface MTU
            modem_interface = self._get_modem_interface()
            if modem_interface:
                stdout, _, _ = self._run_command(["ip", "link", "show", modem_interface])
                if "mtu" in stdout:
                    mtu_parts = stdout.split("mtu")
                    if len(mtu_parts) > 1:
                        try:
                            metrics["mtu"] = int(mtu_parts[1].split()[0])
                        except (ValueError, IndexError):
                            metrics["mtu"] = None

            return {"success": True, "metrics": metrics}

        except Exception as e:
            logger.error(f"Error getting network metrics: {e}")
            return {"success": False, "error": str(e)}


# Global instance
_network_optimizer_instance: Optional[NetworkOptimizer] = None


def get_network_optimizer() -> NetworkOptimizer:
    """Get or create network optimizer singleton"""
    global _network_optimizer_instance
    if _network_optimizer_instance is None:
        _network_optimizer_instance = NetworkOptimizer()
    return _network_optimizer_instance
