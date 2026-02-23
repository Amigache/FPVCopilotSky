# 📥 Guía de Instalación

Guía completa para instalar FPV Copilot Sky en un SBC Linux (Radxa Zero, Raspberry Pi, Orange Pi, x86…).

---

## 1. Requisitos previos

### Hardware

| Componente     | Mínimo            | Recomendado                     |
| -------------- | ----------------- | ------------------------------- |
| SBC Linux      | 1 GB RAM, ARM/x86 | Radxa Zero 2 GB                 |
| Almacenamiento | MicroSD 16 GB     | MicroSD 32 GB                   |
| Cámara         | USB UVC           | Logitech C920 o similar         |
| Modem 4G       | —                 | Huawei E3372h / E8372h (HiLink) |
| Conexión al FC | UART o USB-serie  | Cable directo al UART del FC    |

### Software

- **SO**: Debian 11+, Ubuntu 22.04+, o Armbian
- **Acceso**: SSH o terminal local
- **Usuario**: con permisos sudo

### Conexiones físicas

```
  Controlador de vuelo
         │ UART / USB
         ▼
   ┌────────────┐      ┌──────────┐
   │  SBC Linux │──USB─│ Cámara   │
   │ (Radxa...) │──USB─│ Modem 4G │
   │            │──WiFi─ Red local │
   └────────────┘
```

---

## 2. Instalación

### 2.1 Clonar el repositorio

```bash
cd /opt
sudo git clone https://github.com/Amigache/FPVCopilotSky.git
cd FPVCopilotSky
sudo chown -R $(whoami):$(whoami) .
```

### 2.2 Instalar dependencias del sistema

```bash
bash install.sh
```

Este script instala y configura automáticamente (~15 minutos):

#### 👤 Creación del Usuario del Sistema

**El script crea automáticamente el usuario `fpvcopilotsky` si no existe:**

- Usuario dedicado para ejecutar el servicio systemd
- Solicita establecer una contraseña durante la instalación
- Añadido automáticamente a los grupos:
  - `dialout` - Acceso a puertos serie (MAVLink)
  - `video` - Acceso a cámaras
  - `netdev` - Gestión de dispositivos de red
  - `sudo` - Administración del sistema
- Propiedad del directorio `/opt/FPVCopilotSky` asignada al usuario

> **Nota**: Si ya tienes el usuario `fpvcopilotsky`, el script lo detecta y salta este paso.

#### Dependencias del Sistema (APT)

**Esenciales**:

- Python 3, pip, venv, dev tools
- pkg-config, curl, net-tools, iproute2

**GStreamer** (video streaming):

- `gstreamer1.0-tools` - Herramientas CLI
- `gstreamer1.0-plugins-{base,good,bad,ugly,libav}` - Plugins
- `gir1.2-gstreamer-1.0`, `python3-gi` - Bindings Python
- Plugins críticos: `jpegenc`, `x264enc`, `v4l2src`, `rtpjpegpay`, `rtph264pay`

**FFmpeg & WebRTC**:

- `libavcodec-dev`, `libavformat-dev`, `libavutil-dev` - Codecs
- `libswscale-dev`, `libswresample-dev`, `libavfilter-dev` - Procesamiento
- `libsrtp2-dev` - RTP seguro (WebRTC)
- `libopus-dev` - Codec de audio
- `libvpx-dev` - VP8/VP9 video
- `ffmpeg`, `v4l-utils` - Herramientas

**Red & Conectividad**:

- `network-manager`, `modemmanager` - Gestión de red
- `hostapd`, `wireless-tools` - WiFi
- `usb-modeswitch` - Modems USB
- `ethtool` - Configuración de interfaces

**Web Server**: `nginx`

**Node.js 20**: Para compilar frontend

#### Permisos y Configuración

**Grupos de usuario**:

```bash
# El script agrega el usuario a estos grupos automáticamente
dialout  # Acceso a puertos serie (MAVLink)
video    # Acceso a cámaras
```

