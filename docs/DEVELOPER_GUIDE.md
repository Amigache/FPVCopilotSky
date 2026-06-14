# 🛠️ Guía de Desarrollo

Arquitectura, stack tecnológico, estructura del proyecto, cómo contribuir y cómo extender FPV Copilot Sky con nuevos proveedores.

---

## 1. Stack tecnológico

| Capa               | Tecnología               | Versión       |
| ------------------ | ------------------------ | ------------- |
| **Backend**        | Python, FastAPI, Uvicorn | 3.12+, 0.109+ |
| **Telemetría**     | PyMAVLink, pyserial      | 2.4+, 3.5+    |
| **Video**          | GStreamer (PyGObject)    | 1.20+         |
| **Modem**          | huawei-lte-api           | 1.9+          |
| **Frontend**       | React, Vite, i18next     | 19, 7.x       |
| **Servidor web**   | Nginx                    | 1.18+         |
| **VPN**            | Tailscale                | 1.50+         |
| **Gestión de red** | NetworkManager           | —             |
| **Servicio**       | systemd                  | —             |

### Dependencias Python (`requirements.txt`)

```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
pymavlink>=2.4.41
pyserial>=3.5
python-multipart>=0.0.6
pydantic>=2.5.0
huawei-lte-api>=1.9.0
PyGObject>=3.42.0

# WebRTC support
aiortc>=1.5.0        # Python WebRTC implementation
av>=10.0.0           # PyAV - Python bindings for FFmpeg

# Testing
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-cov>=4.1.0
pytest-mock>=3.12.0
httpx>=0.25.0
psutil>=5.9.0
```

**Paquetes críticos**:

- `fastapi` - Framework web backend
- `pymavlink` - Comunicación MAVLink con drones
- `pyserial` - Comunicación serie (UART)
- `PyGObject` - Bindings Python para GStreamer
- `aiortc` - Implementación WebRTC para Python
- `av` (PyAV) - Bindings Python para FFmpeg (procesamiento multimedia)
- `huawei-lte-api` - API para modems Huawei HiLink

**Dependencias del sistema requeridas**:

- `libavcodec-dev`, `libavformat-dev`, `libavutil-dev` - Para PyAV
- `libsrtp2-dev`, `libopus-dev`, `libvpx-dev` - Para aiortc
- `gstreamer1.0-*`, `gir1.2-gstreamer-1.0` - Para PyGObject

### Dependencias Frontend (`package.json`)

```json
{
  "dependencies": {
    "framer-motion": "^12.33.0",
    "i18next": "^25.8.1",
    "i18next-browser-languagedetector": "^8.2.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-i18next": "^16.5.4"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^5.1.1",
    "vite": "^7.2.4",
    "eslint": "^9.39.1",
    "prettier": "^3.1.0",
    "vitest": "^1.0.0"
  }
}
```

**Frameworks**:

- React 18.3+ con hooks
- Vite 7.x como bundler (HMR ultrarrápido)
- i18next para internacionalización (ES/EN)

**Compilación**:

```bash
cd frontend/client
npm install
npm run build  # output: dist/
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

| Tipo de mensaje    | Intervalo | Datos                       |
| ------------------ | --------- | --------------------------- |
| `telemetry`        | 1s        | GPS, actitud, batería, modo |
| `router_status`    | 2s        | Salidas MAVLink             |
| `video_status`     | 2s        | Estado del stream           |
| `system_resources` | 3s        | CPU, RAM                    |
| `status`           | 5s        | Health check                |
| `system_services`  | 5s        | Estado de servicios         |
| `vpn_status`       | 10s       | Conexión Tailscale          |
| `modem_status`     | 10s       | Señal, tráfico, dispositivo |

El frontend consume estos mensajes con el hook `useWebSocket()`:

```jsx
const { messages } = useWebSocket();
const modemData = messages.modem_status; // Se actualiza automáticamente
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
│   │   ├── network/             # Red, WiFi, modem (modular, ~1700 líneas)
│   │   │   ├── __init__.py      # Router principal (44 líneas)
│   │   │   ├── common.py        # Utilidades compartidas (105 líneas)
│   │   │   ├── status.py        # Estado y dashboard (404 líneas)
│   │   │   ├── flight_mode.py   # Optimización FPV (275 líneas)
│   │   │   ├── flight_session.py # Grabación de vuelo (150 líneas)
│   │   │   ├── latency.py       # Monitoreo de latencia (187 líneas)
│   │   │   ├── failover.py      # Auto-failover (174 líneas)
│   │   │   ├── dns.py           # Caché DNS (122 líneas)
│   │   │   ├── bridge.py        # Network-video bridge (105 líneas)
│   │   │   └── mptcp.py         # Multi-Path TCP (125 líneas)
│   │   ├── vpn.py               # VPN Tailscale (~7 endpoints)
│   │   ├── system.py            # CPU, RAM, servicios
│   │   ├── status.py            # Health check
│   │   ├── router.py            # Salidas MAVLink
│   │   ├── modem.py             # Modems 4G provider-based
│   │   └── network_interface.py # Gestión de interfaces de red
│   │
│   ├── providers/               # Proveedores de hardware (patrón abstracto)
│   │   ├── registry.py          # ProviderRegistry (singleton)
│   │   ├── base/                # Clases abstractas
│   │   │   ├── modem_provider.py
│   │   │   ├── vpn_provider.py
│   │   │   ├── network_interface.py
│   │   │   ├── video_source_provider.py     # [NUEVO] Para fuentes de video
│   │   │   └── video_encoder_provider.py    # [NUEVO] Para codificadores
│   │   ├── board/               # [NUEVO] Proveedores de board/plataforma
│   │   │   ├── board_provider.py           # Clase abstracta BoardProvider
│   │   │   ├── board_registry.py           # Singleton con auto-discovery
│   │   │   ├── board_definitions.py        # Enums y DTOs
│   │   │   ├── detected_board.py           # DTO resultante
│   │   │   └── implementations/
│   │   │       └── radxa/zero.py           # RadxaZeroProvider (Amlogic S905Y2)
│   │   ├── modem/               # Implementaciones de modem
│   │   │   ├── hilink/huawei.py # HuaweiE3372hProvider (~1500 líneas)
│   │   │   ├── usb_dongle.py
│   │   │   └── router.py
│   │   ├── vpn/
│   │   │   └── tailscale.py     # TailscaleProvider
│   │   ├── network/
│   │   │   ├── ethernet.py
│   │   │   ├── wifi.py
│   │   │   ├── vpn_interface.py
│   │   │   └── modem_interface.py
│   │   ├── video_source/        # [NUEVO] Proveedores de fuentes de video
│   │   │   ├── v4l2_camera.py           # V4L2CameraSource (USB, CSI)
│   │   │   ├── libcamera_source.py      # LibCameraSource (Raspberry Pi)
│   │   │   ├── hdmi_capture.py          # HDMICaptureSource (captura HDMI)
│   │   │   ├── network_stream.py        # NetworkStreamSource (RTSP, HLS)
│   │   │   ├── __init__.py
│   │   │   └── video_source_registry_init.py
│   │   └── video/               # [NUEVO] Proveedores de codificadores
│   │       ├── mjpeg_encoder.py         # MJPEGEncoder
│   │       ├── x264_encoder.py          # X264Encoder (H.264 software)
│   │       ├── openh264_encoder.py      # OpenH264Encoder (deshabilitado)
│   │       ├── hardware_h264_encoder.py # HardwareH264Encoder (SoC)
│   │       ├── __init__.py
│   │       └── video_registry_init.py
│   │
│   ├── services/                # Servicios core (no hardware-specific)
│   │   ├── mavlink_bridge.py    # Bridge serie ↔ red
│   │   ├── mavlink_router.py    # Gestión de salidas
│   │   ├── gstreamer_service.py # Pipeline de video
│   │   ├── cache_service.py     # Caché centralizado thread-safe
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
│   │   │   ├── TabBar/          # Navegación por pestañas
│   │   │   ├── Toggle/          # Toggle switch reutilizable
│   │   │   ├── PeerSelector/    # Selector de peers VPN
│   │   │   ├── Badge/, Modal/, Toast/
│   │   │   └── Pages/           # Vistas principales
│   │   │       ├── VideoView.jsx          # Orquestador de video
│   │   │       ├── video/                 # Sub-componentes de video
│   │   │       │   ├── videoConstants.js   # Constantes, rangos, helpers
│   │   │       │   ├── StatusBanner.jsx    # Estado: emitiendo/detenido/error
│   │   │       │   ├── VideoSourceCard.jsx # Cámara, resolución, FPS
│   │   │       │   ├── EncodingConfigCard.jsx # Codec, bitrate, calidad
│   │   │       │   ├── NetworkSettingsCard.jsx # Modo, IP, puerto, RTSP
│   │   │       │   ├── StreamControlCard.jsx   # Iniciar/detener/reiniciar
│   │   │       │   ├── PipelineCard.jsx   # Pipeline GStreamer visible
│   │   │       │   └── StatsCard.jsx      # FPS, bitrate, uptime en vivo
│   │   │       └── Modem, VPN, Network, Status, System…
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
│   ├── setup-system-sudoers.sh  # Permisos sudo sistema
│   └── setup-tailscale-sudoers.sh # Permisos sudo Tailscale
│
├── systemd/
│   ├── fpvcopilot-sky.service   # Servicio systemd
│   └── fpvcopilot-sky.nginx     # Configuración nginx
│
├── tests/
│   ├── test_mavlink_bridge.py           # Tests MAVLink bridge
│   ├── test_video_config_validation.py  # 59 tests: VideoConfig/StreamingConfig clamping
│   ├── test_video_routes_validation.py  # 71 tests: Pydantic model validation
│   ├── test_flight_session.py           # Tests de sesión de vuelo
│   └── test_network_priority.py         # Tests de priorización de red
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

**Usando el CLI (recomendado)**:

```bash
./fpv
# Selecciona opción 3: "Start Development Mode"
```

**Manual**:

```bash
bash scripts/dev.sh
```

Esto arranca:

- **Backend**: `uvicorn app.main:app --reload --port 8000` (hot-reload Python)
- **Frontend**: `npm run dev` en `frontend/client/` (Vite HMR en `:5173`)

### Build y deploy manual

**Usando el CLI (recomendado)**:

```bash
./fpv
# Selecciona opción 2: "Deploy to Production"
```

**Manual**:

```bash
cd frontend/client && npm run build      # Compilar React
bash scripts/deploy.sh                   # Desplegar todo
```

### Tests

**Usando el CLI**:

