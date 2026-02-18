# 🤝 Guía de Contribución

¡Gracias por tu interés en contribuir a **FPV Copilot Sky**! 🚁

Este documento te guiará en el proceso de contribuir al proyecto, ya sea reportando bugs, sugiriendo mejoras, mejorando la documentación o enviando código.

---

## 📋 Tabla de contenidos

- [Código de Conducta](#-código-de-conducta)
- [¿Cómo puedo contribuir?](#-cómo-puedo-contribuir)
  - [Reportar bugs](#reportar-bugs)
  - [Sugerir mejoras](#sugerir-mejoras)
  - [Mejorar documentación](#mejorar-documentación)
  - [Contribuir código](#contribuir-código)
- [Configuración del entorno de desarrollo](#-configuración-del-entorno-de-desarrollo)
- [Estructura del proyecto](#-estructura-del-proyecto)
- [Guías de estilo](#-guías-de-estilo)
  - [Python](#python)
  - [JavaScript/React](#javascriptreact)
  - [Commits](#commits)
- [Proceso de contribución](#-proceso-de-contribución)
- [Sistema de Providers](#-sistema-de-providers)
- [Internacionalización (i18n)](#-internacionalización-i18n)
- [Testing](#-testing)
- [Documentación](#-documentación)

---

## 📜 Código de Conducta

### Nuestro compromiso

Este proyecto está comprometido con proporcionar un ambiente abierto, inclusivo y respetuoso para todos los contribuidores, independientemente de su nivel de experiencia, género, identidad, orientación, discapacidad, etnia o religión.

### Comportamiento esperado

- **Sé respetuoso**: Trata a todos con respeto y empatía
- **Sé constructivo**: Ofrece críticas constructivas y acepta feedback
- **Sé colaborativo**: Ayuda a otros contribuidores cuando sea posible
- **Sé paciente**: Recuerda que todos estamos aprendiendo

### Comportamiento inaceptable

- Lenguaje ofensivo, discriminatorio o acosador
- Ataques personales o políticos
- Publicar información privada de otros sin permiso
- Cualquier conducta considerada inapropiada en un entorno profesional

---

## 🚀 ¿Cómo puedo contribuir?

### Reportar bugs

Los bugs se reportan como **GitHub Issues**. Antes de crear un issue:

1. **Busca en los issues existentes** para evitar duplicados
2. **Verifica con la última versión** del código
3. **Recoge información relevante**: logs, configuración, hardware

#### Template para reportar bugs

```markdown
**Descripción del bug**
Una descripción clara y concisa del problema.

**Pasos para reproducir**

1. Ir a '...'
2. Hacer clic en '...'
3. Ver error

**Comportamiento esperado**
Qué esperabas que sucediera.

**Comportamiento actual**
Qué está sucediendo realmente.

**Screenshots/Logs**
Si aplica, añade capturas o logs relevantes.

**Entorno**

- Hardware: [Radxa Zero, Raspberry Pi 4, etc.]
- OS: [Armbian, Ubuntu 24.04, etc.]
- Python: [3.12, 3.13, etc.]
- Browser: [Chrome 120, Firefox 115, etc.]

**Contexto adicional**
Cualquier otra información relevante.
```

### Sugerir mejoras

Las sugerencias de nuevas funcionalidades también se gestionan como Issues:

1. **Describe el problema** que tu feature resolvería
2. **Propón una solución** con detalles de implementación si es posible
3. **Describe alternativas** que hayas considerado
4. **Considera el impacto** en hardware, rendimiento y UX

### Mejorar documentación

La documentación es tan importante como el código:

- **Corrige errores** tipográficos o gramaticales
- **Aclara secciones confusas**
- **Añade ejemplos prácticos**
- **Actualiza información obsoleta**
- **Mejora traducciones** (EN/ES)

Archivos de documentación:

- `README.md` - Introducción general del proyecto
- `docs/INSTALLATION.md` - Guía de instalación
- `docs/USER_GUIDE.md` - Manual de usuario
- `docs/DEVELOPER_GUIDE.md` - Guía técnica detallada

### Contribuir código

Las contribuciones de código son bienvenidas en:

- **Backend (Python/FastAPI)**: APIs, servicios, providers
- **Frontend (React)**: Componentes, vistas, estilos
- **Scripts**: Instalación, despliegue, utilidades
- **Tests**: Unitarios, integración, end-to-end

---

## 🛠️ Configuración del entorno de desarrollo

### Requisitos previos

- **Linux** (Debian/Ubuntu, Armbian) - ARM o x86_64
- **Python 3.12+** con `pip` y `venv`
- **Node.js 20+** con `npm`
- **Git** para control de versiones

### Setup rápido

```bash
# 1. Clonar el repositorio
git clone https://github.com/tu-usuario/FPVCopilotSky.git
cd FPVCopilotSky

# 2. Backend: Crear entorno virtual e instalar dependencias
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Frontend: Instalar dependencias
cd frontend/client
npm install
cd ../..

# 4. Configurar Nginx (opcional, para desarrollo local)
sudo cp systemd/fpvcopilot-sky.nginx /etc/nginx/sites-available/fpvcopilot-sky
sudo ln -s /etc/nginx/sites-available/fpvcopilot-sky /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo systemctl reload nginx

# 5. Script de desarrollo (backend + frontend)
./fpv    # Opción 3: "Start Development Mode"
# O manualmente:
bash scripts/dev.sh
```

### Desarrollo con hot-reload

**Usando el CLI (recomendado)**:

```bash
./fpv
# Selecciona opción 3: "Start Development Mode"
```

**Manual**:

```bash
# Terminal 1: Backend con auto-reload
source venv/bin/activate
cd app
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Frontend con Vite dev server
cd frontend/client
npm run dev
```

**URLs de desarrollo:**

- Frontend: http://localhost:5173 (Vite dev server)
- Backend API: http://localhost:8000/api
- API Docs: http://localhost:8000/docs

---

## 📂 Estructura del proyecto

```
FPVCopilotSky/
├── app/                          # Backend Python/FastAPI
│   ├── main.py                   # Entry point de FastAPI
│   ├── config.py                 # Configuración global
│   ├── api/                      # Endpoints REST
│   │   └── routes/              # Rutas por dominio
│   │       ├── mavlink.py       # Telemetría MAVLink
│   │       ├── router.py        # MAVLink router outputs
│   │       ├── video.py         # Streaming de video
│   │       ├── network/         # Gestión de red (modular)
│   │       │   ├── __init__.py  # Router principal
│   │       │   ├── common.py    # Utilidades compartidas
│   │       │   ├── status.py    # Estado y dashboard
│   │       │   ├── flight_mode.py    # Optimización FPV
│   │       │   ├── flight_session.py # Grabación de vuelo
│   │       │   ├── latency.py   # Monitoreo de latencia
│   │       │   ├── failover.py  # Auto-failover
│   │       │   ├── dns.py       # Caché DNS
│   │       │   ├── bridge.py    # Network-video bridge
│   │       │   └── mptcp.py     # Multi-Path TCP
│   │       ├── modem.py         # Modems 4G/LTE
│   │       ├── vpn.py           # VPN (Tailscale)
│   │       ├── status.py        # Estado del sistema
│   │       └── system.py        # Operaciones de sistema
│   ├── services/                # Lógica de negocio
│   │   ├── mavlink_bridge.py   # Conexión MAVLink
│   │   ├── mavlink_router.py   # Enrutamiento MAVLink
│   │   ├── gstreamer_service.py # Video GStreamer
│   │   ├── cache_service.py     # Caché centralizado (TTL, thread-safe)
│   │   ├── preferences.py       # Persistencia de config
│   │   ├── serial_detector.py   # Auto-detección serial
│   │   ├── system_service.py    # Operaciones de sistema
│   │   └── websocket_manager.py # Push WebSocket
│   ├── providers/               # Sistema modular de providers
│   │   ├── registry.py          # Registro central
│   │   ├── base/                # Interfaces abstractas
│   │   ├── board/               # Detección de hardware
│   │   ├── modem/               # Modems 4G (HuaweiHiLink, etc)
│   │   ├── network/             # Gestión de red (WiFi, etc)
│   │   ├── video/               # Encoders (H.264, MJPEG)
│   │   ├── video_source/        # Fuentes (CSI, USB, HDMI)
│   │   └── vpn/                 # Tailscale, Wireguard...
│   ├── i18n/                    # Traducciones backend
│   │   ├── en.json
│   │   └── es.json
│   └── utils/
│       └── logger.py            # Logging centralizado
├── frontend/client/             # Frontend React/Vite
│   ├── src/
│   │   ├── main.jsx             # Entry point React
│   │   ├── App.jsx              # Layout principal
│   │   ├── components/          # Componentes React
│   │   │   ├── Pages/          # Vistas principales
│   │   │   │   ├── Dashboard.jsx
│   │   │   │   ├── TelemetryView.jsx
│   │   │   │   ├── VideoView.jsx
│   │   │   │   ├── NetworkView.jsx
│   │   │   │   ├── ModemView.jsx
│   │   │   │   ├── VPNView.jsx
│   │   │   │   ├── StatusView.jsx
│   │   │   │   └── SystemView.jsx
│   │   │   ├── Header/
│   │   │   ├── Toast/
│   │   │   ├── Modal/
│   │   │   └── PeerSelector/
│   │   ├── contexts/           # React Contexts
│   │   │   ├── ToastContext.jsx
│   │   │   ├── ModalContext.jsx
│   │   │   └── WebSocketContext.jsx
│   │   ├── services/           # API clients
│   │   │   └── api.js
│   │   └── i18n/               # Traducciones frontend
│   │       └── locales/
│   │           ├── en.json
│   │           └── es.json
│   ├── public/                 # Assets estáticos
│   ├── vite.config.js
│   └── package.json
├── scripts/                     # Scripts de utilidad
│   ├── install-production.sh   # Instalación completa
│   ├── deploy.sh               # Despliegue y reinicio
│   ├── dev.sh                  # Modo desarrollo
│   ├── status.sh               # Estado del sistema
│   └── configure-modem.sh      # Configuración modem
├── systemd/                     # Archivos systemd
│   ├── fpvcopilot-sky.service
│   └── fpvcopilot-sky.nginx
├── docs/                        # Documentación
│   ├── INSTALLATION.md
│   ├── USER_GUIDE.md
│   ├── DEVELOPER_GUIDE.md
│   └── BOARD_PROVIDER_SYSTEM.md
├── tests/                       # Tests
├── requirements.txt             # Dependencias Python
├── pyproject.toml              # Configuración Python
└── README.md
```

**Arquitectura de datos:**

```
Frontend (React)
    ↕ HTTP/WebSocket
Backend (FastAPI)
    ↕
Services (MAVLink, Video, etc.)
    ↕
Providers (abstracción de hardware)
    ↕
Hardware (FC, Camera, Modem, etc.)
```

---

## 🎨 Guías de estilo

### Python

Seguimos **PEP 8** con algunas convenciones adicionales:

```python
# ✅ Buenas prácticas
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/example", tags=["example"])

class RequestModel(BaseModel):
    """Request model with clear docstring"""
    field_name: str
    optional_field: Optional[int] = None

@router.get("/endpoint")
async def get_data() -> Dict[str, Any]:
    """
    Endpoint description

    Returns:
        Dict with status and data
    """
    try:
        result = await some_async_operation()
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

**Convenciones:**

- **Nombres**: `snake_case` para variables/funciones, `PascalCase` para clases
- **Docstrings**: Obligatorios en funciones públicas y endpoints
- **Type hints**: Usa siempre type hints en funciones
- **Async/await**: Usa `async def` para operaciones I/O
- **Error handling**: Captura excepciones específicas, usa `HTTPException` en APIs
- **Logging**: Usa `app.utils.logger` en lugar de `print()`

### JavaScript/React

Seguimos **ESLint** con configuración de Vite:

```jsx
// ✅ Buenas prácticas
import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useToast } from "../../contexts/ToastContext";
import api from "../../services/api";

const MyComponent = () => {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  // useCallback para funciones que se pasan como props
  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get("/api/endpoint");
      if (response.ok) {
        const result = await response.json();
        setData(result);
        showToast(t("success.dataLoaded"), "success");
      } else {
        showToast(t("errors.loadFailed"), "error");
      }
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      setLoading(false);
    }
  }, [t, showToast]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading) return <div className="loading">Loading...</div>;

  return (
    <div className="my-component">
      <h2>{t("component.title")}</h2>
      {data && <pre>{JSON.stringify(data, null, 2)}</pre>}
    </div>
  );
};

export default MyComponent;
```

**Convenciones:**

- **Nombres**: `camelCase` para variables/funciones, `PascalCase` para componentes
- **Hooks**: Usa hooks en lugar de clases
- **useCallback/useMemo**: Para optimizar re-renders
- **i18n**: SIEMPRE usa `t()` para textos, nunca hardcodees strings
- **API calls**: Usa `api.js` con timeout handling
- **Toast/Modal**: Usa contexts en lugar de alerts nativos
- **CSS**: Usa CSS Modules o clases BEM, evita inline styles

### Commits

Usamos **Conventional Commits** para mensajes claros:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**

- `feat`: Nueva funcionalidad
- `fix`: Corrección de bug
- `docs`: Cambios en documentación
- `style`: Formato, no afecta código (espacios, etc)
- `refactor`: Refactorización sin cambiar funcionalidad
- `perf`: Mejoras de rendimiento
- `test`: Añadir o corregir tests
- `chore`: Tareas de mantenimiento (build, deps, etc)

**Ejemplos:**

```bash
feat(video): añadir soporte para encoder hardware H.264
fix(mavlink): corregir deadlock en preferences save
docs(readme): actualizar diagrama de flujo de datos
refactor(modem): mover band presets a API endpoint
chore(deps): actualizar FastAPI a 0.115.0
```

---

## 🔄 Proceso de contribución

### 1. Fork y clone

```bash
# Fork el repositorio en GitHub, luego:
git clone https://github.com/TU-USUARIO/FPVCopilotSky.git
cd FPVCopilotSky
git remote add upstream https://github.com/REPO-ORIGINAL/FPVCopilotSky.git
```

### 2. Crea una rama

```bash
# Actualiza main
git checkout main
git pull upstream main

# Crea rama descriptiva
git checkout -b feat/descripcion-feature
# o
git checkout -b fix/descripcion-bug
```

### 3. Desarrolla y commitea

```bash
# Haz cambios, prueba localmente
./fpv                    # CLI: opción 3 "Start Development Mode"
# O manualmente: npm run dev en frontend/client

# Commit con mensaje descriptivo
git add .
git commit -m "feat(video): añadir soporte para cámara HDMI"
```

### 4. Mantén tu rama actualizada

```bash
# Sincroniza con upstream regularmente
git fetch upstream
git rebase upstream/main
```

### 5. Push y Pull Request

```bash
# Push a tu fork
git push origin feat/descripcion-feature

# Abre Pull Request en GitHub con:
# - Título descriptivo
# - Descripción de cambios
# - Screenshots si aplica
# - Referencia a issues relacionados
```

### 6. Code Review

- Responde a comentarios de forma constructiva
- Realiza cambios solicitados
- Push additional commits a la misma rama
- El PR se actualizará automáticamente

### 7. Merge

Una vez aprobado, tu PR será mergeado por un maintainer. ¡Gracias por tu contribución! 🎉

---

## 🧩 Sistema de Providers

FPV Copilot Sky usa un **sistema modular de providers** para abstraer hardware. Esto permite soportar diferentes modems, cámaras, encoders, etc., sin modificar el código core.

### Anatomía de un Provider

```python
# app/providers/base/modem_provider.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class ModemProvider(ABC):
    """Base class for modem providers"""

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Get modem connection status"""
        pass

    @abstractmethod
    def connect(self) -> Dict[str, Any]:
        """Connect modem"""
        pass

    @abstractmethod
    def disconnect(self) -> Dict[str, Any]:
        """Disconnect modem"""
        pass
```

### Implementar nuevo provider

```python
# app/providers/modem/mi_modem.py
from providers.base.modem_provider import ModemProvider

class MiModemProvider(ModemProvider):
    """Provider para Mi Modem XYZ"""

    def __init__(self):
        self.name = "mi_modem_xyz"
        self.available = self._check_availability()

    def _check_availability(self) -> bool:
        """Check if modem is connected"""
        # Lógica de detección
        return True

    def get_status(self) -> Dict[str, Any]:
        """Get status from modem"""
        return {
            "connected": True,
            "signal_strength": 85,
            "network_type": "4G"
        }

    def connect(self) -> Dict[str, Any]:
        """Connect modem"""
        # Implementación específica
        return {"success": True}

    def disconnect(self) -> Dict[str, Any]:
        """Disconnect modem"""
        return {"success": True}
```

### Registrar provider

```python
# app/providers/registry.py
from providers.modem.mi_modem import MiModemProvider

def init_modem_providers(registry):
    """Initialize all modem providers"""
    registry.register_modem_provider("mi_modem_xyz", MiModemProvider)
    # ... otros providers
```

**Documentación completa**: [docs/BOARD_PROVIDER_SYSTEM.md](docs/BOARD_PROVIDER_SYSTEM.md)

---

## 🌍 Internacionalización (i18n)

El proyecto soporta **español (ES)** e **inglés (EN)**. Todas las cadenas de texto deben ser traducidas.

### Backend (Python)

```python
# app/i18n/es.json
{
  "modem": {
    "connection_failed": "Conexión fallida",
    "signal_strength": "Fuerza de señal"
  }
}

# app/i18n/en.json
{
  "modem": {
    "connection_failed": "Connection failed",
    "signal_strength": "Signal strength"
  }
}

# Uso en código
from app.i18n import translate, get_language_from_request

@router.get("/status")
async def get_status(request: Request):
    lang = get_language_from_request(request)
    message = translate("modem.connection_failed", lang)
    return {"message": message}
```

### Frontend (React)

```javascript
// frontend/client/src/i18n/locales/es.json
{
  "modem": {
    "title": "Gestión de Modem",
    "signalStrength": "Fuerza de Señal"
  }
}

// frontend/client/src/i18n/locales/en.json
{
  "modem": {
    "title": "Modem Management",
    "signalStrength": "Signal Strength"
  }
}

// Uso en componente
import { useTranslation } from 'react-i18next'

const ModemView = () => {
  const { t } = useTranslation()

  return (
    <div>
      <h2>{t('modem.title')}</h2>
      <p>{t('modem.signalStrength')}</p>
    </div>
  )
}
```

### Añadir nuevo idioma

1. Crear `app/i18n/xx.json` (backend)
2. Crear `frontend/client/src/i18n/locales/xx.json` (frontend)
3. Registrar en `frontend/client/src/i18n/config.js`
4. Añadir selector de idioma en Header

---

## 🧪 Testing

### CI Pipeline

Los tests se ejecutan automáticamente en GitHub Actions en cada Pull Request (`.github/workflows/ci.yml`):

| Job              | Descripción                                 |
| ---------------- | ------------------------------------------- |
| `lint-backend`   | flake8, black, mypy                         |
| `lint-frontend`  | eslint, prettier                            |
| `test-backend`   | pytest con coverage                         |
| `test-frontend`  | vitest con coverage                         |
| `build-frontend` | Validar build de producción (bundle < 5 MB) |
| `security-scan`  | Trivy, Safety, npm audit                    |
| `summary`        | Resumen consolidado                         |

### Backend (Python/pytest)

```bash
# Ejecutar todos los tests
pytest

# Con coverage
pytest --cov=app --cov-report=html

# Ver reporte de coverage
open htmlcov/index.html

# Solo tests unitarios (excluir integration)
pytest -m "not integration"

# Tests rápidos (excluir slow)
pytest -m "not slow"
```

#### Markers

```python
@pytest.mark.asyncio        # Test asíncrono
@pytest.mark.slow           # Test lento (>1s)
@pytest.mark.integration    # Test de integración
@pytest.mark.unit           # Test unitario
@pytest.mark.hardware       # Requiere hardware físico (skip en CI)
```

#### Fixtures disponibles (`tests/conftest.py`)

| Fixture                                 | Descripción                      |
| --------------------------------------- | -------------------------------- |
| `mock_serial_port`                      | Mock de puerto serial            |
| `mock_mavlink_connection`               | Mock de conexión MAVLink         |
| `mock_hilink_modem`                     | Mock de modem Huawei HiLink      |
| `mock_gstreamer`                        | Mock de GStreamer pipeline       |
| `mock_subprocess`                       | Mock de comandos subprocess      |
| `temp_preferences`                      | Archivo temporal de preferencias |
| `mock_network_manager`                  | Mock de NetworkManager           |
| `mock_tailscale`                        | Mock de Tailscale CLI            |
| `sample_mavlink_messages`               | Mensajes MAVLink de ejemplo      |
| `mock_api_services`                     | Mock de servicios para API       |
| `serial_port` / `baudrate` / `tcp_port` | Valores por defecto para tests   |

#### Debugging pytest

```bash
pytest -v             # Salida detallada
pytest -s             # Mostrar prints
pytest -x             # Parar al primer fallo
pytest --pdb          # Debugger interactivo al fallar
pytest tests/test_preferences.py::TestPreferencesBasic::test_load  # Test específico
```

### Frontend (React/Vitest)

```bash
cd frontend/client

# Ejecutar tests
npm run test

# Con UI interactiva
npm run test:ui

# Con coverage
npm run test:coverage

# Watch mode
npm run test -- --watch

# Test específico
npm run test -- Header.test.jsx
```

**Ejemplo de test:**

```jsx
import { render, screen } from "@testing-library/react";
import Header from "../Header/Header";

test("renders header title", () => {
  render(<Header />);
  const title = screen.getByText(/FPV Copilot Sky/i);
  expect(title).toBeInTheDocument();
});
```

### Objetivos de coverage

- **Backend**: ≥ 20 % (configurado en `pyproject.toml` → `fail_under`)
- **Frontend**: ≥ 60 %

---

## 📚 Documentación

La documentación vive en `/docs` y sigue Markdown con GitHub Flavored Markdown.

### Estructura

- **INSTALLATION.md**: Guía de instalación paso a paso
- **USER_GUIDE.md**: Manual de usuario con screenshots
- **DEVELOPER_GUIDE.md**: Arquitectura técnica detallada

### Actualizar documentación

Cuando agregues features:

1. **README.md**: Si afecta funcionalidad principal
2. **INSTALLATION.md**: Si requiere nuevas dependencias
3. **USER_GUIDE.md**: Si afecta la UI o flujo de usuario
4. **DEVELOPER_GUIDE.md**: Si cambia arquitectura o APIs
5. **Docstrings**: Siempre documenta funciones y clases

### Diagramas ASCII

Usamos diagramas ASCII para flujos:

```
┌─────────┐      ┌─────────┐
│ Cliente │─────▶│ Servidor│
└─────────┘      └─────────┘
```

Herramientas recomendadas:

- [ASCIIFlow](https://asciiflow.com/)
- [Monodraw](https://monodraw.helftone.com/) (macOS)

---

## 🎯 Áreas de contribución recomendadas

### 🟢 Principiantes

- Corregir typos en documentación
- Mejorar traducciones (EN/ES)
- Añadir comentarios al código
- Reportar bugs con reproducibilidad clara
- Probar en nuevo hardware y documentar resultados

### 🟡 Intermedio

- Implementar nuevos providers (modem, cámara, encoder)
- Añadir features a la UI (gráficos, tooltips, etc.)
- Optimizar rendimiento (caching, lazy loading)
- Escribir tests unitarios
- Mejorar estilos CSS/responsiveness

### 🔴 Avanzado

- Refactorizar servicios complejos (MAVLink, GStreamer)
- Implementar nuevos protocolos (video, telemetría)
- Optimizar latencia end-to-end
- Setup CI/CD pipelines
- Arquitectura de escalabilidad

---

## 🏆 Reconocimientos

Todos los contribuidores serán reconocidos en:

- **README.md** - Sección de Contributors
- **CHANGELOG.md** - En cada release
- **GitHub** - Contributors graph

Las contribuciones significativas pueden resultar en:

- Rol de maintainer
- Acceso a hardware de desarrollo
- Créditos en releases

---

## 📞 Contacto

- **Issues**: [GitHub Issues](https://github.com/tu-usuario/FPVCopilotSky/issues)
- **Discussions**: [GitHub Discussions](https://github.com/tu-usuario/FPVCopilotSky/discussions)
- **Email**: amigache@hotmail.com

---

## 📖 Referencias

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [React Documentation](https://react.dev/)
- [MAVLink Documentation](https://mavlink.io/en/)
- [GStreamer Documentation](https://gstreamer.freedesktop.org/documentation/)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [PEP 8 Style Guide](https://peps.python.org/pep-0008/)

---

**¡Gracias por hacer FPV Copilot Sky mejor!** 🚁✨

Si tienes dudas sobre cómo contribuir, no dudes en abrir un issue con la etiqueta `question`. ¡Estamos aquí para ayudar!
