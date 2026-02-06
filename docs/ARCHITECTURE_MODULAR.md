# Arquitectura Modular de FPVCopilotSky

## 🎯 Objetivo
Abstraer la aplicación de dependencias específicas de hardware y proveedores, permitiendo:
- Ejecutar en diferentes placas Linux (Radxa Zero, RPi, x86, etc.)
- Usar múltiples proveedores VPN (Tailscale, ZeroTier, WireGuard)
- Usar múltiples modems/conexiones 4G (Huawei, ZTE, TP-Link, etc.)
- Operar en modos diferentes (HiLink, Router, Dongle/Stick)

## 📋 Auditoría de Hardcoding

### ✅ YA ABSTRAÍDO
- **VPN**: Existe `VPNProvider` base con `TailscaleProvider` implementado
- **Preferences**: Sistema de persistencia agnóstico

### ❌ NECESITA ABSTRACCIÓN
- **Modem**: `hilink_service.py` es específico a Huawei E3372h-153
- **Hardware Serial**: Paths hardcodeados (`/dev/ttyAML0`, `/dev/ttyUSB0`)
- **Network Interfaces**: Métodos específicos de detección en `network_service.py`
- **Configuración de Placa**: No existe diccionario de placas soportadas

### ⚠️ DISTRIBUIDO POR EL CÓDIGO
```
Radxa Zero específico:
- /dev/ttyAML0 (puerto serial principal)
- network_service.py busca "tailscale0" hardcodeado
- IPs, puertos, paths distribuidos

Huawei E3372h específico:
- hilink_service.py (1271 líneas monolíticas)
- Bandas LTE de Orange España
- Puerto 192.168.1.1 (router HiLink)
- huawei-lte-api como dependencia
```

## 🏗️ Propuesta Arquitectónica

### 1. ABSTRACCIÓN DE MODEM
```
ModemProvider (Base)
├── HilinkModemProvider (Huawei, ZTE, etc.)
├── RouterModemProvider (4G router como gateway)
└── DongleModemProvider (Modem USB sin interfaz web)
```

**Interfaz común:**
```python
class ModemProvider(ABC):
    @abstractmethod
    def is_available(self) -> bool
    
    @abstractmethod
    def get_status(self) -> Dict
    
    @abstractmethod
    def connect(self) -> Dict
    
    @abstractmethod
    def get_signal_strength(self) -> int
    
    @abstractmethod
    def get_network_info(self) -> Dict
```

### 2. ABSTRACCIÓN DE HARDWARE
```
HardwareProfile
├── board_name: str (radxa_zero, raspberry_pi, x86, etc.)
├── serial_ports: List[str] (paths a buscar en orden)
├── supported_modems: List[str]
├── default_vpn: Optional[str]
├── available_features: Dict[str, bool]
```

**Diccionario de placas:**
```python
HARDWARE_PROFILES = {
    'radxa_zero': HardwareProfile(
        board_name='Radxa Zero',
        serial_ports=['/dev/ttyAML0', '/dev/ttyS0', '/dev/ttyUSB*'],
        supported_modems=['hilink', 'router', 'dongle'],
        available_features={'wifi': True, 'ethernet': False}
    ),
    'raspberry_pi': HardwareProfile(
        board_name='Raspberry Pi',
        serial_ports=['/dev/ttyAMA0', '/dev/ttyUSB*'],
        supported_modems=['hilink', 'router', 'dongle'],
        available_features={'wifi': True, 'ethernet': True}
    ),
}
```

### 3. REGISTRY DE PROVEEDORES
```python
class ProviderRegistry:
    """Registro dinámico de proveedores VPN y Modem"""
    
    def register_vpn_provider(name: str, provider_class)
    def register_modem_provider(name: str, provider_class)
    def get_vpn_provider(name: str)
    def get_modem_provider(name: str)
    def list_available_vpn()
    def list_available_modem()
```

### 4. ABSTRACCIÓN DE RED
```
NetworkInterface (Base)
├── EthernetInterface
├── WiFiInterface
├── VPNInterface (Tailscale, ZeroTier, etc.)
└── ModemInterface (4G/LTE)

Properties:
- interface_name: str
- ip_address: str (v4/v6)
- gateway: str
- metric: int (para routing)
- status: enum (UP, DOWN, CONNECTING)
```

## 📁 Estructura de Directorios Propuesta

