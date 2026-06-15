"""
Tailscale VPN Provider
Modular implementation of Tailscale VPN integration
"""

import logging
import re
import json
from typing import Dict, Optional, List
from ..base import VPNProvider
from app.utils.cmd import run_cmd

logger = logging.getLogger(__name__)


class TailscaleProvider(VPNProvider):
    """Tailscale VPN provider implementation"""

    def __init__(self):
        super().__init__()
        self.name = "tailscale"
        self.display_name = "Tailscale"

    def is_installed(self) -> bool:
        """Check if Tailscale is installed"""
        try:
            _, _, returncode = run_cmd(["which", "tailscale"], timeout=2, check=False)
            return returncode == 0
        except Exception as e:
            logger.error(f"Error checking Tailscale installation: {e}")
            return False

    def get_status(self) -> Dict:
        """Get Tailscale connection status"""
        if not self.is_installed():
            return {
                "success": False,
                "installed": False,
                "error": "Tailscale not installed",
            }

        try:
            # Get main status
            stdout, stderr, returncode = run_cmd(
                ["tailscale", "status", "--json"],
                timeout=5,
                check=False,
            )

            # Check if logged out
            if "Logged out" in stderr or returncode != 0:
                if "Logged out" in stderr:
                    return {
                        "success": True,
                        "installed": True,
                        "connected": False,
                        "authenticated": False,
                        "message": "Not authenticated",
                    }
                else:
                    return {
                        "success": True,
                        "installed": True,
                        "connected": False,
                        "authenticated": False,
                        "message": "Tailscale daemon not running",
                    }

            # Parse JSON output if available
            try:
                status_data = json.loads(stdout)

                # Extract relevant information
                backend_state = status_data.get("BackendState", "Unknown")
                self_node = status_data.get("Self", {})
                peers = status_data.get("Peer", {}) or {}  # Handle null Peer after logout
                auth_url = status_data.get("AuthURL", "")

                # Check if node is really online and active
                node_online = self_node.get("Online", False)
                node_active = self_node.get("Active", False)

                # Authenticated means has valid credentials and is not in login-required state
                # User is authenticated in these states: Stopped, Starting, Running
                # User is NOT authenticated in: NeedsLogin, NoState
                authenticated = backend_state not in [
                    "NeedsLogin",
                    "NoState",
                    "Unknown",
                    "",
                ]

                # Connected only if backend running AND node is online/active AND authenticated
                connected = backend_state == "Running" and (node_online or node_active) and authenticated

                # Get Tailscale IP
                tailscale_ips = self_node.get("TailscaleIPs", [])
                ip_address = tailscale_ips[0] if tailscale_ips else None

                # Get hostname
                hostname = self_node.get("HostName", "Unknown")

                # Get online peers count
                online_peers = sum(1 for peer in peers.values() if peer.get("Online", False))

                response = {
                    "success": True,
                    "installed": True,
                    "connected": connected,
                    "authenticated": authenticated,
                    "ip_address": ip_address,
                    "hostname": hostname,
                    "interface": self._get_interface(),
                    "peers_count": len(peers),
                    "online_peers": online_peers,
                    "backend_state": backend_state,
                }

                # If there's an auth URL, include it for UI purposes but don't override authenticated
                # (auth_url can temporarily appear during reconnection)
                if auth_url:
                    response["needs_auth"] = True
                    response["auth_url"] = auth_url
                    response["message"] = "Device needs re-authentication"
                    # Override authenticated only if we're actually in NeedsLogin state
                    if backend_state in ["NeedsLogin", "NoState"]:
                        response["authenticated"] = False

                return response

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Tailscale status JSON: {e}")
                return {
                    "success": False,
                    "installed": True,
                    "connected": False,
                    "authenticated": False,
                    "error": "Failed to parse Tailscale status",
                }

        except Exception as e:
            logger.error(f"Error getting Tailscale status: {e}")
            return {"success": False, "installed": True, "error": str(e)}

    def _get_interface(self) -> Optional[str]:
        """Get Tailscale interface name"""
        try:
            stdout, _, _ = run_cmd(["ip", "link", "show"], timeout=2, check=False)
            for line in stdout.split("\n"):
                if "tailscale" in line:
                    match = re.search(r"\d+:\s+(tailscale\d+):", line)
                    if match:
                        return match.group(1)
        except Exception as e:
            logger.error(f"Error getting Tailscale interface: {e}")
        return None

    def connect(self) -> Dict:
        """Connect to Tailscale"""
        try:
            # Check if Tailscale daemon is running
            _, _, daemon_returncode = run_cmd(
                ["systemctl", "is-active", "tailscaled"],
                timeout=5,
                check=False,
            )

            if daemon_returncode != 0:
                # Tailscale daemon is not running
                return {
                    "success": False,
                    "error": "Tailscale daemon is not running. Please start it with: sudo systemctl start tailscaled",
                    "needs_daemon_start": True,
                }

            # Check if already connected
            status = self.get_status()
            if status.get("connected") and status.get("authenticated"):
                return {
                    "success": True,
                    "message": "Already connected",
                    "already_connected": True,
                }

            # First, check if we need a login URL by checking current state
            # If backend_state is NeedsLogin, we need to get an auth URL
            backend_state = status.get("backend_state", "")

            if backend_state == "NeedsLogin" or not status.get("authenticated"):
                # If status already contains an auth URL, return it immediately
                # (tailscale status --json always has AuthURL when in NeedsLogin state)
                if status.get("needs_auth") and status.get("auth_url"):
                    logger.info(f"Auth URL already available from status: {status['auth_url'][:60]}...")
                    return {
                        "success": True,
                        "needs_auth": True,
                        "auth_url": status["auth_url"],
                        "message": "Authentication required",
                    }

                # No auth URL in status; run tailscale up to generate one
                # timeout wraps sudo so it can kill it without needing sudoers entry for timeout
                cmd = ["timeout", "5", "sudo", "-n", "tailscale", "up"]

                logger.info(f"Executing: {' '.join(cmd)}")

                stdout_up, stderr_up, up_returncode = run_cmd(
                    cmd,
                    timeout=10,
                    check=False,
                )
                combined_output = f"{stdout_up}\n{stderr_up}".strip()
                logger.info(f"Tailscale up result: returncode={up_returncode}, output={combined_output[:200]}")
                if up_returncode == -1:
                    logger.warning("Tailscale up timed out at Python level")

                # Try extract auth URL from subprocess output
                auth_url = self._extract_auth_url(combined_output)

                if auth_url:
                    return {
                        "success": True,
                        "needs_auth": True,
                        "auth_url": auth_url,
                        "message": "Authentication required",
                    }

                # Fallback: read tailscale status --json directly for AuthURL
                # (more reliable than going through get_status() wrapper)
                try:
                    raw_stdout, _, raw_returncode = run_cmd(["tailscale", "status", "--json"], timeout=5, check=False)
                    if raw_returncode == 0:
                        status_json = json.loads(raw_stdout)
                        fallback_url = status_json.get("AuthURL", "")
                        if fallback_url:
                            logger.info(f"Got auth URL from status fallback: {fallback_url[:60]}...")
                            return {
                                "success": True,
                                "needs_auth": True,
                                "auth_url": fallback_url,
                                "message": "Authentication required",
                            }
                except Exception as e:
                    logger.warning(f"Fallback status check failed: {e}")

                # Last resort: check via get_status()
                check_status = self.get_status()
                if check_status.get("needs_auth") and check_status.get("auth_url"):
                    return {
                        "success": True,
                        "needs_auth": True,
                        "auth_url": check_status.get("auth_url"),
                        "message": "Authentication required",
                    }

                # If now connected (was already authenticated but just needed 'up')
                if check_status.get("connected"):
                    return {"success": True, "message": "Connected successfully"}

                return {
                    "success": False,
                    "error": "Could not get authentication URL. Try again.",
                }

            # Already authenticated, just need to bring it up
            cmd = ["timeout", "10", "sudo", "-n", "tailscale", "up"]
            logger.info(f"Executing (already authenticated): {' '.join(cmd)}")

            _, _, up_returncode = run_cmd(cmd, timeout=15, check=False)
            if up_returncode == -1:
                logger.warning("Tailscale up timed out for authenticated connect")

            import time

            time.sleep(2)

            verify_status = self.get_status()

            if verify_status.get("connected"):
                return {"success": True, "message": "Connected successfully"}

            # Check if device was deleted from admin panel
            if verify_status.get("backend_state") != "NeedsLogin" and not verify_status.get("needs_auth"):
                logger.warning("Device appears deleted from admin panel")
                return {
                    "success": False,
                    "needs_logout": True,
                    "error": 'Device was deleted from admin panel. Please click the "Logout" button and try again.',
                }

            return {"success": False, "error": "Connection status unclear"}

        except Exception as e:
            logger.error(f"Error connecting Tailscale: {e}")
            return {"success": False, "error": str(e)}

    def _extract_auth_url(self, output: str) -> Optional[str]:
        """Extract authentication URL from output"""
        match = re.search(
            r"https://login\.tailscale\.com/a/[a-zA-Z0-9]+",
            output,
            re.MULTILINE | re.DOTALL,
        )
        return match.group(0) if match else None

    def disconnect(self) -> Dict:
        """Disconnect from Tailscale"""
        try:
            _, stderr, returncode = run_cmd(
                ["sudo", "tailscale", "down"],
                timeout=10,
                check=False,
            )

            if returncode != 0:
                return {"success": False, "error": stderr}

            return {"success": True, "message": "Disconnected successfully"}

        except Exception as e:
            logger.error(f"Error disconnecting Tailscale: {e}")
            return {"success": False, "error": str(e)}

    def logout(self) -> Dict:
        """Logout from Tailscale (clears local credentials)"""
        try:
            # Check if Tailscale daemon is running
            _, _, daemon_returncode = run_cmd(
                ["systemctl", "is-active", "tailscaled"],
                timeout=5,
                check=False,
            )

            if daemon_returncode != 0:
                # Tailscale daemon is not running
                return {
                    "success": False,
                    "error": "Tailscale daemon is not running. Please start it with: sudo systemctl start tailscaled",
                    "needs_daemon_start": True,
                }

            _, stderr, returncode = run_cmd(
                ["sudo", "-n", "tailscale", "logout"],
                timeout=10,
                check=False,
            )

            if returncode != 0:
                error_msg = stderr.strip()
                if "password is required" in error_msg or "a password is required" in error_msg.lower():
                    return {
                        "success": False,
                        "error": (
                            "Logout requires sudo password. " 'Please run "sudo tailscale logout" manually in terminal.'
                        ),
                    }
                return {"success": False, "error": error_msg or "Logout failed"}

            return {
                "success": True,
                "message": "Logged out successfully. You can now reconnect with a fresh authentication.",
            }

        except Exception as e:
            logger.error(f"Error logging out from Tailscale: {e}")
            return {"success": False, "error": str(e)}

    def get_info(self) -> Dict:
        """Get Tailscale provider information"""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": "Secure mesh VPN with easy setup",
            "features": [
                "Zero-config mesh networking",
                "Cross-platform support",
                "Built-in NAT traversal",
                "Free for personal use (up to 20 devices)",
                "Web-based authentication",
            ],
            "requires_auth": True,
            "auth_method": "web",
            "install_url": "https://tailscale.com/download",
        }

    def get_peers(self) -> List[Dict]:
        """Get list of Tailscale peers/nodes"""
        if not self.is_installed():
            return []

        try:
            stdout, stderr, returncode = run_cmd(
                ["tailscale", "status", "--json"],
                timeout=5,
                check=False,
            )

            if returncode != 0:
                logger.error(f"Failed to get Tailscale peers: {stderr}")
                return []

            try:
                status_data = json.loads(stdout)
                peers_data = status_data.get("Peer", {}) or {}
                self_node = status_data.get("Self", {})

                peers = []

                # Add self node first
                if self_node:
                    dns_fqdn = self_node.get("DNSName", "")
                    host_name = self_node.get("HostName", "Unknown")
                    # Extract short hostname from FQDN like "device.tailXXXX.ts.net."
                    display_name = dns_fqdn.split(".")[0] if dns_fqdn else host_name
                    # MagicDNS name (strip trailing dot)
                    magic_dns = dns_fqdn.rstrip(".") if dns_fqdn else ""

                    peers.append(
                        {
                            "id": self_node.get("ID", ""),
                            "hostname": display_name,
                            "dns_name": magic_dns,
                            "ip_addresses": self_node.get("TailscaleIPs", []),
                            "os": self_node.get("OS", "Unknown"),
                            "online": self_node.get("Online", False),
                            "active": self_node.get("Active", False),
                            "is_self": True,
                            "exit_node": self_node.get("ExitNode", False),
                            "exit_node_option": self_node.get("ExitNodeOption", False),
                            "relay": self_node.get("CurAddr", ""),
                            "last_seen": self_node.get("LastSeen", ""),
                        }
                    )

                # Add other peers
                for peer_id, peer_data in peers_data.items():
                    dns_fqdn = peer_data.get("DNSName", "")
                    host_name = peer_data.get("HostName", "Unknown")
                    # Extract short hostname from FQDN like "device.tailXXXX.ts.net."
                    display_name = dns_fqdn.split(".")[0] if dns_fqdn else host_name
                    # MagicDNS name (strip trailing dot)
                    magic_dns = dns_fqdn.rstrip(".") if dns_fqdn else ""

                    peers.append(
                        {
                            "id": peer_id,
                            "hostname": display_name,
                            "dns_name": magic_dns,
                            "ip_addresses": peer_data.get("TailscaleIPs", []),
                            "os": peer_data.get("OS", "Unknown"),
                            "online": peer_data.get("Online", False),
                            "active": peer_data.get("Active", False),
                            "is_self": False,
                            "exit_node": peer_data.get("ExitNode", False),
                            "exit_node_option": peer_data.get("ExitNodeOption", False),
                            "relay": peer_data.get("CurAddr", ""),
                            "last_seen": peer_data.get("LastSeen", ""),
                            "rx_bytes": peer_data.get("RxBytes", 0),
                            "tx_bytes": peer_data.get("TxBytes", 0),
                        }
                    )

                return peers

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Tailscale status JSON: {e}")
                return []

        except Exception as e:
            logger.error(f"Error getting Tailscale peers: {e}")
            return []
