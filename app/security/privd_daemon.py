"""
Root privileged helper daemon for FPV Copilot Sky.

The main service runs unprivileged with ``NoNewPrivileges=true`` and forwards
the few operations that need root (network configuration, service management,
VPN) to this daemon over a root-owned unix socket. The daemon only executes
commands accepted by :mod:`app.security.privd_policy`.

Run as root via ``fpvcopilot-privd.service``::

    /opt/FPVCopilotSky/venv/bin/python3 -m app.security.privd_daemon

Protocol (one JSON object per line, both directions):
    request  {"cmd": ["ip", ...], "timeout": 15, "input": "optional stdin"}
    response {"returncode": 0, "stdout": "...", "stderr": "..."}
"""

import json
import logging
import grp
import os
import socket
import subprocess
import threading
from typing import Optional

from app.security.privd_policy import is_allowed

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("fpvcopilot.privd")

SOCKET_PATH = os.getenv("FPV_PRIVD_SOCKET", "/run/fpvcopilot-priv.sock")
SERVICE_GROUP = os.getenv("FPV_PRIVD_GROUP", "fpvcopilotsky")
MAX_MESSAGE = 1 << 20  # 1 MiB
CONNECTION_TIMEOUT = 5.0


def _read_request(conn: socket.socket) -> Optional[dict]:
    data = b""
    while not data.endswith(b"\n") and len(data) < MAX_MESSAGE:
        chunk = conn.recv(65536)
        if not chunk:
            break
        data += chunk
    if not data.strip():
        return None
    return json.loads(data.decode(errors="replace"))


def _execute(request: dict) -> dict:
    argv = request.get("cmd") or []
    try:
        timeout = float(request.get("timeout", 15))
    except (TypeError, ValueError):
        timeout = 15.0

    if not isinstance(argv, list) or not argv or not is_allowed(argv):
        logger.warning("denied: %s", " ".join(str(arg) for arg in argv) if isinstance(argv, list) else argv)
        return {"returncode": 126, "stdout": "", "stderr": f"command not permitted: {argv}"}

    logger.info("exec: %s", " ".join(str(arg) for arg in argv))
    input_data = request.get("input")
    try:
        proc = subprocess.run(
            [str(arg) for arg in argv],
            # text=True expects a str for stdin (subprocess encodes it).
            input=input_data if isinstance(input_data, str) else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": f"command timed out after {timeout}s"}
    except Exception as exc:  # pragma: no cover - defensive
        return {"returncode": -1, "stdout": "", "stderr": f"helper error: {exc}"}


def _handle(conn: socket.socket) -> None:
    try:
        conn.settimeout(CONNECTION_TIMEOUT)
        request = _read_request(conn)
        response = _execute(request) if request else {"returncode": -1, "stdout": "", "stderr": "empty request"}
        conn.sendall((json.dumps(response) + "\n").encode())
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("request handling error: %s", exc)
    finally:
        try:
            conn.close()
        except OSError:
            pass


def _prepare_socket() -> socket.socket:
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET_PATH)
    try:
        gid = grp.getgrnam(SERVICE_GROUP).gr_gid
        os.chmod(SOCKET_PATH, 0o660)
        os.chown(SOCKET_PATH, 0, gid)
    except KeyError:
        logger.warning("group %s not found; restricting socket to root", SERVICE_GROUP)
        os.chmod(SOCKET_PATH, 0o600)
    server.listen(16)
    return server


def main() -> None:
    if os.geteuid() != 0:
        raise SystemExit("fpvcopilot-privd must run as root")
    server = _prepare_socket()
    logger.info("fpvcopilot-privd listening on %s", SOCKET_PATH)
    while True:
        conn, _ = server.accept()
        threading.Thread(target=_handle, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()
