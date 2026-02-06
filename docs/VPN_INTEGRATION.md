# 🔐 VPN Integration - Tailscale

Documentación del sistema VPN integrado en FPV Copilot Sky usando Tailscale.

## 🎯 ¿Para Qué Sirve?

El sistema VPN te permite acceder a tu drone y telemetría desde **cualquier lugar del mundo** de forma segura:

- ✅ Acceso remoto a la WebUI sin abrir puertos
- ✅ Streaming de telemetría sobre internet
- ✅ Red privada entre tus dispositivos (móvil, PC, Radxa)
- ✅ Conexión cifrada automáticamente
- ✅ No necesitas IP pública ni configurar router

## 🌐 ¿Qué es Tailscale?

Tailscale es una **VPN mesh moderna** que:
- Crea una red privada entre tus dispositivos
- Cada dispositivo obtiene una IP privada (100.x.x.x)
- Funciona a través de NATs y firewalls (sin configuración)
- Usa WireGuard (protocolo VPN moderno y rápido)
- Gratis para uso personal (hasta 100 dispositivos)

## 🏗️ Arquitectura

```
┌──────────────┐         Internet          ┌──────────────┐
│  Tu Móvil    │◄─────────────────────────►│  Radxa Zero  │
│  (VPN activa)│      Conexión segura       │  (Drone Sky) │
│ 100.x.x.1    │      punto a punto         │ 100.x.x.2    │
└──────────────┘                            └──────────────┘
      │                                            │
      │  Acceso directo vía VPN                   │
      ▼                                            ▼
http://100.x.x.2              Mission Planner/QGC conecta a:
     (WebUI)                  udp://100.x.x.2:14550
```

## 📦 Instalación de Tailscale

### Automática (Recomendado)

El instalador principal ya incluye Tailscale:

```bash
cd /opt/FPVCopilotSky
bash install.sh
```

### Manual

```bash
# Instalar Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# Configurar permisos sudo
bash /opt/FPVCopilotSky/scripts/setup-tailscale-sudoers.sh
```

## 🚀 Uso desde la Interfaz

### Conectar por Primera Vez

1. **Abrir la WebUI** del drone (conectado localmente)
2. **Ir a la pestaña VPN**
3. **Click en "Conectar"**
4. **Aparecer un código QR y una URL**
5. **Escanear el QR o copiar la URL** desde tu móvil/PC
6. **Autenticarse** con tu cuenta (Google, Microsoft, GitHub...)
7. **¡Listo!** La VPN se conecta automáticamente

### Usar la VPN

Una vez conectado:
- La interfaz muestra la IP VPN del Radxa (ej: `100.97.169.80`)
- Puedes ver los **peers conectados** (otros dispositivos)
- Accede a la WebUI usando la IP VPN desde cualquier lugar

### Configurar Telemetría Remota

1. **Ve a la pestaña "Telemetría"**
2. **Crea una salida** (UDP o TCP)
3. **Usa el selector de IPs** (botón dropdown) para elegir un peer VPN
4. **Selecciona tu PC o móvil** de la lista
5. **Se auto-rellena la IP** del peer seleccionado
6. **Crea la salida** y conecta Mission Planner/QGC a esa IP

### Configurar Video Remoto

1. **Ve a la pestaña "Video"**
2. **En "IP Destino"**, usa el selector de peers VPN
3. **Selecciona tu dispositivo** de la lista
4. **Configura el puerto** (ej: 5600)
5. **Aplica y Start Stream**

## 🔑 Permisos Sudo (Importante)

Tailscale requiere permisos sudo para conectar/desconectar. El sistema está configurado para permitir comandos específicos sin contraseña:

**Archivo:** `/etc/sudoers.d/fpvcopilot-tailscale`

```bash
# Permite tailscale up/down sin contraseña
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/bin/tailscale up *
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/bin/tailscale down
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/bin/tailscale status *
```

**Configurar manualmente:**
```bash
sudo bash /opt/FPVCopilotSky/scripts/setup-tailscale-sudoers.sh
```

## 🛠️ Arquitectura Técnica

### Backend

**Archivo:** `app/services/vpn_service.py`

Sistema basado en **Provider Pattern** (extensible para ZeroTier, WireGuard, etc.):

```python
# Abstract base class
class VPNProvider:
    def is_installed() -> bool
    def get_status() -> dict
    def connect() -> dict
    def disconnect() -> dict
    def get_peers() -> list  # Lista de nodos VPN

# Implementación Tailscale
class TailscaleProvider(VPNProvider):
    # Usa: tailscale status --json
    # Parse: IPs, peers, estado de backend
```