```bash
./fpv
# Selecciona opción 4: "Run Tests"
```

**Manual**:

```bash
# Backend (pytest desde el venv)
source venv/bin/activate
python -m pytest tests/ -v

# Frontend (Vitest)
cd frontend/client
npx vitest run                    # Todos (104 tests, 8 archivos)
npx vitest run --reporter=verbose # Con detalle
```

**Suite de tests de video:**

| Archivo                           | Tests | Cubre                                                |
| --------------------------------- | ----- | ---------------------------------------------------- |
| `test_video_config_validation.py` | 59    | Clamping, codec whitelist, multicast, RTSP URL       |
| `test_video_routes_validation.py` | 71    | Pydantic: rangos, Literal, validación IPv4           |
| `videoConstants.test.js`          | 20    | safeInt, isValidMulticastIp, isValidIpv4, constantes |
| `SubComponents.test.jsx`          | 41    | 7 sub-componentes de video                           |
| `VideoView.test.jsx`              | 7     | Renderizado, GStreamer check, carga de datos         |

---

## 5. Convenciones de código

### Python (Backend)

- **PEP 8** con type hints
- **Async/await** para operaciones de I/O
- `ThreadPoolExecutor` (`loop.run_in_executor`) para llamadas síncronas bloqueantes desde rutas async
- Logging con `logging.getLogger(__name__)`
- Docstrings en todas las funciones públicas
- Imports absolutos: `from providers import get_provider_registry`

#### Política de ejecución de comandos del sistema

- Usar siempre `run_cmd()` / `run_cmd_async()` desde [app/utils/cmd.py](../app/utils/cmd.py) para evitar `subprocess` directo en rutas/servicios/proveedores críticos.
- Contrato único: `(stdout: str, stderr: str, returncode: int)` y nunca lanzar excepción al caller.
- Timeout obligatorio por comando (default `15s`), con `returncode = -1` cuando hay timeout/error de ejecución.
- Reintentos configurables para errores transitorios:
  - `retries`: cantidad de reintentos adicionales (default `0`).
  - `backoff_base_s` / `backoff_max_s`: backoff exponencial acotado entre intentos.
  - `retry_on_returncodes`: conjunto opcional para limitar qué códigos no-cero reintentar.
- Recomendación operativa:
  - Lecturas/health checks: `retries=0` o `1` con timeout corto.
  - Operaciones de recuperación/failover: `retries=1..3` y backoff pequeño.
  - Acciones destructivas: evitar reintento automático salvo idempotencia garantizada.

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

## 6.2 Sistema de Board Providers

Como FPV Copilot Sky ejecuta en diversas placas SBC (Radxa Zero, Jetson, Raspberry Pi, etc.) con distintas distros y kernels, usamos un **Board Provider System** que detecta y declara:

1. **Hardware detectado**: CPU cores, RAM, GPU, almacenamiento (en runtime, sin hardcoding)
2. **Variante actual**: SO, versión kernel, tipo almacenamiento
3. **Features soportados**: Video sources, video encoders, conectividad, periféricos

### Arquitectura: BoardProvider + BoardRegistry

**Estructura de archivos:**

```
app/providers/board/
├── board_provider.py               # Clase abstracta
├── board_registry.py               # Singleton con auto-discovery
├── board_definitions.py            # Enums/DTOs
├── detected_board.py               # DTO del resultado
└── implementations/
    ├── __init__.py
    └── radxa/
        ├── __init__.py
        └── zero.py                 # RadxaZeroProvider implementado
```

**Patrón de descubrimiento automático:**

`BoardRegistry` importa dinámicamente todos los módulos en `implementations/*/` usando `importlib`. Cada módulo que contenga una clase heredando de `BoardProvider` se registra automáticamente. No requiere cambios en `main.py`.

```python
# En app/main.py al startup
from providers.board import BoardRegistry

registry = BoardRegistry()  # Auto-descubre e intenta detectar
detected_board = registry.get_detected_board()
if detected_board:
    logger.info(f"✅ Board detected: {detected_board.board_name}")
```

### Implementación actual: RadxaZeroProvider

```python
# app/providers/board/implementations/radxa/zero.py
from ..board_provider import BoardProvider
from ..board_definitions import (
    HardwareInfo, VariantInfo, StorageType, DistroFamily, CPUArch,
    VideoSourceFeature, VideoEncoderFeature, ConnectivityFeature, SystemFeature
)
import os
import subprocess

class RadxaZeroProvider(BoardProvider):
    """Radxa Zero (Amlogic S905Y2)

    Auto-detecta en runtime:
    - CPU cores: os.cpu_count() o /proc/cpuinfo
    - RAM: /proc/meminfo → MemTotal
    - Storage: df / → tamaño root filesystem
    - Variante: /etc/os-release → nombre + versión
    """

    @property
    def board_name(self) -> str:
        return "Radxa Zero"

    @property
    def board_identifier(self) -> str:
        return "radxa_zero_amlogic_s905y2"

    def detect_board(self) -> bool:
        """Verifica si es Radxa Zero: /proc/device-tree/model o cpuinfo"""
        return self._check_detection_criteria()

    def _check_detection_criteria(self) -> bool:
        # Primero intenta /proc/device-tree/model
        try:
            with open('/proc/device-tree/model', 'r') as f:
                model = f.read().strip()
                return 'Radxa Zero' in model
        except FileNotFoundError:
            pass

        # Fallback: busca en cpuinfo
        try:
            with open('/proc/cpuinfo', 'r') as f:
                content = f.read()
                return 'Amlogic' in content and 'S905Y2' in content
        except FileNotFoundError:
            return False

    def _get_hardware_info(self) -> HardwareInfo:
        """Auto-detecta specs en runtime"""
        return HardwareInfo(
            cpu_model="Amlogic S905Y2",      # Inmutable
            cpu_cores=self._detect_cpu_cores(),   # Runtime
            cpu_arch=CPUArch.ARMV8,               # Inmutable
            ram_gb=self._detect_ram_gb(),         # Runtime
            storage_gb=self._detect_storage_gb(), # Runtime
            has_gpu=True,                         # Inmutable
            gpu_model="Mali-G31 MP2"             # Inmutable
        )

    @staticmethod
    def _detect_cpu_cores() -> int:
        try:
            return os.cpu_count() or 4
        except:
            return 4

    @staticmethod
    def _detect_ram_gb() -> int:
        try:
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if line.startswith('MemTotal:'):
                        kb = int(line.split()[1])
                        return max(1, int(round(kb / (1024 * 1024))))
        except:
            pass
        return 4  # fallback

    @staticmethod
    def _detect_storage_gb() -> int:
        try:
            output = subprocess.check_output(['df', '/'], text=True)
            lines = output.strip().split('\n')
            if len(lines) > 1:
                parts = lines[1].split()
                kb = int(parts[1])  # Tamaño en 1K-blocks
                return max(1, int(round(kb / (1024 * 1024))))
        except:
            pass
        return 32  # fallback

    def detect_running_variant(self) -> Optional[VariantInfo]:
        """Lee /etc/os-release para detectar variante actual"""
        try:
            distro = None
            version = None
            with open('/etc/os-release', 'r') as f:
                for line in f:
                    if line.startswith('ID='):
                        distro = line.split('=')[1].strip().strip('"')
                    elif line.startswith('VERSION_ID='):
                        version = line.split('=')[1].strip().strip('"')

            if distro and distro.lower() in ['armbian', 'ubuntu', 'debian']:
                # Detecta automáticamente el kernel
                kernel_version = subprocess.check_output(
                    ['uname', '-r'], text=True
                ).strip()

                return VariantInfo(
                    name=f"{distro.capitalize()} {version}",
                    storage_type=StorageType.EMMC,
                    distro_family=(
                        DistroFamily.ARMBIAN if distro.lower() == 'armbian'
                        else DistroFamily.DEBIAN
                    ),
                    distro_version=version or "unknown",
                    kernel_version=kernel_version,
                    is_default=True,
                    video_sources=[VideoSourceFeature.V4L2, VideoSourceFeature.LIBCAMERA],
                    video_encoders=[
                        VideoEncoderFeature.HARDWARE_H264,
                        VideoEncoderFeature.MJPEG,
                        VideoEncoderFeature.X264_SOFTWARE,
                    ],
                    connectivity=[
                        ConnectivityFeature.WIFI,
                        ConnectivityFeature.USB_MODEM,
                        ConnectivityFeature.USB_3,
                    ],
                    system_features=[
                        SystemFeature.GPIO,
                        SystemFeature.I2C,
                        SystemFeature.SPI
                    ]
                )
        except Exception as e:
            logger.warning(f"Could not detect running variant: {e}")

        return None
```

### Acceso a información del board

**Desde servicios o rutas API:**

```python
from providers.board import BoardRegistry

registry = BoardRegistry()  # Singleton - la misma instancia siempre
detected = registry.get_detected_board()

if detected:
    print(f"Board: {detected.board_name}")
    print(f"CPU: {detected.hardware.cpu_cores} cores @ {detected.hardware.cpu_model}")
    print(f"RAM: {detected.hardware.ram_gb} GB")
    print(f"Storage: {detected.hardware.storage_gb} GB")
    print(f"Encoder support: {detected.variant.video_encoders}")
```

**Ejemplo: GStreamerService adapta codec según board**

```python
# En gstreamer_service.py
from providers.board import BoardRegistry

def _adapt_codec_to_board(self, preferred_codec: str) -> str:
    """Selecciona codec disponible en esta placa"""
    registry = BoardRegistry()
    board = registry.get_detected_board()

    if not board:
        return preferred_codec  # No detection, usar preferido

    available = board.variant.video_encoders

    # Fallback chain: HW H.264 → x264 → MJPEG
    if VideoEncoderFeature.HARDWARE_H264 in available:
        return 'h264'
    elif VideoEncoderFeature.X264_SOFTWARE in available:
        return 'x264'
    else:
        return 'mjpeg'  # Siempre disponible
```

### Endpoint API: `/api/system/board`

```python
# app/api/routes/system.py
@router.get("/board")
async def get_board_info():
    registry = BoardRegistry()
    detected = registry.get_detected_board()

    if not detected:
        return {"success": False, "message": "No board detected"}

    return {
        "success": True,
        "data": detected.to_dict()  # DTO con todos los detalles
    }
```

**Respuesta JSON:**

