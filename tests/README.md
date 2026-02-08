# 🧪 Tests

Test suite para FPV Copilot Sky utilizando pytest y vitest.

## 📋 Estructura

```
tests/
├── conftest.py              # Fixtures compartidos y configuración pytest
├── test_preferences.py      # Tests del servicio de preferencias
├── test_api_status.py       # Tests de endpoints de API
├── test_mavlink_service.py  # Tests del servicio MAVLink
└── test_mavlink_bridge.py   # Script de debugging manual (legacy)
```

## 🚀 Ejecutar tests

### Backend (Python/pytest)

```bash
# Instalar dependencias de testing
pip install -r requirements.txt

# Ejecutar todos los tests
pytest

# Con coverage
pytest --cov=app --cov-report=html

# Ver reporte de coverage
open htmlcov/index.html

# Tests específicos
pytest tests/test_preferences.py
pytest tests/test_api_status.py -v

# Solo tests unitarios (excluir integration)
pytest -m "not integration"

# Tests rápidos (excluir slow)
pytest -m "not slow"
```

### Frontend (JavaScript/Vitest)

```bash
cd frontend/client

# Instalar dependencias
npm install

# Ejecutar tests
npm run test

# Con UI interactiva
npm run test:ui

# Con coverage
npm run test:coverage

# Watch mode
npm run test -- --watch
```

## 🔧 Configuración

### pytest (pyproject.toml)

- Mínimo coverage: No configurado (recomendado: 70%)
- Tests en: `tests/`
- Markers: `asyncio`, `slow`, `integration`, `unit`, `hardware`

### Vitest (vitest.config.js)

- Environment: jsdom (React testing)
- Setup file: `src/test/setup.js`
- Coverage provider: v8

## 📝 Escribir tests

### Backend Example

```python
import pytest
from app.services.preferences import PreferencesService

@pytest.mark.asyncio
async def test_save_preferences(temp_preferences):
    """Test saving preferences"""
    prefs = PreferencesService(config_path=str(temp_preferences))

    result = prefs.set_serial_config(port="/dev/ttyUSB0", baudrate=115200)

    assert result is True
    config = prefs.get_serial_config()
    assert config["port"] == "/dev/ttyUSB0"
```

### Frontend Example

```javascript
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import MyComponent from "../MyComponent";

test("renders component", () => {
  render(<MyComponent />);
  expect(screen.getByText(/expected text/i)).toBeInTheDocument();
});
```

## 🧩 Fixtures disponibles

Los fixtures están definidos en `conftest.py`:

- `mock_serial_port` - Mock de puerto serial
- `mock_mavlink_connection` - Mock de conexión MAVLink
- `mock_hilink_modem` - Mock de modem Huawei HiLink
- `mock_gstreamer` - Mock de GStreamer pipeline
- `mock_subprocess` - Mock de comandos subprocess
- `temp_preferences` - Archivo temporal de preferencias
- `mock_network_manager` - Mock de NetworkManager
- `mock_tailscale` - Mock de Tailscale CLI
- `sample_mavlink_messages` - Mensajes MAVLink de ejemplo

### Uso de fixtures

```python
def test_with_mock_modem(mock_hilink_modem):
    """Test que usa el fixture de modem"""
    # mock_hilink_modem ya está configurado
    provider = HuaweiHiLinkRouter()
    status = provider.get_status()
    assert status["available"] is True
```

## 🏷️ Markers

```python
@pytest.mark.asyncio        # Test asíncrono
@pytest.mark.slow           # Test lento (>1s)
@pytest.mark.integration    # Test de integración
@pytest.mark.unit           # Test unitario
@pytest.mark.hardware       # Requiere hardware físico (skip en CI)
```

```bash
# Ejecutar solo tests unitarios
pytest -m unit

# Excluir tests de hardware
pytest -m "not hardware"
```

## 🔍 Coverage

### Objetivo de coverage

- Backend: **>70%**
- Frontend: **>60%**

### Ver coverage actual

```bash
# Backend
pytest --cov=app --cov-report=term-missing

# Frontend
cd frontend/client
npm run test:coverage
```

### Archivos excluidos de coverage

- `*/tests/*`
- `*/__pycache__/*`
- `*/venv/*`
- `node_modules/`
- Config files

## 🐛 Debugging tests

### pytest

```bash
# Verbose output
pytest -v

# Show print statements
pytest -s

# Stop on first failure
pytest -x

# Run specific test
pytest tests/test_preferences.py::TestPreferencesBasic::test_load_existing_preferences

# Debug with pdb
pytest --pdb
```

### Vitest

```bash
# UI mode (recommended)
npm run test:ui

# Watch mode
npm run test -- --watch

# Run specific test file
npm run test -- Header.test.jsx
```

## 📊 CI/CD

Los tests se ejecutan automáticamente en GitHub Actions en cada Pull Request.

Ver: `.github/workflows/ci.yml`

### Workflow stages:

1. **Lint** - flake8, black, mypy, eslint, prettier
2. **Test Backend** - pytest con coverage
3. **Test Frontend** - vitest con coverage
4. **Build** - Validar build de producción
5. **Security** - Trivy, Safety, npm audit

## 🔗 Referencias

- [pytest docs](https://docs.pytest.org/)
- [Vitest docs](https://vitest.dev/)
- [Testing Library](https://testing-library.com/)
- [Coverage.py](https://coverage.readthedocs.io/)

---

**Última actualización**: 8 de febrero de 2026
