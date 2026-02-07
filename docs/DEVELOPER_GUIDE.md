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

| Tipo | Nombre | ID | Prioridad | Descripción |
|------|--------|----|-----------|----|
| **Source** | V4L2 Camera | `v4l2` | 70 | Cámaras USB, CSI (video4linux2) |
| | LibCamera | `libcamera` | 80 | CSI en Raspberry Pi 4+, Radxa |
| | HDMI Capture | `hdmi` | 75 | Captura HDMI (USB/PCIe) |
| | Network Stream | `network` | 50 | RTSP, HTTP, HLS, RTMP |
| **Encoder** | Hardware H.264 | `h264_hw` | 100 | v4l2h264enc, meson_venc (SoC) |
| | MJPEG | `mjpeg` | 70 | Baja latencia (~30ms) |
| | x264 | `h264` | 60 | H.264 software, buena calidad |
| | OpenH264 | `h264_openh264` | 0 | Deshabilitado (lento sin HW) |

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
POST /api/video/configure             # Aplicar configuración (codec, bitrate, etc.)
GET  /api/video/cameras               # Cámaras detectadas (todos los providers)
GET  /api/video/codecs                # Codificadores disponibles (todos los providers)
PUT  /api/video/update-property       # Cambiar bitrate/quality en vivo
```

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
    "encoder": "x264 Encoder",      // Proveedor activo
    "source": "V4L2 Camera"         // Fuente activa
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
    "provider": "V4L2 Camera",       // Proveedor que la detecó
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
    "available": false,              // No disponible en este SoC
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

---

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
