import pathlib

import app.main as main_module


def test_read_version_from_pyproject(monkeypatch):
    monkeypatch.setattr(pathlib.Path, "read_text", lambda self: 'version = "9.8.7"\n')

    assert main_module._read_version() == "9.8.7"


def test_read_version_falls_back_on_error(monkeypatch):
    def raise_error(self):
        raise RuntimeError("boom")

    monkeypatch.setattr(pathlib.Path, "read_text", raise_error)

    assert main_module._read_version() == "unknown"
