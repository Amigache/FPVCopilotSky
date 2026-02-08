"""Status endpoint for system and application information."""

import subprocess
import os
import sys
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from importlib import metadata

router = APIRouter(prefix="/api/status", tags=["status"])


def check_python_dependencies():
    """Check if all Python dependencies are installed."""
    try:
        requirements_path = Path(__file__).parents[3] / "requirements.txt"
        if not requirements_path.exists():
            return {"status": "warning", "message": "requirements.txt not found"}

        # Read lines once
        with open(requirements_path, "r") as f:
            lines = [
                line.strip() for line in f if line.strip() and not line.startswith("#")
            ]

        missing = []
        for line in lines:
            # Extract package name, removing extras like [standard]
            package = (
                line.split("[")[0]
                .split("==")[0]
                .split(">=")[0]
                .split("<=")[0]
                .split("<")[0]
                .split(">")[0]
                .strip()
            )

            try:
                # Use importlib.metadata which checks installed packages
                # This works regardless of virtual environment or import name differences
                metadata.version(package)
            except metadata.PackageNotFoundError:
                missing.append(package)

        if missing:
            return {
                "status": "warning",
                "installed": len(lines) - len(missing),
                "total": len(lines),
                "missing": missing,
            }

        return {"status": "ok", "message": "All dependencies installed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def check_npm_dependencies():
    """Check if all npm dependencies are installed for frontend."""
    try:
        package_json = Path("/opt/FPVCopilotSky/frontend/client/package.json")
        if not package_json.exists():
            return {"status": "warning", "message": "Frontend not available"}

        node_modules = Path("/opt/FPVCopilotSky/frontend/client/node_modules")

        if node_modules.exists() and len(list(node_modules.iterdir())) > 0:
            return {"status": "ok", "message": "All dependencies installed"}
        else:
            return {"status": "warning", "message": "node_modules not found or empty"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_user_permissions():
    """Get current user permissions."""
    try:
        import pwd
        import grp

        uid = os.getuid()
        user = pwd.getpwuid(uid)

        # Check sudoers
        sudoers_list = []
        sudoers_file = "/etc/sudoers"
        sudoers_d_dir = "/etc/sudoers.d"

        try:
            # Check /etc/sudoers
            if os.path.isfile(sudoers_file) and os.access(sudoers_file, os.R_OK):
                with open(sudoers_file, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and user.pw_name in line:
                            sudoers_list.append({"source": "sudoers", "entry": line})
        except:
            pass

        # Check /etc/sudoers.d
        try:
            if os.path.isdir(sudoers_d_dir):
                for filename in os.listdir(sudoers_d_dir):
                    filepath = os.path.join(sudoers_d_dir, filename)
                    try:
                        with open(filepath, "r") as f:
                            for line in f:
                                line = line.strip()
                                if line and not line.startswith("#") and user.pw_name in line:
                                    sudoers_list.append(
                                        {
                                            "source": f"sudoers.d/{filename}",
                                            "entry": line,
                                        }
                                    )
                    except:
                        pass
        except:
            pass

        perms = {
            "username": user.pw_name,
            "uid": uid,
            "gid": user.pw_gid,
            "groups": [grp.getgrgid(g).gr_name for g in os.getgroups()],
            "home": user.pw_dir,
            "is_root": uid == 0,
            "can_write_opt": os.access("/opt/FPVCopilotSky", os.W_OK),
            "can_read_opt": os.access("/opt/FPVCopilotSky", os.R_OK),
            "sudoers": sudoers_list,
        }

        return {"status": "ok", "permissions": perms}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def check_system_info():
    """Get system information."""
    try:
        import platform

        return {
            "status": "ok",
            "system": {
                "platform": platform.system(),
                "hostname": os.uname().nodename,
                "architecture": platform.machine(),
                "python_version": platform.python_version(),
                "python_executable": sys.executable,
            },
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_app_version():
    """Get app version from pyproject.toml."""
    try:
        pyproject_path = Path("/opt/FPVCopilotSky/pyproject.toml")
        if pyproject_path.exists():
            import re

            with open(pyproject_path, "r") as f:
                content = f.read()
                # Look for version = "x.x.x"
                match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
                if match:
                    version = match.group(1)
                    return {"status": "ok", "version": version}

        return {"status": "warning", "version": "unknown"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_frontend_version():
    """Get frontend version from package.json."""
    try:
        package_json_path = Path("/opt/FPVCopilotSky/frontend/client/package.json")
        if package_json_path.exists():
            import json

            with open(package_json_path, "r") as f:
                data = json.load(f)
                if "version" in data:
                    return {"status": "ok", "version": data["version"]}

        return {"status": "warning", "version": "unknown"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_node_version():
    """Get Node.js version from the runtime if available."""
    try:
        result = subprocess.run(
            ["node", "-v"], capture_output=True, text=True, check=True
        )
        version = result.stdout.strip()
        if version.startswith("v"):
            version = version[1:]
        return {"status": "ok", "version": version or "unknown"}
    except FileNotFoundError:
        return {"status": "warning", "version": "not installed"}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "message": e.stderr.strip() or str(e)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/health")
async def health_check():
    """Get overall application health status."""
    try:
        backend = {
            "running": True,
            "python_deps": check_python_dependencies(),
            "system": check_system_info(),
            "app_version": get_app_version(),
        }

        frontend = {
            "npm_deps": check_npm_dependencies(),
            "frontend_version": get_frontend_version(),
            "node_version": get_node_version(),
        }

        permissions = get_user_permissions()

        return {
            "success": True,
            "backend": backend,
            "frontend": frontend,
            "permissions": permissions,
            "timestamp": int(__import__("time").time()),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/permissions")
async def get_permissions():
    """Get detailed user permissions."""
    return get_user_permissions()


@router.get("/dependencies")
async def get_dependencies():
    """Get dependency status for both backend and frontend."""
    return {
        "success": True,
        "backend": check_python_dependencies(),
        "frontend": check_npm_dependencies(),
    }


@router.get("/system")
async def get_system():
    """Get system information."""
    return check_system_info()
