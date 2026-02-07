# 🛠️ Guía de Desarrollo

Arquitectura, stack tecnológico, estructura del proyecto, cómo contribuir y cómo extender FPV Copilot Sky con nuevos proveedores.

---

## 1. Stack tecnológico

| Capa | Tecnología | Versión |
|------|-----------|---------|
| **Backend** | Python, FastAPI, Uvicorn | 3.12+, 0.109+ |
| **Telemetría** | PyMAVLink, pyserial | 2.4+, 3.5+ |
| **Video** | GStreamer (PyGObject) | 1.20+ |
| **Modem** | huawei-lte-api | 1.9+ |
| **Frontend** | React, Vite, i18next | 19, 7.x |
| **Servidor web** | Nginx | 1.18+ |
| **VPN** | Tailscale | 1.50+ |
| **Gestión de red** | NetworkManager | — |
| **Servicio** | systemd | — |

### Dependencias Python (`requirements.txt`)

```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
pymavlink>=2.4.41
pyserial>=3.5
python-multipart>=0.0.6
pydantic>=2.5.0
huawei-lte-api>=1.9.0
```

---

## 2. Arquitectura

```
                    ┌─────────────┐
                    │  Navegador  │
                    └──────┬──────┘
                           │ HTTP / WebSocket
                    ┌──────▼──────┐
                    │   Nginx:80  │  Proxy inverso + estáticos
                    └──────┬──────┘
              ┌────────────┼────────────┐
              │ /api/*     │ /ws        │ /*
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ FastAPI  │ │WebSocket │ │ React    │
        │  :8000   │ │ Manager  │ │ SPA      │
        └────┬─────┘ └────┬─────┘ └──────────┘
             │            │
     ┌───────┼────────────┼───────────┐
     │       │            │           │
     ▼       ▼            ▼           ▼
 ┌────────┐ ┌──────┐ ┌────────┐ ┌─────────┐
 │MAVLink │ │Video │ │Provider│ │Services │
 │Bridge  │ │GStr. │ │Registry│ │Prefs... │
 └────────┘ └──────┘ └───┬────┘ └─────────┘
                          │
            ┌─────────────┼─────────────┐
            ▼             ▼             ▼
      ┌──────────┐ ┌──────────┐ ┌──────────┐
      │  Modem   │ │   VPN    │ │ Network  │
      │Providers │ │Providers │ │Providers │
      └──────────┘ └──────────┘ └──────────┘
```

### Patrón central: Provider Registry

El sistema usa una **arquitectura agnóstica de hardware** basada en proveedores abstractos:

- **`ModemProvider`** → HuaweiE3372hProvider, USBDongleProvider, RouterProvider…
- **`VPNProvider`** → TailscaleProvider (futuro: ZeroTier, WireGuard…)
- **`NetworkInterface`** → EthernetInterface, WiFiInterface, VPNInterface, ModemInterface

Todos los proveedores se registran en `ProviderRegistry` al arrancar y se acceden desde cualquier punto:

```python
from providers import get_provider_registry

registry = get_provider_registry()
modem = registry.get_modem_provider('huawei_e3372h')
vpn = registry.get_vpn_provider('tailscale')
```

### Comunicación en tiempo real

El backend emite datos periódicamente por **WebSocket** a todos los clientes conectados:

| Tipo de mensaje | Intervalo | Datos |
|----------------|-----------|-------|
| `telemetry` | 1s | GPS, actitud, batería, modo |
| `router_status` | 2s | Salidas MAVLink |
| `video_status` | 2s | Estado del stream |
| `system_resources` | 3s | CPU, RAM |
| `status` | 5s | Health check |
| `system_services` | 5s | Estado de servicios |
| `vpn_status` | 10s | Conexión Tailscale |
| `modem_status` | 10s | Señal, tráfico, dispositivo |

El frontend consume estos mensajes con el hook `useWebSocket()`:

```jsx
const { messages } = useWebSocket()
const modemData = messages.modem_status  // Se actualiza automáticamente
```

---

## 3. Estructura del proyecto

