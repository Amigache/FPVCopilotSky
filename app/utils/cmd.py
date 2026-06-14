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
from typing import List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT: float = 15.0
_CommandResult = Tuple[str, str, int]


def _should_retry(
    returncode: int,
    *,
    attempt: int,
    retries: int,
    retry_on_returncodes: Optional[Set[int]],
) -> bool:
    if attempt >= retries:
        return False
    if returncode == -1:
        return True
    if retry_on_returncodes is None:
        return returncode != 0
    return returncode in retry_on_returncodes


def _compute_backoff_s(*, attempt: int, backoff_base_s: float, backoff_max_s: float) -> float:
    return min(backoff_base_s * (2**attempt), backoff_max_s)


def run_cmd(
    cmd: List[str],
    *,
    timeout: float = _DEFAULT_TIMEOUT,
    check: bool = False,
    retries: int = 0,
    backoff_base_s: float = 0.2,
    backoff_max_s: float = 2.0,
    retry_on_returncodes: Optional[Set[int]] = None,
) -> _CommandResult:
    """Run *cmd* synchronously and return (stdout, stderr, returncode).

    Args:
        cmd:     Command and arguments.
        timeout: Seconds before the process is killed (default 15).
        check:   If True, log an ERROR when returncode != 0.
        retries: Number of retries after first failure/timeout (default 0).
        backoff_base_s: Initial exponential backoff delay in seconds.
        backoff_max_s: Maximum delay between retries in seconds.
        retry_on_returncodes: Return codes that should trigger a retry.
            If None, retries any non-zero return code.

    Returns:
        (stdout, stderr, returncode)  — returncode is -1 on timeout/exception.
    """
    for attempt in range(retries + 1):
        t0 = time.monotonic()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            stdout, stderr, returncode = result.stdout.strip(), result.stderr.strip(), result.returncode
        except subprocess.TimeoutExpired:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.error(
                "Command timed out",
                extra={"cmd": " ".join(cmd), "timeout_s": timeout, "elapsed_ms": elapsed_ms},
            )
            stdout, stderr, returncode = "", f"Command timed out after {timeout}s", -1
        except Exception as e:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.error(
                "Command execution error",
                extra={"cmd": " ".join(cmd), "error": str(e), "elapsed_ms": elapsed_ms},
            )
            stdout, stderr, returncode = "", str(e), -1

        should_retry = _should_retry(
            returncode,
            attempt=attempt,
            retries=retries,
            retry_on_returncodes=retry_on_returncodes,
        )
        if not should_retry:
            if check and returncode != 0:
                logger.error(
                    "Command failed",
                    extra={
                        "cmd": " ".join(cmd),
                        "returncode": returncode,
                        "stderr": stderr,
                        "elapsed_ms": elapsed_ms,
                    },
                )
            return stdout, stderr, returncode

        delay_s = _compute_backoff_s(
            attempt=attempt,
            backoff_base_s=backoff_base_s,
            backoff_max_s=backoff_max_s,
        )
        logger.warning(
            "Retrying command after failure",
            extra={
                "cmd": " ".join(cmd),
                "attempt": attempt + 1,
                "max_attempts": retries + 1,
                "returncode": returncode,
                "backoff_s": delay_s,
            },
        )
        time.sleep(delay_s)

    return "", "Unknown command execution error", -1


async def run_cmd_async(
    cmd: List[str],
    *,
    timeout: float = _DEFAULT_TIMEOUT,
    check: bool = False,
    retries: int = 0,
    backoff_base_s: float = 0.2,
    backoff_max_s: float = 2.0,
    retry_on_returncodes: Optional[Set[int]] = None,
) -> _CommandResult:
    """Run *cmd* asynchronously and return (stdout, stderr, returncode).

    Uses asyncio.create_subprocess_exec so the event loop is never blocked.

    Args:
        cmd:     Command and arguments.
        timeout: Seconds before the process is killed (default 15).
        check:   If True, log an ERROR when returncode != 0.
        retries: Number of retries after first failure/timeout (default 0).
        backoff_base_s: Initial exponential backoff delay in seconds.
        backoff_max_s: Maximum delay between retries in seconds.
        retry_on_returncodes: Return codes that should trigger a retry.
            If None, retries any non-zero return code.

    Returns:
        (stdout, stderr, returncode)  — returncode is -1 on timeout/exception.
    """
    for attempt in range(retries + 1):
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
            returncode = proc.returncode
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
            stdout, stderr, returncode = "", f"Command timed out after {timeout}s", -1
        except Exception as e:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.error(
                "Async command execution error",
                extra={"cmd": " ".join(cmd), "error": str(e), "elapsed_ms": elapsed_ms},
            )
            stdout, stderr, returncode = "", str(e), -1

        should_retry = _should_retry(
            returncode,
            attempt=attempt,
            retries=retries,
            retry_on_returncodes=retry_on_returncodes,
        )
        if not should_retry:
            if check and returncode != 0:
                logger.error(
                    "Async command failed",
                    extra={
                        "cmd": " ".join(cmd),
                        "returncode": returncode,
                        "stderr": stderr,
                        "elapsed_ms": elapsed_ms,
                    },
                )
            return stdout, stderr, returncode

        delay_s = _compute_backoff_s(
            attempt=attempt,
            backoff_base_s=backoff_base_s,
            backoff_max_s=backoff_max_s,
        )
        logger.warning(
            "Retrying async command after failure",
            extra={
                "cmd": " ".join(cmd),
                "attempt": attempt + 1,
                "max_attempts": retries + 1,
                "returncode": returncode,
                "backoff_s": delay_s,
            },
        )
        await asyncio.sleep(delay_s)

    return "", "Unknown async command execution error", -1
