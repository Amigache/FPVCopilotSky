# Roadmap de Migración a Arquitectura Modular

## 📍 Estado Actual

### ✅ Implementado
- [x] Abstracciones base (`ModemProvider`, `VPNProvider`, `NetworkInterface`)
- [x] Sistema de registro (`ProviderRegistry`)
- [x] Documentación de arquitectura
- [x] Guía de implementación

### 🟠 Parcialmente Hecho
- [ ] VPNProvider base existe en `vpn_service.py` (ANTIGUO)
- [ ] TailscaleProvider implementado (ANTIGUO)
- [ ] HiLink service monolítico (NECESITA REFACTOR)

### ❌ TODO
- [ ] Migrar VPNProvider al nuevo sistema
- [ ] Crear HilinkModemProvider
- [ ] Crear RouterModemProvider
- [ ] Crear DongleModemProvider
- [ ] Crear NetworkInterfaceManager
- [ ] Hardware profiles

## 📅 Plan de Migración (Fases)

## FASE 0: Coexistencia (ACTUAL - 1 día)
**Objetivo**: Las abstracciones nuevas coexisten sin romper lo viejo

```
app/services/
├── vpn_service.py           ← Sigue siendo usado (ANTIGUO)
└── hilink_service.py        ← Sigue siendo usado (ANTIGUO)

app/providers/
├── base/                    ← Nuevas abstracciones
├── registry.py              ← Nuevo registry
└── (vacío - sin implementaciones)  ← Los proveedores irán aquí
```

**Cambios en main.py**: NINGUNO (todavía)

**Tests**: Funciona como antes

---

## FASE 1: Migración de VPNProvider (1-2 días)
**Objetivo**: Integrar VPNProvider antiguo con el nuevo registry

### Paso 1.1: Mover TailscaleProvider al nuevo sistema

```
app/providers/vpn/tailscale.py  ← Nuevo

# Extracto del antiguo vpn_service.py
class TailscaleProvider(VPNProvider):
    def is_installed(self) -> bool: ...
    # (método compatible con ambas interfaces)
```

### Paso 1.2: Actualizar main.py para registrar

```python
from providers import init_provider_registry
from providers.vpn.tailscale import TailscaleProvider

# En @app.on_event("startup"):
registry = init_provider_registry()
registry.register_vpn_provider('tailscale', TailscaleProvider)
```

### Paso 1.3: VPNService usa registry

```python
# vpn_service.py REFACTORIZADO
class VPNService:
    def __init__(self):
        self.registry = get_provider_registry()
    
    def get_status(self):
        provider = self.registry.get_vpn_provider(self.preferred_vpn)
        return provider.get_status() if provider else {...}
```

**Resultado**: VPNService trabaja con registry, pero código de clientes no cambia

---

## FASE 2: HiLink Modularización (2-3 días)
**Objetivo**: Extraer funcionalidad de hilink_service.py a ModemProviders

### Paso 2.1: Crear HilinkModemProvider base

```
app/providers/modem/hilink/__init__.py
app/providers/modem/hilink/base.py  ← Lógica común HiLink
app/providers/modem/hilink/huawei.py    ← HuaweiE3372hProvider
app/providers/modem/hilink/zte.py       ← ZTEProvider (futuro)
```

### Paso 2.2: HuaweiE3372hProvider

```python
# Extraer de hilink_service.py:
class HuaweiE3372hProvider(ModemProvider):
    def __init__(self):
        self.client = None
        # ... código de hilink_service.py
    
    def detect(self) -> bool:
        # Intentar conectar a 192.168.1.1
    
    def get_status(self) -> Dict:
        # Código de get_status_info()
    
    # ... etc
```

### Paso 2.3: Registrar en main.py

```python
from providers.modem.hilink.huawei import HuaweiE3372hProvider

registry.register_modem_provider('huawei_e3372h', HuaweiE3372hProvider)
```

**Resultado**: hilink_service.py se convierte en adaptador delgado del registry

---

## FASE 3: Network Services Refactor (2-3 días)
**Objetivo**: Abstraer network_service.py con NetworkInterface

### Paso 3.1: Crear interfaces de red

```
app/providers/network/__init__.py
app/providers/network/interfaces.py
```

### Paso 3.2: Implementar interfaces específicas

```python
class EthernetInterface(NetworkInterface):
    def __init__(self, name: str)
    
class WiFiInterface(NetworkInterface):
    def __init__(self, name: str)

class VPNInterface(NetworkInterface):
    def __init__(self, vpn_name: str)

class ModemInterface(NetworkInterface):
    def __init__(self, modem_name: str)
```

### Paso 3.3: NetworkManager orquesta

```python
class NetworkManager:
    def __init__(self):
        self.interfaces: Dict[str, NetworkInterface] = {}
        self.registry = get_provider_registry()
    
    def scan_interfaces(self):
        # Descubrir todas las interfaces disponibles
    
    def set_priority(self, interface: str, metric: int):
        # Cambiar métrica de enrutamiento
```