```
FPVCopilotSky/
├── README.md                    # Presentación del proyecto
├── requirements.txt             # Dependencias Python
├── pyproject.toml               # Metadatos del proyecto
├── install.sh                   # Instalador de dependencias del sistema
├── preferences.json             # Preferencias persistentes del usuario
│
├── app/                         # Backend (FastAPI)
│   ├── main.py                  # App FastAPI, WebSocket, broadcast loop
│   ├── config.py                # Configuración
│   │
│   ├── api/routes/              # Endpoints REST
│   │   ├── mavlink.py           # Conexión y telemetría MAVLink
│   │   ├── video.py             # Control de streaming
│   │   ├── network.py           # Red, WiFi, modem (~35 endpoints)
│   │   ├── vpn.py               # VPN Tailscale (~7 endpoints)
│   │   ├── system.py            # CPU, RAM, servicios
│   │   ├── status.py            # Health check
│   │   ├── router.py            # Salidas MAVLink
│   │   └── modem.py             # (alias, redirige a network.py)
│   │
│   ├── providers/               # Proveedores de hardware (patrón abstracto)
│   │   ├── registry.py          # ProviderRegistry (singleton)
│   │   ├── base/                # Clases abstractas
│   │   │   ├── modem_provider.py
│   │   │   ├── vpn_provider.py
│   │   │   └── network_interface.py
│   │   ├── modem/               # Implementaciones de modem
│   │   │   ├── hilink/huawei.py # HuaweiE3372hProvider (~1500 líneas)
│   │   │   ├── usb_dongle.py
│   │   │   └── router.py
│   │   ├── vpn/
│   │   │   └── tailscale.py     # TailscaleProvider
│   │   └── network/
│   │       ├── ethernet.py
│   │       ├── wifi.py
│   │       ├── vpn_interface.py
│   │       └── modem_interface.py
│   │
│   ├── services/                # Servicios core (no hardware-specific)
│   │   ├── mavlink_bridge.py    # Bridge serie ↔ red
│   │   ├── mavlink_router.py    # Gestión de salidas
│   │   ├── gstreamer_service.py # Pipeline de video
│   │   ├── video_config.py      # Configuración de video
│   │   ├── video_stream_info.py # MAVLink VIDEO_STREAM_INFORMATION
│   │   ├── preferences.py       # Persistencia de preferencias
│   │   ├── system_service.py    # Info del sistema
│   │   ├── serial_detector.py   # Detección de puertos serie
│   │   └── websocket_manager.py # Broadcast WebSocket
│   │
│   └── utils/
│       └── logger.py
│
├── frontend/client/             # Frontend (React + Vite)
│   ├── src/
│   │   ├── App.jsx              # Router principal
│   │   ├── main.jsx             # Punto de entrada
│   │   ├── components/
│   │   │   ├── Header/          # Barra superior con badges
│   │   │   ├── Sidebar/         # Navegación lateral
│   │   │   ├── Pages/           # Vistas: Modem, VPN, Video, Network…
│   │   │   ├── PeerSelector/    # Selector de peers VPN
│   │   │   └── Badge/, Modal/, Toast/
│   │   ├── contexts/
│   │   │   ├── WebSocketContext.jsx  # Hook useWebSocket()
│   │   │   ├── ToastContext.jsx
│   │   │   └── ModalContext.jsx
│   │   ├── services/
│   │   │   └── api.js           # Cliente HTTP + helpers
│   │   └── i18n/                # Traducciones ES/EN
│   └── vite.config.js
│
├── scripts/                     # Scripts de operación
│   ├── deploy.sh                # Compilar + desplegar
│   ├── dev.sh                   # Desarrollo con hot-reload
│   ├── install-production.sh    # Configurar nginx + systemd
│   ├── status.sh                # Diagnóstico completo
│   ├── configure-modem.sh       # Configurar modem USB
│   ├── fix-nginx.sh             # Arreglar configuración nginx
│   ├── setup-system-sudoers.sh  # Permisos sudo sistema
│   └── setup-tailscale-sudoers.sh # Permisos sudo Tailscale
│
├── systemd/
│   ├── fpvcopilot-sky.service   # Servicio systemd
│   └── fpvcopilot-sky.nginx     # Configuración nginx
│
├── tests/
│   └── test_mavlink_bridge.py
│
└── docs/                        # Documentación (wiki)
    ├── INDEX.md
    ├── INSTALLATION.md
    ├── USER_GUIDE.md
    └── DEVELOPER_GUIDE.md
```