**API Endpoints:**
- `GET /api/vpn/status` - Estado actual
- `POST /api/vpn/connect` - Iniciar conexión
- `POST /api/vpn/disconnect` - Desconectar
- `GET /api/vpn/peers` - Lista de nodos en la red VPN

### Frontend

**Archivo:** `frontend/client/src/components/Pages/VPNView.jsx`

Características:
- Detección automática de estado via WebSocket
- Polling de autenticación (mientras espera auth)
- QR code generation para URL de auth
- Lista de peers con estado online/offline

**Componente PeerSelector:**

Selector de IPs VPN reutilizable:
- `frontend/client/src/components/PeerSelector/PeerSelector.jsx`
- Usado en TelemetryView y VideoView
- Auto-completa IPs de peers VPN
- Filtra solo peers online

## 📡 Estados de Tailscale

### Backend State

- **`Running`**: Conectado y funcionando
- **`Stopped`**: Desconectado
- **`NeedsLogin`**: Requiere autenticación
- **`Starting`**: Iniciando conexión
- **`NoState`**: Estado desconocido

### Connection Flow

```
1. Usuario click "Conectar"
   ↓
2. Backend: tailscale up --authkey=... --qr
   ↓
3. Parse auth URL del output
   ↓
4. Frontend: Muestra QR + URL
   ↓
5. Usuario autentica en móvil/PC
   ↓
6. Tailscale detecta auth exitosa
   ↓
7. Backend: status=connected, IP asignada
   ↓
8. Frontend: Muestra IP + peers
```

## 🔄 Auto-Conexión

El servicio intenta reconectar automáticamente al arrancar:

```python
# app/main.py - startup_event()
def auto_connect_vpn():
    time.sleep(2)  # Espera sistema estable
    status = vpn_service.get_status()
    
    if status['authenticated'] and not status['connected']:
        vpn_service.connect()
```

## 🐛 Troubleshooting

### Tailscale no instalado

```bash
# Instalar manualmente
curl -fsSL https://tailscale.com/install.sh | sh

# Verificar
tailscale version
```

### No puede conectar (Permission denied)

```bash
# Configurar permisos sudo
sudo bash /opt/FPVCopilotSky/scripts/setup-tailscale-sudoers.sh

# Verificar
sudo -l | grep tailscale
```

### Auth URL no aparece

```bash
# Ver logs del servicio
sudo journalctl -u fpvcopilot-sky -f | grep tailscale

# Intentar manualmente
sudo tailscale up --qr
```

### No ve peers

```bash
# Verificar estado
tailscale status

# Ver JSON completo
tailscale status --json

# Verificar que otros dispositivos estén conectados
# desde tu móvil/PC: abrir app Tailscale
```

### Peers muestran "localhost"

Resuelto en v1.0.0: El sistema ahora usa `DNSName` en lugar de `HostName`:

```python
# Prefer DNSName (more reliable)
dns_name = peer.get('DNSName', '')  # "device.tail1234.ts.net."
display_name = dns_name.split('.')[0]  # "device"
```

## 🔮 Futuro: Soportar Más Providers

El sistema está diseñado para soportar múltiples VPN providers:

```python
# Añadir ZeroTier
class ZeroTierProvider(VPNProvider):
    def is_installed(self):
        return shutil.which("zerotier-cli") is not None
    
    def get_status(self):
        # zerotier-cli listnetworks...
        pass

# Registrar provider
vpn_service.register_provider("zerotier", ZeroTierProvider())
```

## 📚 Recursos

- [Tailscale Docs](https://tailscale.com/kb/)
- [Tailscale CLI Reference](https://tailscale.com/kb/1080/cli/)
- [WireGuard Protocol](https://www.wireguard.com/)

## 🔐 Seguridad

### Lo que hace Tailscale

- ✅ Cifrado end-to-end (ChaCha20-Poly1305)
- ✅ Autenticación mutual de dispositivos
- ✅ Claves rotadas automáticamente
- ✅ No hay servidor central con acceso a tu tráfico

### Lo que NO hace

- ❌ No protege tu WiFi/4G local (usa HTTPS para eso)
- ❌ No es un firewall (sigue protegiendo otros servicios)
- ❌ No oculta tu IP pública (no es una VPN comercial como NordVPN)

---

**¿Preguntas?** Consulta [Tailscale KB](https://tailscale.com/kb/) o abre un issue en GitHub.
