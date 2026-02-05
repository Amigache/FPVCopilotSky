# 🚁 FPV Copilot Sky

**Sistema de control y telemetría MAVLink para drones FPV con streaming de video**

Aplicación completa para Radxa Zero (o sistemas Linux embebidos) que proporciona:
- 📡 Puente MAVLink (Serial ↔ UDP/TCP)
- 🎥 Streaming de video H264/MJPEG via GStreamer
- 🌐 Gestión de red WiFi/4G con priorización
- 🔐 Soporte VPN (Tailscale)
- 💻 WebUI completa en React
- 🔌 WebSocket en tiempo real
- ⚙️ API REST completa

## 📋 Stack Tecnológico

### Backend
- **Python 3.12** + FastAPI
- **Uvicorn** (ASGI server)
- **PyMAVLink** (protocolo MAVLink)
- **GStreamer** (streaming de video)
- **Network Manager** (gestión de redes)

### Frontend
- **React 19.2** + Vite
- **React Router** (navegación)
- **i18n** (internacionalización EN/ES)
- **WebSocket** (comunicación en tiempo real)

## 🚀 Quick Start

### Instalación

```bash
# Clonar el repositorio
git clone <repo-url> /opt/FPVCopilotSky
cd /opt/FPVCopilotSky

# Ejecutar instalación
bash install.sh
```

El script instala:
- Dependencias del sistema (GStreamer, Python, Node.js)
- Entorno virtual Python con todas las dependencias
- Dependencias npm del frontend
- Tailscale VPN (opcional)

### Modo Desarrollo

```bash
# Usar script automático (recomendado)
bash scripts/dev.sh

# O manualmente:
# Terminal 1 - Backend
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 - Frontend
cd frontend/client
npm run dev
```

Acceso:
- **Frontend**: http://localhost:5173
- **Backend**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

### Modo Producción

```bash
# 1. Setup inicial (solo primera vez)
sudo bash scripts/install-production.sh

# 2. Compilar y desplegar
bash scripts/deploy.sh
```

Esto configura:
- ✅ Servicio systemd (auto-inicia al arrancar)
- ✅ Nginx como proxy reverso
- ✅ Frontend compilado y optimizado
- ✅ Logs centralizados en journald

Acceso:
- **Aplicación**: http://192.168.1.145 (IP de tu Radxa)

📖 **Guía completa**: [docs/PRODUCTION.md](docs/PRODUCTION.md)

## 📁 Estructura del Proyecto

```
FPVCopilotSky/
├── app/                      # Backend FastAPI
│   ├── main.py              # Aplicación principal
│   ├── api/                 # Endpoints REST
│   │   └── routes/          # Rutas API
│   ├── services/            # Lógica de negocio
│   │   ├── mavlink_bridge.py
│   │   ├── gstreamer_service.py
│   │   ├── network_service.py
│   │   ├── vpn_service.py
│   │   └── websocket_manager.py
│   └── utils/               # Utilidades
├── frontend/client/         # Frontend React
│   ├── src/
│   │   ├── components/      # Componentes React
│   │   ├── contexts/        # React Contexts
│   │   ├── services/        # Cliente API
│   │   └── i18n/            # Traducciones
│   ├── package.json
│   └── vite.config.js
├── scripts/                 # Scripts de utilidad
│   ├── deploy.sh           # Deployment producción
│   ├── dev.sh              # Modo desarrollo
│   └── install-production.sh
├── systemd/                 # Configuración systemd
│   ├── fpvcopilot-sky.service
│   └── fpvcopilot-sky.nginx
├── docs/                    # Documentación
│   └── PRODUCTION.md       # Guía de producción
├── install.sh              # Instalación inicial
├── requirements.txt        # Dependencias Python
└── pyproject.toml         # Metadata del proyecto

```

## 🎯 Características Principales

### 📡 MAVLink Bridge
- Conexión serial a controlador de vuelo
- Auto-detección de puerto y baudrate
- Routing UDP/TCP a múltiples clientes
- Soporte para Mission Planner, QGroundControl

### 🎥 Video Streaming
- Codecs: H264, MJPEG
- Múltiples fuentes: USB, CSI, test pattern
- Resoluciones configurables
- Latencia ultra-baja