**Permisos sudo sin contraseña** (`/etc/sudoers.d/`):

- **fpvcopilot-wifi**: WiFi, red, routing (nmcli, ip route, iw)
- **fpvcopilot-system**: Servicios, logs, sysctl, ethtool, dnsmasq
- **tailscale**: VPN management (up, down, status)

**Optimizaciones del sistema** (`/etc/sysctl.d/99-fpv-streaming.conf`):

- TCP BBR congestion control
- Buffers TCP/UDP optimizados (134 MB)
- Network backlog aumentado
- IPv6 deshabilitado
- swappiness=10

**Puertos serie**:

- Reglas udev para `/dev/ttyAML*`, `/dev/ttyS*`, `/dev/ttyUSB*`, `/dev/ttyACM*`
- `serial-getty@ttyAML0` y `serial-getty@ttyS4` deshabilitados (evita conflictos con MAVLink)
- En **Radxa Zero 3W (Armbian)** se habilita automáticamente el overlay `rk3568-uart4-m1`
  para exponer UART4_M1 (requiere reinicio)

> **Nota**: El entorno virtual se crea con `--system-site-packages` para acceder a GStreamer (PyGObject).
> Requiere **reiniciar sesión** después de la instalación para que los grupos dialout/video tomen efecto.

### 2.3 Despliegue a producción

Después de `install.sh`, usa el **CLI de gestión** para desplegar:

```bash
./fpv
```

Selecciona la opción **"Deploy to Production"** del menú.

O manualmente:

```bash
bash scripts/deploy.sh
```

Esto:

- Compila el frontend React
- Instala el servicio systemd `fpvcopilot-sky`
- Configura nginx como proxy inverso
- Arranca el servicio
- Ejecuta un health-check automático

---

## 3. CLI de Gestión

FPVCopilotSky incluye una interfaz de línea de comandos interactiva:

```bash
cd /opt/FPVCopilotSky
./fpv
```

### Funciones del CLI

📦 **Instalación & Despliegue**

- Instalar dependencias del sistema
- Desplegar a producción

🛠️ **Desarrollo**

- Iniciar modo desarrollo con hot-reload
- Ejecutar suite de tests

📊 **Diagnóstico**

- Estado del sistema completo
- Verificación pre-vuelo exhaustiva
- Logs en tiempo real

⚙️ **Configuración**

- Configurar modem USB 4G
- Configurar puertos serie MAVLink
- Actualizar permisos sudo
- Test de gestión de red

🔧 **Mantenimiento**

- Rollback de cambios de red (emergencia)
- Reiniciar/detener servicio

> **Tip**: El CLI es la forma más fácil de gestionar el sistema. Todos los scripts en `scripts/` están accesibles desde el menú.

---

## 4. Verificación

### 4.1 Pre-flight check exhaustivo

Usa el **CLI**:

```bash
./fpv
# Selecciona opción 6: "Pre-flight Check"
```

O manualmente:

```bash
bash scripts/preflight-check.sh
```

Verifica **todas** las dependencias, permisos y configuraciones antes de volar:

- ✅ Dependencias del sistema (Python, GStreamer, FFmpeg, herramientas de red)
- ✅ Plugins GStreamer críticos
- ✅ Bibliotecas WebRTC (libsrtp2, libopus, libvpx)
- ✅ Python venv y paquetes críticos (fastapi, pymavlink, aiortc, av)
- ✅ Grupos de usuario (dialout, video)
- ✅ Permisos sudo sin contraseña
- ✅ Archivos sudoers configurados
- ✅ Configuración de red (NetworkManager, wlan0)
- ✅ Puertos serie y serial-getty
- ✅ Dispositivos de video
- ✅ Frontend build
- ✅ Servicios systemd
- ✅ Optimizaciones del sistema

Salida:

```
✅ ALL CHECKS PASSED
System is ready for flight! 🚀
```

### 4.2 Script de estado

Usa el **CLI**:

