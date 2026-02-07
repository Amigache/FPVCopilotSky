# 📥 Guía de Instalación

Guía completa para instalar FPV Copilot Sky en un SBC Linux (Radxa Zero, Raspberry Pi, Orange Pi, x86…).

---

## 1. Requisitos previos

### Hardware

| Componente | Mínimo | Recomendado |
|------------|--------|-------------|
| SBC Linux | 1 GB RAM, ARM/x86 | Radxa Zero 2 GB |
| Almacenamiento | MicroSD 16 GB | MicroSD 32 GB |
| Cámara | USB UVC | Logitech C920 o similar |
| Modem 4G | — | Huawei E3372h / E8372h (HiLink) |
| Conexión al FC | UART o USB-serie | Cable directo al UART del FC |

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

- **Python 3** + entorno virtual con PyMAVLink, FastAPI, huawei-lte-api
- **GStreamer** completo (plugins good, bad, ugly, libav)
- **Node.js 20** + dependencias del frontend
- **NetworkManager** + ModemManager
- **Tailscale** (VPN)
- **Permisos de serial**: grupos `dialout`/`video`, reglas udev
- **USB modem**: `usb_modeswitch` para modems Huawei en modo almacenamiento
- **Sysctl**: TCP BBR, buffers UDP optimizados, IPv6 deshabilitado, swappiness bajo

> **Nota**: El entorno virtual se crea con `--system-site-packages` para acceder a GStreamer (PyGObject).

### 2.3 Configurar producción

```bash
sudo bash scripts/install-production.sh
```

Esto configura:

- **Nginx** como servidor web (proxy inverso → FastAPI:8000)
- **Servicio systemd** `fpvcopilot-sky` (arranque automático al encender)
- **Reglas udev** para puertos serie
- **Serial-getty** deshabilitado en ttyAML0 (Radxa)
- **Permisos** del proyecto

### 2.4 Compilar y desplegar

```bash
bash scripts/deploy.sh
```

Compila el frontend React, instala la configuración de nginx/systemd, y arranca el servicio. Incluye health-check automático al final.

---

## 3. Verificación

### 3.1 Script de estado

```bash
bash scripts/status.sh
```

Muestra: estado del servicio, puertos, dependencias, USB, red, modem, VPN, conectividad.

### 3.2 Verificación manual

```bash
# Servicio activo
sudo systemctl status fpvcopilot-sky

# Backend responde
curl -s http://localhost:8000/api/status/health

# Frontend accesible
curl -s -o /dev/null -w "%{http_code}" http://localhost/
# Debe devolver 200
```

### 3.3 Acceder a la WebUI

Abre en el navegador:

```
http://<IP-DE-TU-SBC>
```

Obtén la IP con `hostname -I`.

---

## 4. Configuración del modem 4G (opcional)

Si usas un modem Huawei HiLink USB:

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

## 5. Configuración de Tailscale VPN (opcional)

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

## 6. Actualización

```bash
cd /opt/FPVCopilotSky
git pull
bash scripts/deploy.sh
```

---

## 7. Estructura de servicios

### Systemd

| Servicio | Descripción |
|----------|-------------|
| `fpvcopilot-sky.service` | Backend FastAPI (uvicorn :8000) |
| `nginx` | Servidor web, proxy inverso, WebSocket |

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

| Puerto | Servicio |
|--------|----------|
| 80 | Nginx (HTTP) |
| 8000 | FastAPI (backend) |
| 5600 | Video RTP/UDP (streaming saliente) |

---

## 8. Solución de problemas de instalación

### "Welcome to nginx" en vez de la WebUI

```bash
bash scripts/fix-nginx.sh
# o manualmente:
sudo rm /etc/nginx/sites-enabled/default
sudo ln -sf /etc/nginx/sites-available/fpvcopilot-sky /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

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

[← Índice](INDEX.md) · [Siguiente: Guía de Usuario →](USER_GUIDE.md)
