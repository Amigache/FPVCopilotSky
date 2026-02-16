"""
System Service
Manages system-level operations
"""

import glob
import os
import platform
import subprocess
import time
from typing import List, Dict, Any
from app.services.cache_service import get_cache_service


class SystemService:
    # Services to monitor
    MONITORED_SERVICES = ["fpvcopilot-sky", "nginx"]

    # Cache for CPU usage calculation
    _last_cpu_times = None
    _last_cpu_check = 0

    # Cache service instance
    _cache = get_cache_service()

    @staticmethod
    def get_memory_info() -> Dict[str, Any]:
        """
        Get memory (RAM) usage information.

        Returns:
            Dictionary with memory information in MB and percentage
        """
        try:
            with open("/proc/meminfo", "r") as f:
                lines = f.readlines()

            mem_info = {}
            for line in lines:
                if ":" in line:
                    key, value = line.split(":")
                    # Parse value (usually in kB)
                    value = value.strip().split()[0]
                    mem_info[key.strip()] = int(value)

            total_kb = mem_info.get("MemTotal", 0)
            free_kb = mem_info.get("MemFree", 0)
            available_kb = mem_info.get("MemAvailable", free_kb)
            buffers_kb = mem_info.get("Buffers", 0)
            cached_kb = mem_info.get("Cached", 0)

            # Calculate used (excluding buffers/cache)
            used_kb = total_kb - available_kb

            total_mb = total_kb / 1024
            used_mb = used_kb / 1024
            available_mb = available_kb / 1024

            percentage = (used_kb / total_kb * 100) if total_kb > 0 else 0

            return {
                "total_mb": round(total_mb, 1),
                "used_mb": round(used_mb, 1),
                "available_mb": round(available_mb, 1),
                "percentage": round(percentage, 1),
                "buffers_mb": round(buffers_kb / 1024, 1),
                "cached_mb": round(cached_kb / 1024, 1),
            }
        except Exception as e:
            print(f"⚠️ Error getting memory info: {e}")
            return {
                "total_mb": 0,
                "used_mb": 0,
                "available_mb": 0,
                "percentage": 0,
                "buffers_mb": 0,
                "cached_mb": 0,
            }

    @staticmethod
    def get_cpu_info() -> Dict[str, Any]:
        """
        Get CPU usage and information.

        Returns:
            Dictionary with CPU usage percentage and core info
        """
        try:
            # Get CPU usage from /proc/stat
            with open("/proc/stat", "r") as f:
                lines = f.readlines()

            # Parse CPU line (first line)
            cpu_line = lines[0].strip()
            cpu_values = cpu_line.split()[1:]  # Skip 'cpu' label

            # Values: user, nice, system, idle, iowait, irq, softirq, steal, guest, guest_nice
            user = int(cpu_values[0])
            nice = int(cpu_values[1])
            system = int(cpu_values[2])
            idle = int(cpu_values[3])
            iowait = int(cpu_values[4]) if len(cpu_values) > 4 else 0

            total = user + nice + system + idle + iowait
            active = user + nice + system

            # Calculate usage based on delta from last check
            current_time = time.time()
            usage = 0.0

            if SystemService._last_cpu_times is not None:
                last_total, last_active = SystemService._last_cpu_times
                total_delta = total - last_total
                active_delta = active - last_active

                if total_delta > 0:
                    usage = (active_delta / total_delta) * 100

            SystemService._last_cpu_times = (total, active)
            SystemService._last_cpu_check = current_time

            # Get number of cores
            cores = 0
            for line in lines:
                if line.startswith("cpu") and line[3].isdigit():
                    cores += 1

            # Get CPU temperature
            temperature = SystemService._get_cpu_temperature()

            # Get CPU frequency
            freq_mhz = SystemService._get_cpu_frequency()

            # Get load average
            load_avg = [0.0, 0.0, 0.0]
            try:
                with open("/proc/loadavg", "r") as f:
                    parts = f.read().split()
                    load_avg = [float(parts[0]), float(parts[1]), float(parts[2])]
            except Exception:
                pass

            return {
                "usage_percent": round(usage, 1),
                "cores": cores,
                "temperature": temperature,
                "frequency_mhz": freq_mhz,
                "load_avg_1m": round(load_avg[0], 2),
                "load_avg_5m": round(load_avg[1], 2),
                "load_avg_15m": round(load_avg[2], 2),
            }
        except Exception as e:
            print(f"⚠️ Error getting CPU info: {e}")
            return {
                "usage_percent": 0,
                "cores": 0,
                "temperature": None,
                "frequency_mhz": None,
                "load_avg_1m": 0,
                "load_avg_5m": 0,
                "load_avg_15m": 0,
            }

    @staticmethod
    def _get_cpu_temperature() -> float | None:
        """Get CPU temperature from thermal zones."""
        temp_paths = [
            "/sys/class/thermal/thermal_zone0/temp",
            "/sys/class/hwmon/hwmon0/temp1_input",
            "/sys/devices/virtual/thermal/thermal_zone0/temp",
        ]

        for path in temp_paths:
            try:
                if os.path.exists(path):
                    with open(path, "r") as f:
                        temp = int(f.read().strip())
                        # Temperature is in millidegrees
                        return round(temp / 1000, 1)
            except Exception:
                pass

        return None

    @staticmethod
    def _get_cpu_frequency() -> int | None:
        """Get current CPU frequency in MHz."""
        freq_paths = [
            "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq",
            "/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_cur_freq",
        ]

        for path in freq_paths:
            try:
                if os.path.exists(path):
                    with open(path, "r") as f:
                        freq_khz = int(f.read().strip())
                        return freq_khz // 1000
            except Exception:
                pass

        return None

    @staticmethod
    def get_services_status() -> List[Dict[str, Any]]:
        """
        Get status of monitored systemd services with CPU/memory usage.

        Returns:
            List of dictionaries with service status information
        """
        services = []

        for service_name in SystemService.MONITORED_SERVICES:
            service_info = {
                "name": service_name,
                "active": False,
                "status": "unknown",
                "description": "",
                "memory": None,
                "memory_bytes": 0,
                "cpu_percent": None,
                "uptime": None,
                "pid": None,
            }

            try:
                # Check if service is active
                result = subprocess.run(
                    ["systemctl", "is-active", service_name],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                service_info["active"] = result.returncode == 0
                service_info["status"] = result.stdout.strip()

                # Get service description, memory, and PID if active
                if service_info["active"]:
                    # Get service properties
                    show_result = subprocess.run(
                        [
                            "systemctl",
                            "show",
                            service_name,
                            "--property=Description,MemoryCurrent,ActiveEnterTimestamp,MainPID",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )

                    if show_result.returncode == 0:
                        for line in show_result.stdout.strip().split("\n"):
                            if "=" in line:
                                key, value = line.split("=", 1)
                                if key == "Description":
                                    service_info["description"] = value
                                elif key == "MemoryCurrent":
                                    try:
                                        mem_bytes = int(value)
                                        service_info["memory_bytes"] = mem_bytes
                                        if mem_bytes >= 1024 * 1024 * 1024:
                                            service_info["memory"] = f"{mem_bytes / (1024*1024*1024):.1f} GB"
                                        else:
                                            service_info["memory"] = f"{mem_bytes // (1024*1024)} MB"
                                    except Exception:
                                        pass
                                elif key == "ActiveEnterTimestamp":
                                    service_info["uptime"] = value
                                elif key == "MainPID":
                                    try:
                                        service_info["pid"] = int(value)
                                    except Exception:
                                        pass

                    # Get CPU usage for the service's main process
                    if service_info["pid"]:
                        cpu_percent = SystemService._get_process_cpu(service_info["pid"])
                        if cpu_percent is not None:
                            service_info["cpu_percent"] = round(cpu_percent, 1)

            except subprocess.TimeoutExpired:
                service_info["status"] = "timeout"
            except Exception as e:
                service_info["status"] = f"error: {str(e)}"

            services.append(service_info)

        return services

    @staticmethod
    def _get_process_cpu(pid: int) -> float | None:
        """Get CPU usage percentage for a process."""
        try:
            # Read process stat
            with open(f"/proc/{pid}/stat", "r") as f:
                stat = f.read().split()

            # utime (14) + stime (15) = total CPU time in jiffies
            utime = int(stat[13])
            stime = int(stat[14])
            total_time = utime + stime

            # Get system uptime
            with open("/proc/uptime", "r") as f:
                uptime = float(f.read().split()[0])

            # Get process start time (in jiffies since boot)
            starttime = int(stat[21])

            # Get clock ticks per second
            clk_tck = os.sysconf(os.sysconf_names["SC_CLK_TCK"])

            # Calculate seconds the process has been running
            seconds = uptime - (starttime / clk_tck)

            if seconds > 0:
                cpu_usage = ((total_time / clk_tck) / seconds) * 100
                return cpu_usage

            return 0.0
        except Exception:
            return None

    @staticmethod
    def get_available_serial_ports() -> List[Dict[str, str]]:
        """
        Get list of available serial ports

        Returns:
            List of dictionaries with port information
        """
        ports = []

        # Check common serial port patterns (Linux)
        patterns = [
            "/dev/ttyAML*",  # Amlogic UART (Radxa, etc)
            "/dev/ttyUSB*",  # USB serial adapters
            "/dev/ttyACM*",  # USB CDC ACM devices
            "/dev/ttyS*",  # Standard serial ports
            "/dev/ttyAMA*",  # ARM serial ports (Raspberry Pi, etc)
            "/dev/serial/by-id/*",  # Persistent USB names
        ]

        for pattern in patterns:
            for port_path in sorted(glob.glob(pattern)):
                # Check if port exists and is accessible
                if os.path.exists(port_path):
                    try:
                        port_info = {
                            "path": port_path,
                            "name": os.path.basename(port_path),
                        }
                        ports.append(port_info)
                    except Exception as e:
                        print(f"⚠️ Error checking port {port_path}: {e}")

        # Remove duplicates (in case of symlinks)
        seen = set()
        unique_ports = []
        for port in ports:
            if port["path"] not in seen:
                seen.add(port["path"])
                unique_ports.append(port)

        return unique_ports

    @staticmethod
    def get_system_info() -> Dict[str, str]:
        """
        Get system information

        Returns:
            Dictionary with system information
        """
        try:
            # Try to read device model
            device_model = "Unknown"
            model_files = [
                "/proc/device-tree/model",
                "/sys/firmware/devicetree/base/model",
            ]

            for model_file in model_files:
                if os.path.exists(model_file):
                    try:
                        with open(model_file, "r") as f:
                            device_model = f.read().strip().replace("\x00", "")
                            break
                    except Exception:
                        pass

            return {
                "platform": platform.system(),
                "machine": platform.machine(),
                "device": device_model,
                "python_version": platform.python_version(),
            }
        except Exception as e:
            print(f"⚠️ Error getting system info: {e}")
            return {
                "platform": "Unknown",
                "machine": "Unknown",
                "device": "Unknown",
                "python_version": platform.python_version(),
            }

    @staticmethod
    def restart_backend() -> Dict[str, Any]:
        """
        Restart the backend service (fpvcopilot-sky)
        Note: This will kill the current process, so we spawn it in background

        Returns:
            Dictionary with success status and message
        """
        try:
            # Use nohup and background process to ensure restart completes
            # even after our process dies
            subprocess.Popen(
                ["sudo", "-n", "systemctl", "restart", "fpvcopilot-sky"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

            return {
                "success": True,
                "message": "Backend service restart initiated. Connection will be lost momentarily.",
            }
        except Exception as e:
            return {"success": False, "message": f"Error restarting backend: {str(e)}"}

    @staticmethod
    def restart_frontend() -> Dict[str, Any]:
        """
        Restart nginx (frontend web server)
        Note: This will kill active connections, so we spawn it in background

        Returns:
            Dictionary with success status and message
        """
        try:
            # Use nohup and background process to ensure restart completes
            # even after connections are lost
            subprocess.Popen(
                ["sudo", "-n", "systemctl", "restart", "nginx"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

            return {
                "success": True,
                "message": "Nginx restart initiated. Connection will be lost momentarily.",
            }
        except Exception as e:
            return {"success": False, "message": f"Error restarting nginx: {str(e)}"}

    @staticmethod
    def get_backend_logs(lines: int = 100) -> str:
        """
        Get backend service logs from journalctl with caching

        Args:
            lines: Number of log lines to retrieve

        Returns:
            Log content as string
        """
        # Check cache using CacheService
        cached_logs = SystemService._cache.get("logs_backend")
        if cached_logs is not None:
            return cached_logs

        # Cache miss or expired - fetch fresh logs
        try:
            result = subprocess.run(
                ["journalctl", "-u", "fpvcopilot-sky", "-n", str(lines), "--no-pager"],
                capture_output=True,
                text=True,
                timeout=3,  # Reduced timeout from 5 to 3 seconds
            )

            if result.returncode == 0:
                logs = result.stdout
            else:
                logs = f"Error fetching logs: {result.stderr}"

            # Update cache with 2 second TTL
            SystemService._cache.set("logs_backend", logs, ttl=2)

            return logs
        except subprocess.TimeoutExpired:
            return "Error: Log fetching timed out"
        except Exception as e:
            return f"Error fetching logs: {str(e)}"

    @staticmethod
    def get_frontend_logs(lines: int = 100) -> str:
        """
        Get frontend logs (nginx access and error logs) with caching

        Args:
            lines: Number of log lines to retrieve

        Returns:
            Log content as string
        """
        # Check cache using CacheService
        cached_logs = SystemService._cache.get("logs_frontend")
        if cached_logs is not None:
            return cached_logs

        # Cache miss or expired - fetch fresh logs
        try:
            # Try to get nginx error logs
            nginx_error = ""
            nginx_access = ""

            # Check for nginx error log
            if os.path.exists("/var/log/nginx/error.log"):
                result = subprocess.run(
                    ["tail", "-n", str(lines // 2), "/var/log/nginx/error.log"],
                    capture_output=True,
                    text=True,
                    timeout=2,  # Reduced timeout from 3 to 2 seconds
                )
                if result.returncode == 0:
                    nginx_error = "=== Nginx Error Log ===\\n" + result.stdout

            # Check for nginx access log
            if os.path.exists("/var/log/nginx/access.log"):
                result = subprocess.run(
                    ["tail", "-n", str(lines // 2), "/var/log/nginx/access.log"],
                    capture_output=True,
                    text=True,
                    timeout=2,  # Reduced timeout from 3 to 2 seconds
                )
                if result.returncode == 0:
                    nginx_access = "\\n=== Nginx Access Log ===\\n" + result.stdout

            combined = nginx_error + nginx_access
            logs = combined if combined else "No frontend logs available"

            # Update cache with 2 second TTL
            SystemService._cache.set("logs_frontend", logs, ttl=2)

            return logs
        except subprocess.TimeoutExpired:
            return "Error: Log fetching timed out"
        except Exception as e:
            return f"Error fetching frontend logs: {str(e)}"