```bash
./fpv
# Selecciona opción 5: "System Status"
```

O manualmente:

```bash
bash scripts/status.sh
```

Muestra: estado del servicio, puertos, dependencias, USB, red, modem, VPN, conectividad.

### 4.3 Verificación manual

```bash
# Servicio activo
sudo systemctl status fpvcopilot-sky

# Backend responde
curl -s http://localhost:8000/api/status/health

# Frontend accesible
curl -s -o /dev/null -w "%{http_code}" http://localhost/
# Debe devolver 200
```

### 4.4 Acceder a la WebUI

Abre en el navegador:

```
http://<IP-DE-TU-SBC>
```

Obtén la IP con `hostname -I`.

---

## 5. Configuración del modem 4G (opcional)

Si usas un modem Huawei HiLink USB:

Usa el **CLI**:

```bash
./fpv
# Selecciona opción 8: "Configure USB Modem"
```

O manualmente:

```bash
bash scripts/configure-modem.sh
```

El script:

1. Detecta el modem Huawei por USB (vendor `12d1`)
2. Si está en modo almacenamiento masivo, ejecuta `usb_modeswitch` para cambiarlo a modo modem
3. Verifica que ModemManager lo detecte
4. Comprueba la interfaz de red HiLink (típicamente `enx*`) y la puerta de enlace `192.168.8.1`

**Verificar manualmente:**

```bash
lsusb | grep -i huawei                  # Debe aparecer el dispositivo
ip link show | grep enx                 # Interfaz HiLink
ping -c 1 192.168.8.1                   # API del modem
curl -s http://192.168.8.1/api/device/information  # Info del modem
```

---

## 6. Configuración de Tailscale VPN (opcional)

Si `install.sh` ya instaló Tailscale, los permisos sudo están configurados. Para conectar:

1. Abre la WebUI → pestaña **VPN**
2. Pulsa **Conectar** → se genera una URL de autenticación
3. Abre la URL en cualquier navegador, autentica con tu cuenta Tailscale
4. El dispositivo se une a tu red mesh

O desde terminal:

```bash
sudo tailscale up                   # Genera URL de auth
sudo tailscale status               # Ver estado
```

**Sudoers configurados** en `/etc/sudoers.d/tailscale`:

```
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/bin/tailscale up
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/bin/tailscale up *
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/bin/tailscale down
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/bin/tailscale logout
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/bin/tailscale status
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/bin/tailscale status *
```

---

## 7. Actualización

```bash
cd /opt/FPVCopilotSky
git pull
./fpv
# Selecciona opción 2: "Deploy to Production"
```

O manualmente:

```bash
bash scripts/deploy.sh
```

---

## 8. Estructura de servicios

### Systemd

| Servicio                 | Descripción                            |
| ------------------------ | -------------------------------------- |
| `fpvcopilot-sky.service` | Backend FastAPI (uvicorn :8000)        |
| `nginx`                  | Servidor web, proxy inverso, WebSocket |

```bash
sudo systemctl status fpvcopilot-sky    # Estado
sudo systemctl restart fpvcopilot-sky   # Reiniciar
sudo journalctl -u fpvcopilot-sky -f    # Logs
```

### Nginx

- Sirve el frontend estático desde `frontend/client/dist/`
- Proxy `/api/*` → `http://127.0.0.1:8000`
- Proxy WebSocket `/ws` → `ws://127.0.0.1:8000/ws` (timeout 7 días)
- Compresión gzip, caché de assets estáticos (1 año)
- Config: `/etc/nginx/sites-available/fpvcopilot-sky`

### Puertos

| Puerto | Servicio                                   |
| ------ | ------------------------------------------ |
| 80     | Nginx (HTTP)                               |
| 8000   | FastAPI (backend)                          |
| 5600   | Video RTP/UDP (streaming saliente)         |
| 8554   | RTSP Server (solo cuando modo RTSP activo) |

---

## 9. Solución de problemas de instalación

### "Welcome to nginx" en vez de la WebUI

