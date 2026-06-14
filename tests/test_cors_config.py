import app.main as main_module


def test_parse_cors_origins_wildcard_collapses():
    assert main_module._parse_cors_origins("http://localhost:5173, *") == ["*"]


def test_build_cors_settings_from_env(monkeypatch):
    monkeypatch.setenv("FPV_CORS_ALLOW_ORIGINS", "http://localhost:5173,https://fpv.example.com")
    monkeypatch.setenv("FPV_CORS_ALLOW_CREDENTIALS", "true")
    monkeypatch.setenv("FPV_CORS_ALLOW_METHODS", "GET,POST,OPTIONS")
    monkeypatch.setenv("FPV_CORS_ALLOW_HEADERS", "Authorization,Content-Type")

    settings = main_module._build_cors_settings()

    assert settings["allow_origins"] == ["http://localhost:5173", "https://fpv.example.com"]
    assert settings["allow_credentials"] is True
    assert settings["allow_methods"] == ["GET", "POST", "OPTIONS"]
    assert settings["allow_headers"] == ["Authorization", "Content-Type"]


def test_build_cors_settings_disables_credentials_with_wildcard(monkeypatch):
    monkeypatch.setenv("FPV_CORS_ALLOW_ORIGINS", "*")
    monkeypatch.setenv("FPV_CORS_ALLOW_CREDENTIALS", "true")

    settings = main_module._build_cors_settings()

    assert settings["allow_origins"] == ["*"]
    assert settings["allow_credentials"] is False
