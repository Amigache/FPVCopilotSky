"""Unit tests for the unified command execution helpers."""

import asyncio
import subprocess
from unittest.mock import AsyncMock, Mock, patch

from app.utils.cmd import run_cmd, run_cmd_async


class TestRunCmd:
    @patch("app.utils.cmd.subprocess.run")
    def test_run_cmd_success(self, mock_run):
        mock_run.return_value = Mock(stdout=" ok\n", stderr="", returncode=0)

        stdout, stderr, returncode = run_cmd(["echo", "ok"], timeout=1, check=False)

        assert stdout == "ok"
        assert stderr == ""
        assert returncode == 0

    @patch("app.utils.cmd.logger.error")
    @patch("app.utils.cmd.subprocess.run")
    def test_run_cmd_nonzero_logs_when_check_true(self, mock_run, mock_log_error):
        mock_run.return_value = Mock(stdout="", stderr="boom\n", returncode=2)

        stdout, stderr, returncode = run_cmd(["false"], timeout=1, check=True)

        assert stdout == ""
        assert stderr == "boom"
        assert returncode == 2
        mock_log_error.assert_called_once()

    @patch("app.utils.cmd.logger.error")
    @patch("app.utils.cmd.subprocess.run")
    def test_run_cmd_timeout_returns_minus_one(self, mock_run, mock_log_error):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["sleep", "5"], timeout=0.01)

        stdout, stderr, returncode = run_cmd(["sleep", "5"], timeout=0.01, check=False)

        assert stdout == ""
        assert "timed out" in stderr.lower()
        assert returncode == -1
        mock_log_error.assert_called_once()

    @patch("app.utils.cmd.logger.error")
    @patch("app.utils.cmd.subprocess.run")
    def test_run_cmd_exception_returns_minus_one(self, mock_run, mock_log_error):
        mock_run.side_effect = RuntimeError("unexpected")

        stdout, stderr, returncode = run_cmd(["x"], timeout=1, check=False)

        assert stdout == ""
        assert "unexpected" in stderr
        assert returncode == -1
        mock_log_error.assert_called_once()

    @patch("app.utils.cmd.time.sleep")
    @patch("app.utils.cmd.subprocess.run")
    def test_run_cmd_retries_and_recovers(self, mock_run, mock_sleep):
        mock_run.side_effect = [
            Mock(stdout="", stderr="temp fail\n", returncode=2),
            Mock(stdout=" ok\n", stderr="", returncode=0),
        ]

        stdout, stderr, returncode = run_cmd(
            ["demo"],
            timeout=1,
            retries=1,
            backoff_base_s=0.1,
            backoff_max_s=1.0,
            check=False,
        )

        assert stdout == "ok"
        assert stderr == ""
        assert returncode == 0
        assert mock_run.call_count == 2
        mock_sleep.assert_called_once_with(0.1)

    @patch("app.utils.cmd.subprocess.run")
    def test_run_cmd_retry_filter_blocks_retry(self, mock_run):
        mock_run.side_effect = [
            Mock(stdout="", stderr="bad\n", returncode=2),
            Mock(stdout=" ok\n", stderr="", returncode=0),
        ]

        stdout, stderr, returncode = run_cmd(
            ["demo"],
            timeout=1,
            retries=1,
            retry_on_returncodes={1},
            check=False,
        )

        assert stdout == ""
        assert stderr == "bad"
        assert returncode == 2
        assert mock_run.call_count == 1


class TestRunCmdAsync:
    @patch("app.utils.cmd.asyncio.create_subprocess_exec")
    async def test_run_cmd_async_success(self, mock_create_proc):
        proc = AsyncMock()
        proc.communicate = AsyncMock(return_value=(b" ok\n", b""))
        proc.returncode = 0
        mock_create_proc.return_value = proc

        stdout, stderr, returncode = await run_cmd_async(["echo", "ok"], timeout=1, check=False)

        assert stdout == "ok"
        assert stderr == ""
        assert returncode == 0

    @patch("app.utils.cmd.logger.error")
    @patch("app.utils.cmd.asyncio.create_subprocess_exec")
    async def test_run_cmd_async_nonzero_logs_when_check_true(self, mock_create_proc, mock_log_error):
        proc = AsyncMock()
        proc.communicate = AsyncMock(return_value=(b"", b"fail\n"))
        proc.returncode = 3
        mock_create_proc.return_value = proc

        stdout, stderr, returncode = await run_cmd_async(["false"], timeout=1, check=True)

        assert stdout == ""
        assert stderr == "fail"
        assert returncode == 3
        mock_log_error.assert_called_once()

    @patch("app.utils.cmd.logger.error")
    @patch("app.utils.cmd.asyncio.create_subprocess_exec")
    @patch("app.utils.cmd.asyncio.wait_for")
    async def test_run_cmd_async_timeout_kills_process(self, mock_wait_for, mock_create_proc, mock_log_error):
        async def _raise_timeout(awaitable, timeout):
            awaitable.close()
            raise asyncio.TimeoutError

        proc = AsyncMock()
        proc.kill = Mock()
        proc.wait = AsyncMock(return_value=None)
        mock_create_proc.return_value = proc
        mock_wait_for.side_effect = _raise_timeout

        stdout, stderr, returncode = await run_cmd_async(["sleep", "5"], timeout=0.01, check=False)

        assert stdout == ""
        assert "timed out" in stderr.lower()
        assert returncode == -1
        proc.kill.assert_called_once()
        proc.wait.assert_awaited_once()
        mock_log_error.assert_called_once()

    @patch("app.utils.cmd.logger.error")
    @patch("app.utils.cmd.asyncio.create_subprocess_exec")
    async def test_run_cmd_async_exception_returns_minus_one(self, mock_create_proc, mock_log_error):
        mock_create_proc.side_effect = RuntimeError("spawn failed")

        stdout, stderr, returncode = await run_cmd_async(["x"], timeout=1, check=False)

        assert stdout == ""
        assert "spawn failed" in stderr
        assert returncode == -1
        mock_log_error.assert_called_once()

    @patch("app.utils.cmd.asyncio.sleep", new_callable=AsyncMock)
    @patch("app.utils.cmd.asyncio.wait_for")
    @patch("app.utils.cmd.asyncio.create_subprocess_exec")
    async def test_run_cmd_async_retries_and_recovers(self, mock_create_proc, mock_wait_for, mock_sleep):
        proc1 = AsyncMock()
        proc1.kill = Mock()
        proc1.wait = AsyncMock(return_value=None)
        proc2 = AsyncMock()
        proc2.returncode = 0

        mock_create_proc.side_effect = [proc1, proc2]

        async def _timeout_then_success(awaitable, timeout):
            awaitable.close()
            if _timeout_then_success.calls == 0:
                _timeout_then_success.calls += 1
                raise asyncio.TimeoutError
            return (b" ok\n", b"")

        _timeout_then_success.calls = 0
        mock_wait_for.side_effect = _timeout_then_success

        stdout, stderr, returncode = await run_cmd_async(
            ["demo"],
            timeout=1,
            retries=1,
            backoff_base_s=0.1,
            backoff_max_s=1.0,
            check=False,
        )

        assert stdout == "ok"
        assert stderr == ""
        assert returncode == 0
        assert mock_create_proc.call_count == 2
        proc1.kill.assert_called_once()
        proc1.wait.assert_awaited_once()
        mock_sleep.assert_awaited_once_with(0.1)