```json
{
  "success": true,
  "data": {
    "board_name": "Radxa Zero",
    "board_model": "Radxa Zero (Amlogic S905Y2)",
    "hardware": {
      "cpu_model": "Amlogic S905Y2",
      "cpu_cores": 4,
      "cpu_arch": "aarch64",
      "ram_gb": 4,
      "storage_gb": 29,
      "has_gpu": true,
      "gpu_model": "Mali-G31 MP2"
    },
    "variant": {
      "name": "Ubuntu 24.04",
      "storage_type": "eMMC",
      "distro_family": "debian",
      "distro_version": "24.04",
      "kernel_version": "6.1.63-current-meson64"
    },
    "features": {
      "video_sources": ["v4l2", "libcamera"],
      "video_encoders": ["hardware_h264", "mjpeg", "x264"],
      "connectivity": ["wifi", "usb_modem", "usb3"],
      "system_features": ["gpio", "i2c", "spi"]
    }
  }
}
```

### Integración frontend

**En SystemView.jsx:**

- Card que muestra: board name, model, CPU/RAM/Storage detectados
- Badge con kernel version y distro
- Tags de features: video sources, encoders, connectivity, periféricos
- Datos obtenidos via `GET /api/system/board` al montar el componente

### Checklist para agregar nuevo board

1. **Crear implementación:**

   ```bash
   mkdir -p app/providers/board/implementations/<marca>/
   touch app/providers/board/implementations/<marca>/<modelo>.py
   ```

2. **Heredar de BoardProvider e implementar:**

   - `board_name`, `board_identifier` (properties)
   - `detect_board()` → conocer si esta placa está presente
   - `_get_hardware_info()` → **auto-detectar** CPU cores, RAM, storage (no hardcodear)
     - CPU cores: `os.cpu_count()`, `/proc/cpuinfo`, o `lscpu`
     - RAM: `/proc/meminfo` → MemTotal
     - Storage: `df /`, `lsblk`, o `statvfs()`
   - `detect_running_variant()` → detectar SO/kernel actual
   - `get_variants()` → definir variantes soportadas y features

3. **Testing:**

   - Verificar que `BoardRegistry` lo auto-descubre: `logger.info()` en main.py
   - Testear endpoint: `curl http://localhost:8000/api/system/board`
   - Validar specs auto-detectadas vs `df`, `uname`, `/proc/*` en shell

4. **Git:**
   - Guardar en `implementations/<marca>/<modelo>.py`
   - Auto-discovery ocurre sin cambios en main.py
   - Verificar que detecta solo en hardware real (no falsos positivos en dev)

### Notas sobre detección

- La detección ocurre en `app/main.py` al inicializar el app
- Una placa se considera "detectada" cuando todos los criterios coinciden
- Cada variante puede tener diferentes features (ej: SD vs eMMC)
- La detección automática de variante es el mejor esfuerzo (puede fallar)
- Si no hay match perfecto, se puede retornar la variante por defecto
- Los servicios consultan `BoardRegistry.get_detected_board()` para adaptar comportamiento

### Troubleshooting del Board Provider

```bash
# Verificar detección
curl -s http://localhost:8000/api/system/board | python3 -m json.tool

# Comprobar device-tree (Radxa, RPi, Jetson…)
cat /proc/device-tree/model

# CPU info
lscpu
cat /proc/cpuinfo | grep -i "model name\|CPU arch"

# RAM detectada
grep MemTotal /proc/meminfo

# Storage detectado
df -h /

# Kernel y distro
uname -r
cat /etc/os-release
```

---

## 6.3 Proveedores de Video: Fuentes (Cámaras) y Codificadores

FPV Copilot Sky usa una arquitectura basada en proveedores para **fuentes de video** (cámaras) y **codificadores** (H.264, MJPEG, etc.), permitiendo soporte flexible para múltiples hardware.

### Estructura de proveedores de video

```
providers/video_source/           # Proveedores de fuentes de video
├── v4l2_camera.py               # Cámaras USB, CSI (video4linux2)
├── libcamera_source.py          # LibCamera (Raspberry Pi, Radxa)
├── hdmi_capture.py              # Captura HDMI (USB, PCIe)
├── network_stream.py            # Streams remotos (RTSP, HTTP, HLS)
└── __init__.py

providers/video/                  # Proveedores de codificadores
├── mjpeg_encoder.py             # MJPEG (baja latencia, alto ancho de banda)
├── x264_encoder.py              # H.264 software (calidad/latencia)
├── openh264_encoder.py          # H.264 software (OpenH264, deshabilitado)
├── hardware_h264_encoder.py     # H.264 hardware (v4l2h264enc, meson_venc)
└── __init__.py
```

### VideoSourceProvider — Estructura base

```python
# app/providers/base/video_source_provider.py
from abc import ABC, abstractmethod

class VideoSourceProvider(ABC):
    """
    Proveedor abstracto para fuentes de video (cámaras, streams).
    Detecta dispositivos disponibles y construye elementos GStreamer.
    """

    def __init__(self):
        self.name: str = ""              # ID único: "v4l2", "libcamera", etc.
        self.display_name: str = ""      # Nombre visible: "V4L2 Camera"
        self.priority: int = 50          # Mayor = preferencia (0-100)

    @abstractmethod
    def is_available(self) -> bool:
        """Verificar si el proveedor puede funcionar en este hardware."""
        ...

    @abstractmethod
    def discover_sources(self) -> list[dict]:
        """
        Listar todas las fuentes disponibles.

        Retorna:
        [
            {
                "device": "/dev/video0",
                "name": "USB Camera Brio 100",
                "provider": "V4L2 Camera",
                "resolutions": ["1920x1080", "1280x720", ...],
                "framerates": [30, 24, 15]
            },
            ...
        ]
        """
        ...

    @abstractmethod
    def build_source_element(self, device: str, config: dict) -> dict:
        """
        Construir un elemento GStreamer para esta fuente.

        Args:
            device: Identificador del dispositivo (ej: "/dev/video0")
            config: {"width": 1920, "height": 1080, "framerate": 30, ...}

        Retorna:
        {
            "success": True,
            "source_element": {
                "element": "v4l2src",
                "name": "source",
                "properties": {"device": "/dev/video0", ...}
            },
            "caps_filter": "video/x-raw,width=1920,height=1080,framerate=30/1",
            "post_elements": [...]  # Escalado, conversión de color, etc.
        }
        """
        ...
```

### Ejemplo: Implementar V4L2CameraSource

```python
# app/providers/video_source/v4l2_camera.py
class V4L2CameraSource(VideoSourceProvider):
    def __init__(self):
        super().__init__()
        self.name = "v4l2"
        self.display_name = "V4L2 Camera"
        self.priority = 70

    def is_available(self) -> bool:
        """V4L2 está disponible si hay /dev/video*"""
        import glob
        return len(glob.glob('/dev/video*')) > 0

    def discover_sources(self) -> list[dict]:
        """
        Detectar cámaras USB/CSI disponibles.

        Filtra duplicados agrupando por bus_info (mismo dispositivo físico).
        """
        cameras = []
        for device_path in glob.glob('/dev/video*'):
            try:
                # Leer propiedades con v4l2-ctl
                cap = v4l2_get_capabilities(device_path)
                bus_info = cap.get('bus_info')

                # Agrupar por bus_info para evitar duplicados
                if bus_info not in seen_buses:
                    cameras.append({
                        "device": device_path,
                        "name": cap.get('name', 'Unknown'),
                        "provider": self.display_name,
                        "resolutions": extract_resolutions(device_path),
                        "framerates": extract_framerates(device_path)
                    })
                    seen_buses.add(bus_info)
            except Exception as e:
                logger.warning(f"Error probing {device_path}: {e}")

        return cameras

    def build_source_element(self, device: str, config: dict) -> dict:
        """Construir elemento v4l2src con propiedades de cámara."""
        return {
            "success": True,
            "source_element": {
                "element": "v4l2src",
                "name": "source",
                "properties": {
                    "device": device,
                    "do-timestamp": True
                }
            },
            "caps_filter": (
                f"video/x-raw,width={config['width']},"
                f"height={config['height']},"
                f"framerate={config['framerate']}/1"
            ),
            "post_elements": []
        }
```

### VideoEncoderProvider — Estructura base

```python
# app/providers/base/video_encoder_provider.py
class VideoEncoderProvider(ABC):
    """
    Proveedor abstracto para codificadores de video (H.264, MJPEG, etc).
    Detecta codificadores disponibles y construye elementos GStreamer.
    """

    def __init__(self):
        self.name: str = ""              # ID: "x264", "mjpeg", "h264", etc.
        self.display_name: str = ""      # Nombre visible
        self.priority: int = 50          # Mayor = preferencia
        self.available: bool = False

    @abstractmethod
    def is_available(self) -> bool:
        """Verificar si el codificador está disponible en el sistema."""
        ...

    @abstractmethod
    def validate_config(self, config: dict) -> dict:
        """
        Validar que la configuración es válida para este codificador.

        Retorna:
        {
            "valid": True,
            "errors": [],
            "warnings": []
        }
        """
        ...

    @abstractmethod
    def build_pipeline_elements(self, config: dict) -> dict:
        """
        Construir elementos GStreamer para este codificador.

        Retorna:
        {
            "success": True,
            "elements": [
                {
                    "element": "x264enc",
                    "name": "encoder",
                    "properties": {
                        "bitrate": 2000,
                        "speed-preset": "ultrafast",
                        "key-int-max": 60
                    }
                },
                ...
            ],
            "rtp_payloader": "rtph264pay",
            "rtp_payloader_properties": {"config-interval": 1}
        }
        """
        ...

    def update_property(self, element, property_name: str, value):
        """
        Actualizar una propiedad en vivo (durante transmisión).
        Usado para cambiar bitrate, quality, etc. sin reiniciar.
        """
        ...
```

### Ejemplo: Implementar X264Encoder

```python
# app/providers/video/x264_encoder.py
class X264Encoder(VideoEncoderProvider):
    def __init__(self):
        super().__init__()
        self.name = "h264"
        self.display_name = "H.264 (x264)"
        self.priority = 60

    def is_available(self) -> bool:
        """x264enc disponible si GStreamer lo tiene compilado."""
        return Gst.ElementFactory.make("x264enc", None) is not None

    def validate_config(self, config: dict) -> dict:
        bitrate = config.get('bitrate', 2000)
        errors = []
        warnings = []

        if not 100 <= bitrate <= 10000:
            errors.append(f"Bitrate fuera de rango: {bitrate} kbps (debe ser 100-10000)")

        if bitrate < 500:
            warnings.append(f"Bitrate muy bajo ({bitrate}), puede afectar calidad")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

    def build_pipeline_elements(self, config: dict) -> dict:
        """Construir pipeline: x264enc → rtph264pay → udpsink"""
        bitrate = config.get('bitrate', 2000)
        gop_size = config.get('gop_size', 2)

        return {
            "success": True,
            "elements": [
                {
                    "element": "x264enc",
                    "name": "encoder",
                    "properties": {
                        "bitrate": bitrate,           # kbps
                        "speed-preset": "ultrafast", # Para baja latencia
                        "key-int-max": 30 * gop_size,  # Keyframes cada N segundos
                        "tune": "zerolatency"
                    }
                }
            ],
            "rtp_payloader": "rtph264pay",
            "rtp_payloader_properties": {"config-interval": 1}
        }
```

