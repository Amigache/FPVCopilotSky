# FPV Copilot Sky — Agent Guide

## Stack

- **Backend**: Python 3.12, FastAPI, Uvicorn, PyMAVLink, GStreamer
- **Frontend**: React 18, Vite 7, Vitest, i18next
- **Infra**: systemd, Nginx, NetworkManager, Tailscale, tc/CAKE

## Dev commands

```bash
# Backend (project root)
source venv/bin/activate

pytest                          # all tests (coverage: fail_under=50)
pytest -m "not slow"            # quick subset
pytest tests/test_foo.py -v     # single file
pytest --cov=app --cov-report=html

flake8 app/ tests/
black --check --line-length=120 app/ tests/
mypy app/ --ignore-missing-imports --no-strict-optional

# Frontend (frontend/client/)
npm run test                    # vitest
npm run lint                    # eslint (--max-warnings 0)
npm run build                   # vite build

# Dev server
bash scripts/dev.sh             # backend :8000 + frontend :5173 with hot-reload
```

Pre-commit runs: trailing-whitespace, end-of-file-fixer, black, flake8, prettier (JS/TS), eslint.

## Architecture

- **Entrypoint**: `app/main.py` — FastAPI app with `lifespan` startup/shutdown
- **Routes**: `app/api/routes/` — separate modules per domain (mavlink, video, network, modem, vpn, etc.)
- **Services**: `app/services/` — business logic (mavlink_bridge, gstreamer_service, preferences, etc.)
- **Providers**: `app/providers/` — hardware abstraction (modem, video encoder/source, VPN, board, network interfaces). Registered in `init_provider_registry()` at startup
- **Frontend entry**: `frontend/client/src/main.jsx`
- **CLI**: `./fpv` — bash menu that wraps scripts/

## Testing quirks

- `tests/conftest.py` mocks `gi` (GStreamer bindings) at import level — CI has no GStreamer
- Key fixtures: `mock_serial_port`, `mock_mavlink_connection`, `mock_hilink_modem`, `mock_gstreamer`, `mock_api_services`, `temp_preferences`
- `mock_api_services` patches all service dependencies for API endpoint tests (preferences, MAVLink, video, WebRTC, router)
- `serial_port` / `baudrate` / `tcp_port` fixtures skip if no hardware — override with env vars `MAVLINK_TEST_SERIAL_PORT`, `MAVLINK_TEST_BAUDRATE`, `MAVLINK_TEST_TCP_PORT`
- CI excludes `tests/test_mavlink_bridge.py` from flake8 (known complex file)
- Coverage omits hardware-coupled files: `app/providers/*`, `gstreamer_service.py`, `mavlink_bridge.py`, `mavlink_router.py`, `network_event_bridge.py`
- Tests for advanced networking (modem_pool, policy_routing, vpn_health_checker) mock subprocess

## Important gotchas

- **GStreamer encoder probing** runs in thread-pool executor at startup — `gst-inspect-1.0` can block minutes on first boot while rebuilding plugin registry
- **Hardware H.264 encoder** auto-selected as default if available (Rockchip MPP). Falls back to x264 software
- **Video device inventory** warmed in background after startup to reduce first-open latency
- **CORS** configured via env vars: `FPV_CORS_ALLOW_ORIGINS`, `FPV_CORS_ALLOW_CREDENTIALS`, `FPV_CORS_ALLOW_METHODS`, `FPV_CORS_ALLOW_HEADERS`. Wildcard + credentials → credentials disabled
- **Preferences** persisted as `preferences.json` (gitignored). Test with `temp_preferences` fixture
- **Serial auto-connect** runs in background thread. Exponential backoff (1-30s) on reconnect
- **Coverage gate**: `fail_under = 50` in `pyproject.toml`. CI enforces this hard gate
- **Frontend coverage threshold**: ≥ 60%
- **Flake8** has extensive ignores: `E203,W503,E501,F401,F841,E402,...` — see `.flake8`
- **mypy** is `continue-on-error: true` in CI — non-blocking
- **Vite proxy** forwards `/api` and `/ws` to backend at `127.0.0.1:8000`

## Providers system

- Abstract base classes in `app/providers/base/`
- Register in `_startup_init_providers()` in `main.py`
- Current: Tailscale (VPN), Huawei E3372h (modem), 4 network interfaces, V4L2/libcamera/HDMI/network video sources
- To add a provider: implement the base ABC, register via `provider_registry.register_*_provider()`

## Key files

| File                             | Purpose                                                                                                         |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `pyproject.toml`                 | pytest, coverage, black, mypy config                                                                            |
| `.flake8`                        | flake8 config with ignores                                                                                      |
| `.pre-commit-config.yaml`        | pre-commit hooks                                                                                                |
| `.github/workflows/ci.yml`       | CI: lint-backend, lint-frontend, test-backend, provider-contracts, test-frontend, build-frontend, security-scan |
| `systemd/fpvcopilot-sky.service` | systemd unit                                                                                                    |
| `install.sh`                     | full system setup (user, deps, GStreamer, Nginx, serial, sysctl, deploy)                                        |