```bash
sudo rm /etc/nginx/sites-enabled/default
sudo ln -sf /etc/nginx/sites-available/fpvcopilot-sky /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

> Esto ya lo hace `install-production.sh`, pero puede reaparecer tras actualizar nginx.

### Backend no arranca

```bash
sudo journalctl -u fpvcopilot-sky -n 50 --no-pager   # Ver últimos logs
sudo systemctl restart fpvcopilot-sky
```

### Modem no detectado

```bash
lsusb                                   # ¿Aparece Huawei?
bash scripts/configure-modem.sh         # Reconfigura usb_modeswitch
sudo systemctl restart ModemManager
```

### Puerto serie ocupado

```bash
sudo fuser /dev/ttyAML0                 # ¿Quién lo usa?
sudo systemctl stop serial-getty@ttyAML0
sudo systemctl disable serial-getty@ttyAML0
```

### Permisos insuficientes

```bash
groups                                  # Debe incluir dialout, video
sudo usermod -aG dialout,video $(whoami)
# Requiere cerrar sesión y volver a entrar
```

---

## 4. Scripts de utilidad

Después de instalar, tienes scripts auxiliares disponibles en `scripts/`:

| Script                           | Propósito                                                    | Cuándo usarlo                                                                     |
| -------------------------------- | ------------------------------------------------------------ | --------------------------------------------------------------------------------- |
| **`deploy.sh`**                  | Compila frontend, reinstala systemd/nginx, reinicia servicio | Después de cambios en frontend o backend; despliegue a producción                 |
| **`dev.sh`**                     | Inicia backend con hot-reload y frontend dev server          | Desarrollo local; requiere dos terminales                                         |
| **`status.sh`**                  | Diagnosis completa: servicios, logs, conexiones, recursos    | Troubleshooting; para entender el estado actual                                   |
| **`configure-modem.sh`**         | Detecta e inicializa modem Huawei HiLink y CSQ/RSSI          | Si el modem no se detecta automáticamente en `status.sh`                          |
| **`setup-system-sudoers.sh`**    | Configura permisos sudo para network/modem/tailscale         | Reparar permisos si algunos comandos fallan; `install.sh` lo hace automáticamente |
| **`setup-tailscale-sudoers.sh`** | Configura permisos sudo específicos para Tailscale           | Reparar permisos de Tailscale si `install.sh` falló                               |

### Troubleshooting común

**Si ves "Welcome to nginx" en lugar del frontend:**

```bash
sudo rm /etc/nginx/sites-enabled/default
sudo systemctl reload nginx
```

> Esto ya lo hace `install-production.sh`, pero puede reaparecer si actualizas nginx.

### Flujo típico de instalación:

```bash
# 1. Instalación inicial (obligatorio)
bash install.sh

# 2. Elegir uno de estos:
bash scripts/dev.sh                    # Para desarrollo local
# O
sudo bash scripts/install-production.sh && bash scripts/deploy.sh  # Para producción