```
app/services/
├── providers/                    # ✨ NUEVO
│   ├── __init__.py
│   ├── base/
│   │   ├── modem_provider.py
│   │   ├── vpn_provider.py
│   │   └── network_interface.py
│   ├── modem/                    # Modems
│   │   ├── hilink/
│   │   │   ├── __init__.py
│   │   │   ├── huawei.py
│   │   │   └── zte.py
│   │   ├── router/
│   │   │   └── generic_router.py
│   │   └── dongle/
│   │       └── generic_dongle.py
│   ├── vpn/                      # Ya parcialmente existe
│   │   ├── tailscale.py
│   │   ├── zerotier.py
│   │   └── wireguard.py
│   └── registry.py               # Lo nuevo
│
├── hardware/                     # ✨ NUEVO
│   ├── __init__.py
│   ├── profiles.py              # Diccionario de placas
│   └── detector.py              # Auto-detectar placa
│
├── network/                      # ✨ REFACTORIZADO
│   ├── __init__.py
│   ├── interfaces.py            # Abstracciones de interfaces
│   └── manager.py               # Orquestación (antes network_service)
│
├── vpn_service.py               # ✨ REFACTORIZADO - usa registry
├── hilink_service.py            # ✨ DEPRECADO - migrar a providers/modem
├── network_service.py           # ✨ REFACTORIZADO - usa abstracciones
└── ...
```

## 🔄 Flujo de Inicialización

```
main.py
  ├─> DetectHardware()
  │   └─> Load HardwareProfile (auto o preferences.json)
  │
  ├─> InitProviderRegistry()
  │   ├─> Auto-detect disponibles
  │   └─> Cargar desde plugins
  │
  ├─> InitNetworkManager()
  │   ├─> Escanear interfaces
  │   └─> Auto-detectar modem activo
  │
  ├─> InitVPNService()
  │   ├─> Determinar proveedor (preferences)
  │   └─> Conectar si auto_connect=True
  │
└─> Ready!
```

## ✅ Ventajas

1. **Agnóstico de Hardware**: Funciona en cualquier placa Linux
2. **Plug & Play Providers**: Agregar nuevo modem/VPN sin modificar core
3. **Testeable**: Cada abstracción es mockeable
4. **Escalable**: Estructura lista para múltiples modems simultáneos
5. **Configurable**: Todo via preferences.json

## 📝 Migración Paso a Paso

### Fase 1: Abstracciones Base (Week 1)
- [ ] Crear `ModemProvider` base
- [ ] Crear `NetworkInterface` base

### Fase 2: Registry (Week 1)
- [ ] Implementar `ProviderRegistry`
- [ ] Refactorizar VPNService para usar registry

### Fase 3: Hardware Profiles (Week 2)
- [ ] Crear diccionario de placas
- [ ] Auto-detectar placa actual

### Fase 4: Modem Providers (Week 2)
- [ ] Extraer HilinkModemProvider de hilink_service.py
- [ ] Crear RouterModemProvider básico
- [ ] Crear DongleModemProvider básico

### Fase 5: Network Refactor (Week 3)
- [ ] Refactorizar network_service.py
- [ ] Implementar NetworkInterfaceManager

### Fase 6: Documentation & Testing (Week 4)
- [ ] Escribir guías de extensión
- [ ] Tests para cada proveedor

## 🎓 Ejemplo: Añadir ZeroTier

### Antes (actual):
```python
# En vpn_service.py, línea 52
class TailscaleProvider(VPNProvider):
    ...

# Hardcoded en network_service.py
if 'tailscale' in line.lower():
    ...
```

### Después (con módulos):
```python
# providers/vpn/zerotier.py
class ZeroTierProvider(VPNProvider):
    name = "zerotier"
    ...

# Registrar en main.py
registry.register_vpn_provider('zerotier', ZeroTierProvider)

# ¡Automáticamente disponible en toda la app!
```

## 🎓 Ejemplo: Añadir nueva placa

```python
# hardware/profiles.py
HARDWARE_PROFILES = {
    'jetson_nano': HardwareProfile(
        board_name='NVIDIA Jetson Nano',
        serial_ports=['/dev/ttyTHS1', '/dev/ttyUSB*'],
        supported_modems=['hilink', 'router', 'dongle'],
        available_features={'gpu': True, 'wifi': True}
    )
}

# Auto-detecta en startup, ya funciona!
```

## 📚 Referencias
- VPNProvider: `app/services/vpn_service.py` (ya existe)
- Preferences: `app/services/preferences.py`
- HiLink actual: `app/services/hilink_service.py` (a refactorizar)