### 🌐 Gestión de Red
- Priorización WiFi/4G automática
- Soporte modem HiLink (Huawei E3372)
- Configuración de rutas y métricas
- Monitoreo de interfaces

### 🔐 VPN (Tailscale)
- Conexión segura punto a punto
- Configuración simplificada
- Status en tiempo real

### 💻 WebUI
- Dashboard con telemetría en tiempo real
- Gestión de video y configuración
- Control de red y VPN
- Sistema de permisos y status
- Multi-idioma (EN/ES)

### 🔌 WebSocket
- Telemetría en tiempo real
- Status de video y red
- Actualizaciones push
- Conexión persistente

## 🛠️ Gestión del Servicio

```bash
# Ver estado
sudo systemctl status fpvcopilot-sky

# Ver logs en tiempo real
sudo journalctl -u fpvcopilot-sky -f

# Reiniciar
sudo systemctl restart fpvcopilot-sky

# Detener
sudo systemctl stop fpvcopilot-sky

# Iniciar
sudo systemctl start fpvcopilot-sky
```

## 📊 Monitoreo

### Logs del Backend
```bash
# Journald (producción)
sudo journalctl -u fpvcopilot-sky -f

# Archivo (desarrollo)
tail -f /tmp/backend.log
```

### Logs de Nginx
```bash
# Accesos
sudo tail -f /var/log/nginx/fpvcopilot-sky-access.log

# Errores
sudo tail -f /var/log/nginx/fpvcopilot-sky-error.log
```

### Status General
```bash
# Estado del sistema
systemctl status fpvcopilot-sky nginx

# Procesos activos
ps aux | grep -E "(python|nginx)"

# Puertos abiertos
sudo lsof -i :80 -i :8000 -i :5173
```

## 🔄 Workflow de Desarrollo

### 1. Desarrollo Local
```bash
# Frontend con hot reload
cd frontend/client
npm run dev

# Backend con hot reload
uvicorn app.main:app --reload --port 8001
```

### 2. Testing
```bash
# Verificar backend
curl http://localhost:8000/api/status/health

# Verificar WebSocket
wscat -c ws://localhost:8000/ws
```

### 3. Deploy a Producción
```bash
# Compilar y desplegar
bash scripts/deploy.sh

# Verificar
curl http://localhost/api/status/health
```

## 📚 Documentación Adicional

- [📖 Guía de Producción](docs/PRODUCTION.md) - Deployment y gestión
- [🔧 Configuración de Modem 4G](docs/MODEM_4G_SETUP.md)
- [🌐 Sistema de Prioridad de Red](docs/NETWORK_PRIORITY_SYSTEM.md)
- [⚙️ Optimizaciones del Sistema](docs/OPTIMIZATION_GUIDE.md)
- [🚀 Quick Start](docs/QUICKSTART.md)

## 🐛 Troubleshooting

### Backend no inicia
```bash
# Ver logs detallados
sudo journalctl -u fpvcopilot-sky -xe

# Verificar puerto
sudo lsof -i :8000

# Test manual
cd /opt/FPVCopilotSky
source venv/bin/activate
python3 app/main.py
```

### Frontend no carga
```bash
# Recompilar
cd frontend/client
npm run build

# Verificar build
ls -la dist/

# Recargar nginx
sudo systemctl reload nginx
```

### WebSocket no conecta
```bash
# Verificar nginx config
sudo nginx -t

# Ver logs
sudo tail -f /var/log/nginx/fpvcopilot-sky-error.log
```

## 🤝 Contribuir

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📝 Licencia

Este proyecto está bajo licencia MIT - ver el archivo [LICENSE](LICENSE) para detalles.

## 👥 Autores

- Hector - Desarrollo inicial

## 🙏 Agradecimientos

- PyMAVLink por el protocolo MAVLink
- FastAPI por el framework web
- React por la interfaz de usuario
- GStreamer por el streaming de video

---

**Versión**: 1.0.0  
**Status**: ✅ Producción Ready  
**Plataforma**: Linux (Radxa Zero, Raspberry Pi, x86)
