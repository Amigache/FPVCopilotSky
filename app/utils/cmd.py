"""
Unified command execution layer.

Provides two helpers that centralise all subprocess calls made from both
sync and async contexts:

    run_cmd(cmd, ...)       — sync, for use in threads / non-async services
    run_cmd_async(cmd, ...) — async, for use in FastAPI route handlers

Both helpers share the same contract:
  - Returns (stdout: str, stderr: str, returncode: int)
  - Always enforce a timeout (default 15 s)
  - Kill the subprocess on timeout and return returncode=-1
  - Log every failure with structured fields (cmd, returncode, stderr, elapsed_ms)
  - Never raise — callers inspect the returncode
"""

import asyncio
import logging
import subprocess
import time
from typing import List, Tuple

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT: float = 15.0
_CommandResult = Tuple[str, str, int]


def run_cmd(
    cmd: List[str],
    *,
    timeout: float = _DEFAULT_TIMEOUT,
    check: bool = False,
) -> _CommandResult:
    """Run *cmd* synchronously and return (stdout, stderr, returncode).

    Args:
        cmd:     Command and arguments.
        timeout: Seconds before the process is killed (default 15).
        check:   If True, log an ERROR when returncode != 0.

    Returns:
        (stdout, stderr, returncode)  — returncode is -1 on timeout/exception.
    """
    t0 = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        if check and result.returncode != 0:
            logger.error(
                "Command failed",
                extra={
                    "cmd": " ".join(cmd),
                    "returncode": result.returncode,
                    "stderr": result.stderr.strip(),
                    "elapsed_ms": elapsed_ms,
                },
            )

        return result.stdout.strip(), result.stderr.strip(), result.returncode

    except subprocess.TimeoutExpired:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.error(
            "Command timed out",
            extra={"cmd": " ".join(cmd), "timeout_s": timeout, "elapsed_ms": elapsed_ms},
        )
        return "", f"Command timed out after {timeout}s", -1

    except Exception as e:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.error(
            "Command execution error",
            extra={"cmd": " ".join(cmd), "error": str(e), "elapsed_ms": elapsed_ms},
        )
        return "", str(e), -1


async def run_cmd_async(
    cmd: List[str],
    *,
    timeout: float = _DEFAULT_TIMEOUT,
    check: bool = False,
) -> _CommandResult:
    """Run *cmd* asynchronously and return (stdout, stderr, returncode).

    Uses asyncio.create_subprocess_exec so the event loop is never blocked.

    Args:
        cmd:     Command and arguments.
        timeout: Seconds before the process is killed (default 15).
        check:   If True, log an ERROR when returncode != 0.

    Returns:
        (stdout, stderr, returncode)  — returncode is -1 on timeout/exception.
    """
    t0 = time.monotonic()
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        stdout = stdout_b.decode(errors="replace").strip()
        stderr = stderr_b.decode(errors="replace").strip()

        if check and proc.returncode != 0:
            logger.error(
                "Async command failed",
                extra={
                    "cmd": " ".join(cmd),
                    "returncode": proc.returncode,
                    "stderr": stderr,
                    "elapsed_ms": elapsed_ms,
                },
            )

        return stdout, stderr, proc.returncode

    except asyncio.TimeoutError:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.error(
            "Async command timed out",
            extra={"cmd": " ".join(cmd), "timeout_s": timeout, "elapsed_ms": elapsed_ms},
        )
        if proc is not None:
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass
        return "", f"Command timed out after {timeout}s", -1

    except Exception as e:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.error(
            "Async command execution error",
            extra={"cmd": " ".join(cmd), "error": str(e), "elapsed_ms": elapsed_ms},
        )
        return "", str(e), -1
