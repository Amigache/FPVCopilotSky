# 🚀 Estrategia CI/CD para FPV Copilot Sky

Este documento describe la estrategia de **Continuous Integration** y **Continuous Deployment** para FPV Copilot Sky, considerando los desafíos únicos del proyecto: hardware embebido, dependencias de sistema (GStreamer, NetworkManager), arquitectura ARM, y dispositivos externos (modem, FC, cámara).

---

## 📋 Tabla de contenidos

- [Objetivos](#-objetivos)
- [CI - Continuous Integration](#-ci---continuous-integration)
  - [Lint y Formato](#1-lint-y-formato)
  - [Tests Backend](#2-tests-backend)
  - [Tests Frontend](#3-tests-frontend)
  - [Build Frontend](#4-build-frontend)
  - [Security Scan](#5-security-scan)
- [CD - Continuous Deployment](#-cd---continuous-deployment)
  - [Deploy a Staging](#deploy-a-staging)
  - [Release Automation](#release-automation)
- [Testing Strategy](#-testing-strategy)
  - [Mocks para Hardware](#mocks-para-hardware-dependencies)
  - [Tests a Implementar](#tests-a-implementar)
- [Artifacts y Distribución](#-artifacts-y-distribución)
- [Local Development](#-local-development-helpers)
- [Badges y Métricas](#-badges-para-readme)
- [Roadmap de Implementación](#-roadmap-de-implementación)

---

## 🎯 Objetivos

| Objetivo | Descripción |
|----------|-------------|
| **Calidad de código** | Lint, formato y type checking automático |
| **Testing automático** | Tests unitarios e integración en cada PR |
| **Build validation** | Validar que el frontend se construye correctamente |
| **Security** | Escaneo de vulnerabilidades en dependencias |
| **Deploy automático** | Deploy a staging en cada merge a `main` |
| **Releases** | Generación automática de packages y changelogs |
| **Feedback rápido** | Resultados de CI en <5 minutos |

---

## 🔄 CI - Continuous Integration

Pipeline ejecutado en **cada Pull Request** y **push a main/develop**.

### 1. Lint y Formato

#### Backend (Python)

```yaml
# .github/workflows/ci.yml
lint-backend:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: '3.12'
    
    - name: Install dependencies
      run: |
        pip install flake8 black mypy
        pip install -r requirements.txt
    
    - name: Lint with flake8
      run: flake8 app/ --max-line-length=120 --exclude=__pycache__
    
    - name: Check formatting with black
      run: black --check app/
    
    - name: Type check with mypy
      run: mypy app/ --ignore-missing-imports --no-strict-optional
```

**Reglas de lint:**
- `flake8`: PEP 8 compliance, max line length 120
- `black`: Consistent formatting style
- `mypy`: Type hints validation

#### Frontend (JavaScript/React)

```yaml
lint-frontend:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-node@v4
      with:
        node-version: '20'
    
    - name: Install dependencies
      working-directory: frontend/client
      run: npm ci
    
    - name: Lint with ESLint
      working-directory: frontend/client
      run: npm run lint
    
    - name: Check formatting with Prettier
      working-directory: frontend/client
      run: npx prettier --check src/
```

**Reglas de lint:**
- `ESLint`: React best practices, hooks rules
- `Prettier`: Consistent code formatting

### 2. Tests Backend

```yaml
test-backend:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: '3.12'
    
    - name: Install dependencies
      run: |
        pip install pytest pytest-asyncio pytest-cov pytest-mock
        pip install -r requirements.txt
    
    - name: Run unit tests
      run: |
        pytest tests/ \
          --cov=app \
          --cov-report=xml \
          --cov-report=html \
          --cov-report=term \
          -v \
          --tb=short
    
    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v4
      with:
        file: ./coverage.xml
        flags: backend
        name: backend-coverage
    
    - name: Check coverage threshold
      run: |
        COVERAGE=$(grep -oP 'line-rate="\K[0-9.]+' coverage.xml | head -1)
        THRESHOLD=0.70
        if (( $(echo "$COVERAGE < $THRESHOLD" | bc -l) )); then
          echo "Coverage $COVERAGE is below threshold $THRESHOLD"
          exit 1
        fi
```

**Test requirements:**
- Minimum 70% code coverage
- All tests must pass
- Mock external dependencies (serial, modem, GStreamer)

### 3. Tests Frontend

```yaml
test-frontend:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-node@v4
      with:
        node-version: '20'
    
    - name: Install dependencies
      working-directory: frontend/client
      run: npm ci
    
    - name: Run unit tests
      working-directory: frontend/client
      run: npm run test -- --coverage --run
    
    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v4
      with:
        file: ./frontend/client/coverage/coverage-final.json
        flags: frontend
        name: frontend-coverage
```

**Test framework:**
- `Vitest` for unit tests
- `@testing-library/react` for component testing
- Coverage target: >60%

### 4. Build Frontend

```yaml
build-frontend:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-node@v4
      with:
        node-version: '20'
    
    - name: Install dependencies
      working-directory: frontend/client
      run: npm ci
    
    - name: Build production bundle
      working-directory: frontend/client
      run: npm run build
    
    - name: Check bundle size
      working-directory: frontend/client
      run: |
        SIZE=$(du -sm dist | cut -f1)
        if [ $SIZE -gt 5 ]; then
          echo "Bundle size ${SIZE}MB exceeds 5MB limit"
          exit 1
        fi
    
    - name: Upload build artifacts
      uses: actions/upload-artifact@v4
      with:
        name: frontend-dist
        path: frontend/client/dist/
        retention-days: 7
```

**Build validation:**
- Bundle size must be <5MB
- No build errors or warnings
- Assets are properly optimized

### 5. Security Scan

```yaml
security-scan:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    
    - name: Run Trivy vulnerability scanner
      uses: aquasecurity/trivy-action@master
      with:
        scan-type: 'fs'
        scan-ref: '.'
        format: 'sarif'
        output: 'trivy-results.sarif'
        severity: 'CRITICAL,HIGH'
    
    - name: Upload Trivy results to GitHub Security
      uses: github/codeql-action/upload-sarif@v2
      with:
        sarif_file: 'trivy-results.sarif'
    
    - name: Python security check with Safety
      run: |
        pip install safety
        safety check --json --output safety-report.json || true
    
    - name: Node.js security audit
      working-directory: frontend/client
      run: npm audit --audit-level=high
```

**Security checks:**
- Trivy: Scan for vulnerabilities in dependencies
- Safety: Python package vulnerabilities
- npm audit: JavaScript package vulnerabilities

---

## 📦 CD - Continuous Deployment

### Deploy a Staging

Ejecutado automáticamente en **merge a `main`**.

```yaml
# .github/workflows/deploy-staging.yml
name: CD - Deploy to Staging

on:
  push:
    branches: [main]

jobs:
  deploy-staging:
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
      
      - name: Build frontend
        working-directory: frontend/client
        run: |
          npm ci
          npm run build
      
      - name: Create deployment package
        run: |
          mkdir -p release
          tar -czf release/fpvcopilot-sky-staging.tar.gz \
            --exclude='__pycache__' \
            --exclude='*.pyc' \
            --exclude='venv' \
            --exclude='node_modules' \
            app/ \
            frontend/client/dist/ \
            scripts/ \
            systemd/ \
            requirements.txt \
            install.sh
      
      - name: Deploy to staging SBC via SSH
        uses: appleboy/ssh-action@v1.0.0
        with:
          host: ${{ secrets.STAGING_HOST }}
          username: ${{ secrets.STAGING_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          port: ${{ secrets.STAGING_PORT }}
          script: |
            set -e
            echo "🚀 Starting deployment to staging..."
            
            cd /opt/FPVCopilotSky
            
            # Backup current version
            sudo cp preferences.json preferences.json.backup || true
            
            # Pull latest code
            git fetch origin
            git reset --hard origin/main
            
            # Deploy
            sudo bash scripts/deploy.sh
            
            echo "✅ Deployment complete"
      
      - name: Wait for service startup
        run: sleep 15
      
      - name: Health check
        run: |
          echo "🔍 Checking health endpoint..."
          curl -f http://${{ secrets.STAGING_HOST }}/api/status || exit 1
          echo "✅ Health check passed"
      
      - name: Smoke tests
        run: |
          # Test critical endpoints
          curl -f http://${{ secrets.STAGING_HOST }}/api/mavlink-router/outputs || exit 1
          curl -f http://${{ secrets.STAGING_HOST }}/api/video/sources || exit 1
          echo "✅ Smoke tests passed"
      
      - name: Notify on failure
        if: failure()
        run: |
          curl -X POST ${{ secrets.DISCORD_WEBHOOK }} \
            -H 'Content-Type: application/json' \
            -d '{
              "content": "❌ Staging deployment failed!",
              "embeds": [{
                "title": "Deployment Failed",
                "description": "Check GitHub Actions for details",
                "url": "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}",
                "color": 15158332
              }]
            }'
```

**Staging environment:**
- Dedicated SBC (Radxa Zero or similar)
- Accessible via VPN or SSH tunnel
- Same configuration as production
- Database/preferences backed up before deploy

### Release Automation

Ejecutado en **push de tags** (`v*`).

```yaml
# .github/workflows/release.yml
name: Release - Create Package

on:
  push:
    tags:
      - 'v*'

jobs:
  create-release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Full history for changelog
      
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
      
      - name: Build frontend for production
        working-directory: frontend/client
        run: |
          npm ci
          npm run build
      
      - name: Create release package
        run: |
          VERSION=${GITHUB_REF#refs/tags/v}
          echo "Creating release package for version $VERSION"
          
          mkdir -p release
          
          # Full package
          tar -czf release/fpvcopilot-sky-v${VERSION}.tar.gz \
            --exclude='venv' \
            --exclude='node_modules' \
            --exclude='.git' \
            --exclude='__pycache__' \
            --exclude='*.pyc' \
            --exclude='.DS_Store' \
            app/ \
            frontend/client/dist/ \
            scripts/ \
            systemd/ \
            docs/ \
            requirements.txt \
            pyproject.toml \
            install.sh \
            README.md \
            CONTRIBUTING.md \
            LICENSE
          
          # Checksums
          cd release
          sha256sum fpvcopilot-sky-v${VERSION}.tar.gz > checksums.txt
          md5sum fpvcopilot-sky-v${VERSION}.tar.gz >> checksums.txt
      
      - name: Generate changelog
        id: changelog
        uses: mikepenz/release-changelog-builder-action@v4
        with:
          configuration: |
            {
              "categories": [
                {
                  "title": "## 🚀 Features",
                  "labels": ["feat", "feature"]
                },
                {
                  "title": "## 🐛 Bug Fixes",
                  "labels": ["fix", "bugfix"]
                },
                {
                  "title": "## 📚 Documentation",
                  "labels": ["docs", "documentation"]
                },
                {
                  "title": "## 🔧 Refactor",
                  "labels": ["refactor"]
                },
                {
                  "title": "## ⚡ Performance",
                  "labels": ["perf", "performance"]
                }
              ],
              "template": "#{{CHANGELOG}}\n\n**Full Changelog**: #{{RELEASE_DIFF}}"
            }
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Create GitHub Release
        uses: softprops/action-gh-release@v1
        with:
          body: |
            # FPV Copilot Sky ${{ github.ref_name }}
            
            ${{ steps.changelog.outputs.changelog }}
            
            ## 📦 Installation
            
            ```bash
            VERSION="${{ github.ref_name }}"
            wget https://github.com/${{ github.repository }}/releases/download/${VERSION}/fpvcopilot-sky-${VERSION}.tar.gz
            tar -xzf fpvcopilot-sky-${VERSION}.tar.gz -C /opt/FPVCopilotSky
            cd /opt/FPVCopilotSky
            sudo bash install.sh
            ```
            
            ## 🔍 Verify Download
            
            ```bash
            sha256sum -c checksums.txt
            ```
          files: |
            release/fpvcopilot-sky-*.tar.gz
            release/checksums.txt
          draft: false
          prerelease: false
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Notify Discord/Slack
        if: success()
        run: |
          VERSION=${GITHUB_REF#refs/tags/}
          curl -X POST ${{ secrets.DISCORD_WEBHOOK }} \
            -H 'Content-Type: application/json' \
            -d '{
              "content": "🚀 **New Release Available!**",
              "embeds": [{
                "title": "FPV Copilot Sky '$VERSION'",
                "description": "A new version has been released",
                "url": "https://github.com/${{ github.repository }}/releases/tag/'$VERSION'",
                "color": 3447003,
                "fields": [
                  {
                    "name": "Version",
                    "value": "'$VERSION'",
                    "inline": true
                  },
                  {
                    "name": "Download",
                    "value": "[Release Page](https://github.com/${{ github.repository }}/releases/tag/'$VERSION')",
                    "inline": true
                  }
                ]
              }]
            }'
```

**Release artifacts:**
- Complete package with pre-built frontend
- Checksums (SHA256, MD5)
- Auto-generated changelog
- Installation instructions
- Discord/Slack notifications

---

## 🧪 Testing Strategy

### Mocks para Hardware Dependencies

Dado que el CI no tiene acceso a hardware físico (FC, modem, cámara), necesitamos mocks comprehensivos.

#### Fixtures principales

```python
# tests/conftest.py
import pytest
from unittest.mock import Mock, patch, MagicMock
import json

@pytest.fixture
def mock_serial_port():
    """Mock pyserial for tests without hardware"""
    with patch('serial.Serial') as mock:
        mock_port = Mock()
        mock_port.is_open = True
        mock_port.in_waiting = 0
        mock_port.baudrate = 115200
        mock_port.port = '/dev/ttyUSB0'
        
        # Mock MAVLink heartbeat packet
        mock_port.read.return_value = b'\xfe\x09\x00\x01\x01\x00\x00\x00\x00\x00\x06\x08\x00\x00\x00\x03'
        
        mock.return_value = mock_port
        yield mock_port

@pytest.fixture
def mock_mavlink_connection():
    """Mock MAVLink connection"""
    with patch('pymavlink.mavutil.mavlink_connection') as mock:
        mock_conn = Mock()
        mock_conn.target_system = 1
        mock_conn.target_component = 1
        
        # Mock heartbeat message
        mock_heartbeat = Mock()
        mock_heartbeat.get_type.return_value = 'HEARTBEAT'
        mock_heartbeat.custom_mode = 0
        mock_heartbeat.base_mode = 81
        mock_heartbeat.system_status = 4
        
        mock_conn.recv_match.return_value = mock_heartbeat
        mock_conn.wait_heartbeat.return_value = True
        
        mock.return_value = mock_conn
        yield mock_conn

@pytest.fixture
def mock_hilink_modem():
    """Mock Huawei HiLink API"""
    with patch('huawei_lte_api.Connection') as mock:
        mock_conn = Mock()
        
        # Mock device info
        mock_conn.device.information.return_value = {
            'DeviceName': 'E3372h-320',
            'Imei': '123456789012345',
            'HardwareVersion': 'CL2E3372HM',
            'SoftwareVersion': '22.333.01.00.00'
        }
        
        # Mock signal info
        mock_conn.device.signal.return_value = {
            'rssi': '-65',
            'rsrp': '-95',
            'rsrq': '-10',
            'sinr': '15',
            'cell_id': '12345678'
        }
        
        # Mock network info
        mock_conn.net.current_plmn.return_value = {
            'FullName': 'Orange Spain',
            'ShortName': 'Orange',
            'Numeric': '21407'
        }
        
        mock.return_value = mock_conn
        yield mock_conn

@pytest.fixture
def mock_gstreamer():
    """Mock GStreamer for tests without camera"""
    with patch('gi.repository.Gst') as mock_gst:
        mock_pipeline = MagicMock()
        mock_pipeline.set_state.return_value = (True, 0, 0)
        mock_pipeline.get_state.return_value = (1, 4, 0)  # SUCCESS, PLAYING, VOID_PENDING
        
        mock_gst.Pipeline.return_value = mock_pipeline
        mock_gst.State.PLAYING = 4
        mock_gst.State.NULL = 1
        
        yield mock_gst

@pytest.fixture
def mock_subprocess():
    """Mock subprocess for system commands"""
    with patch('subprocess.run') as mock:
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Mock output"
        mock_result.stderr = ""
        mock.return_value = mock_result
        yield mock

@pytest.fixture
def temp_preferences(tmp_path):
    """Create temporary preferences file"""
    prefs_file = tmp_path / "preferences.json"
    prefs_data = {
        "serial": {
            "port": "/dev/ttyUSB0",
            "baudrate": 115200,
            "auto_connect": False
        },
        "video": {
            "source": "libcamera",
            "codec": "h264",
            "width": 1280,
            "height": 720,
            "fps": 30
        },
        "vpn": {
            "provider": "tailscale",
            "auto_connect": False
        }
    }
    prefs_file.write_text(json.dumps(prefs_data, indent=2))
    return prefs_file
```

### Tests a Implementar

#### Backend Tests

```python
# tests/test_mavlink_bridge.py
import pytest
from app.services.mavlink_bridge import MAVLinkBridge

@pytest.mark.asyncio
async def test_connect_success(mock_serial_port, mock_mavlink_connection):
    """Test successful MAVLink connection"""
    bridge = MAVLinkBridge()
    result = await bridge.connect("/dev/ttyUSB0", 115200)
    
    assert result["success"] is True
    assert bridge.is_connected() is True
    assert bridge.get_system_id() == 1

@pytest.mark.asyncio
async def test_connect_no_heartbeat(mock_serial_port, mock_mavlink_connection):
    """Test connection fails without heartbeat"""
    mock_mavlink_connection.wait_heartbeat.side_effect = TimeoutError()
    
    bridge = MAVLinkBridge()
    result = await bridge.connect("/dev/ttyUSB0", 115200)
    
    assert result["success"] is False
    assert "timeout" in result["message"].lower()

@pytest.mark.asyncio
async def test_disconnect(mock_mavlink_connection):
    """Test clean disconnection"""
    bridge = MAVLinkBridge()
    await bridge.connect("/dev/ttyUSB0", 115200)
    
    result = await bridge.disconnect()
    
    assert result["success"] is True
    assert bridge.is_connected() is False

# tests/test_preferences.py
from app.services.preferences import PreferencesService

def test_save_load_cycle(temp_preferences):
    """Test preferences are persisted correctly"""
    prefs = PreferencesService(config_path=str(temp_preferences))
    
    # Modify serial config
    prefs.set_serial_config(port="/dev/ttyUSB1", baudrate=57600)
    
    # Reload from disk
    prefs2 = PreferencesService(config_path=str(temp_preferences))
    config = prefs2.get_serial_config()
    
    assert config["port"] == "/dev/ttyUSB1"
    assert config["baudrate"] == 57600

def test_concurrent_access(temp_preferences):
    """Test thread-safe access with RLock"""
    prefs = PreferencesService(config_path=str(temp_preferences))
    
    # Simulate concurrent access
    import concurrent.futures
    
    def update_serial():
        prefs.set_serial_config(port="/dev/ttyUSB0", baudrate=115200)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(update_serial) for _ in range(10)]
        concurrent.futures.wait(futures)
    
    # Should not deadlock
    config = prefs.get_serial_config()
    assert config["port"] == "/dev/ttyUSB0"

# tests/test_modem_provider.py
from app.providers.modem.hilink.router import HuaweiHiLinkRouter

def test_get_status(mock_hilink_modem):
    """Test modem status retrieval"""
    provider = HuaweiHiLinkRouter()
    status = provider.get_status()
    
    assert status["available"] is True
    assert "signal" in status
    assert status["signal"]["rssi"] == "-65"

def test_get_band_presets(mock_hilink_modem):
    """Test band presets are returned"""
    provider = HuaweiHiLinkRouter()
    presets = provider.get_band_presets()
    
    assert "presets" in presets
    assert "all" in presets["presets"]
    assert "orange_spain" in presets["presets"]

# tests/test_video_service.py
from app.services.gstreamer_service import GStreamerService

@pytest.mark.asyncio
async def test_start_stream(mock_gstreamer):
    """Test video stream starts successfully"""
    service = GStreamerService()
    config = {
        "source": "libcamera",
        "codec": "h264",
        "width": 1280,
        "height": 720,
        "fps": 30,
        "bitrate": 2000
    }
    
    result = await service.start_stream(config)
    
    assert result["success"] is True
    assert service.is_streaming() is True

@pytest.mark.asyncio
async def test_stop_stream(mock_gstreamer):
    """Test video stream stops cleanly"""
    service = GStreamerService()
    await service.start_stream({})
    
    result = await service.stop_stream()
    
    assert result["success"] is True
    assert service.is_streaming() is False
```

#### Frontend Tests

```jsx
// frontend/client/src/components/__tests__/Header.test.jsx
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import Header from '../Header/Header'

test('renders header title', () => {
  render(
    <BrowserRouter>
      <Header />
    </BrowserRouter>
  )
  const title = screen.getByText(/FPV Copilot Sky/i)
  expect(title).toBeInTheDocument()
})

test('displays connection status', () => {
  render(
    <BrowserRouter>
      <Header streamOnline={true} fcConnected={true} />
    </BrowserRouter>
  )
  
  expect(screen.getByText(/Stream: Online/i)).toBeInTheDocument()
  expect(screen.getByText(/FC Connected/i)).toBeInTheDocument()
})

// frontend/client/src/components/__tests__/TelemetryView.test.jsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import TelemetryView from '../Pages/TelemetryView'

test('loads and displays router outputs', async () => {
  global.fetch = vi.fn(() =>
    Promise.resolve({
      ok: true,
      json: () => Promise.resolve([
        { id: 1, type: 'udp', host: '0.0.0.0', port: 14550, active: true }
      ])
    })
  )
  
  render(<TelemetryView />)
  
  await waitFor(() => {
    expect(screen.getByText(/14550/)).toBeInTheDocument()
  })
})

test('creates new output', async () => {
  const user = userEvent.setup()
  
  global.fetch = vi.fn(() =>
    Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ success: true })
    })
  )
  
  render(<TelemetryView />)
  
  await user.type(screen.getByLabelText(/Host/i), '192.168.1.100')
  await user.type(screen.getByLabelText(/Port/i), '5760')
  await user.click(screen.getByText(/Create/i))
  
  await waitFor(() => {
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/outputs'),
      expect.objectContaining({ method: 'POST' })
    )
  })
})
```

---

## 📦 Artifacts y Distribución

### Estructura del Release Package

```
fpvcopilot-sky-v1.2.0.tar.gz
├── app/                          # Backend Python
│   ├── main.py
│   ├── config.py
│   ├── api/
│   ├── services/
│   ├── providers/
│   ├── i18n/
│   └── utils/
├── frontend/client/dist/         # Frontend pre-built
│   ├── index.html
│   ├── assets/
│   │   ├── index-<hash>.js
│   │   └── index-<hash>.css
│   └── favicon.ico
├── scripts/                      # Utility scripts
│   ├── install-production.sh
│   ├── deploy.sh
│   ├── dev.sh
│   ├── status.sh
│   └── configure-modem.sh
├── systemd/                      # Service files
│   ├── fpvcopilot-sky.service
│   └── fpvcopilot-sky.nginx
├── docs/                         # Documentation
│   ├── INSTALLATION.md
│   ├── USER_GUIDE.md
│   ├── DEVELOPER_GUIDE.md
│   ├── BOARD_PROVIDER_SYSTEM.md
│   └── CI_CD_STRATEGY.md
├── requirements.txt              # Python dependencies
├── pyproject.toml               # Python project config
├── install.sh                   # Main installer
├── README.md
├── CONTRIBUTING.md
└── LICENSE
```

### Instalación desde Release

```bash
# Download latest release
VERSION="1.2.0"
wget https://github.com/user/FPVCopilotSky/releases/download/v${VERSION}/fpvcopilot-sky-v${VERSION}.tar.gz

# Verify checksum
wget https://github.com/user/FPVCopilotSky/releases/download/v${VERSION}/checksums.txt
sha256sum -c checksums.txt

# Extract
sudo mkdir -p /opt/FPVCopilotSky
sudo tar -xzf fpvcopilot-sky-v${VERSION}.tar.gz -C /opt/FPVCopilotSky --strip-components=1

# Install
cd /opt/FPVCopilotSky
sudo bash install.sh

# Verify installation
sudo systemctl status fpvcopilot-sky
curl http://localhost/api/status
```

---

## 🔧 Local Development Helpers

### Act - Run GitHub Actions Locally

```bash
# Install act
curl https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash

# Run CI workflow locally
act pull_request

# Run specific job
act -j test-backend

# With secrets
act -s GITHUB_TOKEN=ghp_xxxx
```

### Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/psf/black
    rev: 24.1.1
    hooks:
      - id: black
        language_version: python3.12
  
  - repo: https://github.com/pycqa/flake8
    rev: 7.0.0
    hooks:
      - id: flake8
        args: [--max-line-length=120]
  
  - repo: https://github.com/pre-commit/mirrors-prettier
    rev: v4.0.0-alpha.8
    hooks:
      - id: prettier
        files: \.(js|jsx|ts|tsx|json|css|md)$
```

```bash
# Install pre-commit
pip install pre-commit
cd /opt/FPVCopilotSky
pre-commit install

# Run manually
pre-commit run --all-files
```

---

## 📊 Badges para README

Añadir al [README.md](../README.md):

```markdown
![CI Status](https://github.com/user/FPVCopilotSky/workflows/CI/badge.svg)
![codecov](https://codecov.io/gh/user/FPVCopilotSky/branch/main/graph/badge.svg)
![GitHub Release](https://img.shields.io/github/v/release/user/FPVCopilotSky)
![License](https://img.shields.io/badge/license-MIT-yellow)
![Python](https://img.shields.io/badge/python-3.12+-blue)
![React](https://img.shields.io/badge/react-19-61dafb)
![Platform](https://img.shields.io/badge/platform-Linux_ARM/x86-green)
```

**Métricas visibles:**
- CI build status
- Code coverage percentage
- Latest release version
- License type
- Platform support

---

## 🎯 Roadmap de Implementación

### Fase 1: Setup Básico (Semana 1)

**Objetivo**: Infraestructura CI básica funcionando

- [ ] **Día 1-2**: Configurar repositorio en GitHub
  - Crear repositorio público/privado
  - Configurar branch protection en `main`
  - Añadir colaboradores y permisos
  - Crear labels para issues (bug, feature, docs, etc.)

- [ ] **Día 3-4**: CI básico - Lint
  - Crear `.github/workflows/ci.yml`
  - Setup flake8, black, mypy para Python
  - Setup ESLint, Prettier para JavaScript
  - Configurar artifact caching para npm/pip

- [ ] **Día 5-7**: Tests iniciales
  - Instalar pytest con plugins necesarios
  - Crear `tests/conftest.py` con fixtures
  - Escribir 3-5 tests básicos como ejemplo
  - Configurar coverage reporting

**Entregables**:
- ✅ CI workflow ejecutándose en PRs
- ✅ Lint checks pasando
- ✅ Tests básicos ejecutándose

### Fase 2: Testing Completo (Semana 2-3)

**Objetivo**: >70% coverage en backend, >60% en frontend

- [ ] **Semana 2**: Backend tests
  - Mock completo de serial/MAVLink
  - Mock completo de HuaweiHiLink
  - Mock completo de GStreamer
  - Tests de servicios críticos:
    - `test_mavlink_bridge.py` (10+ tests)
    - `test_preferences.py` (8+ tests)
    - `test_gstreamer_service.py` (8+ tests)
    - `test_modem_provider.py` (6+ tests)
  - Integration tests básicos

- [ ] **Semana 3**: Frontend tests
  - Setup Vitest + @testing-library/react
  - Tests de componentes principales:
    - Header, Toast, Modal
    - TelemetryView, VideoView, ModemView
  - Tests de contexts (WebSocket, Toast, Modal)
  - Tests de utils/api.js
  - Snapshot testing para componentes estáticos

**Entregables**:
- ✅ Backend coverage >70%
- ✅ Frontend coverage >60%
- ✅ Codecov integration activo

### Fase 3: CD y Releases (Semana 4)

**Objetivo**: Deploy automático y releases automatizadas

- [ ] **Día 1-3**: Staging environment
  - Configurar SBC staging dedicado
  - Setup SSH keys y secrets en GitHub
  - Crear workflow `deploy-staging.yml`
  - Configurar rollback automático en caso de fallo

- [ ] **Día 4-5**: Release automation
  - Crear workflow `release.yml`
  - Configurar changelog generation
  - Setup artifact packaging
  - Crear release template

- [ ] **Día 6-7**: Notifications y monitoring
  - Integrar Discord/Slack webhooks
  - Configurar alertas de fallos
  - Setup status page (opcional)
  - Documentar proceso de release

**Entregables**:
- ✅ Deploy automático a staging funcionando
- ✅ Release tags generan packages automáticamente
- ✅ Notificaciones configuradas

### Fase 4: Optimizaciones (Ongoing)

**Objetivo**: Mejorar velocidad, reliability y coverage

- [ ] **Optimización de CI**
  - Dependency caching mejorado
  - Parallel job execution
  - Matrix testing (Python 3.12, 3.13)
  - ARM emulation tests con QEMU

- [ ] **Security hardening**
  - Dependabot configurado
  - SAST (Static Application Security Testing)
  - Secret scanning
  - License compliance checking

- [ ] **Performance monitoring**
  - Lighthouse CI para frontend
  - Backend performance benchmarks
  - Bundle size tracking
  - Load testing básico

- [ ] **Documentation CI**
  - Auto-generate API docs (Sphinx/JSDoc)
  - Link checking en markdown
  - Spell checking
  - Screenshot automation

**Entregables**:
- ✅ CI time <5 minutes
- ✅ Security scanning activo
- ✅ Performance metrics tracked

---

## 🚦 Métricas de Éxito

| Métrica | Objetivo | Actual |
|---------|----------|--------|
| **CI Build Time** | <5 min | - |
| **Backend Coverage** | >70% | - |
| **Frontend Coverage** | >60% | - |
| **Deploy Time** | <3 min | - |
| **Mean Time to Recovery** | <15 min | - |
| **PR Review Time** | <24h | - |
| **Security Vulns** | 0 high/critical | - |
| **Test Success Rate** | >95% | - |

---

## 📚 Referencias

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [pytest Documentation](https://docs.pytest.org/)
- [Vitest Documentation](https://vitest.dev/)
- [Codecov Documentation](https://docs.codecov.com/)
- [Act - Local GitHub Actions](https://github.com/nektos/act)
- [Pre-commit Framework](https://pre-commit.com/)
- [Conventional Commits](https://www.conventionalcommits.org/)

---

## 🤝 Contribuir al CI/CD

Las mejoras al sistema CI/CD son bienvenidas. Ver [CONTRIBUTING.md](../CONTRIBUTING.md) para detalles sobre:

- Añadir nuevos tests
- Optimizar workflows
- Mejorar mocks
- Documentar procesos

---

**Última actualización**: 8 de febrero de 2026
