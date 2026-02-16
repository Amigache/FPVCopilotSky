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

    # CAKE bufferbloat mitigation (Mejora Nº6)
    enable_cake: bool = True
    cake_bandwidth_up_mbit: int = 10  # Upload bandwidth limit (conservative for LTE)
    cake_bandwidth_down_mbit: int = 30  # Download bandwidth limit

    # VPN policy routing (Mejora Nº5)
    enable_vpn_policy_routing: bool = True
    vpn_fwmark: int = 0x100  # fwmark for VPN control traffic
    vpn_table: int = 100  # Routing table for VPN
    video_table: int = 200  # Routing table for video traffic


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

    # ======================
    # CAKE Bufferbloat Mitigation (Mejora Nº6)
    # ======================

    def _configure_cake(self, interface: str, enable: bool = True) -> bool:
        """
        Configure CAKE qdisc for bufferbloat mitigation.

        CAKE (Common Applications Kept Enhanced) is a queue discipline that:
        - Controls latency under load
        - Reduces queue buildup in LTE uplink buffers
        - Dramatically improves RTT stability during video upload

        This is arguably the single most impactful optimization for 4G streaming.
        """
        try:
            if enable:
                # Remove any existing qdisc first
                self._run_command(
                    ["sudo", "tc", "qdisc", "del", "dev", interface, "root"],
                    check=False,
                )

                # Apply CAKE on egress (upload - most critical for video streaming)
                _, stderr, rc = self._run_command(
                    [
                        "sudo",
                        "tc",
                        "qdisc",
                        "replace",
                        "dev",
                        interface,
                        "root",
                        "cake",
                        "bandwidth",
                        f"{self.config.cake_bandwidth_up_mbit}mbit",
                        "besteffort",  # Single-tier (simpler, lower overhead)
                        "wash",  # Clear DSCP on ingress to prevent priority inversion
                        "nat",  # Perform NAT-aware flow isolation
                        "ack-filter",  # Filter redundant ACKs (saves uplink bandwidth)
                    ]
                )

                if rc != 0:
                    logger.warning(f"CAKE setup failed: {stderr}")
                    return False

                # Apply CAKE on ingress via IFB (download bufferbloat control)
                # Create IFB interface if not exists
                self._run_command(
                    ["sudo", "modprobe", "ifb", "numifbs=1"],
                    check=False,
                )
                self._run_command(
                    ["sudo", "ip", "link", "set", "ifb0", "up"],
                    check=False,
                )

                # Redirect ingress to IFB
                self._run_command(
                    ["sudo", "tc", "qdisc", "del", "dev", interface, "ingress"],
                    check=False,
                )
                self._run_command(
                    [
                        "sudo",
                        "tc",
                        "qdisc",
                        "add",
                        "dev",
                        interface,
                        "ingress",
                    ]
                )
                self._run_command(
                    [
                        "sudo",
                        "tc",
                        "filter",
                        "add",
                        "dev",
                        interface,
                        "parent",
                        "ffff:",
                        "protocol",
                        "ip",
                        "u32",
                        "match",
                        "u32",
                        "0",
                        "0",
                        "action",
                        "mirred",
                        "egress",
                        "redirect",
                        "dev",
                        "ifb0",
                    ],
                    check=False,
                )

                # Apply CAKE on IFB (download direction)
                self._run_command(
                    ["sudo", "tc", "qdisc", "del", "dev", "ifb0", "root"],
                    check=False,
                )
                self._run_command(
                    [
                        "sudo",
                        "tc",
                        "qdisc",
                        "replace",
                        "dev",
                        "ifb0",
                        "root",
                        "cake",
                        "bandwidth",
                        f"{self.config.cake_bandwidth_down_mbit}mbit",
                        "besteffort",
                        "wash",
                        "ingress",
                    ],
                    check=False,
                )

                logger.info(
                    f"CAKE enabled on {interface}: "
                    f"up={self.config.cake_bandwidth_up_mbit}mbit, "
                    f"down={self.config.cake_bandwidth_down_mbit}mbit"
                )
                return True
            else:
                # Remove CAKE qdiscs
                self._run_command(
                    ["sudo", "tc", "qdisc", "del", "dev", interface, "root"],
                    check=False,
                )
                self._run_command(
                    ["sudo", "tc", "qdisc", "del", "dev", interface, "ingress"],
                    check=False,
                )
                self._run_command(
                    ["sudo", "tc", "qdisc", "del", "dev", "ifb0", "root"],
                    check=False,
                )
                logger.info(f"CAKE removed from {interface}")
                return True

        except Exception as e:
            logger.error(f"Error configuring CAKE: {e}")
            return False

    def get_cake_stats(self, interface: str = None) -> Dict:
        """Get CAKE qdisc statistics for monitoring"""
        try:
            if not interface:
                interface = self._get_modem_interface()
            if not interface:
                return {"available": False, "error": "No modem interface"}

            stdout, _, rc = self._run_command(["tc", "-s", "qdisc", "show", "dev", interface, "root"])

            if rc != 0 or "cake" not in stdout.lower():
                return {"available": False, "error": "CAKE not active"}

            # Parse basic CAKE stats
            stats = {"available": True, "interface": interface, "raw": stdout}

            import re

            # Extract key metrics
            sent_match = re.search(r"Sent (\d+) bytes (\d+) pkt", stdout)
            if sent_match:
                stats["bytes_sent"] = int(sent_match.group(1))
                stats["packets_sent"] = int(sent_match.group(2))

            dropped_match = re.search(r"dropped (\d+)", stdout)
            if dropped_match:
                stats["dropped"] = int(dropped_match.group(1))

            backlog_match = re.search(r"backlog (\d+)b", stdout)
            if backlog_match:
                stats["backlog_bytes"] = int(backlog_match.group(1))

            return stats

        except Exception as e:
            return {"available": False, "error": str(e)}

    # ======================
    # VPN Policy Routing (Mejora Nº5)
    # ======================

    def _configure_vpn_policy_routing(self, modem_interface: str, enable: bool = True) -> bool:
        """
        Configure policy routing to isolate VPN control traffic from video traffic.

        This ensures that changing the default route (e.g., WiFi↔4G failover)
        does NOT disrupt the VPN tunnel.

        Architecture:
          Table 100 → VPN control traffic (fwmark 0x100)
          Table 200 → Video traffic (fwmark 0x200)
          Main table → Everything else
        """
        try:
            vpn_mark = hex(self.config.vpn_fwmark)
            vpn_table = str(self.config.vpn_table)

            if enable:
                # Find the modem gateway
                stdout, _, _ = self._run_command(["ip", "route", "show", "dev", modem_interface])
                gateway = None
                for line in stdout.split("\n"):
                    if "default" in line:
                        parts = line.split()
                        if "via" in parts:
                            idx = parts.index("via")
                            if idx + 1 < len(parts):
                                gateway = parts[idx + 1]
                                break

                if not gateway:
                    logger.warning("No gateway found for VPN policy routing")
                    return False

                # Add routing rules (idempotent: delete first, then add)
                # Rule: packets with fwmark vpn_mark → lookup vpn_table
                self._run_command(
                    ["sudo", "ip", "rule", "del", "fwmark", vpn_mark, "table", vpn_table],
                    check=False,
                )
                self._run_command(
                    [
                        "sudo",
                        "ip",
                        "rule",
                        "add",
                        "fwmark",
                        vpn_mark,
                        "table",
                        vpn_table,
                    ]
                )

                # Set default route in vpn_table via modem
                self._run_command(
                    ["sudo", "ip", "route", "del", "default", "table", vpn_table],
                    check=False,
                )
                self._run_command(
                    [
                        "sudo",
                        "ip",
                        "route",
                        "add",
                        "default",
                        "via",
                        gateway,
                        "dev",
                        modem_interface,
                        "table",
                        vpn_table,
                    ]
                )

                # Mark Tailscale/VPN control traffic with fwmark
                # Tailscale uses UDP port 41641
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
                        "41641",
                        "-j",
                        "MARK",
                        "--set-mark",
                        vpn_mark,
                    ],
                    check=False,
                )

                # Also mark WireGuard traffic (UDP port 51820)
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
                        "51820",
                        "-j",
                        "MARK",
                        "--set-mark",
                        vpn_mark,
                    ],
                    check=False,
                )

                logger.info(f"VPN policy routing enabled: fwmark={vpn_mark} → table {vpn_table} via {gateway}")
                return True

            else:
                # Remove rules and routes
                self._run_command(
                    ["sudo", "ip", "rule", "del", "fwmark", vpn_mark, "table", vpn_table],
                    check=False,
                )
                self._run_command(
                    ["sudo", "ip", "route", "flush", "table", vpn_table],
                    check=False,
                )

                # Remove iptables marks
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
                        "41641",
                        "-j",
                        "MARK",
                        "--set-mark",
                        vpn_mark,
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
                        "OUTPUT",
                        "-p",
                        "udp",
                        "--dport",
                        "51820",
                        "-j",
                        "MARK",
                        "--set-mark",
                        vpn_mark,
                    ],
                    check=False,
                )

                logger.info("VPN policy routing disabled")
                return True

        except Exception as e:
            logger.error(f"Error configuring VPN policy routing: {e}")
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

            # 5. Enable CAKE bufferbloat mitigation
            if self.config.enable_cake and self._configure_cake(modem_interface, enable=True):
                optimizations.append(
                    f"CAKE enabled (up={self.config.cake_bandwidth_up_mbit}mbit, "
                    f"down={self.config.cake_bandwidth_down_mbit}mbit)"
                )

            # 6. Configure VPN policy routing
            if self.config.enable_vpn_policy_routing and self._configure_vpn_policy_routing(
                modem_interface, enable=True
            ):
                optimizations.append("VPN policy routing enabled (tunnel isolation)")

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

            # Remove CAKE
            if modem_interface and self.config.enable_cake:
                self._configure_cake(modem_interface, enable=False)

            # Remove VPN policy routing
            if modem_interface and self.config.enable_vpn_policy_routing:
                self._configure_vpn_policy_routing(modem_interface, enable=False)

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
                "cake_enabled": self.config.enable_cake,
                "cake_bandwidth_up": self.config.cake_bandwidth_up_mbit,
                "cake_bandwidth_down": self.config.cake_bandwidth_down_mbit,
                "vpn_policy_routing": self.config.enable_vpn_policy_routing,
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

            # Get CAKE stats
            if modem_interface:
                cake_stats = self.get_cake_stats(modem_interface)
                metrics["cake"] = cake_stats

            # Get MPTCP status
            mptcp_stdout, _, mptcp_rc = self._run_command(["sysctl", "-n", "net.mptcp.enabled"], check=False)
            metrics["mptcp_enabled"] = mptcp_stdout.strip() == "1" if mptcp_rc == 0 else False

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