---

## 4. Entorno de desarrollo

### Setup inicial

```bash
cd /opt/FPVCopilotSky
bash install.sh                          # Instalar todo (primera vez)
source venv/bin/activate                 # Activar entorno virtual
```

### Modo desarrollo

```bash
bash scripts/dev.sh
```

Esto arranca:

- **Backend**: `uvicorn app.main:app --reload --port 8000` (hot-reload Python)
- **Frontend**: `npm run dev` en `frontend/client/` (Vite HMR en `:5173`)

### Build y deploy manual

```bash
cd frontend/client && npm run build      # Compilar React
bash scripts/deploy.sh                   # Desplegar todo
```

### Tests

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

---

## 5. Convenciones de código

### Python (Backend)

- **PEP 8** con type hints
- **Async/await** para operaciones de I/O
- `ThreadPoolExecutor` (`loop.run_in_executor`) para llamadas síncronas bloqueantes desde rutas async
- Logging con `logging.getLogger(__name__)`
- Docstrings en todas las funciones públicas
- Imports absolutos: `from providers import get_provider_registry`

### JavaScript/React (Frontend)

- **Componentes funcionales** con hooks (no clases)
- **useState**, **useEffect**, **useCallback**, **useRef**
- **useWebSocket()** para datos en tiempo real (nunca polling para datos que ya se emiten por WS)
- **i18next** para todas las cadenas de texto (`t('clave')`)
- **api.get()** / **api.post()** para llamadas HTTP
- CSS Modules (un `.css` por componente)

### Commits

Conventional Commits:

```
feat: add flight session recording
fix: VPN auth URL not returned on first connect
docs: rewrite installation guide
refactor: remove legacy network service
```

---

## 6. Cómo añadir un nuevo proveedor

### Ejemplo: Añadir un proveedor VPN (ZeroTier)

#### 6.1 Crear la implementación

```python
# app/providers/vpn/zerotier.py
from ..base import VPNProvider

class ZeroTierProvider(VPNProvider):
    def __init__(self):
        super().__init__()
        self.name = "zerotier"
        self.display_name = "ZeroTier"

    def is_installed(self) -> bool:
        # Verificar si zerotier-cli está disponible
        ...

    def get_status(self) -> dict:
        # Obtener estado de conexión
        ...

    def connect(self) -> dict:
        # Unirse a la red
        ...

    def disconnect(self) -> dict:
        # Salir de la red
        ...

    def get_peers(self) -> list:
        # Listar peers del network
        ...
```

#### 6.2 Registrar en main.py

```python
# En la función de inicialización de providers
from providers.vpn.zerotier import ZeroTierProvider

zerotier = ZeroTierProvider()
if zerotier.is_installed():
    registry.register_vpn_provider(zerotier)
```

#### 6.3 Listo

Los endpoints `/api/vpn/*` ya funcionan con cualquier proveedor registrado. El frontend lo detecta automáticamente en el selector de proveedores.

### Ejemplo: Añadir un proveedor de modem

```python
# app/providers/modem/tplink.py
from ..base import ModemProvider

class TPLinkM7200Provider(ModemProvider):
    def __init__(self):
        super().__init__()
        self.name = "tplink_m7200"
        self.display_name = "TP-Link M7200"

    def is_available(self) -> bool:
        # Verificar si el router responde en su IP
        ...

    def get_signal_info(self) -> dict:
        # Leer señal via API del router
        ...

    def get_device_info(self) -> dict:
        # Info del dispositivo
        ...

    # ... implementar los métodos que necesites
```

### Checklist para nuevos proveedores

