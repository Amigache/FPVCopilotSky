# Guía de Uso del Sistema Modular

## 🎯 Introducción

FPVCopilotSky ahora utiliza un sistema de **proveedores agnósticos** que permite agregar fácilmente nuevos modems, proveedores VPN y interfaces de red sin modificar el código core.

## 📦 Estructura

```
app/providers/
├── base/                    # Abstracciones base
│   ├── modem_provider.py   # Interfaz para modems
│   ├── vpn_provider.py     # Interfaz para VPN
│   └── network_interface.py # Interfaz para dispositivos de red
├── registry.py             # Registro central de proveedores
└── __init__.py            # Exports
```

## 🚀 Ejemplo: Crear un nuevo proveedor VPN (ZeroTier)

### 1. Crear archivo del proveedor

```python
# app/providers/vpn/zerotier.py

from providers.base import VPNProvider
from typing import Dict, List, Optional
import subprocess
import json
import logging

logger = logging.getLogger(__name__)

class ZeroTierProvider(VPNProvider):
    def __init__(self):
        super().__init__()
        self.name = "zerotier"
        self.display_name = "ZeroTier"
    
    def is_installed(self) -> bool:
        try:
            result = subprocess.run(
                ['which', 'zerotier-cli'],
                capture_output=True,
                timeout=2
            )
            return result.returncode == 0
        except:
            return False
    
    def get_status(self) -> Dict:
        if not self.is_installed():
            return {
                'success': False,
                'installed': False,
                'error': 'ZeroTier not installed'
            }
        
        try:
            # Ejemplo: leer estado de ZeroTier
            result = subprocess.run(
                ['zerotier-cli', 'status'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # Parsear resultado... (implementar lógica específica)
            lines = result.stdout.strip().split('\n')
            
            return {
                'success': True,
                'installed': True,
                'connected': len(lines) > 0,
                'peers': len(lines),
                'message': 'ZeroTier status retrieved'
            }
        except Exception as e:
            return {
                'success': False,
                'installed': True,
                'error': str(e)
            }
    
    def connect(self) -> Dict:
        # Implementar lógica de conexión
        pass
    
    def disconnect(self) -> Dict:
        # Implementar lógica de desconexión
        pass
    
    def get_info(self) -> Dict:
        return {
            'name': 'ZeroTier',
            'version': '1.x.x',
            'capabilities': ['peer_management', 'network_selection']
        }
    
    def get_peers(self) -> List[Dict]:
        # Implementar obtención de peers
        return []
```

### 2. Registrar el proveedor en main.py

```python
# app/main.py

from providers import init_provider_registry
from providers.vpn.zerotier import ZeroTierProvider
from providers.vpn.tailscale import TailscaleProvider

# Durante startup:
registry = init_provider_registry()

# Registrar proveedores VPN disponibles
registry.register_vpn_provider('tailscale', TailscaleProvider)
registry.register_vpn_provider('zerotier', ZeroTierProvider)  # ¡Nuevo!

# Ahora ZeroTier está disponible automáticamente en toda la app
```

### 3. Usar en cualquier parte del código

```python
from providers import get_provider_registry

# Obtener lista de VPN disponibles
registry = get_provider_registry()
vpns = registry.get_available_vpn_providers()
# Resultado: [{'name': 'tailscale', ...}, {'name': 'zerotier', ...}]

# Usar un proveedor específico
zerotier = registry.get_vpn_provider('zerotier')
status = zerotier.get_status()
```

## 🌐 Ejemplo: Crear un nuevo proveedor de Modem (TP-Link M7200)

### 1. Crear archivo del proveedor

```python
# app/providers/modem/hilink/tp_link.py

from providers.base import ModemProvider, ModemStatus, ModemInfo, NetworkInfo
from typing import Dict, Optional
import requests
import logging

logger = logging.getLogger(__name__)

class TPLinkM7200Provider(ModemProvider):
    """TP-Link M7200 HiLink modem provider"""
    
    def __init__(self):
        super().__init__()
        self.name = "tp_link_m7200"
        self.display_name = "TP-Link M7200"
        self.base_url = "http://192.168.0.1"  # TP-Link usa 192.168.0.1
    
    def detect(self) -> bool:
        """Detectar si el modem TP-Link está disponible"""
        try:
            response = requests.get(
                f"{self.base_url}/",
                timeout=2
            )
            self.is_available = response.status_code == 200
            return self.is_available
        except:
            self.is_available = False
            return False
    
    def get_status(self) -> Dict:
        if not self.detect():
            return {'available': False, 'status': ModemStatus.UNAVAILABLE}
        
        try:
            info = self.get_modem_info()
            network = self.get_network_info()
            
            return {
                'available': True,
                'status': ModemStatus.CONNECTED if network.status == ModemStatus.CONNECTED else ModemStatus.DISCONNECTED,
                'modem_info': info,
                'network_info': network,
                'error': None
            }
        except Exception as e:
            return {
                'available': False,
                'status': ModemStatus.ERROR,
                'error': str(e)
            }
    
    def get_modem_info(self) -> Optional[ModemInfo]:
        # Implementar lectura de info desde TP-Link API
        pass
    
    def get_network_info(self) -> Optional[NetworkInfo]:
        # Implementar lectura de estado de red
        pass
    
    # ... resto de métodos abstractos
```