# 3. Troubleshooting (si es necesario)
bash scripts/status.sh                 # Ver estado completo
sudo bash scripts/configure-modem.sh   # Si modem no funciona
# Si ves "Welcome to nginx": sudo rm /etc/nginx/sites-enabled/default && sudo systemctl reload nginx
```

---

---

## 5. Advanced Networking Setup

Esta sección cubre la configuración de red avanzada — detección multi-modem, policy routing y VPN health checks — que se instala **automáticamente** con `install.sh`. No se requieren pasos manuales en una instalación limpia.

### 5.1 Permisos sudo (sudoers)

`install.sh` ejecuta `scripts/setup-sudoers.sh` que crea `/etc/sudoers.d/fpvcopilot-sky` con los permisos necesarios para las operaciones de red:

```
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/sbin/iptables -t mangle *
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/sbin/ip rule *
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/sbin/ip route add *
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/sbin/ip route del *
fpvcopilotsky ALL=(ALL) NOPASSWD: /usr/sbin/ip route show *
```

Verificar que están presentes:

```bash
sudo cat /etc/sudoers.d/fpvcopilot-sky | grep -E "iptables|ip rule|ip route"
```

### 5.2 Dependencias instaladas por install.sh

- `iptables` — marcado de tráfico (mangle table)
- `iproute2` — policy routing (`ip rule`, `ip route`)
- `sudo` — ejecución con permisos elevados

> ⚠️ Si tienes `iptables-persistent` instalado, puede causar conflictos con las reglas dinámicas de FPVCopilotSky. `install.sh` detecta este paquete y ofrece desinstalarlo. Para hacerlo manualmente:
>
> ```bash
> sudo apt-get remove -y iptables-persistent
> ```

### 5.3 Reglas dinámicas (sin persistencia manual)

Las reglas se crean **en cada startup** del servicio y se eliminan en cada shutdown. No es necesario `iptables-save` ni scripts manuales.

**Reglas iptables mangle creadas en startup:**

```bash
# VPN (Tailscale / WireGuard) → fwmark 0x100
iptables -t mangle -A OUTPUT -p udp --dport 41641 -j MARK --set-mark 0x100
iptables -t mangle -A OUTPUT -p udp --dport 51820 -j MARK --set-mark 0x100

# Video GStreamer → fwmark 0x200
iptables -t mangle -A OUTPUT -p udp --dport 5600:5610 -j MARK --set-mark 0x200
iptables -t mangle -A OUTPUT -p tcp --dport 8554     -j MARK --set-mark 0x200
iptables -t mangle -A OUTPUT -p udp --dport 8554     -j MARK --set-mark 0x200

# MAVLink → fwmark 0x300 (sigue tabla de video)
iptables -t mangle -A OUTPUT -p udp --dport 14550 -j MARK --set-mark 0x300
iptables -t mangle -A OUTPUT -p udp --dport 14551 -j MARK --set-mark 0x300
```

**Policy rules creadas en startup:**

```bash
ip rule add fwmark 0x100 table 100 priority 100   # VPN → tabla 100
ip rule add fwmark 0x200 table 200 priority 200   # Video → tabla 200
```

### 5.4 Verificación post-instalación

```bash
# 1. Confirmar permisos sudo
sudo cat /etc/sudoers.d/fpvcopilot-sky | grep "iptables\|ip rule\|ip route"

# 2. Confirmar servicio activo
systemctl status fpvcopilot-sky | grep Active

# 3. Confirmar reglas iptables mangle
sudo iptables -t mangle -L OUTPUT -n -v | grep MARK

# 4. Confirmar policy rules
ip rule show
# Salida esperada: 100: from all fwmark 0x100 lookup 100
#                  200: from all fwmark 0x200 lookup 200

# 5. Confirmar API policy routing
curl -s http://localhost:8000/api/network/policy-routing/status | python3 -m json.tool
```

### 5.5 Comportamiento tras reboot

El servicio está habilitado con `systemctl enable`, por lo que tras un reboot:

1. Systemd inicia el servicio automáticamente
2. `PolicyRoutingManager.initialize()` recrea todas las reglas iptables e `ip rule`
3. El estado es siempre consistente con el código — sin reglas residuales

### 5.6 Limpieza manual de emergencia

Si las reglas quedan en un estado inconsistente:

```bash
# Limpiar via API (servicio activo)
curl -X POST http://localhost:8000/api/network/policy-routing/cleanup

# O limpiar manualmente (servicio detenido)
sudo iptables -t mangle -F OUTPUT
sudo iptables -t mangle -F PREROUTING
sudo ip rule del fwmark 0x100 table 100 2>/dev/null || true
sudo ip rule del fwmark 0x200 table 200 2>/dev/null || true

# Reiniciar para recrear reglas limpias
sudo systemctl restart fpvcopilot-sky
```

---

[← Índice](INDEX.md) · [Siguiente: Guía de Usuario →](USER_GUIDE.md)
