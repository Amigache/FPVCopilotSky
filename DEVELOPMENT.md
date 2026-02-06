# 🛠️ FPV Copilot Sky - Development Guide

Guía completa para desarrolladores que deseen contribuir o modificar FPV Copilot Sky.

## 📋 Tabla de Contenidos

- [Arquitectura del Sistema](#arquitectura-del-sistema)
- [Setup del Entorno de Desarrollo](#setup-del-entorno-de-desarrollo)
- [Estructura del Proyecto](#estructura-del-proyecto)
- [Convenciones de Código](#convenciones-de-código)
- [Testing](#testing)
- [Contribuir](#contribuir)

## 🏗️ Arquitectura del Sistema

### Stack Tecnológico

**Backend:**
- **Python 3.12+** con type hints
- **FastAPI** (framework ASGI moderno)
- **Uvicorn** (servidor ASGI)
- **PyMAVLink** (protocolo MAVLink)
- **GStreamer** (via PyGObject) para streaming
- **NetworkManager** (via D-Bus/CLI) para gestión de red

**Frontend:**
- **React 19** con Hooks
- **Vite** (build tool, HMR ultra-rápido)
- **React Router** para navegación
- **i18next** para internacionalización (ES/EN)
- **WebSocket** nativo para comunicación en tiempo real

### Arquitectura de Comunicación

```
┌─────────────────┐
│   React App     │
│   (Port 5173)   │  ← Desarrollo
│   (Port 80)     │  ← Producción
└────────┬────────┘
         │
         ├─ HTTP/REST ──→ /api/*
         └─ WebSocket ──→ /ws
                │
         ┌──────▼──────┐
         │  FastAPI    │
         │ (Port 8000) │
         └──────┬──────┘
                │
    ┌───────────┼───────────┐
    │           │           │
┌───▼────┐ ┌───▼─────┐ ┌───▼────┐
│MAVLink │ │GStreamer│ │Network │
│Bridge  │ │Service  │ │Service │
└───┬────┘ └────┬────┘ └───┬────┘
    │           │          │
┌───▼────┐ ┌───▼─────┐ ┌──▼────┐
│Serial  │ │Camera   │ │ WiFi  │
│ FC     │ │USB/CSI  │ │ 4G    │
└────────┘ └─────────┘ └───────┘
```

### Patrón de Servicio

Todos los servicios siguen un patrón singleton:

```python
# app/services/example_service.py
_service_instance = None

def get_service():
    global _service_instance
    if _service_instance is None:
        _service_instance = ExampleService()
    return _service_instance

class ExampleService:
    def __init__(self):
        # Inicialización
        pass
```

### WebSocket Broadcasting

Sistema pub/sub para actualizaciones en tiempo real:

```python
# Backend (server-side)
await websocket_manager.broadcast("event_name", {"data": "value"})

# Frontend (client-side)
useEffect(() => {
  if (messages.event_name) {
    // Procesar datos
  }
}, [messages.event_name])
```

## 🚀 Setup del Entorno de Desarrollo

### Requisitos Previos

- **Linux** (Debian/Ubuntu/Armbian)
- **Python 3.12+**
- **Node.js 18+** y **npm**
- **Git**
- **GStreamer** (libs de desarrollo)

### Instalación para Desarrollo

```bash
# 1. Clonar repositorio
git clone <repo-url> /opt/FPVCopilotSky
cd /opt/FPVCopilotSky

# 2. Ejecutar instalador base (instala dependencias del sistema)
bash install.sh

# 3. Activar entorno virtual
source venv/bin/activate

# 4. Instalar dependencias de desarrollo
pip install pytest pytest-asyncio black flake8 mypy

# 5. Instalar pre-commit hooks (opcional)
pip install pre-commit
pre-commit install
```

### Modo Desarrollo

**Opción A: Script Automático (Recomendado)**

```bash
bash scripts/dev.sh
```

Esto inicia:
- Backend en `http://localhost:8000` (hot reload)
- Frontend en `http://localhost:5173` (HMR)

**Opción B: Manual**

Terminal 1 - Backend:
```bash
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Terminal 2 - Frontend:
```bash
cd frontend/client
npm run dev
```

### Variables de Entorno

Crear archivo `.env` en la raíz (opcional):

```ini
# Backend
LOG_LEVEL=DEBUG
ENABLE_CORS=true

# API
API_PREFIX=/api
```

## 📁 Estructura del Proyecto

```
FPVCopilotSky/
├── app/                          # Backend FastAPI
│   ├── main.py                   # Punto de entrada, configuración ASGI
│   ├── config.py                 # Configuración centralizada
│   ├── api/                      # API REST
│   │   ├── __init__.py
│   │   └── routes/               # Endpoints por módulo
│   │       ├── system.py         # Sistema (health, status)
│   │       ├── mavlink.py        # MAVLink (conexión, telemetría)
│   │       ├── router.py         # MAVLink Router (outputs)
│   │       ├── video.py          # Video streaming
│   │       ├── network.py        # Gestión de red
│   │       ├── status.py         # Estado del sistema
│   │       └── vpn.py            # VPN (Tailscale)
│   ├── services/                 # Lógica de negocio (Singleton)
│   │   ├── mavlink_bridge.py    # Puente serial ↔ UDP/TCP
│   │   ├── mavlink_router.py    # Router multi-output
│   │   ├── serial_detector.py   # Auto-detección FC
│   │   ├── gstreamer_service.py # Pipeline GStreamer
│   │   ├── video_config.py      # Detección cámaras
│   │   ├── network_service.py   # NetworkManager wrapper
│   │   ├── hilink_service.py    # Gestión modems HiLink
│   │   ├── vpn_service.py       # VPN provider abstraction
│   │   ├── preferences.py       # Persistencia configuración
│   │   ├── system_service.py    # Info del sistema
│   │   └── websocket_manager.py # Broadcasting WebSocket
│   └── utils/
│       └── logger.py             # Logging configurado
│
├── frontend/client/              # Frontend React
│   ├── src/
│   │   ├── main.jsx              # Entry point
│   │   ├── App.jsx               # App principal
│   │   ├── components/           # Componentes React
│   │   │   ├── Header/           # Header con badges
│   │   │   ├── TabBar/           # Navegación tabs
│   │   │   ├── Content/          # Layout content
│   │   │   ├── Badge/            # Badge de estado
│   │   │   ├── Modal/            # Sistema de modales
│   │   │   ├── Toast/            # Notificaciones
│   │   │   ├── PeerSelector/     # Selector IPs VPN
│   │   │   └── Pages/            # Vistas principales
│   │   │       ├── DashboardView.jsx
│   │   │       ├── FlightControllerView.jsx
│   │   │       ├── TelemetryView.jsx
│   │   │       ├── VideoView.jsx
│   │   │       ├── ModemView.jsx
│   │   │       ├── NetworkView.jsx
│   │   │       ├── VPNView.jsx
│   │   │       ├── SystemView.jsx
│   │   │       └── StatusView.jsx
│   │   ├── contexts/             # React Contexts
│   │   │   ├── WebSocketContext.jsx  # WebSocket global
│   │   │   ├── ToastContext.jsx      # Sistema toast
│   │   │   └── ModalContext.jsx      # Sistema modal
│   │   ├── services/
│   │   │   └── api.js            # Cliente API fetch
│   │   └── i18n/                 # Internacionalización
│   │       ├── config.js         # Configuración i18next
│   │       └── locales/
│   │           ├── en.json       # Traducciones inglés
│   │           └── es.json       # Traducciones español
│   ├── package.json
│   ├── vite.config.js            # Config Vite (proxy dev)
│   └── index.html
│
├── scripts/                      # Utilidades
│   ├── install.sh                # Instalación inicial
│   ├── deploy.sh                 # Deploy producción
│   ├── dev.sh                    # Modo desarrollo
│   ├── install-production.sh    # Setup producción (nginx)
│   ├── status.sh                 # Check status completo
│   ├── fix-nginx.sh              # Fix config nginx
│   ├── configure-modem.sh        # Configurar modems 4G
│   └── setup-tailscale-sudoers.sh # Permisos Tailscale
│
├── systemd/                      # Configuración systemd
│   ├── fpvcopilot-sky.service    # Unit file servicio
│   └── fpvcopilot-sky.nginx      # Config nginx
│
├── docs/                         # Documentación
│   ├── PRODUCTION.md             # Guía producción
│   └── VPN_INTEGRATION.md        # Detalles VPN
│
├── tests/                        # Tests unitarios
│   └── test_mavlink_bridge.py
│
├── preferences.json              # Config usuario (auto-generado, gitignored)
├── requirements.txt              # Deps Python
├── pyproject.toml                # Metadata proyecto
├── .gitignore
└── README.md                     # Documentación usuario
```

## 🎨 Convenciones de Código

### Python (Backend)

**Style Guide:** PEP 8 + Type Hints

```python
# Usar type hints siempre
from typing import Dict, List, Optional

def get_status() -> Dict[str, Any]:
    """
    Get current status.
    
    Returns:
        Dict with status information
    """
    return {"status": "ok"}

# Docstrings para funciones públicas
def process_data(data: bytes) -> Optional[str]:
    """Process incoming data packet."""
    pass

# Nombres descriptivos
is_connected = True  # ✅
conn = True          # ❌
```

**Async/Await:**

```python
# Usar async para I/O
async def fetch_data():
    # Operaciones I/O
    pass

# Sync solo para operaciones CPU-bound
def calculate():
    # Cálculos puros
    pass
```

### JavaScript/React

**Style Guide:** Airbnb + Hooks moderno

```javascript
// Componentes funcionales con hooks
export const MyComponent = ({ prop1, prop2 }) => {
  const [state, setState] = useState(null)
  
  useEffect(() => {
    // Side effects
  }, [dependencies])
  
  return <div>{/* JSX */}</div>
}

// Nombrar handlers con handle*
const handleClick = () => {}
const handleChange = (e) => {}

// Nombrar callbacks con on*
<Button onClick={onSubmit} />
```

**Estructura de Componente:**

```javascript
import './Component.css'
import { useState, useEffect } from 'react'

const Component = () => {
  // 1. Hooks de estado
  const [data, setData] = useState(null)
  
  // 2. Hooks de efecto
  useEffect(() => {
    // ...
  }, [])
  
  // 3. Handlers
  const handleEvent = () => {}
  
  // 4. Render helpers
  const renderItem = (item) => {}
  
  // 5. Return JSX
  return <div>...</div>
}

export default Component
```

## 🧪 Testing

### Backend Tests

```bash
# Ejecutar todos los tests
pytest

# Con coverage
pytest --cov=app

# Test específico
pytest tests/test_mavlink_bridge.py -v
```

Ejemplo de test:

```python
import pytest
from app.services.mavlink_bridge import MAVLinkBridge

@pytest.mark.asyncio
async def test_connection():
    bridge = MAVLinkBridge(None, None)
    result = bridge.connect("/dev/ttyUSB0", 115200)
    assert result["success"] == True
```

### Frontend Tests

```bash
cd frontend/client

# Tests unitarios (si existen)
npm test

# Build test
npm run build
```

## 🔄 Workflow de Desarrollo

### 1. Crear Feature Branch

```bash
git checkout -b feature/nueva-funcionalidad
```

### 2. Desarrollo + Commit

```bash
# Hacer cambios
git add .
git commit -m "feat: descripción corta de la feature"
```

**Convención de commits** (Conventional Commits):
- `feat`: nueva funcionalidad
- `fix`: corrección de bug
- `docs`: cambios en documentación
- `style`: formato, sin cambios de código
- `refactor`: refactorización de código
- `test`: añadir/modificar tests
- `chore`: tareas de mantenimiento

### 3. Testing Local

```bash
# Backend
pytest

# Verificar que el servicio arranca
bash scripts/dev.sh

# Verificar producción
bash scripts/deploy.sh
sudo journalctl -u fpvcopilot-sky -f
```

### 4. Pull Request

```bash
git push origin feature/nueva-funcionalidad
# Crear PR en GitHub
```

## 📦 Desplegar Cambios en Producción

```bash
# 1. Pull latest
git pull origin main

# 2. Deploy
bash scripts/deploy.sh

# 3. Verificar
bash scripts/status.sh
sudo journalctl -u fpvcopilot-sky -f
```

## 🐛 Debugging

### Backend

```bash
# Logs en tiempo real
sudo journalctl -u fpvcopilot-sky -f

# Ver últimas 100 líneas
sudo journalctl -u fpvcopilot-sky -n 100

# Buscar errores
sudo journalctl -u fpvcopilot-sky | grep ERROR

# Modo debug (agregar en main.py)
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Frontend

```javascript
// Console logs
console.log('Data:', data)

// React DevTools (instalar extensión de navegador)
// Ver component tree, props, state

// Network tab para ver API calls
// WebSocket messages en Network > WS
```

### GStreamer

```bash
# Ver dispositivos de video
v4l2-ctl --list-devices

# Info de cámara
v4l2-ctl -d /dev/video0 --all

# Test pipeline manualmente
gst-launch-1.0 v4l2src device=/dev/video0 ! jpegdec ! videoconvert ! jpegenc ! rtpjpegpay ! udpsink host=192.168.1.100 port=5600

# Ver debug GST
export GST_DEBUG=3
```

## 📚 Recursos Útiles

- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [React Docs](https://react.dev/)
- [GStreamer Docs](https://gstreamer.freedesktop.org/documentation/)
- [PyMAVLink](https://github.com/ArduPilot/pymavlink)
- [MAVLink Protocol](https://mavlink.io/)

## 🤝 Contribuir

1. Fork el proyecto
2. Crear feature branch
3. Hacer commits con mensajes claros
4. Push al branch
5. Crear Pull Request

### Guidelines

- Código limpio y documentado
- Tests para nuevas features
- Actualizar documentación si es necesario
- Seguir convenciones de estilo

---

**¿Preguntas?** Abre un issue o contacta al equipo de desarrollo.
