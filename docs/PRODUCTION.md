# 📦 FPV Copilot Sky - Production Deployment Guide

Guía detallada para desplegar FPV Copilot Sky en modo producción con systemd y nginx.

## 🏗️ Arquitectura de Producción

```
┌─────────────────────────────────────────────┐
│  Cliente (Navegador/App)                    │
│  http://<radxa-ip>                          │
└────────────┬────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────┐
│  Nginx (Puerto 80)                          │
│  ├─ Sirve frontend estático (/dist)         │
│  ├─ Proxy /api/* → Backend:8000             │
│  └─ Proxy /ws → WebSocket                   │
└────────────┬────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────┐
│  Backend FastAPI (Puerto 8000)              │
│  ├─ Servicio systemd: fpvcopilot-sky        │
│  ├─ Auto-inicio al arrancar                 │
│  ├─ Auto-restart si falla                   │
│  └─ Logs en journald                        │
└─────────────────────────────────────────────┘
```

## 🚀 Pasos de Instalación

### 1. Instalación Base

```bash
cd /opt
sudo git clone <repo-url> FPVCopilotSky
cd FPVCopilotSky

# Instalar dependencias del sistema
bash install.sh
```

Esto instala:
- ✅ Python 3.12+, Node.js, GStreamer
- ✅ NetworkManager, ModemManager
- ✅ Entorno virtual Python
- ✅ Dependencias npm
- ✅ Configuración de modems 4G

**Tiempo:** ~15-20 minutos

### 2. Configuración de Producción

```bash
# Setup inicial (solo primera vez)
sudo bash scripts/install-production.sh
```

Esto configura:
- ✅ Instala nginx
- ✅ Deshabilita default site de nginx
- ✅ Desactiva getty en puerto serie (evita conflictos con MAVLink)
- ✅ Aplica udev rules para permisos de puerto serie
- ✅ Optimiza sistema para streaming 4G (sysctl)

### 3. Despliegue

```bash
# Compilar frontend y desplegar
bash scripts/deploy.sh
```

Esto ejecuta:
1. **Build del frontend** (React → static en `/dist`)
2. **Instala servicio systemd** (`fpvcopilot-sky.service`)
3. **Configura nginx** (copia config, habilita site)
4. **Ajusta permisos** (dist/ → www-data:www-data)
5. **Inicia servicios** (systemd enable + start)
6. **Health check** (verifica backend + frontend)

**Tiempo:** ~1-2 minutos

### 4. Verificación

```bash
# Check completo del sistema
bash scripts/status.sh

# Ver logs
sudo journalctl -u fpvcopilot-sky -f
```

Acceso:
```
http://192.168.1.145  (sustituye con tu IP)
```

## 📋 Gestión del Servicio

### Comandos systemd

```bash
# Ver estado
sudo systemctl status fpvcopilot-sky

# Iniciar
sudo systemctl start fpvcopilot-sky

# Detener
sudo systemctl stop fpvcopilot-sky

# Reiniciar
sudo systemctl restart fpvcopilot-sky

# Ver si auto-inicia
sudo systemctl is-enabled fpvcopilot-sky

# Habilitar auto-inicio
sudo systemctl enable fpvcopilot-sky

# Deshabilitar auto-inicio
sudo systemctl disable fpvcopilot-sky
```

### Ver Logs

```bash
# Tiempo real (follow)
sudo journalctl -u fpvcopilot-sky -f

# Últimas 100 líneas
sudo journalctl -u fpvcopilot-sky -n 100

# Con timestamps
sudo journalctl -u fpvcopilot-sky -n 50 --no-pager

# Buscar errores
sudo journalctl -u fpvcopilot-sky | grep ERROR

# Desde una fecha
sudo journalctl -u fpvcopilot-sky --since "2026-02-01"

# Exportar logs
sudo journalctl -u fpvcopilot-sky -n 200 > logs.txt
```

## 🔧 Configuración

### Servicio Systemd

Archivo: `/etc/systemd/system/fpvcopilot-sky.service`

```ini
[Unit]
Description=FPV Copilot Sky - Backend Service
After=network.target

[Service]
Type=simple
User=fpvcopilotsky
WorkingDirectory=/opt/FPVCopilotSky
Environment="PATH=/opt/FPVCopilotSky/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/opt/FPVCopilotSky/venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

**Notas:**
- `User=fpvcopilotsky`: Ejecuta como usuario normal (no root)
- `Restart=always`: Auto-reinicia si falla
- `RestartSec=3`: Espera 3s antes de reiniciar
- `WorkingDirectory`: Importante para rutas relativas

### Nginx

Archivo: `/etc/nginx/sites-available/fpvcopilot-sky`

```nginx
server {
    listen 80 default_server;
    server_name _;

    # Frontend estático
    location / {
        root /opt/FPVCopilotSky/frontend/client/dist;
        try_files $uri $uri/ /index.html;
        add_header Cache-Control "no-cache";
    }
    
    # API REST
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        
        # Timeouts para API
        proxy_connect_timeout 10s;
        proxy_read_timeout 10s;
        proxy_send_timeout 10s;
    }
    
    # WebSocket
    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        
        # Timeouts largos para WebSocket
        proxy_connect_timeout 7d;
        proxy_read_timeout 7d;
        proxy_send_timeout 7d;
    }
}
```

**Notas importantes:**
- `127.0.0.1` en lugar de `localhost` (evita problemas IPv6)
- `try_files` para SPA routing de React
- `proxy_http_version 1.1` necesario para WebSocket
- Timeouts largos en /ws para mantener conexión

### Permisos

```bash
# Verificar permisos del usuario
groups fpvcopilotsky
# Debe incluir: dialout, video

