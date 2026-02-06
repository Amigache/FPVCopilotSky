# 🚁 FPV Copilot Sky

**Sistema completo de control y telemetría para drones FPV**

FPV Copilot Sky es una solución integral para gestionar tu drone FPV desde cualquier lugar. Convierte tu Radxa Zero (u otro SBC Linux) en un hub completo de telemetría, video y conectividad.

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Platform](https://img.shields.io/badge/platform-Linux-green)
![License](https://img.shields.io/badge/license-MIT-yellow)

## ✨ Características Principales

### 📡 Telemetría MAVLink
- **Conexión directa** al controlador de vuelo (Pixhawk, Ardupilot, iNav...)
- **Auto-detección** de puertos serie y baudrates
- **Múltiples salidas** simultáneas (UDP/TCP)
- Compatible con **Mission Planner**, **QGroundControl**, **APM Planner**

### 🎥 Video en Tiempo Real
- **Streaming ultra-baja latencia** vía RTP/UDP
- Soporte **H.264** y **MJPEG**
- Compatible con cámaras **USB** y **CSI**
- Resoluciones desde 480p hasta 1080p

### 🌐 Conectividad Inteligente
- **WiFi** y **4G/LTE** con priorización automática
- Soporte modems **Huawei HiLink** (E3372, E8372...)
- Gestión visual de redes disponibles
- Cambio automático entre interfaces

### 🔐 Acceso Remoto Seguro (VPN)
- Integración con **Tailscale** (VPN mesh)
- Configuración en **1 click** desde la interfaz
- Acceso seguro desde cualquier lugar
- Lista de dispositivos conectados en tiempo real

### 💻 Interfaz Web Moderna
- **WebUI responsive** en español e inglés
- **Tiempo real** con WebSocket
- Sin instalación de apps, solo navegador
- Dashboard completo de estado del sistema

## 📦 ¿Qué Necesitas?

### Hardware Mínimo
- **Radxa Zero** (2GB RAM recomendado) o similar (Raspberry Pi, Orange Pi...)
- **Tarjeta microSD** 16GB+ (32GB recomendado)
- **Cámara USB** (para video)
- **Modem 4G USB** (opcional, para conectividad móvil)
- Conexión al controlador de vuelo (UART/USB)

### Software
- Sistema operativo Linux (Debian/Ubuntu/Armbian)
- Acceso SSH o terminal

## 🚀 Instalación Rápida

### 1. Descargar e Instalar

```bash
# Clonar el repositorio en /opt
cd /opt
sudo git clone https://github.com/tu-usuario/FPVCopilotSky.git
cd FPVCopilotSky

# Ejecutar instalador (instala dependencias del sistema)
bash install.sh
```

El instalador se encarga de:
- ✅ Instalar Python, Node.js, GStreamer
- ✅ Configurar NetworkManager y ModemManager
- ✅ Detectar y configurar modems 4G
- ✅ Crear entorno virtual de Python
- ✅ Instalar todas las dependencias
- ✅ Compilar el frontend

**Tiempo estimado:** 15-20 minutos (dependiendo de velocidad de internet)

### 2. Configurar para Producción

```bash
# Instalar nginx y configurar servicios (solo primera vez)
sudo bash scripts/install-production.sh

# Compilar y desplegar
bash scripts/deploy.sh
```

Esto configura:
- ✅ Servicio systemd (arranca automáticamente al encender)
- ✅ Nginx como servidor web
- ✅ Frontend optimizado
- ✅ Logs del sistema

### 3. Acceder a la Aplicación

Abre tu navegador y accede a:
```
http://<IP-DE-TU-RADXA>
```

Por ejemplo: `http://192.168.1.145`

💡 **Tip:** Puedes encontrar la IP de tu Radxa con el comando `hostname -I`

## 📱 Guía de Uso

### Primera Configuración

1. **Conectar el Controlador de Vuelo**
   - Ve a la pestaña **"Controlador"**
   - El sistema detecta automáticamente el puerto serie
   - Verás telemetría en tiempo real cuando conecte

2. **Configurar Streaming de Video**
   - Ve a la pestaña **"Video"**
   - Selecciona tu cámara USB
   - Ajusta resolución y codec (H264 = mejor calidad, MJPEG = menor latencia)
   - Configura IP de destino y puerto (puedes usar el selector de peers VPN)
   - Haz clic en **"Aplicar"** y luego **"Iniciar Stream"**

3. **Configurar Telemetría Remota**
   - Ve a la pestaña **"Telemetría"**
   - Crea salidas TCP/UDP según necesites:
     - **Mission Planner**: TCP Server puerto 5760
     - **QGroundControl**: UDP puerto 14550
   - Usa el selector de IPs para elegir destinos en tu red VPN

4. **Conectar VPN (Opcional pero Recomendado)**
   - Ve a la pestaña **"VPN"**
   - Haz clic en **"Conectar"**
   - Escanea el código QR o copia la URL de autenticación
   - Autentica desde tu móvil/ordenador
   - ¡Listo! Ahora puedes acceder desde cualquier lugar

5. **Gestionar Conectividad**
   - Ve a la pestaña **"Red"**
   - Conecta a WiFi o verifica estado del modem 4G
   - Visualiza interfaces activas y rutas

### Comandos Útiles

```bash
# Ver estado de todo el sistema
bash /opt/FPVCopilotSky/scripts/status.sh

# Ver logs en tiempo real
sudo journalctl -u fpvcopilot-sky -f

# Reiniciar servicio
sudo systemctl restart fpvcopilot-sky

# Detener servicio
sudo systemctl stop fpvcopilot-sky

# Actualizar después de cambios
bash /opt/FPVCopilotSky/scripts/deploy.sh
```

## 🔧 Solución de Problemas

### No veo la interfaz web (aparece "Welcome to nginx")
```bash
bash /opt/FPVCopilotSky/scripts/fix-nginx.sh
```

### El backend no responde
```bash
# Reiniciar el servicio
sudo systemctl restart fpvcopilot-sky

# Ver qué está pasando
sudo journalctl -u fpvcopilot-sky -f
```

### No detecta el controlador de vuelo
- Verifica la conexión física del cable
- Comprueba que el puerto serie no esté siendo usado por otro proceso
- Prueba con diferentes baudrates manualmente

### Video no arranca
- Verifica que la cámara esté conectada (`v4l2-ctl --list-devices`)
- Asegúrate de haber configurado una IP de destino
- El primer arranque puede tardar unos segundos

### No hay redes WiFi
- Ejecuta `sudo systemctl restart NetworkManager`
- Verifica que tu interfaz WiFi no esté gestionada por otro servicio

## 📚 Documentación Adicional

- **[Guía de Producción](docs/PRODUCTION.md)** - Detalles de despliegue y arquitectura
- **[Guía para Desarrolladores](DEVELOPMENT.md)** - Si quieres modificar o contribuir
- **[Integración VPN](docs/VPN_INTEGRATION.md)** - Detalles técnicos del sistema VPN

## 🛠️ Soporte Técnico

### Información del Sistema

Para reportar problemas, ejecuta:
```bash
bash /opt/FPVCopilotSky/scripts/status.sh > status.txt
sudo journalctl -u fpvcopilot-sky -n 100 > logs.txt
```

Y comparte los archivos `status.txt` y `logs.txt`.

### Comunidad

- 📧 **Email**: support@fpvcopilotsky.com
- 💬 **Telegram**: @fpvcopilotsky
- 🐛 **Issues**: GitHub Issues

## 📄 Licencia

Este proyecto está bajo licencia MIT. Ver archivo [LICENSE](LICENSE) para más detalles.

## 🙏 Agradecimientos

Construido con:
- [FastAPI](https://fastapi.tiangolo.com/) - Framework web Python
- [React](https://react.dev/) - Framework UI
- [GStreamer](https://gstreamer.freedesktop.org/) - Pipeline multimedia
- [PyMAVLink](https://github.com/ArduPilot/pymavlink) - Protocolo MAVLink
- [Tailscale](https://tailscale.com/) - VPN mesh

---

**¿Necesitas ayuda?** No dudes en abrir un issue o contactarnos. ¡Felices vuelos! 🚁✈️