### Registrar proveedores en main.py

```python
# app/main.py
from providers.video_source import v4l2_camera, libcamera_source, hdmi_capture, network_stream
from providers.video import mjpeg_encoder, x264_encoder, hardware_h264_encoder

def init_provider_registry():
    registry = get_provider_registry()

    # Registrar proveedores de fuentes (orden = prioridad)
    registry.register_video_source(hardware_h264_encoder.HardwareH264Encoder())
    registry.register_video_source(libcamera_source.LibCameraSource())
    registry.register_video_source(hdmi_capture.HDMICaptureSource())
    registry.register_video_source(v4l2_camera.V4L2CameraSource())
    registry.register_video_source(network_stream.NetworkStreamSource())

    # Registrar proveedores de codificadores (orden = prioridad)
    registry.register_video_encoder(hardware_h264_encoder.HardwareH264Encoder())
    registry.register_video_encoder(mjpeg_encoder.MJPEGEncoder())
    registry.register_video_encoder(x264_encoder.X264Encoder())
    registry.register_video_encoder(openh264_encoder.OpenH264Encoder())
```

### Tabla de proveedores disponibles

| Tipo        | Nombre         | ID              | Prioridad | Descripción                     |
| ----------- | -------------- | --------------- | --------- | ------------------------------- |
| **Source**  | V4L2 Camera    | `v4l2`          | 70        | Cámaras USB, CSI (video4linux2) |
|             | LibCamera      | `libcamera`     | 80        | CSI en Raspberry Pi 4+, Radxa   |
|             | HDMI Capture   | `hdmi`          | 75        | Captura HDMI (USB/PCIe)         |
|             | Network Stream | `network`       | 50        | RTSP, HTTP, HLS, RTMP           |
| **Encoder** | Hardware H.264 | `h264_hw`       | 100       | v4l2h264enc, meson_venc (SoC)   |
|             | MJPEG          | `mjpeg`         | 70        | Baja latencia (~30ms)           |
|             | x264           | `h264`          | 60        | H.264 software, buena calidad   |
|             | OpenH264       | `h264_openh264` | 0         | Deshabilitado (lento sin HW)    |

### Flujo de selección automática

```
1. Usuario selecciona dispositivo: /dev/video0
2. API llama: registry.get_available_video_sources()
3. Todos los proveedores hacen discover_sources()
4. Se devuelve lista con provider name: "V4L2 Camera"
5. En transmisión:
   - API selecciona automáticamente encoder de prioridad más alta
   - Ejemplo: HW H.264 > x264 > MJPEG > OpenH264
6. gstreamer_service.py nota provider usado:
   - current_encoder_provider = "x264 Encoder"
   - current_source_provider = "V4L2 Camera"
7. Frontend muestra: "x264 Encoder from V4L2 Camera @ 1920x1080 30fps"
```

### Para añadir un nuevo proveedor de video

1. **Crear clase** en `app/providers/video_source/<nombre>.py` o `app/providers/video/<nombre>.py`
2. **Heredar** de `VideoSourceProvider` o `VideoEncoderProvider`
3. **Implementar** métodos abstractos
4. **Registrar** en `app/main.py` (init_provider_registry)
5. **Auto-detectado** en API `/api/video/cameras` y `/api/video/codecs`

---

### 6.3.1 WebRTC: Arquitectura e Implementación

**WebRTC** es un modo de streaming avanzado que permite **video en tiempo real en el navegador** sin software adicional, con **bitrate adaptativo** optimizado para conexiones 4G/LTE.

#### Stack Tecnológico WebRTC

| Componente             | Tecnología                      | Propósito                                                      |
| ---------------------- | ------------------------------- | -------------------------------------------------------------- |
| **Backend WebRTC**     | aiortc 1.5+                     | Implementación Python de WebRTC (RTCPeerConnection, ICE, DTLS) |
| **Codificación H.264** | GStreamer (x264enc/openh264enc) | Codificación hardware-accelerated sin re-encoding              |
| **RTP Packetization**  | H264PassthroughEncoder (custom) | Empaquetado de NAL units en RTP sin re-encodificación          |
| **Bindings FFmpeg**    | PyAV (av) 10.0+                 | Manejo de frames de video (usado por aiortc)                   |
| **Frontend**           | WebRTC API nativa del navegador | RTCPeerConnection, MediaStream, ICE negotiation                |

#### Arquitectura del Pipeline WebRTC

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          GStreamer Pipeline                               │
│                                                                           │
│  v4l2src → [jpegdec]? → videoconvert → x264enc/openh264enc → h264parse  │
│                                                     │                     │
│                                                     ↓                     │
│                                                  appsink                  │
│                                                     │                     │
└─────────────────────────────────────────────────────┼────────────────────┘
                                                      │
                                           H264 byte-stream
                                                      │
                                                      ↓
┌──────────────────────────────────────────────────────────────────────────┐
│                       WebRTC Service (aiortc)                             │
│                                                                           │
│  H264PassthroughEncoder → RTP Packetization → SRTP → DTLS → ICE         │
│                                                                           │
│  RTCPeerConnection (per browser client)                                  │
│    - Offer/Answer SDP exchange via REST API                              │
│    - ICE candidate trickle                                               │
│    - Connection stats (jitter, packets lost, bitrate)                    │
└──────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ UDP (RTP/RTCP)
                                      ↓
                               Browser (WebRTC)
```

#### Pipeline GStreamer para WebRTC

El modo WebRTC usa un pipeline **ligero** separado del pipeline principal:

```python
# app/services/gstreamer_service.py
def _build_webrtc_pipeline(self) -> bool:
    """
    Pipeline: source → [jpegdec if MJPEG] → videoconvert →
              x264enc/openh264enc (ultrafast/zerolatency) →
              h264parse → appsink

    Los NAL units H.264 se extraen del appsink y se envían a
    aiortc sin re-encodificación.
    """

    # Configuración de encoder para baja latencia
    x264enc.set_property("tune", 0x00000004)     # zerolatency
    x264enc.set_property("speed-preset", 1)      # ultrafast
    x264enc.set_property("bitrate", 1500)        # kbps
    x264enc.set_property("key-int-max", fps * 2) # keyframe cada 2s

    # h264parse normaliza formato NAL
    h264parse.set_property("config-interval", -1)  # SPS/PPS con cada keyframe

    # appsink emite señal con cada frame
    appsink.connect("new-sample", self._on_webrtc_appsink_sample)
```

**Callback appsink:**

```python
def _on_webrtc_appsink_sample(self, appsink):
    """
    GStreamer llama a esta función con cada Access Unit H.264.
    Extrae los bytes y los envía al WebRTC service.
    """
    sample = appsink.emit("pull-sample")
    buf = sample.get_buffer()
    success, map_info = buf.map(Gst.MapFlags.READ)

    h264_data = bytes(map_info.data)  # Byte-stream H.264

    # Enviar a aiortc (sin re-encoding)
    if self.webrtc_service:
        self.webrtc_service.push_video_frame(h264_data)
```

#### WebRTC Service: H264PassthroughEncoder

El **H264PassthroughEncoder** es un encoder personalizado que **no re-codifica** el H.264 ya codificado por GStreamer, solo lo empaqueta en RTP:

```python
# app/services/webrtc_service.py
class H264PassthroughEncoder:
    """
    Reemplazo drop-in del H264Encoder de aiortc.

    En lugar de encodificar con libavcodec, recibe H.264 pre-encodificado
    por GStreamer y lo empaqueta en RTP (FU-A para fragmentación).
    """

    def __init__(self, h264_queue: queue.Queue, framerate: int = 30):
        self._h264_queue = h264_queue
        self._framerate = framerate

    @staticmethod
    def _split_bitstream(buf: bytes):
        """Divide H.264 byte-stream en NAL units individuales."""
        # Busca patrones 0x000001 start codes
        # Yield cada NAL unit

    @staticmethod
    def _packetize_fu_a(data: bytes) -> list:
        """
        Fragmenta NAL units grandes en paquetes FU-A (RFC 6184).

        Cada paquete RTP tiene max 1200 bytes de payload.
        NAL units > 1200 bytes se fragmentan.
        """
        # Crear FU-A header con start/end bits
        # Retornar lista de payloads RTP
```

#### Flujo de conexión WebRTC

**1. Cliente solicita conexión:**

```javascript
// Frontend (React)
const response = await api.post("/api/webrtc/offer", {
  sdp: localDescription.sdp,
  type: localDescription.type,
});

const remoteDescription = response.data.sdp;
await peerConnection.setRemoteDescription(remoteDescription);
```

**2. Backend crea RTCPeerConnection:**

```python
# app/api/routes/webrtc.py
@router.post("/offer")
async def handle_offer(request: WebRTCOfferRequest):
    service = get_webrtc_service()

    # Crear peer connection para este cliente
    peer_id = str(uuid.uuid4())
    peer = service.create_peer(peer_id)

    # Configurar SDP remoto (del navegador)
    await peer.pc.setRemoteDescription(
        RTCSessionDescription(sdp=request.sdp, type=request.type)
    )

    # Crear answer SDP
    answer = await peer.pc.createAnswer()
    await peer.pc.setLocalDescription(answer)

    # Forzar keyframe en GStreamer para que el nuevo peer reciba SPS/PPS/IDR
    if service._gstreamer_service:
        service._gstreamer_service.force_keyframe()

    return {
        "sdp": peer.pc.localDescription.sdp,
        "type": peer.pc.localDescription.type,
        "peer_id": peer_id
    }
```

**3. Force Keyframe en nuevo peer:**

```python
# app/services/gstreamer_service.py
def force_keyframe(self):
    """
    Fuerza al encoder H.264 a producir un keyframe IDR.
    Llamado cuando un nuevo peer WebRTC se conecta para que reciba SPS/PPS/IDR.
    """
    encoder = self.pipeline.get_by_name("webrtc_h264enc")

    # Enviar evento GstForceKeyUnit
    structure = Gst.Structure.new_from_string(
        "GstForceKeyUnit, all-headers=(boolean)true"
    )
    event = Gst.Event.new_custom(Gst.EventType.CUSTOM_UPSTREAM, structure)
    srcpad = encoder.get_static_pad("src")
    success = srcpad.send_event(event)
