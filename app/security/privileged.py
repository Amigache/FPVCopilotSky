"""
Client for the root privileged helper (``fpvcopilot-privd``).

Use :func:`run_privileged_sync` / :func:`run_privileged_async` to execute a
command as root without using ``sudo`` (which is incompatible with
``NoNewPrivileges``). When the helper socket is not available (development or a
non-hardened install) callers should fall back to ``sudo`` themselves.
"""

import asyncio
import json
import logging
import os
import socket
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

PRIVD_SOCKET = os.getenv("FPV_PRIVD_SOCKET", "/run/fpvcopilot-priv.sock")
_COMMAND_RESULT = Tuple[str, str, int]


def is_available() -> bool:
    """Whether the privileged helper socket is present."""
    try:
        return os.path.exists(PRIVD_SOCKET)
    except OSError:
        return False


def run_privileged_sync(
    argv: List[str],
    *,
    timeout: float = 15.0,
    input_data: Optional[bytes] = None,
) -> _COMMAND_RESULT:
    """Ask the helper to run *argv* as root. Returns (stdout, stderr, rc)."""
    payload = {"cmd": [str(arg) for arg in argv], "timeout": float(timeout)}
    if input_data is not None:
        payload["input"] = input_data.decode(errors="replace") if isinstance(input_data, bytes) else str(input_data)

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout + 5.0)
            sock.connect(PRIVD_SOCKET)
            sock.sendall((json.dumps(payload) + "\n").encode())
            buffer = b""
            while not buffer.endswith(b"\n"):
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buffer += chunk
        response = json.loads(buffer.decode(errors="replace") or "{}")
        return (
            response.get("stdout", ""),
            response.get("stderr", ""),
            int(response.get("returncode", -1)),
        )
    except Exception as exc:
        logger.warning("Privileged helper call failed", extra={"error": str(exc), "cmd": " ".join(argv)})
        return "", f"privileged helper error: {exc}", -1


async def run_privileged_async(
    argv: List[str],
    *,
    timeout: float = 15.0,
    input_data: Optional[bytes] = None,
) -> _COMMAND_RESULT:
    """Async wrapper around :func:`run_privileged_sync`."""
    return await asyncio.to_thread(run_privileged_sync, argv, timeout=timeout, input_data=input_data)