### 2. Registrar en main.py

```python
from providers import init_provider_registry
from providers.modem.hilink.tp_link import TPLinkM7200Provider
from providers.modem.hilink.huawei import HuaweiE3372hProvider

registry = init_provider_registry()

# Registrar modems HiLink
registry.register_modem_provider('huawei_e3372h', HuaweiE3372hProvider)
registry.register_modem_provider('tp_link_m7200', TPLinkM7200Provider)  # ¡Nuevo!
```

## 🔌 Ejemplo: Usar un Modem Genérico como Router

```python
# app/providers/modem/router.py

from providers.base import ModemProvider
from typing import Dict

class GenericRouterProvider(ModemProvider):
    """Soporte genérico para routers 4G/LTE como gateway"""
    
    def __init__(self, gateway_ip: str = "192.168.1.1"):
        super().__init__()
        self.name = "generic_router"
        self.display_name = "Generic 4G Router"
        self.gateway_ip = gateway_ip
    
    def detect(self) -> bool:
        """Detectar si hay un router disponible en la puerta de enlace"""
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex((self.gateway_ip, 80))
            sock.close()
            self.is_available = (result == 0)
            return self.is_available
        except:
            return False
    
    # ... implementar resto de métodos
```

## 📱 Ejemplo: Usar un USB Dongle

```python
# app/providers/modem/dongle.py

from providers.base import ModemProvider
from typing import Dict

class USBDongleProvider(ModemProvider):
    """Soporte genérico para USB dongles 4G/LTE"""
    
    def __init__(self):
        super().__init__()
        self.name = "usb_dongle"
        self.display_name = "USB 4G Dongle"
    
    def detect(self) -> bool:
        """Detectar dongles USB"""
        # Buscar dispositivos USB con identificadores de modem
        # Implementar lógica de detección...
        pass
    
    # ... implementar métodos usando libusb, etc.
```

## 🏥 Consultar disponibilidad de proveedores

```python
from providers import get_provider_registry

registry = get_provider_registry()

# VPNs disponibles
vpn_list = registry.get_available_vpn_providers()
print("VPN providers:")
for vpn in vpn_list:
    print(f"  - {vpn['name']}: {vpn['installed']}")

# Modems disponibles
modem_list = registry.get_available_modem_providers()
print("Modem providers:")
for modem in modem_list:
    print(f"  - {modem['name']}: {modem['available']}")
```

## 📡 Integración en endpoints API

```python
# API para listar proveedores disponibles
@app.get("/api/vpn/available-providers")
async def get_available_vpn_providers():
    registry = get_provider_registry()
    return registry.get_available_vpn_providers()

@app.get("/api/modem/available-providers")
async def get_available_modem_providers():
    registry = get_provider_registry()
    return registry.get_available_modem_providers()
```

## 🎓 Checklist para crear un nuevo proveedor

- [ ] Crear clase que hereda de la abstracción base
- [ ] Implementar todos los métodos abstractos
- [ ] Agregar logging apropiado
- [ ] Manejar excepciones y timeouts
- [ ] Registrar en main.py
- [ ] Probar con `detect()` primero
- [ ] Agregar tests unitarios
- [ ] Documentar en README

## ✅ Beneficiosciones

- ✅ **Agnóstico**: Funciona en cualquier placa Linux
- ✅ **Extensible**: Agregar nuevos proveedores sin tocar core
- ✅ **Testeable**: Mockear proveedores fácilmente
- ✅ **Hot-swappable**: Cambiar de proveedor en tiempo de ejecución
- ✅ **Auto-discovery**: Detectar proveedores disponibles automáticamente