# Frontend dist/
ls -l /opt/FPVCopilotSky/frontend/client/dist
# Debe ser: fpvcopilotsky:www-data con 755

# Si hay problemas:
sudo chown -R fpvcopilotsky:www-data /opt/FPVCopilotSky/frontend/client/dist
sudo chmod -R 755 /opt/FPVCopilotSky/frontend/client/dist
```

##  🛠️ Troubleshooting

### "Welcome to nginx" en lugar de la app

```bash
# Ejecutar fix automático
bash scripts/fix-nginx.sh

# O manualmente:
sudo rm /etc/nginx/sites-enabled/default
sudo ln -sf /etc/nginx/sites-available/fpvcopilot-sky /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Backend no responde

```bash
# Ver logs
sudo journalctl -u fpvcopilot-sky -f

# Verificar puerto
ss -tlnp | grep 8000

# Verificar proceso
ps aux | grep uvicorn

# Reiniciar
sudo systemctl restart fpvcopilot-sky

# Si falla al arrancar, ver errores
sudo journalctl -u fpvcopilot-sky -n 50
```

### WebSocket no conecta

```bash
# Verificar nginx
sudo nginx -t

# Ver logs nginx
sudo tail -f /var/log/nginx/error.log

# Verificar proxy_pass en config
sudo cat /etc/nginx/sites-enabled/fpvcopilot-sky | grep -A 10 "location /ws"

# Reiniciar nginx
sudo systemctl restart nginx
```

### Puerto serie ocupado

```bash
# Ver qué proceso usa el puerto
sudo lsof /dev/ttyAML0

# Si es getty:
sudo systemctl stop serial-getty@ttyAML0.service
sudo systemctl disable serial-getty@ttyAML0.service
sudo systemctl mask serial-getty@ttyAML0.service

# Verificar permisos
ls -l /dev/ttyAML0
# Debe ser: crw-rw---- 1 root dialout

# Verificar que el usuario esté en dialout
groups fpvcopilotsky | grep dialout
```

### Permisos de cámara

```bash
# Ver cámaras disponibles
v4l2-ctl --list-devices

# Verificar grupo video
groups fpvcopilotsky | grep video

# Si falta:
sudo usermod -a -G video fpvcopilotsky

# Relogin necesario
sudo systemctl restart fpvcopilot-sky
```

## 🔄 Actualizar la Aplicación

```bash
cd /opt/FPVCopilotSky

# Pull cambios
git pull origin main

# Re-desplegar
bash scripts/deploy.sh

# Verificar
bash scripts/status.sh
sudo journalctl -u fpvcopilot-sky -f
```

## 🧹 Mantenimiento

### Limpiar logs antiguos

```bash
# Ver espacio usado por logs
sudo journalctl --disk-usage

# Limpiar logs antiguos (mantener 7 días)
sudo journalctl --vacuum-time=7d

# O por tamaño (mantener 100MB)
sudo journalctl --vacuum-size=100M
```

### Backup de Configuración

```bash
# Backup completo
cd /opt
sudo tar -czf fpvcopilot-backup-$(date +%Y%m%d).tar.gz \
    FPVCopilotSky/preferences.json \
    FPVCopilotSky/preferences.json.backup*

# Restaurar
sudo tar -xzf fpvcopilot-backup-20260206.tar.gz -C /opt/
```

## 📊 Monitoreo

### Recursos del Sistema

```bash
# CPU y memoria
htop

# Temperaturas (si disponible)
vcgencmd measure_temp

# Espacio en disco
df -h

# Uso de red
iftop
```

### Estadísticas del Servicio

```bash
# Tiempo de uptime
sudo systemctl status fpvcopilot-sky | grep Active

# Memoria usada
ps aux | grep uvicorn | awk '{print $6/1024 " MB"}'
```

## 🐳 Alternativa: Docker (Próximamente)

En desarrollo: contenedor Docker para despliegue simplificado.

```bash
# Build
docker build -t fpvcopilot-sky .

# Run
docker run -d \
  --name fpvcopilot \
  --device=/dev/video0 \
  --device=/dev/ttyAML0 \
  -p 80:80 \
  -v /opt/FPVCopilotSky/preferences.json:/app/preferences.json \
  fpvcopilot-sky
```

---

## 📚 Ver También

- [README.md](../README.md) - Guía de usuario
- [DEVELOPMENT.md](../DEVELOPMENT.md) - Guía de desarrollo
- [VPN_INTEGRATION.md](VPN_INTEGRATION.md) - Sistema VPN

**¿Problemas?** Revisa logs con `sudo journalctl -u fpvcopilot-sky -f` y abre un issue en GitHub.