**Resultado**: Routing inteligente y agnóstico de interfaces

---

## FASE 4: Hardware Profiles (1-2 días)
**Objetivo**: Auto-detectar placa Linux

```
app/hardware/__init__.py
app/hardware/profiles.py
app/hardware/detector.py
```

### Paso 4.1: Diccionario de placas

```python
HARDWARE_PROFILES = {
    'radxa_zero': HardwareProfile(
        board_name='Radxa Zero',
        serial_ports=['/dev/ttyAML0', '/dev/ttyS0'],
        supported_modems=['huawei_e3372h', 'generic_router'],
    ),
    'raspberry_pi': HardwareProfile(
        board_name='Raspberry Pi 4',
        serial_ports=['/dev/ttyAMA0', '/dev/ttyUSB*'],
        supported_modems=['huawei_e3372h', 'generic_router', 'usb_dongle'],
    ),
}
```

### Paso 4.2: Auto-detector

```python
class HardwareDetector:
    @staticmethod
    def detect() -> str:
        # /proc/device-tree/model, /etc/os-release, etc.
        # Retorna: 'radxa_zero', 'raspberry_pi', etc.
    
    @staticmethod
    def get_profile(board_name: str) -> HardwareProfile:
        return HARDWARE_PROFILES.get(board_name, HARDWARE_PROFILES['generic'])
```

**Resultado**: Detecta automáticamente la placa

---

## FASE 5: Providers Iniciales (1-2 días)
**Objetivo**: Implementar proveedores comunes

### Paso 5.1: Modem providers

```
✅ HuaweiE3372hProvider (ya existe en hilink_service)
✅ GenericRouterProvider (gateway router 4G)
✅ USBDongleProvider (detectar dongles USB)
```

### Paso 5.2: VPN providers

```
✅ TailscaleProvider (existente)
⏳ ZeroTierProvider (template lista)
⏳ WireGuardProvider (template lista)
```

---

## Diagrama de Dependencias (Post-refactor)

```
main.py
  ├─> HardwareDetector ──> HardwareProfile
  │
  ├─> ProviderRegistry
  │   ├─> VPNProvider (Tailscale, ZeroTier, WireGuard)
  │   └─> ModemProvider (HiLink, Router, Dongle)
  │
  ├─> NetworkManager
  │   └─> NetworkInterface (Ethernet, WiFi, VPN, Modem)
  │
  ├─> VPNService (REFACTORIZADO)
  │   └─> registry.get_vpn_provider()
  │
  ├─> ModemService (NUEVO)
  │   └─> registry.get_modem_provider()
  │
  └─> Preferences
      └─> Almacena configuración elegida
```

---

## 🧪 Testing Strategy

### Fase 1: Unit Tests
```
tests/providers/
├── test_vpn_provider.py
├── test_modem_provider.py
├── test_registry.py
└── test_network_interface.py
```

### Fase 2: Integration Tests
```
tests/integration/
├── test_vpn_integration.py
├── test_modem_integration.py
└── test_network_integration.py
```

### Fase 3: End-to-End
```
Probar con hardware real:
- Radxa Zero + Huawei E3372h + Tailscale
- RPi 4 + Router 4G + ZeroTier
- x86 + USB Dongle + WireGuard
```

---

## 📋 Checklist de Completitud

### FASE 0 ✅ (DONE)
- [x] Abstracciones base creadas
- [x] ProviderRegistry implementado
- [x] Documentación escrita

### FASE 1 ⏳ (NEXT)
- [ ] Crear `app/providers/vpn/__init__.py`
- [ ] Mover TailscaleProvider a `app/providers/vpn/tailscale.py`
- [ ] Actualizar main.py para registrar
- [ ] Tests para registry
- [ ] Verificar que vpn_service.py sigue funcionando

### FASE 2 🔜
- [ ] Crear estructura `app/providers/modem/hilink/`
- [ ] Implementar HuaweiE3372hProvider
- [ ] Registrar en main.py
- [ ] Refactorizar hilink_service.py para usar registry
- [ ] Tests para modem detection

### FASE 3 🔜
- [ ] Crear abstracciones de NetworkInterface
- [ ] Refactorizar network_service.py
- [ ] Tests para interfaces

### FASE 4 🔜
- [ ] Crear app/hardware/profiles.py
- [ ] Implementar detector
- [ ] Agregar nuevas placas (RPi, x86)

### FASE 5 🔜
- [ ] Implementar proveedores comunes
- [ ] Tests end-to-end
- [ ] Documentación de extensión

---

## ⚠️ Notas Importantes

1. **Compatibilidad**: Durante toda la migración, el código antiguo debe seguir funcionando
2. **Gradual**: No romper nada entre fases
3. **Documentación**: Actualizar docs a medida que se migra
4. **Tests**: Cada fase debe tener tests pasandoantes de pasar a la siguiente

---

## 📞 Contacto para dudas

Revisardefecto en la documentación o planifica una fase específica si tienes dudas sobre la implementación.
