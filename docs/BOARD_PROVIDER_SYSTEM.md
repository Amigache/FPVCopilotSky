# 🎯 Board Provider System

Sistema de detección y declaración de hardware para FPV Copilot Sky. Permite que la aplicación se adapte automáticamente a diferentes placas SBC (Single Board Computer) sin recompilación.

---

## 📋 Índice

1. [Visión General](#visión-general)
2. [Arquitectura](#arquitectura)
3. [Implementación RadxaZero](#implementación-radxazero)
4. [Cómo usar BoardRegistry](#cómo-usar-boardregistry)
5. [Integración en frontend](#integración-en-frontend)
6. [Agregar nuevo board](#agregar-nuevo-board)
7. [Troubleshooting](#troubleshooting)

---

## 🎨 Visión General

El **Board Provider System** resuelve el problema de que FPV Copilot Sky ejecuta en hardware diverso:

| Placa | CPU | RAM | GPU | Video Sources | Conectividad |
|-------|-----|-----|-----|-----------------|-------------|
| **Radxa Zero** | Amlogic S905Y2, 4c | 4GB | Mali-G31 MP2 | V4L2, LibCamera | WiFi, USB modem, USB 3.x |
| **Raspberry Pi 5** | BCM2712, 4c | 4-8GB | VideoCore VII | LibCamera | WiFi 6, USB 3.x |
| **Jetson Nano** | NVIDIA Tegra, 4c | 4GB | NVIDIA Maxwell | V4L2 | Ethernet, USB |
| **OrangePi Zero** | AllWinner H618, 4c | 1-2GB | OpenGL ES | V4L2 | WiFi BLE, USB |

### Objetivos

✅ **Auto-detectar** CPU cores, RAM, storage **en runtime** (sin hardcoding)  
✅ **Identificar variante** actual: SO, kernel, tipo almacenamiento  
✅ **Declarar features** soportados: video sources, encoders, conectividad  
✅ **Adaptar servicios** según placa (ej: GStreamer elige codec disponible)  
✅ **Exponer vía API y frontend** para visibilidad del usuario  

### No es

❌ Reemplazar los Provider patterns existentes (Modem, VPN, Network)  
❌ Instalador de drivers o configurador de hardware  
❌ Sistema de overclocking o tunning de performance  

---

## 🏗️ Arquitectura

### Estructura de carpetas

```
app/providers/board/
├── __init__.py                             # Exports: BoardRegistry
├── board_provider.py                       # Clase abstracta
├── board_registry.py                       # Singleton con auto-discovery
├── board_definitions.py                    # Enums y DTOs
├── detected_board.py                       # Objeto resultado final
└── implementations/
    ├── __init__.py
    └── radxa/
        ├── __init__.py
        └── zero.py                         # RadxaZeroProvider
```

### Flujo de inicialización

```
app/main.py startup_event()
    │
    ├─→ from providers.board import BoardRegistry
    │
    └─→ BoardRegistry()  [singleton instantiation]
        │
        ├─→ _discover_providers()
        │   ├─ importlib.walk_packages('implementations/')
        │   ├─ import radxa.zero
        │   ├─ find RadxaZeroProvider(BoardProvider)
        │   └─ instantiate + register
        │
        └─→ _detect_board()
            ├─ for each provider:
            │   ├─ provider.detect_board() → bool
            │   ├─ if True: provider._get_hardware_info() → HardwareInfo
            │   ├─ provider.detect_running_variant() → VariantInfo
            │   └─ return DetectedBoard(provider, hardware, variant)
            └─ return None if no match
```

### Patrón: Clase abstracta vs Implementación

```
BoardProvider (abstracta en board_provider.py)
    ├─ board_name: str
    ├─ board_identifier: str
    ├─ detect_board() → bool          [¿Esta placa está presente?]
    ├─ _get_hardware_info() → HardwareInfo  [Auto-detectar CPU/RAM/Storage]
    └─ detect_running_variant() → VariantInfo  [OS/kernel actual]
        │
        └─→ RadxaZeroProvider (implementations/radxa/zero.py)
            ├─ board_name = "Radxa Zero"
            ├─ detect_board() → busca /proc/device-tree/model
            ├─ _get_hardware_info() → lee /proc/meminfo, df, os.cpu_count()
            └─ detect_running_variant() → /etc/os-release + uname
```

### DTOs: Qué información fluye

```python
HardwareInfo(cpu_model, cpu_cores, cpu_arch, ram_gb, storage_gb, 
             has_gpu, gpu_model)
    ↓
VariantInfo(name, storage_type, distro_family, distro_version, 
            kernel_version, video_sources[], video_encoders[], 
            connectivity[], system_features[])
    ↓
DetectedBoard(board_name, board_model, hardware, variant, features)
    │
    └─→ .to_dict() → JSON para API/frontend
```

---

## 💾 Implementación RadxaZero

### Característica clave: Auto-detección de kernel families

La implementación del **RadxaZeroProvider** ahora **detecta automáticamente** la familia de kernel Armbian (`legacy`, `current` o `edge`) y adapta los features disponibles consecuentemente.

**¿Por qué es importante?** El soporte HW H.264 encoder en Amlogic S905Y2 varía **significativamente** según la rama de kernel:

| Familia | Kernel | HW H.264 | Support Level |
|---------|--------|----------|---|
| **legacy** | Vendor BSP (5.15.x) | ✅ Disponible | Máximo (vendor integrado) |
| **current** | Mainline estable (6.12.x) | ❌ NO disponible | Bueno (pero sin VPU HW) |
| **edge** | Mainline latest (6.13+) | ❌ NO disponible | Experimental |

**⚠️ Insight importante**: En Amlogic, el soporte HW H.264 depende de integración vendor VPU que solo existe en BSP kernels (legacy). Mainline current NO tiene encoder HW confiable.

#### Variantes soportadas (2 principales)

1. **Armbian current kernel** (default, recomendado)
   - Kernel: 6.12.58-current-meson64
   - HW H.264: ❌ NO disponible (mainline no tiene integración VPU)
   - Encoders: MJPEG, x264 software
   - Ventajas: Mantenimiento activo, estable
   - Usa: Si necesitas estabilidad y fallback a software encoding está OK

2. **Armbian legacy kernel** (máximo HW support)
   - Kernel: 5.15.x-legacy-meson64
   - HW H.264: ✅ Disponible (vendor BSP tiene integración VPU Amlogic)
   - Encoders: H.264 HW, MJPEG, x264 software
   - Ventajas: Máximo soporte de hardware
   - Usa: Si necesitas H.264 HW encoding por eficiencia

#### Cómo funciona la detección

El **`_detect_kernel_family()`** método parsea la versión del kernel y busca los marcadores:

```python
kernel_version = "6.12.58-current-meson64"
# ↓ parsea ↓
family = _detect_kernel_family(kernel_version)
# ↓ detecta "current" ↓
return ArmbiankernelFamily.CURRENT
```

Luego **`_get_variant_for_kernel_family()`** retorna la variante apropiada con features correctos.

### Archivo: `app/providers/board/implementations/radxa/zero.py`

```python
import os
import logging
import subprocess
from typing import Optional

# Imports relativos: funcionan durante auto-discovery
from ...board_provider import BoardProvider
from ...board_definitions import (
    HardwareInfo, VariantInfo, StorageType, DistroFamily, CPUArch,
    VideoSourceFeature, VideoEncoderFeature, ConnectivityFeature, SystemFeature
)

logger = logging.getLogger(__name__)

class RadxaZeroProvider(BoardProvider):
    """
    Radxa Zero - Amlogic S905Y2 (ARM64)
    
    Hardware:
    - CPU: 4x ARM Cortex-A53 @ 1.8 GHz
    - GPU: Mali-G31 MP2
    - RAM: 4GB LPDDR4
    - Storage: 16GB eMMC (expandible via microSD o USB)
    - Conectividad: WiFi 6, Bluetooth 5.0, USB 3.1 Type-C, USB 2.0 Type-A
    
    Auto-detección en runtime:
    - CPU cores: os.cpu_count()
    - RAM: /proc/meminfo
    - Storage: df /
    - Variante (SO/kernel): /etc/os-release + uname
    """
    
    @property
    def board_name(self) -> str:
        """Nombre público del board"""
        return "Radxa Zero"
    
    @property
    def board_identifier(self) -> str:
        """Identificador único para logging/debugging"""
        return "radxa_zero_amlogic_s905y2"
    
    def detect_board(self) -> bool:
        """
        Detecta si el hardware actual es un Radxa Zero.
        
        Estrategia:
        1. Intenta /proc/device-tree/model (método preferido, más confiable)
        2. Fallback: busca en /proc/cpuinfo
        
        Returns:
            bool: True si es Radxa Zero, False en otro caso
        """
        return self._check_detection_criteria()
    
    def _check_detection_criteria(self) -> bool:
        """Verifica criterios de detección"""
        # Método 1: Device tree (más confiable)
        try:
            with open('/proc/device-tree/model', 'r') as f:
                model = f.read().strip()
                if 'Radxa Zero' in model:
                    logger.info(f"✅ Detected via device-tree: {model}")
                    return True
        except FileNotFoundError:
            logger.debug("/proc/device-tree/model not found, trying cpuinfo")
        
        # Método 2: cpuinfo (fallback)
        try:
            with open('/proc/cpuinfo', 'r') as f:
                content = f.read()
                if 'Amlogic' in content or 'S905Y2' in content:
                    logger.info("✅ Detected via cpuinfo: Amlogic S905Y2")
                    return True
        except FileNotFoundError:
            logger.debug("/proc/cpuinfo not found")
        
        return False
    
    def _get_hardware_info(self) -> HardwareInfo:
        """
        Auto-detecta hardware en runtime. NO hardcodear!
        
        Returns:
            HardwareInfo con specs auto-detectados
        """
        return HardwareInfo(
            # Inmutable: modelo CPU, arquitectura, GPU
            cpu_model="Amlogic S905Y2",
            cpu_arch=CPUArch.ARMV8,
            has_gpu=True,
            gpu_model="Mali-G31 MP2",
            
            # AUTO-DETECTADO en runtime:
            cpu_cores=self._detect_cpu_cores(),
            ram_gb=self._detect_ram_gb(),
            storage_gb=self._detect_storage_gb(),
        )
    
    @staticmethod
    def _detect_cpu_cores() -> int:
        """Detecta número de CPU cores\n        \n        Intenta:\n        1. os.cpu_count() (recomendado)\n        2. Fallback: 4 cores (spec Radxa Zero)\n        \"\"\"\n        try:\n            cores = os.cpu_count()\n            if cores:\n                logger.debug(f\"Detected CPU cores: {cores}\")\n                return cores\n        except Exception as e:\n            logger.warning(f\"Error detecting CPU cores: {e}\")\n        \n        logger.warning(\"Using fallback CPU cores: 4\")\n        return 4\n    \n    @staticmethod\n    def _detect_ram_gb() -> int:\n        \"\"\"Detecta GB de RAM desde /proc/meminfo\n        \n        Lee MemTotal y convierte de KB a GB.\n        \n        Returns:\n            int: GB de RAM (mínimo 1)\n        \"\"\"\n        try:\n            with open('/proc/meminfo', 'r') as f:\n                for line in f:\n                    if line.startswith('MemTotal:'):\n                        kb = int(line.split()[1])\n                        gb = max(1, int(round(kb / (1024 * 1024))))\n                        logger.debug(f\"Detected RAM: {gb}GB\")\n                        return gb\n        except Exception as e:\n            logger.warning(f\"Error reading /proc/meminfo: {e}\")\n        \n        logger.warning(\"Using fallback RAM: 4GB\")\n        return 4\n    \n    @staticmethod\n    def _detect_storage_gb() -> int:\n        \"\"\"Detecta GB de almacenamiento en root filesystem\n        \n        Ejecuta `df /` y extrae tamaño del bloque 1K (en KB).\n        Convierte de KB a GB.\n        \n        Returns:\n            int: GB de storage (mínimo 1)\n        \"\"\"\n        try:\n            output = subprocess.check_output(['df', '/'], text=True)\n            lines = output.strip().split('\\n')\n            if len(lines) >= 2:\n                # Formato: Filesystem 1K-blocks Used Available Use% Mounted\n                parts = lines[1].split()\n                kb = int(parts[1])  # 1K-blocks\n                gb = max(1, int(round(kb / (1024 * 1024))))\n                logger.debug(f\"Detected storage: {gb}GB\")\n                return gb\n        except Exception as e:\n            logger.warning(f\"Error executing df: {e}\")\n        \n        logger.warning(\"Using fallback storage: 32GB\")\n        return 32\n    \n    def detect_running_variant(self) -> Optional[VariantInfo]:\n        \"\"\"Detecta variante SO actual\n        \n        Lee /etc/os-release para nombre y versión, luego uname -r\n        para kernel.\n        \n        Soporta: Armbian, Ubuntu, Debian (cualquier distro arm64)\n        \n        Returns:\n            VariantInfo con SO/kernel detectados, None si error\n        \"\"\"\n        try:\n            # Lee /etc/os-release\n            distro = None\n            version = None\n            \n            with open('/etc/os-release', 'r') as f:\n                for line in f:\n                    if line.startswith('ID='):\n                        distro = line.split('=')[1].strip().strip('\"')\n                    elif line.startswith('VERSION_ID='):\n                        version = line.split('=')[1].strip().strip('\"')\n            \n            logger.debug(f\"Detected distro: {distro} {version}\")\n            \n            # Valida que sea soportado (arm64 basado en Debian/Armbian)\n            if not distro or distro.lower() not in ['armbian', 'ubuntu', 'debian']:\n                logger.warning(f\"Unsupported distro: {distro}\")\n                return None\n            \n            # Detecta kernel version\n            kernel_version = subprocess.check_output(\n                ['uname', '-r'], text=True\n            ).strip()\n            logger.debug(f\"Detected kernel: {kernel_version}\")\n            \n            # Retorna variante\n            return VariantInfo(\n                name=f\"{distro.capitalize()} {version or 'unknown'}\",\n                storage_type=StorageType.EMMC,  # Radxa Zero usa eMMC integrado\n                distro_family=(\n                    DistroFamily.ARMBIAN if distro.lower() == 'armbian'\n                    else DistroFamily.DEBIAN\n                ),\n                distro_version=version or \"unknown\",\n                kernel_version=kernel_version,\n                is_default=True,\n                \n                # Features soportados por Radxa Zero\n                video_sources=[\n                    VideoSourceFeature.V4L2,       # Cámaras USB, CSI\n                    VideoSourceFeature.LIBCAMERA,  # Libcamera (Armbian/Ubuntu)\n                ],\n                video_encoders=[\n                    VideoEncoderFeature.HARDWARE_H264,  # Hardware H.264 (SoC)\n                    VideoEncoderFeature.MJPEG,          # MJPEG (fallback)\n                    VideoEncoderFeature.X264_SOFTWARE,  # Software x264\n                ],\n                connectivity=[\n                    ConnectivityFeature.WIFI,       # WiFi 6\n                    ConnectivityFeature.USB_MODEM,  # Módems USB (E3372, etc)\n                    ConnectivityFeature.USB_3,      # USB 3.1 Type-C\n                ],\n                system_features=[\n                    SystemFeature.GPIO,  # GPIO via /sys/class/gpio\n                    SystemFeature.I2C,   # I2C para sensores\n                    SystemFeature.SPI,   # SPI para LCD/EEPROM\n                ]\n            )\n        \n        except FileNotFoundError:\n            logger.error(\"/etc/os-release not found\")\n            return None\n        except Exception as e:\n            logger.error(f\"Error detecting running variant: {e}\")\n            return None\n```

### Salida esperada al iniciar

**Con kernel current (default, recomendado - SIN HW H.264):**
```
2026-02-07 15:30:45 - app.providers.board.board_registry - INFO
    Discovering board providers in 'implementations/'...

2026-02-07 15:30:45 - app.providers.board.implementations.radxa.zero - INFO
    ✅ Detected via device-tree: Radxa Zero

2026-02-07 15:30:45 - app.providers.board.implementations.radxa.zero - INFO
    Detected Armbian CURRENT kernel: 6.12.58-current-meson64

2026-02-07 15:30:45 - app.providers.board.implementations.radxa.zero - INFO
    Using CURRENT kernel variant (recommended)

2026-02-07 15:30:45 - app.providers.board.board_registry - INFO
    ✅ Board detected: Radxa Zero (Amlogic S905Y2)
    - Hardware: 4 cores, 4GB RAM, 29GB storage, Mali-G31 MP2 GPU
    - Variant: Armbian current kernel
    - Kernel: 6.12.58-current-meson64
    - Video: V4L2, LibCamera → MJPEG, x264 software (sin HW H.264 en mainline)
    - Network: WiFi, USB modem, USB 3.x, Ethernet
    - Peripherals: GPIO, I2C, SPI
```

**Con kernel legacy (máximo HW support - CON HW H.264):**
```
2026-02-07 15:30:45 - app.providers.board.implementations.radxa.zero - INFO
    Detected Armbian LEGACY kernel: 5.15.25-legacy-meson64

2026-02-07 15:30:45 - app.providers.board.implementations.radxa.zero - INFO
    Using LEGACY kernel variant (máximo HW support)

2026-02-07 15:30:45 - app.providers.board.board_registry - INFO
    ✅ Board detected: Radxa Zero (Amlogic S905Y2)
    - Hardware: 4 cores, 4GB RAM, 29GB storage, Mali-G31 MP2 GPU
    - Variant: Armbian legacy kernel (máximo HW support)
    - Kernel: 5.15.25-legacy-meson64
    - Video: V4L2, LibCamera → H.264 HW ✅, MJPEG, x264 software
    - Network: WiFi, USB modem, USB 3.x, Ethernet
    - Peripherals: GPIO, I2C, SPI
```

---

## 🔧 Cómo usar BoardRegistry

### En servicios backend

```python
from providers.board import BoardRegistry

# Obtener instancia singleton
registry = BoardRegistry()

# Obtener board detectado
detected_board = registry.get_detected_board()

if detected_board:
    # Acceder a información
    print(f"Board: {detected_board.board_name}")
    print(f"CPU: {detected_board.hardware.cpu_cores} cores")
    print(f"RAM: {detected_board.hardware.ram_gb}GB")
    print(f"Storage: {detected_board.hardware.storage_gb}GB")
    
    # Acceder a features
    print(f"Video sources: {detected_board.variant.video_sources}")
    print(f"Video encoders: {detected_board.variant.video_encoders}")
    
    # Verificar soporte específico
    from board_definitions import VideoEncoderFeature
    has_hw_h264 = VideoEncoderFeature.HARDWARE_H264 in detected_board.variant.video_encoders
    print(f"Supports HW H.264: {has_hw_h264}")
else:
    print("No board detected - using defaults")
```

### Caso de uso: GStreamer elige codec según board

```python
# app/services/gstreamer_service.py
from providers.board import BoardRegistry
from board_definitions import VideoEncoderFeature

class GStreamerService:
    def _adapt_codec_to_board(self, preferred_codec: str) -> str:
        \"\"\"
        Selecciona codec disponible en esta placa.
        
        Fallback chain: HW H.264 → x264 → MJPEG
        \"\"\"
        registry = BoardRegistry()
        board = registry.get_detected_board()
        
        if not board:
            # Sin detección, usar preferido
            logger.warning("No board detected, using preferred codec")
            return preferred_codec
        
        available = board.variant.video_encoders
        
        # Preferencia: máxima eficiencia
        if VideoEncoderFeature.HARDWARE_H264 in available:
            logger.info("Using HW-accelerated H.264")
            return 'h264'
        elif VideoEncoderFeature.X264_SOFTWARE in available:
            logger.info("HW H.264 not available, falling back to x264")
            return 'x264'
        else:
            logger.info("Using MJPEG (fallback)")
            return 'mjpeg'
```

### Caso de uso: Endpoint API que expone board info

```python
# app/api/routes/system.py
from fastapi import APIRouter
from providers.board import BoardRegistry

router = APIRouter()

@router.get("/board")
async def get_board_info():
    \"\"\"Retorna información del board detectado\"\"\"
    registry = BoardRegistry()
    detected = registry.get_detected_board()
    
    if not detected:
        return {
            "success": False,
            "message": "No board detected - using defaults"
        }
    
    return {
        "success": True,
        "data": detected.to_dict()
    }
```

Respuesta ejemplo:
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

---

## 📱 Integración en frontend

### SystemView.jsx: Board Card

```jsx
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import api from '../../services/api'

export default function SystemView() {
  const { t } = useTranslation()
  const [boardInfo, setBoardInfo] = useState(null)
  const [boardLoading, setBoardLoading] = useState(true)
  
  useEffect(() => {
    loadBoard()
  }, [])
  
  const loadBoard = async () => {
    try {
      const response = await api.get('/system/board')
      if (response.success && response.data) {
        setBoardInfo(response.data)
      }
    } catch (error) {
      console.error('Error loading board info:', error)
    } finally {
      setBoardLoading(false)
    }
  }
  
  if (boardLoading) return <div>Loading board info...</div>
  if (!boardInfo) return null
  
  return (
    <div className="board-info-card">
      <h3>{boardInfo.board_name}</h3>
      <p className="board-model">{boardInfo.board_model}</p>
      
      <div className="board-hardware">
        <span>{boardInfo.hardware.cpu_cores} cores @ {boardInfo.hardware.cpu_model}</span>
        <span>{boardInfo.hardware.ram_gb}GB RAM</span>
        <span>{boardInfo.hardware.storage_gb}GB storage</span>
      </div>
      
      <div className="board-variant">
        <p>{boardInfo.variant.name}</p>
        <p>Kernel: {boardInfo.variant.kernel_version}</p>
      </div>
      
      <div className="board-features">
        {boardInfo.features.video_sources && (
          <div className="board-feature-group">
            <span className="board-feature-label">Video Sources:</span>
            <div className="board-feature-tags">
              {boardInfo.features.video_sources.map(f => (
                <span key={f} className="board-tag">{f}</span>
              ))}
            </div>
          </div>
        )}
        
        {boardInfo.features.video_encoders && (
          <div className="board-feature-group">
            <span className="board-feature-label">Video Encoders:</span>
            <div className="board-feature-tags">
              {boardInfo.features.video_encoders.map(f => (
                <span key={f} className="board-tag">{f}</span>
              ))}
            </div>
          </div>
        )}
        {/* Más features... */}
      </div>
    </div>
  )
}
```

---

## 🚀 Agregar nuevo board

### Paso 1: Crear estructura de archivos

```bash
mkdir -p app/providers/board/implementations/myboard/
touch app/providers/board/implementations/myboard/__init__.py
touch app/providers/board/implementations/myboard/model.py
```

### Paso 2: Implementar BoardProvider

```python
# app/providers/board/implementations/myboard/model.py
from ..board_provider import BoardProvider
from ..board_definitions import HardwareInfo, VariantInfo, ...

class MyBoardProvider(BoardProvider):
    @property
    def board_name(self) -> str:
        return "My Board Name"
    
    @property
    def board_identifier(self) -> str:
        return "myboard_vendor_chipset"
    
    def detect_board(self) -> bool:
        # Implementar detección específica
        # Ej: buscar en /proc/device-tree/, /proc/cpuinfo, lspci, dmidecode
        pass
    
    def _get_hardware_info(self) -> HardwareInfo:
        # ⚠️ IMPORTANTE: Auto-detectar, NO hardcodear
        # - CPU cores: os.cpu_count(), /proc/cpuinfo
        # - RAM: /proc/meminfo
        # - Storage: df /, lsblk
        pass
    
    def detect_running_variant(self) -> Optional[VariantInfo]:
        # Detectar SO actual y features soportados
        pass
```

### Paso 3: Verificar auto-discovery

```bash
python3 -c "from app.providers.board import BoardRegistry; \
            r = BoardRegistry(); \
            print(f'Registered providers: {[p.board_name for p in r._providers]}')"
```

Debería listar tu nuevo provider.

### Paso 4: Test manual

```bash
# Revisar logs
tail -f /var/log/fpvcopilot-sky/app.log

# Testear API
curl http://localhost:8000/api/system/board | jq

# Deben aparecer tus specs auto-detectados, no hardcoded
```

### Checklist

- [ ] Crear clase en `implementations/<marca>/<modelo>.py`
- [ ] Heredar de `BoardProvider`
- [ ] Implementar `board_name`, `board_identifier` (properties)
- [ ] Implementar `detect_board()` — conocer si esta placa está presente
- [ ] Implementar `_get_hardware_info()`:
  - [ ] **Auto-detectar** CPU cores (no hardcodear 4)
  - [ ] **Auto-detectar** RAM (no hardcodear 4GB)
  - [ ] **Auto-detectar** Storage (no hardcodear)
  - [ ] Solo hardcodear: CPU model, architecture, GPU model (inmutables)
- [ ] Implementar `detect_running_variant()` — SO/kernel actual
- [ ] Implementar `get_variants()` si hay múltiples configuraciones soportadas
- [ ] Test en hardware real
- [ ] Verificar logs de auto-discovery
- [ ] Testear `/api/system/board`

---

## 🐛 Troubleshooting

### BoardRegistry retorna None

**Síntoma**: `get_detected_board()` retorna None

**Diagnóstico**:
```bash
# 1. Revisar logs
journalctl -u fpvcopilot-sky -n 50

# 2. Test manual en Python
python3 << 'EOF'
from app.providers.board import BoardRegistry
r = BoardRegistry()
print(f"Providers found: {len(r._providers)}")
for p in r._providers:
    print(f"  - {p.board_name}: detect={p.detect_board()}")
print(f"Detected: {r.get_detected_board()}")
EOF
```

**Soluciones comunes**:
- ❌ Provider no se descubre: verificar nombre de clase (debe heredar `BoardProvider`)
- ❌ `detect_board()` retorna False: revisar criterios en `_check_detection_criteria()`
- ❌ Rutas incorrectas: usar imports relativos (`from ..board_provider`)

### Auto-detection devuelve valores incorrectos

**Síntoma**: `cpu_cores`, `ram_gb`, `storage_gb` valen números raros

**Diagnóstico**:
```bash
# Validar valores reales
cat /proc/cpuinfo | grep processor | wc -l         # cores
grep MemTotal /proc/meminfo                          # RAM
df / | tail -1 | awk '{print $2}'                    # Storage (KB)

# Comparar con lo que retorna el provider
python3 -c "from app.providers.board.implementations.radxa.zero import RadxaZeroProvider as R; \
            r = R(); \
            print(f'cores: {r._detect_cpu_cores()}'); \
            print(f'ram: {r._detect_ram_gb()}GB'); \
            print(f'storage: {r._detect_storage_gb()}GB')"
```

**Soluciones**:
- Revisar comandos en `_detect_*()` methods
- Verificar formato esperado (KB vs GB)
- Agregar fallbacks robustos

### Variante detectada incorrecta

**Síntoma**: `detect_running_variant()` retorna None o SO incorrecto

**Diagnóstico**:
```bash
cat /etc/os-release
uname -r
```

**Soluciones**:
- Agregar soporte para más distros
- Hacer menos estrictos los criterios (`distro.lower() in [...]`)

### Imports relativos causan ModuleNotFoundError

**Síntoma**: `from ...board_provider import BoardProvider` falla

**Causa**: Mixin de imports (relativos vs absolutos) durante auto-discovery

**Solución**:
```python
# ✅ Siempre usar imports relativos en implementations/
from ...board_provider import BoardProvider
from ...board_definitions import HardwareInfo

# ❌ Nunca usar absolutos aquí
from app.providers.board.board_provider import BoardProvider  # MAL!
```

---

## 📚 Referencias rápidas

### Leer specs del hardware

```bash
# CPU info
cat /proc/cpuinfo
lscpu
nproc

# RAM
grep MemTotal /proc/meminfo

# Storage
df -h /
lsblk

# Device tree
cat /proc/device-tree/model
cat /proc/device-tree/compatible

# OS
cat /etc/os-release
uname -a
```

### Logging en providers

```python
import logging
logger = logging.getLogger(__name__)

logger.info("Board detected successfully")
logger.warning("Feature not supported")
logger.error("Critical error occurred")
logger.debug("Debug info")
```

### DTOs disponibles

```python
from providers.board.board_definitions import (
    # Hardware
    HardwareInfo, CPUArch, 
    
    # Variante
    VariantInfo, StorageType, DistroFamily,
    
    # Features (enums)
    VideoSourceFeature,
    VideoEncoderFeature,
    ConnectivityFeature,
    SystemFeature,
)
```

---

**Última actualización**: 7 de febrero de 2026  
**Versión**: 1.0  
**Autor**: Development Team
