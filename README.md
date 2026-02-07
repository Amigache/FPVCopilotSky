# 🚁 FPV Copilot Sky

**Plataforma completa de telemetría, video y conectividad para drones FPV**

FPV Copilot Sky convierte un SBC Linux (Radxa Zero, Raspberry Pi, Orange Pi…) en un hub inteligente que gestiona telemetría MAVLink, streaming de video en baja latencia y conectividad 4G/VPN — todo controlable desde una interfaz web moderna.

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Platform](https://img.shields.io/badge/platform-Linux_ARM/x86-green)
![License](https://img.shields.io/badge/license-MIT-yellow)
![Python](https://img.shields.io/badge/python-3.12+-blue)
![React](https://img.shields.io/badge/react-19-61dafb)

---

## ✨ ¿Qué puedes hacer?

| Función | Descripción |
|---------|-------------|
| **📡 Telemetría MAVLink** | Conexión directa al FC, auto-detección de puertos, múltiples salidas UDP/TCP simultáneas |
| **🎥 Video HD** | Streaming RTP/UDP ultra-baja latencia, H.264 y MJPEG, cámaras USB y CSI |
| **📱 Modem 4G/LTE** | Gestión completa de Huawei HiLink, bandas LTE, modo video optimizado, test de latencia |
| **🔐 VPN Tailscale** | Acceso remoto en 1 clic, conexión mesh P2P cifrada desde cualquier lugar |
| **🌐 Red inteligente** | Priorización WiFi/4G automática, failover, métricas de ruta |
| **💻 WebUI** | Interfaz responsive en español e inglés, tiempo real por WebSocket |

## 🏗️ Flujo de datos

```
            ┌─────────────────────────────────────────┐
            │      NAVEGADOR / CONTROL REMOTO         │
            │    (Dashboard, Telemetría, Video)       │
            └──────────────────┬──────────────────────┘
                               │ HTTPS / HTTP
                    ┌──────────▼──────────┐
                    │   FPV Copilot Sky   │
                    │  (SBC: Radxa/RPi)   │
                    └──────┬──┬──┬──┬─────┘
        ┌───────────────────┘  │  │  └────────────────┐
        │                      │  │                    │
    ┌───▼──────┐    ┌─────────▼──▼───────┐    ┌──────▼────┐
    │ FC       │    │   Video Stream    │    │  Modem    │
    │ MAVLink  │    │   GStreamer UDP   │    │  4G/LTE   │
    │ Telemetry│    │   H.264 / MJPEG   │    │  Huawei   │
    └──────────┘    └─────────┬─────────┘    └──────┬────┘
                              │                      │
                              ▼                      ▼
                    ┌────────────────────────────────────┐
                    │  RED LOCAL / 4G / INTERNET        │
                    │  WiFi • Ethernet • LTE • Tailscale │
                    └────────────────────────────────────┘
                              │
                              ▼
                    ┌────────────────────┐
                    │ Controlador de GCS  │
                    │ QGroundControl /    │
                    │ Mission Planner     │
                    └────────────────────┘
```

### Arquitectura de componentes

- **Backend (Python/FastAPI)**: Maneja MAVLink, video, VPN, modem
- **Frontend (React/Vite)**: Interfaz web responsive, WebSocket en tiempo real  
- **Servicios (systemd)**: Arranque automático, gestor de procesos
- **Nginx**: Proxy inverso, hosting de estáticos, compresión gzip
- **Providers**: Sistema modular agnóstico de hardware (modem, VPN, network)

## 📦 ¿Qué necesitas?

### Hardware

- **SBC Linux** — Radxa Zero 2GB+ (recomendado), Raspberry Pi 4/5, Orange Pi, o cualquier x86
- **MicroSD** 16 GB+ (32 GB recomendado)
- **Cámara USB** para video (o CSI si tu placa lo soporta)
- **Modem 4G USB** Huawei HiLink (E3372, E8372…) — opcional, para conectividad móvil
- **Conexión al FC** por UART o USB (cable serie)

### Software

- Debian / Ubuntu / Armbian
- Acceso SSH o terminal

## 🚀 Primeros pasos

```bash
# 1. Clonar
cd /opt
sudo git clone https://github.com/Amigache/FPVCopilotSky.git
cd FPVCopilotSky

# 2. Instalar dependencias del sistema y entorno Python/Node
bash install.sh              # ~15 min la primera vez

# 3. Configurar producción (nginx + systemd)
sudo bash scripts/install-production.sh

# 4. Compilar frontend y arrancar
bash scripts/deploy.sh
```

Abre `http://<IP-DE-TU-SBC>` en el navegador. Listo.

> **Tip:** Obtén la IP con `hostname -I`

## 🔧 Comandos rápidos

```bash
bash scripts/status.sh                   # Estado completo del sistema
sudo journalctl -u fpvcopilot-sky -f     # Logs en tiempo real
sudo systemctl restart fpvcopilot-sky    # Reiniciar servicio
bash scripts/deploy.sh                   # Recompilar y desplegar
bash scripts/dev.sh                      # Modo desarrollo con hot-reload
```

## 📚 Documentación

Toda la documentación extendida está en la **[Wiki del proyecto](docs/INDEX.md)**:

| Documento | Descripción |
|-----------|-------------|
| [📑 Índice](docs/INDEX.md) | Punto de entrada a toda la wiki |
| [📥 Guía de Instalación](docs/INSTALLATION.md) | Requisitos, instalación paso a paso, verificación |
| [📖 Guía de Usuario](docs/USER_GUIDE.md) | Uso de cada pestaña, configuración, solución de problemas |
| [🛠️ Guía de Desarrollo](docs/DEVELOPER_GUIDE.md) | Arquitectura, stack, cómo contribuir y extender |

## 🏗️ Tecnologías

| Capa | Stack |
|------|-------|
| **Backend** | Python 3.12, FastAPI, Uvicorn, PyMAVLink, GStreamer, huawei-lte-api |
| **Frontend** | React 19, Vite, i18next, WebSocket |
| **Infra** | Nginx, systemd, NetworkManager, Tailscale |

## 📄 Licencia

MIT — ver [LICENSE](LICENSE).

## 📧 Contacto

- **GitHub**: [github.com/Amigache/FPVCopilotSky](https://github.com/Amigache/FPVCopilotSky)
- **Issues**: [Abrir un issue](https://github.com/Amigache/FPVCopilotSky/issues)

---

Construido con ❤️ y opensource: [FastAPI](https://fastapi.tiangolo.com/) · [React](https://react.dev/) · [GStreamer](https://gstreamer.freedesktop.org/) · [PyMAVLink](https://github.com/ArduPilot/pymavlink) · [Tailscale](https://tailscale.com/)