```

#### API REST WebRTC

| Método | Endpoint               | Descripción                                       |
| ------ | ---------------------- | ------------------------------------------------- |
| POST   | `/api/webrtc/offer`    | Crea peer connection, negocia SDP, retorna answer |
| POST   | `/api/webrtc/ice`      | Recibe ICE candidates del cliente                 |
| DELETE | `/api/webrtc/peer/:id` | Desconecta peer específico                        |
| GET    | `/api/webrtc/status`   | Estado del servicio (peers activos, stats)        |

#### Dependencias del Sistema

**Paquetes Debian/Ubuntu necesarios:**

```bash
# FFmpeg libraries (para PyAV)
sudo apt-get install -y \
    libavformat-dev \
    libavcodec-dev \
    libavdevice-dev \
    libavutil-dev \
    libswscale-dev \
    libswresample-dev \
    libavfilter-dev \
    libopus-dev \
    libvpx-dev \
    libsrtp2-dev \
    pkg-config
```

**Paquetes Python:**

```bash
pip install aiortc>=1.5.0 av>=10.0.0
```

#### Frontend: WebRTCViewerCard

El componente React gestiona la conexión WebRTC del lado del cliente:

```jsx
// frontend/client/src/components/Pages/VideoView/video/WebRTCViewerCard.jsx
const WebRTCViewerCard = ({ key }) => {
  const [peerConnection, setPeerConnection] = useState(null);
  const [connectionState, setConnectionState] = useState("disconnected");

  const connect = async () => {
    // Crear RTCPeerConnection
    const pc = new RTCPeerConnection({
      iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
    });

    // Listener de tracks (video)
    pc.ontrack = (event) => {
      videoRef.current.srcObject = event.streams[0];
    };

    // Crear offer
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    // Enviar offer al backend
    const response = await api.post("/api/webrtc/offer", {
      sdp: offer.sdp,
      type: offer.type,
    });

    // Configurar answer
    await pc.setRemoteDescription({
      sdp: response.data.sdp,
      type: response.data.type,
    });

    setPeerConnection(pc);
  };

  return (
    <div className="card">
      <video ref={videoRef} autoPlay playsInline />
      <button onClick={connect}>▶️ Conectar</button>
    </div>
  );
};
```

**Reinicio de conexión sin detener stream:**

El prop `key` permite forzar el remount del componente (desconectar + reconectar) sin detener el pipeline GStreamer del backend:

```jsx
// VideoView.jsx
const [webrtcKey, setWebrtcKey] = useState(0);

const restartStream = async () => {
  await api.post("/api/video/restart");
  setWebrtcKey((prev) => prev + 1); // Fuerza remount de WebRTCViewerCard
};

return <WebRTCViewerCard key={webrtcKey} />;
```

#### Optimizaciones para 4G/LTE

1. **Bitrate adaptativo**: aiortc ajusta automáticamente el bitrate según feedback RTCP
2. **Keyframe forzado**: Cada nuevo peer recibe SPS/PPS/IDR inmediatamente
3. **Ultrafast preset**: x264enc usa preset 1 (ultrafast) y tune zerolatency
4. **No re-encoding**: H.264 pre-codificado por GStreamer → passthrough → RTP
5. **Max buffers**: Appsink con max-buffers=3, drop=true para mínima latencia

#### Troubleshooting

**"Failed to create offer":**

- Verificar que aiortc y av estén instalados: `pip list | grep -E "aiortc|av"`
- Verificar FFmpeg libraries: `pkg-config --modversion libavcodec`

**"No video en navegador":**

- Comprobar que GStreamer envía frames: logs con "WebRTC appsink: pulled H264 frame"
- Forzar keyframe manualmente: `force_keyframe()` debe retornar True
- Verificar SDP: debe contener `a=rtpmap:96 H264/90000` (no VP8)

**"Connection failed / ICE timeout":**

- Verificar firewall: UDP ports necesarios para RTP
- STUN server alcanzable: `stun:stun.l.google.com:19302`
- Si detrás de CGNAT: considerar usar TURN server

---

## 6.4 Servicios de Red Avanzados

FPV Copilot Sky incluye servicios especializados para optimización de red, monitoreo de latencia, failover automático y caching DNS.

### Arquitectura de Servicios de Red

```
┌─────────────────────────────────────────┐
│         Latency Monitor                 │
│  Ping continuo a múltiples targets      │
│  Calcula: avg, min, max, jitter, p95    │
└───────────┬─────────────────────────────┘
            │ Publica métricas cada 2s
            ↓
┌─────────────────────────────────────────┐
│      Network Event Bridge  🧠           │
│  Quality Score compuesto (0-100)        │
│  SINR 35% + Jitter 30% + RSRQ 15%     │
│  + Packet Loss 20%, EMA smoothing      │
│  Cell change detection, SINR trends     │
│  → Auto-ajusta video (bitrate/GOP/kf)  │
│  → WebSocket broadcast: network_quality │
└───────────┬─────────────────────────────┘
            │ Alimenta failover predictivo
            ↓
┌─────────────────────────────────────────┐
│         Auto-Failover                   │
│  Lee latency stats + bridge SINR trend  │
│  Failover predictivo: anticipa caídas   │
│  Hysteresis: 30s cooldown, 15 samples  │
└───────────┬─────────────────────────────┘
            │ Ejecuta callback de switch
            ↓
┌─────────────────────────────────────────┐
│      Network Priority Switch            │
│  Ajusta route metrics vía ip command    │
│  WiFi: metric 200, 4G: metric 100       │
└───────────┬─────────────────────────────┘
            │
            ↓
┌─────────────────────────────────────────┐
│    Flight Mode (Network Optimizer)      │
│  MTU 1420, QoS DSCP, TCP BBR           │
│  CAKE bufferbloat, VPN policy routing   │
│  Buffers 25MB, power saving OFF         │
└─────────────────────────────────────────┘
```

### LatencyMonitor (`app/services/latency_monitor.py`)

**Propósito**: Monitoreo continuo de latencia de red mediante ping a múltiples targets.

**Características**:

- Ping paralelo a 3 targets (8.8.8.8, 1.1.1.1, 9.9.9.9)
- Intervalo configurable (default: 2 segundos)
- Histórico con ventana deslizante (default: 30 samples = 1 minuto)
- Cálculo de métricas: avg, min, max, packet loss, **jitter, variance, p95 latency**
- Thread-safe con asyncio

**Uso**:

```python
from app.services.latency_monitor import get_latency_monitor, start_latency_monitoring

# Iniciar monitoreo global
await start_latency_monitoring()

# Obtener métricas actuales
monitor = get_latency_monitor()
stats = await monitor.get_current_latency()
# stats = {"8.8.8.8": LatencyStats(...), "1.1.1.1": ...}

# Test one-shot para una interfaz específica
stat = await monitor.test_interface_latency("wlan0", count=5)
# stat.avg_latency, stat.packet_loss, etc.

# Detener
await stop_latency_monitoring()
```

**API Endpoints**:

```
POST /api/network/latency/start         # Iniciar monitoreo
POST /api/network/latency/stop          # Detener
GET  /api/network/latency/current       # Stats actuales
GET  /api/network/latency/history       # Histórico
POST /api/network/latency/test/{iface}  # Test one-time
```

**Configuración**:

```python
LatencyMonitor(
    targets=["8.8.8.8", "1.1.1.1", "9.9.9.9"],
    interval=2.0,        # segundos entre pings
    history_size=30,     # samples a mantener
    timeout=2.0          # timeout del ping
)
```

---

### AutoFailover (`app/services/auto_failover.py`)

**Propósito**: Switching automático entre WiFi ↔ 4G basado en métricas de latencia con **failover predictivo**.

**Características**:

- Threshold configurable de latencia (default: 200ms)
- Ventana de decisión: 15 muestras malas consecutivas (~30s)
- Hysteresis: cooldown de 30s entre switches
- Restore automático al modo preferido (default: modem) tras 60s
- Switch callback personalizable
- **Failover predictivo** (cuando Network Event Bridge está activo):
  - Analiza tendencia SINR (tasa de caída dB/min)
  - Incorpora jitter del bridge a la decisión
  - Calcula `predictive_urgency` para ajustar dinámicamente el threshold
  - Reduce ventana de decisión cuando la señal está cayendo rápido
  - Configurable: `sinr_critical_threshold`, `sinr_drop_rate_threshold`, `jitter_threshold_ms`, `predictive_weight`

**Lógica de Decisión**:

```
1. Monitor loop cada 2 segundos
2. Obtiene latencia promedio de LatencyMonitor
3. Si Network Event Bridge activo:
   a. Obtiene SINR trend (derivada de señal)
   b. Obtiene jitter actual
   c. Calcula predictive_urgency (0-1)
   d. effective_threshold = threshold × (1 - urgency × weight)
   e. effective_window = window × (1 - urgency × 0.5)
4. Si latency > effective_threshold:
   - Incrementa consecutive_bad_samples
   - Si consecutive >= effective_window:
     - Verifica cooldown (30s desde último switch)
     - Ejecuta switch a interfaz alternativa
     - Reset consecutive_bad_samples
5. Si latency OK:
   - Reset consecutive_bad_samples
   - Verifica restore (60s desde último switch)
   - Si latency < threshold * 0.7 → restore a preferido
```

**Uso**:

```python
from app.services.auto_failover import get_auto_failover, NetworkMode

# Definir callback de switch
async def switch_callback(target_mode: NetworkMode) -> bool:
    # Llamar a API de priority switching
    return await set_priority_mode(target_mode.value)

failover = get_auto_failover()
failover.switch_callback = switch_callback

# Iniciar
await failover.start(initial_mode=NetworkMode.MODEM)

# Configurar
await failover.update_config(
    latency_threshold_ms=250,
    latency_check_window=10,
    switch_cooldown_s=45
)

# Forzar switch manual
await failover.force_switch(NetworkMode.WIFI, reason="Manual override")