- [ ] Crear clase en `app/providers/<tipo>/<nombre>.py`
- [ ] Heredar de la clase base apropiada (`VPNProvider`, `ModemProvider`, `NetworkInterface`)
- [ ] Implementar todos los métodos abstractos
- [ ] Registrar en `app/main.py` dentro de `init_provider_registry()`
- [ ] Los endpoints REST funcionan automáticamente
- [ ] Probar con `curl` los endpoints relevantes

---

## 7. API REST — Referencia rápida

### Telemetría / MAVLink

```
GET  /api/mavlink/status              # Estado de conexión
POST /api/mavlink/connect             # Conectar al FC
POST /api/mavlink/disconnect          # Desconectar
GET  /api/mavlink/telemetry           # Datos de telemetría
```

### Video

```
GET  /api/video/status                # Estado del stream
POST /api/video/start                 # Iniciar streaming
POST /api/video/stop                  # Detener streaming
POST /api/video/configure             # Aplicar configuración
GET  /api/video/cameras               # Cámaras detectadas
```

### Red / Modem

```
GET  /api/network/interfaces          # Interfaces de red
GET  /api/network/modem/status        # Estado del modem
GET  /api/network/modem/status/enhanced  # Estado completo (señal+dispositivo+tráfico+banda)
POST /api/network/modem/band          # Cambiar banda LTE
POST /api/network/modem/mode          # Cambiar modo de red
GET  /api/network/modem/latency       # Test de latencia
GET  /api/network/modem/video-quality # Evaluación de calidad
POST /api/network/modem/video-mode/enable   # Activar modo video
POST /api/network/modem/video-mode/disable  # Desactivar modo video
POST /api/network/modem/flight-session/start  # Iniciar sesión de vuelo
POST /api/network/modem/flight-session/stop   # Detener sesión de vuelo
GET  /api/network/wifi/scan           # Escanear redes WiFi
POST /api/network/wifi/connect        # Conectar a WiFi
```

### VPN

```
GET  /api/vpn/providers               # Proveedores disponibles
GET  /api/vpn/status                  # Estado de conexión
GET  /api/vpn/peers                   # Nodos de la red
POST /api/vpn/connect                 # Conectar
POST /api/vpn/disconnect              # Desconectar
POST /api/vpn/logout                  # Cerrar sesión
```

### Sistema

```
GET  /api/status/health               # Health check
GET  /api/system/resources            # CPU, RAM
GET  /api/system/services             # Estado de servicios
```

---

## 8. WebSocket

Endpoint: `ws://<host>/ws`

### Protocolo

Mensajes JSON con formato:

```json
{
  "type": "modem_status",
  "data": { ... }
}
```

### Consumir desde el frontend

```jsx
import { useWebSocket } from '../../contexts/WebSocketContext'

const MyComponent = () => {
  const { messages, isConnected } = useWebSocket()

  // messages.modem_status se actualiza automáticamente cada 10s
  // messages.telemetry se actualiza cada 1s
  // messages.vpn_status se actualiza cada 10s
  // etc.

  return <div>{messages.modem_status?.signal?.rssi}</div>
}
```

---

## 9. Debugging

### Backend

```bash
# Logs en tiempo real
sudo journalctl -u fpvcopilot-sky -f

# Logs con nivel debug
sudo journalctl -u fpvcopilot-sky -f --output=cat

# Probar endpoint específico
curl -s http://localhost:8000/api/network/modem/status/enhanced | python3 -m json.tool
```

### Frontend

- DevTools del navegador → Console para errores JS
- DevTools → Network → WS para ver mensajes WebSocket
- `npm run dev` para desarrollo con hot-reload y source maps

### GStreamer

```bash
# Listar cámaras
v4l2-ctl --list-devices

# Probar pipeline manualmente
GST_DEBUG=3 gst-launch-1.0 v4l2src device=/dev/video0 ! videoconvert ! autovideosink
```

### Red

```bash
ip route show                          # Tabla de rutas
ip addr show                           # Interfaces con IPs
nmcli device status                    # Estado NetworkManager
ping -c 3 192.168.8.1                  # Test modem HiLink
tailscale status                       # Estado Tailscale
```

---

[← Índice](INDEX.md) · [Anterior: Guía de Usuario](USER_GUIDE.md)
