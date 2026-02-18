"""
DNS Caching Service

Local DNS caching with dnsmasq for reduced latency and faster name resolution.
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Optional, List

logger = logging.getLogger(__name__)


@dataclass
class DNSCacheConfig:
    """DNS cache configuration"""

    # dnsmasq configuration
    cache_size: int = 1000  # Number of cached entries
    port: int = 53  # DNS port

    # Upstream DNS servers
    upstream_dns: List[str] = None  # Will default to ["8.8.8.8", "1.1.1.1", "9.9.9.9"]

    # Cache behavior
    min_ttl: int = 300  # Minimum TTL in seconds (5 minutes)
    max_ttl: int = 3600  # Maximum TTL in seconds (1 hour)
    negative_ttl: int = 60  # TTL for negative responses (NXDOMAIN)

    # Configuration file path
    config_file: str = "/etc/dnsmasq.d/fpvcopilot.conf"

    def __post_init__(self):
        if self.upstream_dns is None:
            self.upstream_dns = ["8.8.8.8", "1.1.1.1", "9.9.9.9"]


class DNSCache:
    """
    DNS caching service using dnsmasq.

    Features:
    - Local DNS caching for reduced latency
    - Configurable cache size and TTL
    - Multiple upstream DNS servers
    - Automatic configuration generation
    """

    def __init__(self, config: DNSCacheConfig = None):
        """
        Initialize DNS cache service.

        Args:
            config: DNS cache configuration
        """
        self.config = config or DNSCacheConfig()
        self._active = False

        logger.info(f"DNSCache initialized with cache_size={self.config.cache_size}")

    async def _exec(self, *cmd: str, timeout: float = 10, input_data: bytes = None) -> tuple:
        """Execute a subprocess with timeout protection.

        Args:
            cmd: Command and arguments
            timeout: Max seconds to wait (default: 10)
            input_data: Optional bytes to send to stdin

        Returns:
            Tuple of (stdout_bytes, stderr_bytes, returncode).
            On timeout returns (b"", b"timeout", -1).
        """
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE if input_data else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(input=input_data), timeout=timeout)
            return stdout, stderr, proc.returncode
        except asyncio.TimeoutError:
            logger.warning(f"Command timed out after {timeout}s: {' '.join(cmd)}")
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass
            return b"", b"Command timed out", -1

    async def is_installed(self) -> bool:
        """Check if dnsmasq is installed"""
        try:
            _, _, rc = await self._exec("which", "dnsmasq", timeout=5)
            return rc == 0
        except Exception as e:
            logger.error(f"Error checking dnsmasq installation: {e}")
            return False

    async def install(self) -> bool:
        """Install dnsmasq package"""
        try:
            logger.info("Installing dnsmasq...")

            # Update package list
            await self._exec("sudo", "apt-get", "update", timeout=120)

            # Install dnsmasq
            _, stderr, rc = await self._exec("sudo", "apt-get", "install", "-y", "dnsmasq", timeout=120)

            if rc == 0:
                logger.info("dnsmasq installed successfully")
                return True
            else:
                logger.error(f"Failed to install dnsmasq: {stderr.decode()}")
                return False

        except Exception as e:
            logger.error(f"Error installing dnsmasq: {e}")
            return False

    def _generate_config(self) -> str:
        """Generate dnsmasq configuration"""
        config_lines = [
            "# FPVCopilotSky DNS Cache Configuration",
            "# Auto-generated - do not edit manually",
            "",
            f"# Cache size: {self.config.cache_size} entries",
            f"cache-size={self.config.cache_size}",
            "",
            "# Listen on localhost only",
            "listen-address=127.0.0.1",
            f"port={self.config.port}",
            "",
            "# Do not read /etc/hosts",
            "no-hosts",
            "",
            "# Do not read /etc/resolv.conf",
            "no-resolv",
            "",
            "# Upstream DNS servers",
        ]

        for dns in self.config.upstream_dns:
            config_lines.append(f"server={dns}")

        config_lines.extend(
            [
                "",
                "# TTL settings",
                f"min-cache-ttl={self.config.min_ttl}",
                f"max-cache-ttl={self.config.max_ttl}",
                f"neg-ttl={self.config.negative_ttl}",
                "",
                "# Performance tuning",
                "dns-forward-max=1000",
                "",
                "# Logging (disable for production)",
                "# log-queries",
                "# log-facility=/var/log/dnsmasq.log",
            ]
        )

        return "\n".join(config_lines) + "\n"

    async def configure(self) -> bool:
        """Generate and write dnsmasq configuration"""
        try:
            config_content = self._generate_config()

            # Create config directory if it doesn't exist
            config_dir = os.path.dirname(self.config.config_file)
            if not os.path.exists(config_dir):
                await self._exec("sudo", "mkdir", "-p", config_dir, timeout=10)

            # Write configuration file
            _, _, rc = await self._exec(
                "sudo",
                "tee",
                self.config.config_file,
                timeout=10,
                input_data=config_content.encode(),
            )

            if rc == 0:
                logger.info(f"dnsmasq configuration written to {self.config.config_file}")
                return True
            else:
                logger.error("Failed to write dnsmasq configuration")
                return False

        except Exception as e:
            logger.error(f"Error configuring dnsmasq: {e}")
            return False

    async def start(self) -> bool:
        """Start dnsmasq service"""
        try:
            # Check if installed
            if not await self.is_installed():
                logger.warning("dnsmasq not installed, attempting to install...")
                if not await self.install():
                    return False

            # Generate configuration
            if not await self.configure():
                return False

            # Restart dnsmasq service
            _, stderr, rc = await self._exec("sudo", "systemctl", "restart", "dnsmasq", timeout=15)

            if rc == 0:
                self._active = True
                logger.info("dnsmasq service started successfully")

                # Optionally update /etc/resolv.conf to use local DNS
                await self._update_resolv_conf()

                return True
            else:
                logger.error(f"Failed to start dnsmasq: {stderr.decode()}")
                return False

        except Exception as e:
            logger.error(f"Error starting dnsmasq: {e}")
            return False

    async def stop(self) -> bool:
        """Stop dnsmasq service"""
        try:
            _, _, rc = await self._exec("sudo", "systemctl", "stop", "dnsmasq", timeout=15)

            if rc == 0:
                self._active = False
                logger.info("dnsmasq service stopped")

                # Restore original DNS settings
                await self._restore_resolv_conf()

                return True
            else:
                logger.error("Failed to stop dnsmasq")
                return False

        except Exception as e:
            logger.error(f"Error stopping dnsmasq: {e}")
            return False

    async def get_status(self) -> dict:
        """Get dnsmasq status and statistics"""
        try:
            # Check if service is running
            stdout, _, _ = await self._exec("sudo", "systemctl", "is-active", "dnsmasq", timeout=10)
            is_running = stdout.decode().strip() == "active"

            status = {
                "installed": await self.is_installed(),
                "running": is_running,
                "active": self._active,
                "config": {
                    "cache_size": self.config.cache_size,
                    "upstream_dns": self.config.upstream_dns,
                    "min_ttl": self.config.min_ttl,
                    "max_ttl": self.config.max_ttl,
                },
            }

            # Get statistics if available
            if is_running:
                stats = await self._get_statistics()
                if stats:
                    status["statistics"] = stats

            return status

        except Exception as e:
            logger.error(f"Error getting dnsmasq status: {e}")
            return {"installed": False, "running": False, "active": False, "error": str(e)}

    async def _get_statistics(self) -> Optional[dict]:
        """Get dnsmasq cache statistics"""
        try:
            # Send SIGUSR1 to dnsmasq to dump cache stats to log
            await self._exec("sudo", "killall", "-USR1", "dnsmasq", timeout=5)

            # Read systemd journal for stats
            stdout, _, _ = await self._exec(
                "sudo",
                "journalctl",
                "-u",
                "dnsmasq",
                "-n",
                "50",
                "--no-pager",
                timeout=10,
            )

            log_output = stdout.decode()

            # Parse cache statistics from log
            # Look for lines like "cache size 1000, 0/123 cache insertions re-used unexpired cache entries"
            stats = {
                "cache_hits": 0,
                "cache_misses": 0,
                "cache_insertions": 0,
            }

            for line in log_output.split("\n"):
                if "cache size" in line:
                    # Parse cache statistics
                    # This is a simplified parser - actual format may vary
                    pass

            return stats

        except Exception as e:
            logger.debug(f"Could not get dnsmasq statistics: {e}")
            return None

    async def _update_resolv_conf(self):
        """Update /etc/resolv.conf to use local DNS cache"""
        try:
            # Backup original resolv.conf
            await self._exec(
                "sudo",
                "cp",
                "/etc/resolv.conf",
                "/etc/resolv.conf.backup",
                timeout=10,
            )

            # Write new resolv.conf with localhost
            resolv_content = "nameserver 127.0.0.1\n"

            await self._exec(
                "sudo",
                "tee",
                "/etc/resolv.conf",
                timeout=10,
                input_data=resolv_content.encode(),
            )

            logger.info("Updated /etc/resolv.conf to use local DNS cache")

        except Exception as e:
            logger.warning(f"Could not update /etc/resolv.conf: {e}")

    async def _restore_resolv_conf(self):
        """Restore original /etc/resolv.conf"""
        try:
            backup_file = "/etc/resolv.conf.backup"

            # Check if backup exists
            if os.path.exists(backup_file):
                await self._exec("sudo", "cp", backup_file, "/etc/resolv.conf", timeout=10)

                logger.info("Restored original /etc/resolv.conf")

        except Exception as e:
            logger.warning(f"Could not restore /etc/resolv.conf: {e}")

    async def clear_cache(self) -> bool:
        """Clear DNS cache"""
        try:
            # Send SIGHUP to dnsmasq to clear cache
            _, _, rc = await self._exec("sudo", "killall", "-HUP", "dnsmasq", timeout=5)

            if rc == 0:
                logger.info("DNS cache cleared")
                return True
            else:
                return False

        except Exception as e:
            logger.error(f"Error clearing DNS cache: {e}")
            return False


# Global DNS cache instance
_dns_cache: Optional[DNSCache] = None


def get_dns_cache() -> DNSCache:
    """Get global DNS cache instance"""
    global _dns_cache
    if _dns_cache is None:
        _dns_cache = DNSCache()
    return _dns_cache