# Detener
await failover.stop()
```

**Configuración**:

```python
FailoverConfig(
    latency_threshold_ms=200.0,    # Switch si latencia > 200ms
    latency_check_window=15,        # 15 samples malas
    switch_cooldown_s=30.0,         # Min 30s entre switches
    restore_delay_s=60.0,           # 60s antes de restore
    preferred_mode=NetworkMode.MODEM  # Modo preferido
)
```

**API Endpoints**:

```
POST /api/network/failover/start?initial_mode=modem
POST /api/network/failover/stop
GET  /api/network/failover/status
POST /api/network/failover/config
POST /api/network/failover/force-switch
```

---

### NetworkOptimizer (`app/services/network_optimizer.py`)

**Propósito**: Optimizaciones de red a nivel sistema para streaming (Flight Mode).

**Optimizaciones Aplicadas**:

1. **MTU Optimization**:

   - Establece MTU 1420 en interfaz modem
   - Evita fragmentación de paquetes
   - Reduce latencia ~15%

2. **QoS with DSCP**:

   - Marca tráfico UDP en puertos video (5600, 5601, 8554)
   - DSCP EF (46) = máxima prioridad
   - vía iptables POSTROUTING

3. **TCP BBR Congestion Control**:

   - `net.ipv4.tcp_congestion_control = bbr`
   - Mejor throughput con pérdidas de paquetes
   - Requiere kernel 4.9+

4. **TCP Buffer Tuning**:

   - `net.core.rmem_max = 26214400` (25 MB)
   - `net.core.wmem_max = 26214400` (25 MB)
   - Manejo de ráfagas de tráfico

5. **Power Saving OFF**:

   - Desactiva power saving en interfaz Ethernet
   - Latencia más consistente

6. **CAKE Bufferbloat Control** (nuevo):

   - `tc qdisc replace dev <iface> root cake bandwidth <bw>mbit`
   - AQM (Active Queue Management) que elimina bufferbloat en 4G
   - Configurable: `enable_cake`, `cake_bandwidth_up_mbit` (10), `cake_bandwidth_down_mbit` (30)
   - Reduce latencia de video hasta un 40% bajo carga
   - `get_cake_stats()` → estadísticas de cola en tiempo real

7. **VPN Policy Routing** (nuevo):
   - Separa tráfico video del tráfico de control VPN
   - `iptables -t mangle` para marcar paquetes con `fwmark`
   - `ip rule` para enrutar por tablas diferentes
   - Configurable: `enable_vpn_policy_routing`, `vpn_fwmark`, `vpn_table`, `video_table`
   - Evita que Tailscale encapsule tráfico de video innecesariamente

**Uso**:

```python
from app.services.network_optimizer import get_network_optimizer

optimizer = get_network_optimizer()

# Activar Flight Mode
result = optimizer.enable_flight_mode(interface="enx001122334455")
# Aplica: MTU, QoS, TCP BBR, buffers, power saving

# Verificar estado
status = optimizer.get_status()
# {"active": True, "interface": "enx...", "config": {...}}

# Obtener métricas actuales
metrics = optimizer.get_network_metrics()
# {"tcp_congestion": "bbr", "rmem_max": "26214400", ...}

# Desactivar
optimizer.disable_flight_mode()
```

**API Endpoints**:

```
POST /api/network/flight-mode/enable
POST /api/network/flight-mode/disable
GET  /api/network/flight-mode/status
GET  /api/network/flight-mode/metrics
```

**Configuración**:

```python
FlightModeConfig(
    mtu=1420,
    video_ports=[5600, 5601, 8554],
    qos_enabled=True,
    dscp_value=46,  # EF - Expedited Forwarding
    tcp_congestion="bbr",
    buffer_size_kb=25600,  # 25 MB
    power_saving=False
)
```

---

### DNSCache (`app/services/dns_cache.py`)

**Propósito**: Caché DNS local con dnsmasq para reducir latencia de lookups.

**Características**:

- Instalación automática de dnsmasq
- Configuración auto-generada
- Cache size configurable (default: 1000 entries)
- TTL configurable (min: 5min, max: 1h)
- Múltiples upstream DNS (8.8.8.8, 1.1.1.1, 9.9.9.9)
- Gestión de /etc/resolv.conf

**Uso**:

```python
from app.services.dns_cache import get_dns_cache

dns_cache = get_dns_cache()

# Verificar si dnsmasq está instalado
is_installed = await dns_cache.is_installed()

# Instalar si no existe
if not is_installed:
    await dns_cache.install()

# Configurar y arrancar
await dns_cache.start()
# Genera config en /etc/dnsmasq.d/fpvcopilot.conf
# Actualiza /etc/resolv.conf → nameserver 127.0.0.1

# Estado
status = await dns_cache.get_status()
# {"installed": True, "running": True, "config": {...}}

# Limpiar cache
await dns_cache.clear_cache()

# Detener
await dns_cache.stop()
```

**Configuración**:

```python
DNSCacheConfig(
    cache_size=1000,        # 1000 entradas
    upstream_dns=["8.8.8.8", "1.1.1.1", "9.9.9.9"],
    min_ttl=300,            # 5 minutos
    max_ttl=3600,           # 1 hora
    negative_ttl=60,        # TTL para NXDOMAIN
    config_file="/etc/dnsmasq.d/fpvcopilot.conf"
)
```

**API Endpoints**:

```
GET  /api/network/dns/status
POST /api/network/dns/install
POST /api/network/dns/start
POST /api/network/dns/stop
POST /api/network/dns/clear
```

**Beneficio**: Reduce latencia DNS de ~50ms a ~2ms (95% mejora).

---

### NetworkEventBridge (`app/services/network_event_bridge.py`) 🧠

**Propósito**: Puente inteligente que conecta eventos de red (señal celular, latencia, jitter) con acciones sobre el pipeline de video para auto-curación del streaming.

**Características**:

- **Quality Score compuesto** (0–100) con pesos configurables:
  - SINR: 35% — señal/ruido del modem
  - Jitter: 30% — variación de latencia
  - RSRQ: 15% — calidad de referencia
  - Packet Loss: 20% — pérdida de paquetes
- **Suavizado EMA** (Exponential Moving Average) para evitar oscilaciones
- **Detección de cambios de celda** (cell_id/PCI changes)
- **Análisis de tendencia SINR** (tasa de caída dB/minuto)
- **14 tipos de NetworkEvent**: signal_degradation, cell_change, high_jitter, packet_loss_spike, sinr_drop, etc.
- **9 tipos de VideoAction**: reduce_bitrate, increase_bitrate, force_keyframe, reduce_resolution, etc.
- **Broadcast WebSocket** de quality score cada ciclo (~1s) vía tipo `network_quality`
- **Singleton global** via `get_network_event_bridge()`

**Inicialización** (`app/main.py`):

```python
from app.services.network_event_bridge import get_network_event_bridge

# En startup_event(), después de inicializar video:
bridge = get_network_event_bridge()
bridge.set_services(
    modem_provider=modem_provider,
    gstreamer_service=gstreamer_service,
    webrtc_service=webrtc_service,
    websocket_manager=websocket_manager,
    latency_monitor=latency_monitor
)
await bridge.start()

# En shutdown_event():
bridge = get_network_event_bridge()
await bridge.stop()
```

**Ciclo de monitoreo** (`_monitor_loop`):

```
Cada ~1 segundo:
1. Lee señal del modem (SINR, RSRQ, RSRP, cell_id, PCI, band, EARFCN)
2. Lee latencia del LatencyMonitor (avg, jitter, packet_loss, p95)
3. Calcula score parcial por componente:
   - sinr_score = clamp((sinr - (-10)) / (25 - (-10)) × 100)
   - rsrq_score = clamp((rsrq - (-20)) / (-3 - (-20)) × 100)
   - jitter_score = clamp((1 - jitter/100) × 100)
   - loss_score = clamp((1 - loss/10) × 100)
4. Pondera: score = 0.35×sinr + 0.15×rsrq + 0.30×jitter + 0.20×loss
5. Suavizado EMA: smoothed = α × raw + (1-α) × previous  (α = 0.3)
6. Detecta eventos: cell_change, sinr_drop, high_jitter...
7. Mapea eventos → acciones de video (reduce_bitrate, force_keyframe...)
8. Ejecuta acciones via GStreamer/WebRTC APIs
9. Broadcast via WebSocket: {type: "network_quality", data: {...}}
```

**Formato WebSocket** (`network_quality`):

```json
{
  "type": "network_quality",
  "data": {
    "active": true,
    "quality_score": {
      "score": 72.5,
      "label": "Bueno",
      "color": "#f0ad4e",
      "components": {
        "sinr": { "value": 14.2, "score": 69.1 },
        "rsrq": { "value": -8.5, "score": 67.6 },
        "jitter": { "value": 18.3, "score": 81.7 },
        "packet_loss": { "value": 0.5, "score": 95.0 }
      }
    },
    "cell_info": {
      "cell_id": "1234567",
      "pci": "42",
      "band": "B3",
      "earfcn": "1300"
    },
    "latency": {
      "avg_ms": 45.2,
      "jitter_ms": 18.3,
      "packet_loss_pct": 0.5,
      "p95_ms": 72.1
    },
    "recommended_settings": {
      "bitrate_kbps": 3000,
      "gop_size": 15,
      "resolution": "854x480"
    },
    "recent_events": [
      {
        "type": "high_jitter",
        "timestamp": "2026-02-08T17:30:15Z",
        "details": { "jitter_ms": 45.2, "threshold": 30.0 }
      }
    ]
  }
}
```

**API Endpoints**:

```
POST /api/network/bridge/start         # Iniciar bridge
POST /api/network/bridge/stop          # Detener
GET  /api/network/bridge/status        # Estado completo (score, cell, events)
GET  /api/network/bridge/quality-score # Solo quality score
GET  /api/network/bridge/events        # Últimos N eventos
```

**Uso programático**:

```python
from app.services.network_event_bridge import get_network_event_bridge

bridge = get_network_event_bridge()

# Obtener estado
status = bridge.get_status()
# {active, quality_score, cell_info, latency, recent_events, recommended_settings}

# Quality score actual
score = bridge.get_quality_score()
# {score: 72.5, label: "Bueno", color: "#f0ad4e", components: {...}}

