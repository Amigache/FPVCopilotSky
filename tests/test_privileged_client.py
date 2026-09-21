"""Tests for the privileged helper client and cmd routing."""

import json
import socket
import threading
from types import SimpleNamespace
from unittest.mock import patch

from app.security import privileged
from app.utils import cmd as cmd_mod


class TestPrivilegedClient:
    def test_is_available_false_without_socket(self, monkeypatch, tmp_path):
        monkeypatch.setattr(privileged, "PRIVD_SOCKET", str(tmp_path / "missing.sock"))
        assert privileged.is_available() is False

    def test_sync_errors_without_socket(self, monkeypatch, tmp_path):
        monkeypatch.setattr(privileged, "PRIVD_SOCKET", str(tmp_path / "missing.sock"))
        stdout, stderr, returncode = privileged.run_privileged_sync(["ip", "route"])
        assert returncode == -1
        assert "privileged helper" in stderr
        assert stdout == ""

    def test_roundtrip_with_fake_daemon(self, monkeypatch, tmp_path):
        monkeypatch.setattr(privileged, "PRIVD_SOCKET", str(tmp_path / "priv.sock"))
        received = {}

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(privileged.PRIVD_SOCKET)
        server.listen(1)

        def serve():
            conn, _ = server.accept()
            data = b""
            while not data.endswith(b"\n"):
                data += conn.recv(65536)
            received.update(json.loads(data.decode()))
            conn.sendall((json.dumps({"returncode": 0, "stdout": "ok", "stderr": ""}) + "\n").encode())
            conn.close()
            server.close()

        thread = threading.Thread(target=serve)
        thread.start()
        try:
            stdout, _, returncode = privileged.run_privileged_sync(["ip", "route", "show"], timeout=5)
        finally:
            thread.join(timeout=5)

        assert (stdout, returncode) == ("ok", 0)
        assert received["cmd"] == ["ip", "route", "show"]


class TestCmdRouting:
    def test_routes_sudo_through_helper_when_available(self):
        with (
            patch.object(cmd_mod._privileged, "is_available", return_value=True),
            patch.object(cmd_mod._privileged, "run_privileged_sync", return_value=("out", "", 0)) as mock_priv,
        ):
            stdout, _, returncode = cmd_mod.run_cmd(["sudo", "-n", "ip", "route", "show"])

        assert (stdout, returncode) == ("out", 0)
        assert mock_priv.call_args[0][0] == ["ip", "route", "show"]

    def test_routes_timeout_wrapped_sudo(self):
        with (
            patch.object(cmd_mod._privileged, "is_available", return_value=True),
            patch.object(cmd_mod._privileged, "run_privileged_sync", return_value=("", "", 0)) as mock_priv,
        ):
            cmd_mod.run_cmd(["timeout", "5", "sudo", "-n", "tailscale", "up"])

        assert mock_priv.call_args[0][0] == ["tailscale", "up"]

    def test_falls_back_to_subprocess_when_unavailable(self):
        fake = SimpleNamespace(stdout="o", stderr="", returncode=0)
        with (
            patch.object(cmd_mod._privileged, "is_available", return_value=False),
            patch.object(cmd_mod.subprocess, "run", return_value=fake) as mock_run,
        ):
            stdout, _, returncode = cmd_mod.run_cmd(["sudo", "-n", "ip", "route", "show"])

        assert (stdout, returncode) == ("o", 0)
        assert mock_run.call_args[0][0] == ["sudo", "-n", "ip", "route", "show"]

    def test_extract_sudo_plain_command(self):
        assert cmd_mod._extract_sudo(["ip", "route"]) == (["ip", "route"], False)


class TestPrivdDaemonExecute:
    def test_passes_stdin_as_str_with_text_mode(self):
        from app.security import privd_daemon

        captured = {}

        def fake_run(argv, **kwargs):
            captured["argv"] = argv
            captured.update(kwargs)
            return SimpleNamespace(returncode=0, stdout="ok", stderr="")

        with patch.object(privd_daemon.subprocess, "run", side_effect=fake_run):
            result = privd_daemon._execute({"cmd": ["ip", "route", "show"], "timeout": 5, "input": "hello\n"})

        assert result == {"returncode": 0, "stdout": "ok", "stderr": ""}
        # text=True requires a str for stdin; passing bytes breaks subprocess.
        assert captured["input"] == "hello\n"
        assert captured["text"] is True

    def test_denies_non_whitelisted_command(self):
        from app.security import privd_daemon

        result = privd_daemon._execute({"cmd": ["tee", "/etc/sudoers.d/evil"]})
        assert result["returncode"] == 126
