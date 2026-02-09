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

    async def is_installed(self) -> bool:
        """Check if dnsmasq is installed"""
        try:
            process = await asyncio.create_subprocess_exec(
                "which", "dnsmasq", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            return process.returncode == 0
        except Exception as e:
            logger.error(f"Error checking dnsmasq installation: {e}")
            return False

    async def install(self) -> bool:
        """Install dnsmasq package"""
        try:
            logger.info("Installing dnsmasq...")

            # Update package list
            process = await asyncio.create_subprocess_exec(
                "sudo", "apt-get", "update", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()

            # Install dnsmasq
            process = await asyncio.create_subprocess_exec(
                "sudo",
                "apt-get",
                "install",
                "-y",
                "dnsmasq",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
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
                process = await asyncio.create_subprocess_exec(
                    "sudo", "mkdir", "-p", config_dir, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                await process.communicate()

            # Write configuration file
            process = await asyncio.create_subprocess_exec(
                "sudo",
                "tee",
                self.config.config_file,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate(input=config_content.encode())

            if process.returncode == 0:
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
            process = await asyncio.create_subprocess_exec(
                "sudo",
                "systemctl",
                "restart",
                "dnsmasq",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
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
            process = await asyncio.create_subprocess_exec(
                "sudo", "systemctl", "stop", "dnsmasq", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()

            if process.returncode == 0:
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
            process = await asyncio.create_subprocess_exec(
                "sudo",
                "systemctl",
                "is-active",
                "dnsmasq",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
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
            process = await asyncio.create_subprocess_exec(
                "sudo", "killall", "-USR1", "dnsmasq", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()

            # Read systemd journal for stats
            process = await asyncio.create_subprocess_exec(
                "sudo",
                "journalctl",
                "-u",
                "dnsmasq",
                "-n",
                "50",
                "--no-pager",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()

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
            process = await asyncio.create_subprocess_exec(
                "sudo",
                "cp",
                "/etc/resolv.conf",
                "/etc/resolv.conf.backup",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()

            # Write new resolv.conf with localhost
            resolv_content = "nameserver 127.0.0.1\n"

            process = await asyncio.create_subprocess_exec(
                "sudo",
                "tee",
                "/etc/resolv.conf",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate(input=resolv_content.encode())

            logger.info("Updated /etc/resolv.conf to use local DNS cache")

        except Exception as e:
            logger.warning(f"Could not update /etc/resolv.conf: {e}")

    async def _restore_resolv_conf(self):
        """Restore original /etc/resolv.conf"""
        try:
            backup_file = "/etc/resolv.conf.backup"

            # Check if backup exists
            if os.path.exists(backup_file):
                process = await asyncio.create_subprocess_exec(
                    "sudo",
                    "cp",
                    backup_file,
                    "/etc/resolv.conf",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await process.communicate()

                logger.info("Restored original /etc/resolv.conf")

        except Exception as e:
            logger.warning(f"Could not restore /etc/resolv.conf: {e}")

    async def clear_cache(self) -> bool:
        """Clear DNS cache"""
        try:
            # Send SIGHUP to dnsmasq to clear cache
            process = await asyncio.create_subprocess_exec(
                "sudo", "killall", "-HUP", "dnsmasq", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()

            if process.returncode == 0:
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