# Últimos eventos
events = bridge.get_recent_events(limit=20)
```

---

### MPTCP (Multi-Path TCP)

**Propósito**: Usar WiFi + 4G simultáneamente para redundancia y mayor ancho de banda combinado.

**Requisitos**: Kernel 5.6+ con soporte MPTCP. El instalador verifica y configura automáticamente:

```
net.mptcp.enabled = 1
net.mptcp.allow_join_initial_addr_port = 1
net.mptcp.checksum_enabled = 0
```

**API Endpoints**:

```
GET  /api/network/mptcp/status         # Estado MPTCP
POST /api/network/mptcp/enable         # Habilitar (sysctl + ip mptcp)
POST /api/network/mptcp/disable        # Deshabilitar
```

**Flujo de habilitación**:

1. `sysctl -w net.mptcp.enabled=1`
2. `ip mptcp endpoint add <iface_ip> dev <iface> subflow` para cada interfaz
3. Verifica endpoints creados

---

### Network Dashboard API

El endpoint `/api/network/dashboard` unifica todos los datos de red en una sola llamada HTTP.

**Propósito**: Reducir overhead de múltiples requests HTTP desde el frontend.

**Datos Unificados**:

```json
{
  "success": true,
  "timestamp": 1707488340.123,
  "cached": false,
  "cache_age": 0.0,
  "network": {
    "wifi_interface": "wlan0",
    "modem_interface": "enx001122334455",
    "primary_interface": "enx001122334455",
    "mode": "modem",
    "interfaces": [...],
    "routes": [...]
  },
  "modem": {
    "available": true,
    "connected": true,
    "device": {...},
    "signal": {...},
    "network": {...},
    "traffic": {...}
  },
  "wifi_networks": [...],
  "flight_mode": {
    "active": false,
    "network_optimizer_active": false,
    "modem_video_mode_active": false
  }
}
```

**Optimizaciones**:

- **Carga paralela** via `asyncio.gather()`
- **Caché inteligente** (TTL: 2 segundos)
- **Fallos parciales OK**: si modem no disponible, solo ese campo null

**Performance**:

```
Antes (4 API calls):  ~4-5 segundos
Ahora (1 API call):   ~1.3 segundos (primera carga)
Con caché:            ~0.4 segundos (70% más rápido)
```

**Uso desde Frontend**:

```javascript
const loadDashboard = async (forceRefresh = false) => {
  const url = `/api/network/dashboard${
    forceRefresh ? "?force_refresh=true" : ""
  }`;
  const response = await fetch(url);
  const data = await response.json();

  // Actualizar todos los estados en un solo request
  setNetworkStatus(data.network);
  setModemStatus(data.modem);
  setWifiNetworks(data.wifi_networks);
  setFlightMode(data.flight_mode);
};
```

**Endpoint**:

```
GET /api/network/dashboard?force_refresh=false
```

---

### Integración de Servicios

Los servicios de red se integran en el flujo normal de la aplicación:

**Inicio de la Aplicación** (`app/main.py`):

```python
# No se inician automáticamente, solo se crean instancias globales
# El usuario los activa via API según necesidad
```

**Flight Mode** (combinación de servicios):

```python
# 1. NetworkOptimizer: optimizaciones sistema
optimizer = get_network_optimizer()
await optimizer.enable_flight_mode(interface=modem_interface)

# 2. Modem Provider: configuración modem
modem = get_modem_provider("huawei_e3372h")
await modem.enable_video_mode()  # 4G Only, B3+B7 bands
```

**Auto-Failover** (funcionamiento autónomo):

```python
# 1. Iniciar LatencyMonitor
await start_latency_monitoring()

# 2. Iniciar AutoFailover con callback
failover = get_auto_failover()
failover.switch_callback = switch_network_callback
await failover.start(initial_mode=NetworkMode.MODEM)

# 3. Loop automático:
#    - Lee latency cada 2s
#    - Decide switch si threshold excedido
#    - Ejecuta callback
#    - Logs en journalctl
```

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
GET  /api/video/status                # Estado del stream (incluye providers activos)
POST /api/video/start                 # Iniciar streaming (auto-selecciona providers)
POST /api/video/stop                  # Detener streaming
POST /api/video/restart               # Reiniciar streaming
POST /api/video/config/video          # Configurar video (Pydantic: VideoConfigRequest)
POST /api/video/config/streaming      # Configurar red/emisión (StreamingConfigRequest)
GET  /api/video/cameras               # Cámaras detectadas (todos los providers)
GET  /api/video/codecs                # Codificadores disponibles (todos los providers)
GET  /api/video/network/ip            # IP de la placa y URL RTSP sugerida
PUT  /api/video/live-update           # Cambiar property+value en vivo (LiveUpdateRequest)
GET  /api/video/config/auto-adaptive-bitrate  # Estado del auto-ajuste de bitrate
POST /api/video/config/auto-adaptive-bitrate  # Activar/desactivar auto-ajuste (enabled: bool)
```

> **Validación**: Las rutas POST/PUT usan modelos Pydantic con validación de rangos,
> Literal types para enums (codec, mode, transport), y validación IPv4/multicast.
> El backend aplica clamping adicional en `VideoConfig.__post_init__` y
> `StreamingConfig.__post_init__` como segunda capa de defensa.

**Ejemplo: Respuesta de `/api/video/status`**

```json
{
  "streaming": true,
  "config": {
    "device": "/dev/video0",
    "codec": "h264",
    "width": 1920,
    "height": 1080,
    "framerate": 30,
    "h264_bitrate": 2000
  },
  "providers": {
    "encoder": "x264 Encoder", // Proveedor activo
    "source": "V4L2 Camera" // Fuente activa
  },
  "stats": {
    "current_fps": 29,
    "current_bitrate": 2100,
    "frames_sent": 15420,
    "health": "good"
  }
}
```

**Ejemplo: Respuesta de `/api/video/cameras`**

```json
[
  {
    "device": "/dev/video0",
    "name": "Brio 100",
    "provider": "V4L2 Camera", // Proveedor que la detecó
    "resolutions": ["1920x1080", "1280x720", "640x480"],
    "framerates": [30, 24, 15]
  }
]
```

**Ejemplo: Respuesta de `/api/video/codecs`**

```json
[
  {
    "id": "h264_hw",
    "name": "H.264 Hardware",
    "available": false, // No disponible en este SoC
    "priority": 100,
    "description": "v4l2h264enc (hardware)"
  },
  {
    "id": "mjpeg",
    "name": "MJPEG",
    "available": true,
    "priority": 70,
    "description": "Motion JPEG (baja latencia)"
  },
  {
    "id": "h264",
    "name": "H.264 (x264)",
    "available": true,
    "priority": 60,
    "description": "x264 software encoding"
  }
]
```

**Ejemplo: Auto-Adaptive Bitrate**

```
GET /api/video/config/auto-adaptive-bitrate
```

Respuesta:

```json
{
  "enabled": true,
  "description": "Auto-ajuste activado. El Network Event Bridge controla el bitrate según calidad de red."
}
```

```
POST /api/video/config/auto-adaptive-bitrate
Content-Type: application/json

{
  "enabled": true
}
```

Cuando `enabled: true`:

- El selector de bitrate en la UI muestra "AUTO" en lugar de un dropdown
- El Network Event Bridge ajusta automáticamente el bitrate cada 2 segundos según SINR, jitter y latencia
- El bitrate objetivo se muestra en la UI pero no es editable manualmente
- Los ajustes se realizan llamando internamente a `/api/video/live-update` con `property: "bitrate"` y `value: <nuevo_bitrate_kbps>`

Cuando `enabled: false`:

- El selector de bitrate vuelve a ser un dropdown manual
- El usuario selecciona el bitrate fijo desde la interfaz
- El Network Event Bridge no interviene en el bitrate

---

### Red / Modem

**Gestión de Red**:

```
GET  /api/network/status              # Estado de red (WiFi, modem, interfaces)
GET  /api/network/interfaces          # Lista de interfaces de red
GET  /api/network/routes              # Tabla de rutas
POST /api/network/priority            # Cambiar prioridad (wifi/modem/auto)
GET  /api/network/dashboard           # Endpoint unificado (network+modem+wifi+flight)
```

**WiFi**:

```
GET  /api/network/wifi/networks       # Escanear redes WiFi
POST /api/network/wifi/connect        # Conectar a WiFi (nmcli real)
POST /api/network/wifi/disconnect     # Desconectar WiFi
GET  /api/network/wifi/saved          # Conexiones guardadas
POST /api/network/wifi/forget         # Olvidar conexión
```

**Modem**:

```
GET  /api/network/modem/status        # Estado completo del modem
GET  /api/network/modem/apn           # Configuración APN
POST /api/network/modem/apn           # Cambiar APN
GET  /api/network/modem/band          # Bandas LTE actuales
POST /api/network/modem/band          # Cambiar banda LTE
GET  /api/network/modem/mode          # Modo de red (2G/3G/4G/Auto)
POST /api/network/modem/mode          # Cambiar modo de red
GET  /api/network/modem/latency       # Test de latencia
GET  /api/network/modem/video-quality # Evaluación de calidad
POST /api/network/modem/video-mode/enable   # Activar modo video
POST /api/network/modem/video-mode/disable  # Desactivar modo video
```

**Flight Mode**:

```
GET  /api/network/flight-mode/status  # Estado Flight Mode
POST /api/network/flight-mode/enable  # Activar (optimizer + modem)
POST /api/network/flight-mode/disable # Desactivar
GET  /api/network/flight-mode/metrics # Métricas de red actuales
```

**Latency Monitoring**:

```
POST /api/network/latency/start       # Iniciar monitoreo continuo
POST /api/network/latency/stop        # Detener monitoreo
GET  /api/network/latency/current     # Estadísticas actuales
GET  /api/network/latency/history     # Histórico (último N samples)
GET  /api/network/latency/interface/{iface}  # Stats por interfaz
POST /api/network/latency/test/{iface}       # Test one-time
DELETE /api/network/latency/history   # Limpiar histórico
```

**Auto-Failover**:

```
POST /api/network/failover/start?initial_mode=modem  # Iniciar failover
POST /api/network/failover/stop                      # Detener
GET  /api/network/failover/status                    # Estado y config
POST /api/network/failover/config                    # Actualizar config
POST /api/network/failover/force-switch              # Switch manual
```

**DNS Caching**:

```
GET  /api/network/dns/status          # Estado dnsmasq
POST /api/network/dns/install         # Instalar dnsmasq
POST /api/network/dns/start           # Iniciar servicio
POST /api/network/dns/stop            # Detener servicio
POST /api/network/dns/clear           # Limpiar cache
```

**Network Event Bridge** (auto-curación streaming):

```
POST /api/network/bridge/start        # Iniciar bridge
POST /api/network/bridge/stop         # Detener
GET  /api/network/bridge/status       # Estado completo (score, cell, events)
GET  /api/network/bridge/quality-score # Quality score actual
GET  /api/network/bridge/events       # Últimos eventos de red
```

**MPTCP** (multi-path TCP):

```
GET  /api/network/mptcp/status        # Estado MPTCP
POST /api/network/mptcp/enable        # Habilitar bonding WiFi+4G
POST /api/network/mptcp/disable       # Deshabilitar
```

