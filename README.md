# 🚁 FPV Copilot Sky

**Plataforma completa de telemetría, video y conectividad para drones FPV**

FPV Copilot Sky convierte un SBC Linux (Radxa Zero, Raspberry Pi, Orange Pi…) en un hub inteligente que gestiona telemetría MAVLink, streaming de video en baja latencia y conectividad 4G/VPN — todo controlable desde una interfaz web moderna.

![CI Status](https://github.com/Amigache/FPVCopilotSky/workflows/CI%20-%20Lint%20&%20Test/badge.svg)
![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Platform](https://img.shields.io/badge/platform-Linux_ARM/x86-green)
![License](https://img.shields.io/badge/license-MIT-yellow)
![Python](https://img.shields.io/badge/python-3.12+-blue)
![React](https://img.shields.io/badge/react-19-61dafb)

---

## ✨ ¿Qué puedes hacer?

### 📡 **Telemetría MAVLink - Control de vuelo inteligente**

- **Auto-detección de puertos serie** — El sistema detecta automáticamente tu controladora de vuelo conectada por USB/UART
- **Router MAVLink integrado** — Crea salidas UDP/TCP ilimitadas para conectar múltiples GCS (QGroundControl, Mission Planner) simultáneamente
- **Configuración desde WebUI** — Ajusta baudrate, puertos, y crea presets para tus aplicaciones favoritas sin tocar el terminal
- **Auto-conexión** — Opción de conectar automáticamente al arranque para vuelos autónomos
- **Parámetros de vuelo** — Lee y modifica parámetros de ArduPilot/PX4 directamente, aplica configuraciones recomendadas para FPV con un clic
- **Monitor de telemetría** — Visualiza actitud, GPS, batería, velocidades y mensajes del FC en tiempo real

### 🎥 **Video HD - Streaming profesional de baja latencia**

- **Múltiples códecs** — H.264 hardware/software, MJPEG; selección automática del mejor encoder según tu hardware
- **Modos de red flexibles** — UDP unicast, Multicast (multi-receptor), RTSP server, WebRTC embebido en navegador
- **Ajustes en vivo** — Cambia bitrate, calidad JPEG, GOP size sin reiniciar el stream durante el vuelo
- **Auto-start** — Arranca automáticamente el video al iniciar el sistema para operaciones desatendidas
- **Selector de cámaras** — Soporta USB (V4L2), CSI (libcamera en Raspberry Pi), streams de red; cambio en caliente
- **Resoluciones adaptables** — Desde 640×480 hasta 1920×1080, múltiples framerates (15/24/30 fps)
- **Pipeline visible** — Inspecciona el comando GStreamer generado, cópialo para depuración o uso externo
- **Estadísticas en vivo** — FPS actual, bitrate real, salud del pipeline, uptime del stream

### 📱 **Modem 4G/LTE - Conectividad móvil optimizada**

- **Gestión Huawei HiLink** — Control completo de modems E3372, E8372, E3276 vía API HTTP nativa
- **Análisis de cobertura** — Visualiza RSSI, RSRQ, SINR, Cell ID, PCI, bandas activas en tiempo real
- **Modo Video** — Preset de optimización que configura bandas LTE, network mode y parámetros para mínima latencia
- **Test de latencia** — Ping continuo a 1.1.1.1 con estadísticas de RTT, jitter, packet loss y clasificación de calidad
- **Video Quality Score** — Recomendaciones automáticas de bitrate, resolución y FPS según la señal actual
- **Cambio de banda** — Presets para forzar B3/B7/B20 o combinaciones multi-banda desde la WebUI
- **Reboot remoto** — Reinicia el modem sin desconectar físicamente cuando se cuelga
- **Métricas de tráfico** — Download/upload actual y acumulado, tiempo de conexión

### 🔐 **VPN Tailscale - Acceso remoto sin configuración**

- **Conexión en 1 clic** — Escanea automáticamente proveedores VPN instalados (Tailscale, ZeroTier, WireGuard)
- **Auth flow embebido** — Abre la URL de autenticación desde la WebUI, polling automático hasta conectar
- **Auto-connect** — Habilita la reconexión automática al arranque para control remoto permanente
- **Vista de red mesh** — Listado de todos los peers conectados con hostname, IP tailnet, OS, tráfico TX/RX
- **Selector de peers** — Dropdown inteligente para rellenar IPs de destino en video/telemetría
- **Status en vivo** — Badge que muestra estado conectado/desconectado con contador de peers activos

### 🌐 **Red inteligente - Auto-failover WiFi ⇄ 4G**

- **Priorización dinámica** — Cambia entre WiFi y 4G como ruta principal con un toggle; actualiza métricas automáticamente
- **Flight Mode** — Activa optimizaciones de red completas para vuelo (tc qdisc, sysctls, prioridades de ruta)
- **Calidad de Red en tiempo real** — Score compuesto (0-100) basado en SINR, RSRQ, RTT, jitter y packet loss
- **Bridge de eventos** — Conecta la calidad de red con el pipeline de video para adaptar parámetros automáticamente
- **Recomendaciones adaptativas** — El sistema sugiere bitrate, resolución y FPS óptimos según la calidad detectada
- **Monitoreo de interfaces** — Visualiza estado de wlan0, usb0/eth1 (modem), eth0 con IPs, gateways, métricas
- **Rutas por defecto** — Tabla de enrutamiento con visual de la ruta activa y sus prioridades
- **WiFi scanner** — Detecta redes cercanas con nivel de señal, conéctate desde la interfaz

### 🧠 **Optimizaciones avanzadas - Network Event Bridge**

- **Auto-ajuste de bitrate** — Reduce o aumenta automáticamente el bitrate del video según SINR y latencia medidos cada 2 segundos
- **CAKE Qdisc anti-bufferbloat** — Reduce la latencia de video hasta un 40% en enlaces 4G congestionados controlando colas activas
- **Failover predictivo** — Anticipa degradación de red analizando tendencias de SINR y jitter; cambia de ruta antes del corte total
- **MPTCP bonding** — Combina WiFi + 4G en una sola conexión multi-ruta para redundancia real (requiere kernel 5.6+)
- **VPN policy routing** — Separa tráfico de video (fwmark 0x200) y control VPN (fwmark 0x100) en tablas de enrutamiento distintas
- **Self-healing de streaming** — Fuerza keyframes, reinicia GStreamer, ajusta resolución automáticamente según eventos de red
- **Registro de eventos** — Historial de cambios de celda, bandas, SINR drops, reconnections con timestamps

### 💻 **WebUI moderna - Interfaz completa y responsive**

- **Dashboard en tiempo real** — Actitud, GPS, batería, velocidades, mensajes del FC actualizados por WebSocket
- **8 pestañas funcionales** — Dashboard, Video, Red, Telemetría, Router MAVLink, Modem, VPN, Sistema
- **Bilingüe (ES/EN)** — Cambio de idioma persistente, traducciones completas con react-i18next
- **Modo claro/oscuro** — Tema oscuro por defecto optimizado para uso nocturno en campo
- **Logs integrados** — Visualiza logs de backend y frontend sin salir del navegador
- **Gestión de preferencias** — Reset completo de configuración, backup/restore manual
- **Flight Session recorder** — Graba muestras de calidad de red durante el vuelo para análisis posterior
- **Experimental tab** — Filtros OpenCV en vivo (edges, blur, threshold) sobre el stream de video

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
                             # Crea automáticamente el usuario fpvcopilotsky si no existe

# 3. Usar el CLI para gestión completa
./fpv                        # Interfaz de menú amigable
```

Abre `http://<IP-DE-TU-SBC>` en el navegador. Listo.

> **Tip:** Obtén la IP con `hostname -I`

## 🔧 Comandos rápidos

### CLI de Gestión (Recomendado)

```bash
./fpv    # Interfaz de menú interactiva para todas las operaciones
```

El CLI proporciona acceso guiado a:

- 📦 Instalación y Despliegue
- 🛠️ Modo Desarrollo
- 📊 Diagnóstico y Estado del Sistema
- ⚙️ Configuración (Modem, Puertos Serie, Permisos)
- 🔧 Mantenimiento y Recuperación

### Comandos Manuales

```bash
bash scripts/status.sh                   # Estado completo del sistema
bash scripts/preflight-check.sh          # Verificación exhaustiva pre-vuelo
sudo journalctl -u fpvcopilot-sky -f     # Logs en tiempo real
sudo systemctl restart fpvcopilot-sky    # Reiniciar servicio
bash scripts/deploy.sh                   # Recompilar y desplegar
bash scripts/dev.sh                      # Modo desarrollo con hot-reload
```

### CORS por entorno

El backend configura CORS mediante variables de entorno:

- `FPV_CORS_ALLOW_ORIGINS`
- `FPV_CORS_ALLOW_CREDENTIALS`
- `FPV_CORS_ALLOW_METHODS`
- `FPV_CORS_ALLOW_HEADERS`

Configuración detallada y ejemplos dev/prod en [docs/INSTALLATION.md](docs/INSTALLATION.md).

## 📚 Documentación

Toda la documentación extendida está en la **[Wiki del proyecto](docs/INDEX.md)**:

| Documento                                        | Descripción                                               |
| ------------------------------------------------ | --------------------------------------------------------- |
| [📑 Índice](docs/INDEX.md)                       | Punto de entrada a toda la wiki                           |
| [📥 Guía de Instalación](docs/INSTALLATION.md)   | Requisitos, instalación paso a paso, verificación         |
| [📖 Guía de Usuario](docs/USER_GUIDE.md)         | Uso de cada pestaña, configuración, solución de problemas |
| [🛠️ Guía de Desarrollo](docs/DEVELOPER_GUIDE.md) | Arquitectura, stack, cómo contribuir y extender           |

## 🏗️ Tecnologías

| Capa         | Stack                                                               |
| ------------ | ------------------------------------------------------------------- |
| **Backend**  | Python 3.12, FastAPI, Uvicorn, PyMAVLink, GStreamer, huawei-lte-api |
| **Frontend** | React 19, Vite, i18next, WebSocket                                  |
| **Infra**    | Nginx, systemd, NetworkManager, Tailscale, tc/CAKE, MPTCP, iptables |

## 📄 Licencia

MIT — ver [LICENSE](LICENSE).

## 📧 Contacto

- **GitHub**: [github.com/Amigache/FPVCopilotSky](https://github.com/Amigache/FPVCopilotSky)
- **Issues**: [Abrir un issue](https://github.com/Amigache/FPVCopilotSky/issues)

---

Construido con ❤️ y opensource: [FastAPI](https://fastapi.tiangolo.com/) · [React](https://react.dev/) · [GStreamer](https://gstreamer.freedesktop.org/) · [PyMAVLink](https://github.com/ArduPilot/pymavlink) · [Tailscale](https://tailscale.com/)

---
