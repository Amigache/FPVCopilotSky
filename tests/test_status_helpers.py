from types import SimpleNamespace

import grp
import os
import platform
import pwd

import pytest

from app.api.routes import status as status_module


class DummyCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ttl=None):
        self.store[key] = value


@pytest.fixture(autouse=True)
def isolated_status_cache(monkeypatch):
    monkeypatch.setattr(status_module, "_cache", DummyCache())


def test_check_python_dependencies_all_installed(tmp_path, monkeypatch):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("fastapi\npytest\n")
    monkeypatch.setattr(status_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(status_module.metadata, "version", lambda package: "1.0.0")

    result = status_module.check_python_dependencies()

    assert result == {"status": "ok", "message": "All dependencies installed"}


def test_check_python_dependencies_reports_missing(tmp_path, monkeypatch):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("fastapi\nmissingpkg\n")
    monkeypatch.setattr(status_module, "PROJECT_ROOT", tmp_path)

    def fake_version(package):
        if package == "missingpkg":
            raise status_module.metadata.PackageNotFoundError
        return "1.0.0"

    monkeypatch.setattr(status_module.metadata, "version", fake_version)

    result = status_module.check_python_dependencies()

    assert result["status"] == "warning"
    assert result["installed"] == 1
    assert result["total"] == 2
    assert result["missing"] == ["missingpkg"]


def test_check_npm_dependencies_detects_missing_frontend(tmp_path, monkeypatch):
    monkeypatch.setattr(status_module, "PROJECT_ROOT", tmp_path)

    result = status_module.check_npm_dependencies()

    assert result == {"status": "warning", "message": "Frontend not available"}


def test_check_npm_dependencies_reports_installed(tmp_path, monkeypatch):
    package_json = tmp_path / "frontend/client/package.json"
    node_modules = tmp_path / "frontend/client/node_modules"
    node_modules.mkdir(parents=True)
    (node_modules / "dummy.txt").write_text("x")
    package_json.parent.mkdir(parents=True, exist_ok=True)
    package_json.write_text('{"name": "fpv", "version": "1.2.3"}')
    monkeypatch.setattr(status_module, "PROJECT_ROOT", tmp_path)

    result = status_module.check_npm_dependencies()

    assert result == {"status": "ok", "message": "All dependencies installed"}


def test_get_user_permissions_happy_path(monkeypatch, tmp_path):
    monkeypatch.setattr(status_module.os, "getuid", lambda: 1000)
    monkeypatch.setattr(status_module.os, "getgroups", lambda: [1000])
    monkeypatch.setattr(status_module.os, "access", lambda path, mode: True)
    monkeypatch.setattr(status_module.os.path, "isfile", lambda path: False)
    monkeypatch.setattr(status_module.os.path, "isdir", lambda path: False)
    monkeypatch.setattr(
        pwd, "getpwuid", lambda uid: SimpleNamespace(pw_name="tester", pw_gid=1000, pw_dir="/home/tester")
    )
    monkeypatch.setattr(grp, "getgrgid", lambda gid: SimpleNamespace(gr_name="wheel"))
    monkeypatch.setattr(status_module, "PROJECT_ROOT", tmp_path)

    result = status_module.get_user_permissions()

    assert result["status"] == "ok"
    assert result["permissions"]["username"] == "tester"
    assert result["permissions"]["groups"] == ["wheel"]
    assert result["permissions"]["is_root"] is False


def test_check_system_info(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(platform, "python_version", lambda: "3.12.3")
    monkeypatch.setattr(status_module.os, "uname", lambda: SimpleNamespace(nodename="fpv-test"))

    result = status_module.check_system_info()

    assert result["status"] == "ok"
    assert result["system"]["platform"] == "Linux"
    assert result["system"]["hostname"] == "fpv-test"


def test_get_app_version_and_frontend_version(tmp_path, monkeypatch):
    pyproject = tmp_path / "pyproject.toml"
    package_json = tmp_path / "frontend/client/package.json"
    package_json.parent.mkdir(parents=True)
    pyproject.write_text('[project]\nversion = "2.4.6"\n')
    package_json.write_text('{"name": "fpv", "version": "7.8.9"}')
    monkeypatch.setattr(status_module, "PROJECT_ROOT", tmp_path)

    assert status_module.get_app_version() == {"status": "ok", "version": "2.4.6"}
    assert status_module.get_frontend_version() == {"status": "ok", "version": "7.8.9"}


def test_get_node_version_variants(monkeypatch):
    monkeypatch.setattr(status_module, "run_cmd", lambda *args, **kwargs: ("v20.1.0\n", "", 0))
    assert status_module.get_node_version() == {"status": "ok", "version": "20.1.0"}

    monkeypatch.setattr(status_module, "run_cmd", lambda *args, **kwargs: ("", "not found", 127))
    assert status_module.get_node_version() == {"status": "error", "message": "not found"}

    monkeypatch.setattr(status_module, "run_cmd", lambda *args, **kwargs: ("", "", -1))
    assert status_module.get_node_version() == {"status": "warning", "version": "not available"}