**Flight Session** (logging vuelo):

```
POST /api/network/modem/flight-session/start   # Iniciar sesión
POST /api/network/modem/flight-session/stop    # Detener sesión
POST /api/network/modem/flight-session/sample  # Registrar muestra
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
import { useWebSocket } from "../../contexts/WebSocketContext";

const MyComponent = () => {
  const { messages, isConnected } = useWebSocket();

  // messages.modem_status se actualiza automáticamente cada 10s
  // messages.telemetry se actualiza cada 1s
  // messages.vpn_status se actualiza cada 10s
  // messages.network_quality se actualiza cada ~1s (cuando bridge activo)
  // etc.

  return <div>{messages.modem_status?.signal?.rssi}</div>;
};
```

### Tipos de mensaje WebSocket

| Tipo              | Frecuencia | Fuente               | Datos principales                                            |
| ----------------- | ---------- | -------------------- | ------------------------------------------------------------ |
| `telemetry`       | ~1s        | MAVLink service      | GPS, actitud, batería, modo vuelo                            |
| `modem_status`    | ~10s       | Modem provider       | Señal, tráfico, operador                                     |
| `vpn_status`      | ~10s       | VPN provider         | Conectado, IP, peers                                         |
| `network_quality` | ~1s        | Network Event Bridge | Quality score, cell info, latencia, eventos, recomendaciones |

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

---

## FASE 1: ModemPool

### Propósito

Gestión inteligente de múltiples modems 4G/LTE simultáneos: detección, health checks individuales, quality scoring y selección automática o manual del modem activo.

### Ubicación

- Servicio: `app/services/modem_pool.py`
- API: `app/api/routes/network/modem_pool.py`
- Integración WS: `app/services/network_event_bridge.py`

### Arquitectura

```
ModemPool (singleton)
├── auto-detection loop (cada 5 s via detect_modem_interfaces())
├── health monitoring por modem (ping + status de modem provider)
├── quality scoring compuesto 0-100
│     sinr_score    = clamp((sinr + 5) * 100 / 30)   # SINR: peso 40%
│     rsrq_score    = clamp((rsrq + 20) * 100 / 17)  # RSRQ: peso 15%
│     latency_score = clamp(100 - latency_ms / 4)    # Latencia: peso 30%
│     jitter_score  = clamp(100 - jitter_ms)         # Jitter: peso 15%
├── anti-flapping: delta > 20 pts + cooldown 60 s
└── apply_modem_priority() → llama a PolicyRoutingManager
```

### Dataclasses clave

```python
@dataclass
class ModemInfo:
    interface: str          # e.g. "enx001122334455"
    ip_address: Optional[str]
    gateway: Optional[str]
    is_connected: bool
    is_active: bool         # modem seleccionado actualmente
    is_healthy: bool
    signal: ModemSignalMetrics   # SINR, RSRQ, RSRP, band, operator
    network: ModemNetworkMetrics # latency_avg_ms, jitter_ms, packet_loss_pct
    quality_score: float    # 0-100 compuesto
    signal_score: float
    network_score: float

class ModemSelectionMode(Enum):
    MANUAL      = "manual"
    BEST_SCORE  = "best_score"
    BEST_SINR   = "best_sinr"
    BEST_LATENCY= "best_latency"
    ROUND_ROBIN = "round_robin"
```

### API Endpoints

| Método | Endpoint                          | Descripción                   |
| ------ | --------------------------------- | ----------------------------- |
| GET    | `/api/network/modems`             | Lista todos los modems        |
| GET    | `/api/network/modems/connected`   | Solo modems conectados        |
| GET    | `/api/network/modems/healthy`     | Solo modems saludables        |
| GET    | `/api/network/modems/active`      | Modem actualmente activo      |
| GET    | `/api/network/modems/best`        | Mejor modem por quality_score |
| GET    | `/api/network/modems/{interface}` | Modem específico              |
| POST   | `/api/network/modems/select`      | Seleccionar modem manualmente |
| POST   | `/api/network/modems/refresh`     | Forzar re-detección           |
| POST   | `/api/network/modems/mode`        | Cambiar modo de selección     |
| GET    | `/api/network/modems/status`      | Resumen del pool              |

### WebSocket broadcast (campo `modem_pool` en `network_quality`)

```json
"modem_pool": {
  "enabled": true,
  "total_modems": 2,
  "active_modem": "enx001122334455",
  "selection_mode": "best_score",
  "modems": [ { "interface": "...", "quality_score": 85.3, ... } ]
}
```

### Inicialización / shutdown (app/main.py)

```python
from app.services.modem_pool import get_modem_pool
modem_pool = get_modem_pool()
await modem_pool.start()    # startup
await modem_pool.stop()     # shutdown
```

### Parámetros de configuración

Modificar en `app/services/modem_pool.py`:

```python
self.weight_sinr    = 0.40
self.weight_rsrq    = 0.15
self.weight_latency = 0.30
self.weight_jitter  = 0.15
self.health_check_interval_s = 5.0
self.failure_threshold       = 3     # fallos consecutivos → unhealthy
self.switch_delta_threshold  = 20.0  # puntos mínimos para auto-switch
self.switch_cooldown_s       = 60.0
```

---

## FASE 2: PolicyRoutingManager

### Propósito

Aislar tráfico crítico (VPN, video, MAVLink) en tablas de routing dedicadas usando iptables mangle + `ip rule`. Garantiza que los cambios de modem **no interrumpan VPN ni degraden video**.

### Ubicación

- Servicio: `app/services/policy_routing_manager.py`
- API: `app/api/routes/network/policy_routing.py`

### Tablas de routing

| Tabla     | ID   | Tráfico                                                             | fwmark        |
| --------- | ---- | ------------------------------------------------------------------- | ------------- |
| main      | 254  | Tráfico general                                                     | -             |
| vpn       | 100  | Tailscale UDP 41641, WireGuard UDP 51820                            | 0x100         |
| video     | 200  | GStreamer UDP 5600-5610, RTSP TCP/UDP 8554, MAVLink UDP 14550/14551 | 0x200 / 0x300 |
| modem1..N | 201+ | Rutas por modem individual                                          | -             |

### Integración con ModemPool

Cuando `ModemPool.select_modem()` cambia el modem activo, llama a:

```python
await policy_routing.update_active_modem(interface, gateway)
# → ip route del default table 100
# → ip route add default via <gw> dev <iface> table 100
# → ip route del default table 200
# → ip route add default via <gw> dev <iface> table 200
```

### API Endpoints

| Método | Endpoint                                      | Descripción                         |
| ------ | --------------------------------------------- | ----------------------------------- |
| GET    | `/api/network/policy-routing/status`          | Estado completo                     |
| POST   | `/api/network/policy-routing/initialize`      | Inicializar (idempotente)           |
| POST   | `/api/network/policy-routing/cleanup`         | Limpiar todas las reglas            |
| POST   | `/api/network/policy-routing/update-modem`    | Actualizar modem activo manualmente |
| GET    | `/api/network/policy-routing/tables`          | Rutas en todas las tablas           |
| GET    | `/api/network/policy-routing/rules`           | Policy rules (`ip rule show`)       |
| GET    | `/api/network/policy-routing/traffic-classes` | Clases de tráfico configuradas      |

### Ciclo de vida (idempotente)

```python
from app.services.policy_routing_manager import get_policy_routing_manager
manager = get_policy_routing_manager()
await manager.initialize()  # startup — crea iptables + ip rule + ip route
await manager.cleanup()     # shutdown — elimina todas las reglas
```

### Filosofía: Configuration as Code

Las reglas son **dinámicas** (recreadas en cada startup) — no se usa `iptables-persistent`. Esto garantiza que las reglas siempre reflejan el código actual sin residuos ni conflictos tras actualizaciones.

---

## FASE 3: VPNHealthChecker

### Propósito

Verificar que la VPN (Tailscale, WireGuard, OpenVPN) esté activa antes y después de cada switch de modem, con rollback automático si no se recupera.

### Ubicación

- Servicio: `app/services/vpn_health_checker.py`
- API: `app/api/routes/network/vpn_health.py`

### VPNs soportadas

| VPN       | Detección                          | Health check                   |
| --------- | ---------------------------------- | ------------------------------ |
| Tailscale | `tailscale status`                 | Logged in + ping a peer        |
| WireGuard | `wg show`                          | Interface activa + allowed IPs |
| OpenVPN   | `pgrep openvpn` + interfaz tun/tap | Proceso activo + ping          |

### Flujo de protección en ModemPool.select_modem()

```python
# 1. PRE-SWITCH
vpn_was_healthy = await vpn_checker.check_vpn_health()

# 2. SWITCH
success = await self._apply_modem_priority(interface)

# 3. POST-SWITCH (solo si VPN estaba sana)
if vpn_was_healthy:
    recovered = await vpn_checker.wait_for_vpn_recovery(timeout_s=15)
    if not recovered:
        logger.error("❌ VPN failed — rolling back")
        await self._apply_modem_priority(previous_modem)
        return False
```

### API Endpoints

| Método | Endpoint                          | Descripción                    |
| ------ | --------------------------------- | ------------------------------ |
| GET    | `/api/network/vpn-health/status`  | Estado completo de VPN         |
| POST   | `/api/network/vpn-health/check`   | Health check manual            |
| GET    | `/api/network/vpn-health/peer-ip` | IP de peer para latency checks |
| GET    | `/api/network/vpn-health/type`    | Tipo de VPN detectada          |

### Respuesta de status

```json
{
  "is_active": true,
  "vpn_type": "tailscale",
  "interface": "tailscale0",
  "local_ip": "100.101.102.103",
  "peers": ["100.64.0.1"],
  "peer_reachable": true,
  "peer_latency_ms": 23.4
}
```

### Inicialización (app/main.py)

```python
from app.services.vpn_health_checker import get_vpn_health_checker
vpn_checker = get_vpn_health_checker()
await vpn_checker.initialize()   # detecta tipo VPN
await vpn_checker.cleanup()      # shutdown
```

### WebSocket broadcast (campo `vpn_health` en `network_quality`)

Los tipos de mensaje WebSocket disponibles se amplían con `vpn_health`:

| Tipo              | Frecuencia | Nuevos campos                                |
| ----------------- | ---------- | -------------------------------------------- |
| `network_quality` | ~1s        | `modem_pool`, `policy_routing`, `vpn_health` |

---

[← Índice](INDEX.md) · [Anterior: Guía de Usuario](USER_GUIDE.md)
