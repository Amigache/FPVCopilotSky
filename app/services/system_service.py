"""
System Service
Manages system-level operations
"""

import glob
import os
import platform
import subprocess
import time
import requests
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

    # Local data directory for installation-specific files
    DATA_DIR = "/var/lib/fpvcopilot-sky"

    # Version file path (local to installation)
    VERSION_FILE = os.path.join(DATA_DIR, "version")

    # Previous version file (for rollback)
    PREVIOUS_VERSION_FILE = os.path.join(DATA_DIR, "previous_version")

    @staticmethod
    def _ensure_data_directory():
        """Ensure the data directory exists with proper permissions"""
        try:
            os.makedirs(SystemService.DATA_DIR, mode=0o755, exist_ok=True)
        except Exception as e:
            print(f"Warning: Failed to create data directory: {str(e)}")

    @staticmethod
    def get_version() -> Dict[str, str]:
        """
        Get current installed version from local version file.
        If local file doesn't exist, read from git tag.

        Returns:
            Dictionary with version string
        """
        SystemService._ensure_data_directory()

        try:
            # Try local version file first
            if os.path.exists(SystemService.VERSION_FILE):
                with open(SystemService.VERSION_FILE, "r") as f:
                    version = f.read().strip()
                    if version:
                        return {"version": version, "success": True}

            # Fallback: get version from git tag
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            result = subprocess.run(
                ["git", "describe", "--tags", "--exact-match", "HEAD"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                git_version = result.stdout.strip().lstrip("v")
                # Save to local file for future use
                with open(SystemService.VERSION_FILE, "w") as f:
                    f.write(git_version)
                return {"version": git_version, "success": True}
            else:
                return {
                    "version": "unknown",
                    "success": False,
                    "error": "VERSION file not found",
                }
        except Exception as e:
            return {"version": "unknown", "success": False, "error": str(e)}

    @staticmethod
    def check_for_updates() -> Dict[str, Any]:
        """
        Check for updates by comparing local version with GitHub releases.

        Returns:
            Dictionary with update information
        """
        try:
            # Get current version
            current_version_data = SystemService.get_version()
            if not current_version_data.get("success"):
                return {
                    "success": False,
                    "error": "Could not read current version",
                    "current_version": "unknown",
                }

            current_version = current_version_data["version"]

            # GitHub API URL for latest release
            # Format: https://api.github.com/repos/OWNER/REPO/releases/latest
            github_api_url = "https://api.github.com/repos/Amigache/FPVCopilotSky/releases/latest"

            # Make request with timeout
            response = requests.get(github_api_url, timeout=10)

            if response.status_code == 404:
                # No releases yet
                return {
                    "success": True,
                    "update_available": False,
                    "current_version": current_version,
                    "latest_version": current_version,
                    "message": "No releases published yet",
                }

            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"GitHub API returned status {response.status_code}",
                    "current_version": current_version,
                }

            release_data = response.json()

            # Extract version from tag_name (removes 'v' prefix if present)
            latest_version = release_data.get("tag_name", "").lstrip("v")
            release_name = release_data.get("name", "")
            release_notes = release_data.get("body", "")
            published_at = release_data.get("published_at", "")
            html_url = release_data.get("html_url", "")

            # Compare versions (simple string comparison for semantic versioning)
            update_available = SystemService._compare_versions(current_version, latest_version)

            return {
                "success": True,
                "update_available": update_available,
                "current_version": current_version,
                "latest_version": latest_version,
                "release_name": release_name,
                "release_notes": release_notes,
                "published_at": published_at,
                "url": html_url,
            }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "error": "GitHub API timeout",
                "current_version": current_version_data.get("version", "unknown"),
            }
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": f"Network error: {str(e)}",
                "current_version": current_version_data.get("version", "unknown"),
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "current_version": current_version_data.get("version", "unknown"),
            }

    @staticmethod
    def _compare_versions(current: str, latest: str) -> bool:
        """
        Compare two semantic version strings.

        Returns:
            True if latest > current, False otherwise
        """
        try:
            # Split versions into parts (e.g., "1.2.3" -> [1, 2, 3])
            current_parts = [int(x) for x in current.split(".")]
            latest_parts = [int(x) for x in latest.split(".")]

            # Pad shorter version with zeros
            max_len = max(len(current_parts), len(latest_parts))
            current_parts += [0] * (max_len - len(current_parts))
            latest_parts += [0] * (max_len - len(latest_parts))

            # Compare part by part
            return latest_parts > current_parts
        except (ValueError, AttributeError):
            # If parsing fails, do simple string comparison
            return latest > current

    @staticmethod
    def _restart_service_delayed(delay_seconds: int = 2) -> None:
        """
        Restart the service after a short delay.
        Called as a BackgroundTask so the HTTP response is sent BEFORE the restart.
        """
        time.sleep(delay_seconds)
        subprocess.run(
            ["sudo", "systemctl", "restart", "fpvcopilot-sky"],
            capture_output=True,
            text=True,
            timeout=30,
        )

    @staticmethod
    def apply_update(target_version: str = None, do_restart: bool = True) -> Dict[str, Any]:  # noqa: C901
        """
        Apply system update by checking out a specific version tag from git.

        This method:
        1. Verifies update availability
        2. Checks git repository status
        3. Fetches latest changes and checks out the target version tag
        4. Updates dependencies
        5. Updates VERSION file
        6. Rebuilds frontend
        7. Restarts backend service

        Args:
            target_version: Version to update to (e.g., "1.0.1"). If None, uses latest from GitHub.

        Returns:
            Dictionary with update status and progress information
        """
        # Get project root directory
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

        try:
            # Step 1: Check for updates
            if target_version is None:
                update_info = SystemService.check_for_updates()
                if not update_info.get("success"):
                    return {
                        "success": False,
                        "step": "check_updates",
                        "error": "Failed to check for updates",
                        "details": update_info.get("error", "Unknown error"),
                    }

                if not update_info.get("update_available"):
                    return {
                        "success": False,
                        "step": "check_updates",
                        "error": "No update available",
                        "current_version": update_info.get("current_version"),
                        "latest_version": update_info.get("latest_version"),
                    }

                target_version = update_info.get("latest_version")

            # Step 2: Reset any local changes (users cannot commit in installed apps)
            try:
                subprocess.run(
                    ["git", "reset", "--hard"],
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            except Exception as e:
                # Non-fatal, force checkout will handle it
                print(f"Warning: git reset had issues: {str(e)}")

            # Step 3: Fetch latest changes from GitHub
            try:
                result = subprocess.run(
                    ["git", "fetch", "origin", "--tags"],
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode != 0:
                    return {
                        "success": False,
                        "step": "git_fetch",
                        "error": "Git fetch failed",
                        "details": result.stderr,
                    }

            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "step": "git_fetch",
                    "error": "Git fetch timed out (network issue?)",
                }
            except Exception as e:
                return {
                    "success": False,
                    "step": "git_fetch",
                    "error": f"Failed to fetch updates: {str(e)}",
                }

            # Step 3: Save current version BEFORE checkout (for rollback)
            original_version = None
            try:
                current_version_data = SystemService.get_version()
                if current_version_data.get("success"):
                    original_version = current_version_data["version"]
            except Exception as e:
                return {
                    "success": False,
                    "step": "save_original_version",
                    "error": f"Failed to read original version: {str(e)}",
                }

            # Step 4: Checkout target version tag
            tag_name = f"v{target_version}"
            try:
                # First verify the tag exists
                result = subprocess.run(
                    ["git", "tag", "-l", tag_name],
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if not result.stdout.strip():
                    return {
                        "success": False,
                        "step": "git_checkout",
                        "error": f"Tag {tag_name} not found in repository",
                    }

                # Force checkout the tag (discard any local changes)
                result = subprocess.run(
                    ["git", "checkout", "--force", tag_name],
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode != 0:
                    return {
                        "success": False,
                        "step": "git_checkout",
                        "error": f"Failed to checkout {tag_name}",
                        "details": result.stderr,
                    }

            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "step": "git_checkout",
                    "error": "Git checkout timed out",
                }
            except Exception as e:
                return {
                    "success": False,
                    "step": "git_checkout",
                    "error": f"Failed to checkout version: {str(e)}",
                }

            # Step 5: Save original version to .previous_version for rollback
            try:
                if original_version:
                    # Save original version to .previous_version for rollback
                    with open(SystemService.PREVIOUS_VERSION_FILE, "w") as f:
                        f.write(original_version)

                # Update VERSION file to new version
                with open(SystemService.VERSION_FILE, "w") as f:
                    f.write(target_version)
            except Exception as e:
                return {
                    "success": False,
                    "step": "update_version_file",
                    "error": f"Failed to update VERSION file: {str(e)}",
                }

            # Step 6: Install Python dependencies
            try:
                venv_python = os.path.join(project_root, "venv", "bin", "python3")
                requirements_file = os.path.join(project_root, "requirements.txt")

                result = subprocess.run(
                    [venv_python, "-m", "pip", "install", "-r", requirements_file],
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minutes for pip install
                )

                if result.returncode != 0:
                    # Non-fatal, continue with update
                    print(f"Warning: pip install had issues: {result.stderr}")  # Log but don't fail

            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "step": "install_dependencies",
                    "error": "Dependencies installation timed out",
                }
            except Exception as e:
                # Non-fatal, log and continue
                print(f"Warning: Failed to install dependencies: {str(e)}")

            # Step 7: Rebuild frontend
            try:
                frontend_dir = os.path.join(project_root, "frontend", "client")

                # Run npm install (in case there are new dependencies)
                result = subprocess.run(
                    ["npm", "install"],
                    cwd=frontend_dir,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minutes
                )

                # Run npm build
                result = subprocess.run(
                    ["npm", "run", "build"],
                    cwd=frontend_dir,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minutes
                )

                if result.returncode != 0:
                    return {
                        "success": False,
                        "step": "build_frontend",
                        "error": "Frontend build failed",
                        "details": result.stderr,
                    }

            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "step": "build_frontend",
                    "error": "Frontend build timed out",
                }
            except Exception as e:
                return {
                    "success": False,
                    "step": "build_frontend",
                    "error": f"Failed to build frontend: {str(e)}",
                }

            # Step 8: Restart backend service (only if not delegated to BackgroundTasks)
            if do_restart:
                try:
                    result = subprocess.run(
                        ["sudo", "systemctl", "restart", "fpvcopilot-sky"],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )

                    if result.returncode != 0:
                        return {
                            "success": False,
                            "step": "restart_service",
                            "error": "Failed to restart backend service",
                            "details": result.stderr,
                        }

                except subprocess.TimeoutExpired:
                    return {
                        "success": False,
                        "step": "restart_service",
                        "error": "Service restart timed out",
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "step": "restart_service",
                        "error": f"Failed to restart service: {str(e)}",
                    }

            # Success!
            return {
                "success": True,
                "updated_to": target_version,
                "message": f"Successfully updated to version {target_version}",
                "steps_completed": [
                    "check_updates",
                    "git_reset",
                    "git_fetch",
                    "git_checkout",
                    "update_version_file",
                    "install_dependencies",
                    "build_frontend",
                    "restart_service",
                ],
            }

        except Exception as e:
            return {
                "success": False,
                "step": "unknown",
                "error": f"Unexpected error during update: {str(e)}",
            }

    @staticmethod
    def can_rollback() -> Dict[str, Any]:
        """
        Check if rollback is available (i.e., if there's a previous version saved).

        Returns:
            Dictionary with rollback availability info
        """
        try:
            if os.path.exists(SystemService.PREVIOUS_VERSION_FILE):
                with open(SystemService.PREVIOUS_VERSION_FILE, "r") as f:
                    previous_version = f.read().strip()

                if previous_version:
                    # Get current version for comparison
                    current_version_data = SystemService.get_version()
                    if current_version_data.get("success"):
                        current_version = current_version_data["version"]

                        # Don't allow rollback to the same version
                        if previous_version == current_version:
                            # Remove invalid .previous_version file
                            try:
                                os.remove(SystemService.PREVIOUS_VERSION_FILE)
                            except OSError:
                                pass
                            return {
                                "can_rollback": False,
                                "success": True,
                                "message": "No previous version available",
                            }

                    return {
                        "can_rollback": True,
                        "previous_version": previous_version,
                        "success": True,
                    }

            return {
                "can_rollback": False,
                "success": True,
                "message": "No previous version available",
            }
        except Exception as e:
            return {
                "can_rollback": False,
                "success": False,
                "error": str(e),
            }

    @staticmethod
    def rollback_to_previous_version(do_restart: bool = True) -> Dict[str, Any]:
        """
        Rollback to the previous version of the system.

        This method:
        1. Checks if a previous version exists
        2. Performs git checkout to the previous version tag
        3. Updates VERSION file
        4. Rebuilds frontend
        5. Restarts backend service

        Returns:
            Dictionary with rollback status
        """
        # Get project root directory
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

        try:
            # Step 1: Check if previous version file exists
            if not os.path.exists(SystemService.PREVIOUS_VERSION_FILE):
                return {
                    "success": False,
                    "step": "check_previous_version",
                    "error": "No previous version found. Cannot rollback.",
                }

            # Read previous version
            try:
                with open(SystemService.PREVIOUS_VERSION_FILE, "r") as f:
                    previous_version = f.read().strip()

                if not previous_version:
                    return {
                        "success": False,
                        "step": "check_previous_version",
                        "error": "Previous version file is empty",
                    }
            except Exception as e:
                return {
                    "success": False,
                    "step": "check_previous_version",
                    "error": f"Failed to read previous version: {str(e)}",
                }

            # Step 2: Reset any local changes (users cannot commit in installed apps)
            try:
                subprocess.run(
                    ["git", "reset", "--hard"],
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            except Exception as e:
                # Non-fatal, force checkout will handle it
                print(f"Warning: git reset had issues: {str(e)}")

            # Step 3: Fetch latest changes (to ensure we have all tags)
            try:
                result = subprocess.run(
                    ["git", "fetch", "origin", "--tags"],
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode != 0:
                    # Non-fatal, continue anyway
                    print(f"Warning: git fetch had issues: {result.stderr}")

            except Exception as e:
                # Non-fatal
                print(f"Warning: Failed to fetch: {str(e)}")

            # Step 4: Checkout previous version tag
            tag_name = f"v{previous_version}"
            try:
                # Verify tag exists
                result = subprocess.run(
                    ["git", "tag", "-l", tag_name],
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if not result.stdout.strip():
                    return {
                        "success": False,
                        "step": "git_checkout",
                        "error": f"Tag {tag_name} not found in repository. "
                        f"Cannot rollback to version {previous_version}.",
                    }

                # Force checkout the tag (discard any local changes)
                result = subprocess.run(
                    ["git", "checkout", "--force", tag_name],
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode != 0:
                    return {
                        "success": False,
                        "step": "git_checkout",
                        "error": f"Failed to checkout {tag_name}",
                        "details": result.stderr,
                    }

            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "step": "git_checkout",
                    "error": "Git checkout timed out",
                }
            except Exception as e:
                return {
                    "success": False,
                    "step": "git_checkout",
                    "error": f"Failed to checkout version: {str(e)}",
                }

            # Step 5: Update VERSION file
            try:
                with open(SystemService.VERSION_FILE, "w") as f:
                    f.write(previous_version)
            except Exception as e:
                return {
                    "success": False,
                    "step": "update_version_file",
                    "error": f"Failed to update VERSION file: {str(e)}",
                }

            # Step 6: Install Python dependencies
            try:
                venv_python = os.path.join(project_root, "venv", "bin", "python3")
                requirements_file = os.path.join(project_root, "requirements.txt")

                result = subprocess.run(
                    [venv_python, "-m", "pip", "install", "-r", requirements_file],
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )

                # Non-fatal
                if result.returncode != 0:
                    print(f"Warning: pip install had issues: {result.stderr}")

            except Exception as e:
                # Non-fatal
                print(f"Warning: Failed to install dependencies: {str(e)}")

            # Step 7: Rebuild frontend
            try:
                frontend_dir = os.path.join(project_root, "frontend", "client")

                # Run npm install
                result = subprocess.run(
                    ["npm", "install"],
                    cwd=frontend_dir,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )

                # Run npm build
                result = subprocess.run(
                    ["npm", "run", "build"],
                    cwd=frontend_dir,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )

                if result.returncode != 0:
                    return {
                        "success": False,
                        "step": "build_frontend",
                        "error": "Frontend build failed during rollback",
                        "details": result.stderr,
                    }

            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "step": "build_frontend",
                    "error": "Frontend build timed out",
                }
            except Exception as e:
                return {
                    "success": False,
                    "step": "build_frontend",
                    "error": f"Failed to build frontend: {str(e)}",
                }

            # Step 8: Restart backend service (only if not delegated to BackgroundTasks)
            if do_restart:
                try:
                    result = subprocess.run(
                        ["sudo", "systemctl", "restart", "fpvcopilot-sky"],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )

                    if result.returncode != 0:
                        return {
                            "success": False,
                            "step": "restart_service",
                            "error": "Failed to restart backend service",
                            "details": result.stderr,
                        }

                except subprocess.TimeoutExpired:
                    return {
                        "success": False,
                        "step": "restart_service",
                        "error": "Service restart timed out",
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "step": "restart_service",
                        "error": f"Failed to restart service: {str(e)}",
                    }

            # Step 9: Remove previous version file (rollback complete)
            try:
                if os.path.exists(SystemService.PREVIOUS_VERSION_FILE):
                    os.remove(SystemService.PREVIOUS_VERSION_FILE)
            except Exception as e:
                # Non-fatal
                print(f"Warning: Failed to remove previous version file: {str(e)}")

            # Success!
            return {
                "success": True,
                "rolled_back_to": previous_version,
                "message": f"Successfully rolled back to version {previous_version}",
                "steps_completed": [
                    "check_previous_version",
                    "git_reset",
                    "git_checkout",
                    "update_version_file",
                    "install_dependencies",
                    "build_frontend",
                    "restart_service",
                ],
            }

        except Exception as e:
            return {
                "success": False,
                "step": "unknown",
                "error": f"Unexpected error during rollback: {str(e)}",
            }

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
            # Try to get nginx error logs (access_log is off in our config)
            nginx_error = ""

            # Check for fpvcopilot-sky nginx error log (access_log is off in our config)
            nginx_log_paths = [
                "/var/log/nginx/fpvcopilot-sky-error.log",  # Custom log from our nginx config
                "/var/log/nginx/error.log",  # Fallback generic nginx error log
            ]
            for log_path in nginx_log_paths:
                if os.path.exists(log_path):
                    result = subprocess.run(
                        ["tail", "-n", str(lines), log_path],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        nginx_error = f"=== Nginx Error Log ({log_path}) ===\\n" + result.stdout
                    break

            combined = nginx_error
            logs = combined if combined else "No frontend logs available"

            # Update cache with 2 second TTL
            SystemService._cache.set("logs_frontend", logs, ttl=2)

            return logs
        except subprocess.TimeoutExpired:
            return "Error: Log fetching timed out"
        except Exception as e:
            return f"Error fetching frontend logs: {str(e)}"

    @staticmethod
    def _get_all_processes_info() -> List[Dict[str, Any]]:
        """
        Get information for all running processes.

        Returns:
            List of dictionaries with process information (pid, name, cmdline, cpu_percent, mem_mb)
        """
        processes = []

        try:
            proc_dirs = [d for d in os.listdir("/proc") if d.isdigit()]

            for pid_str in proc_dirs:
                try:
                    pid = int(pid_str)

                    # Read process name
                    with open(f"/proc/{pid}/comm", "r") as f:
                        name = f.read().strip()

                    # Read command line
                    cmdline = ""
                    try:
                        with open(f"/proc/{pid}/cmdline", "r") as f:
                            cmdline = f.read().replace("\x00", " ").strip()
                    except Exception:
                        pass

                    # Get CPU usage
                    cpu_percent = SystemService._get_process_cpu(pid) or 0

                    # Get memory usage
                    mem_mb = 0
                    try:
                        with open(f"/proc/{pid}/status", "r") as f:
                            for line in f:
                                if line.startswith("VmRSS:"):
                                    mem_kb = int(line.split()[1])
                                    mem_mb = round(mem_kb / 1024, 1)
                                    break
                    except Exception:
                        pass

                    processes.append(
                        {
                            "pid": pid,
                            "name": name,
                            "cmdline": cmdline[:100] if cmdline else name,
                            "cpu_percent": round(cpu_percent, 1),
                            "mem_mb": mem_mb,
                        }
                    )

                except (FileNotFoundError, ProcessLookupError, PermissionError):
                    continue
                except Exception:
                    continue

            return processes

        except Exception as e:
            print(f"⚠️ Error getting process information: {e}")
            return []

    @staticmethod
    def get_top_processes_by_cpu(limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get top processes by CPU usage.

        Args:
            limit: Maximum number of processes to return (default: 10)

        Returns:
            List of dictionaries with process information sorted by CPU usage
        """
        processes = SystemService._get_all_processes_info()
        processes.sort(key=lambda p: p["cpu_percent"], reverse=True)
        return processes[:limit]

    @staticmethod
    def get_top_processes_by_memory(limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get top processes by memory (RAM) usage.

        Args:
            limit: Maximum number of processes to return (default: 10)

        Returns:
            List of dictionaries with process information sorted by memory usage
        """
        processes = SystemService._get_all_processes_info()
        processes.sort(key=lambda p: p["mem_mb"], reverse=True)
        return processes[:limit]
