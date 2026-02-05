# FPV Copilot Sky - Production Deployment Guide

## 📋 Descripción General

Este proyecto puede ejecutarse en dos modos:

1. **🚀 Modo Producción**: Servicio systemd automático al arrancar + Nginx
2. **🛠️ Modo Desarrollo**: Hot reload para desarrollo continuo

## 🏗️ Arquitectura de Producción

```
┌─────────────────────────────────────────────┐
│  Cliente (Navegador)                        │
│  http://radxa-ip                            │
└────────────┬────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────┐
│  Nginx (Puerto 80)                          │
│  - Sirve frontend estático (React build)    │
│  - Proxy /api/* → Backend                   │
│  - Proxy /ws → WebSocket                    │
└────────────┬────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────┐
│  Backend FastAPI (Puerto 8000)              │
│  - Servicio systemd: fpvcopilot-sky         │
│  - Auto-inicia al arrancar                  │
│  - Auto-restart si falla                    │
└─────────────────────────────────────────────┘
```

## 🚀 Setup Inicial de Producción

### 1. Instalar dependencias de producción

```bash
sudo bash /opt/FPVCopilotSky/scripts/install-production.sh
```

Esto instala:
- Nginx (deshabilita el site por defecto automáticamente)
- Configura permisos
- Prepara el entorno

### 2. Compilar y desplegar

```bash
bash /opt/FPVCopilotSky/scripts/deploy.sh
```

Esto:
- ✅ Compila el frontend (React → build estático)
- ✅ Instala el servicio systemd
- ✅ Configura nginx (deshabilita default site)
- ✅ Verifica permisos y propietarios de archivos
- ✅ Inicia el servicio automáticamente
- ✅ Habilita auto-inicio al arrancar
- ✅ Realiza health check

### 3. Verificar funcionamiento

```bash
# Ver estado del servicio
sudo systemctl status fpvcopilot-sky

# Ver logs en tiempo real
sudo journalctl -u fpvcopilot-sky -f

# Verificar nginx
sudo systemctl status nginx

# Quick status check
bash /opt/FPVCopilotSky/scripts/status.sh
```

### 4. Acceder a la aplicación

Abre un navegador y ve a:
```
http://192.168.1.145
```
(Sustituye con la IP de tu Radxa)

**Si ves "Welcome to nginx"** en lugar de la aplicación, ejecuta:
```bash
bash /opt/FPVCopilotSky/scripts/fix-nginx.sh
```

## 🛠️ Desarrollo en Paralelo

### Opción 1: Script de desarrollo automático

```bash
bash /opt/FPVCopilotSky/scripts/dev.sh
```

Esto inicia:
- **Backend** en puerto 8001 (o 8000 si producción está parada) con hot reload
- **Frontend** en puerto 5173 con hot reload
- Ambos se detienen con Ctrl+C

Acceso:
- Frontend Dev: `http://localhost:5173`
- Backend Dev: `http://localhost:8001`
- API Docs: `http://localhost:8001/docs`

### Opción 2: Manual (mayor control)

#### Terminal 1 - Backend
```bash
cd /opt/FPVCopilotSky
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

#### Terminal 2 - Frontend
```bash
cd /opt/FPVCopilotSky/frontend/client
npm run dev
```

## 📊 Gestión del Servicio

### Comandos útiles

```bash
# Iniciar servicio
sudo systemctl start fpvcopilot-sky

# Detener servicio
sudo systemctl stop fpvcopilot-sky

# Reiniciar servicio
sudo systemctl restart fpvcopilot-sky

# Ver estado
sudo systemctl status fpvcopilot-sky

# Habilitar auto-inicio (ya hecho por deploy.sh)
sudo systemctl enable fpvcopilot-sky

# Deshabilitar auto-inicio
sudo systemctl disable fpvcopilot-sky

# Ver logs en tiempo real
sudo journalctl -u fpvcopilot-sky -f

# Ver logs recientes
sudo journalctl -u fpvcopilot-sky -n 100

# Ver logs desde hoy
sudo journalctl -u fpvcopilot-sky --since today
```

### Nginx

```bash
# Reiniciar nginx
sudo systemctl restart nginx

# Verificar configuración
sudo nginx -t

# Recargar configuración (sin downtime)
sudo systemctl reload nginx

# Ver logs de acceso
sudo tail -f /var/log/nginx/fpvcopilot-sky-access.log

# Ver logs de errores
sudo tail -f /var/log/nginx/fpvcopilot-sky-error.log
```

## 🔄 Workflow de Actualización

### Actualizar la aplicación en producción:

```bash
# 1. Hacer cambios en el código
# 2. Re-desplegar
bash /opt/FPVCopilotSky/scripts/deploy.sh
```

El script automáticamente:
1. Compila el nuevo frontend
2. Reinicia el servicio backend
3. Recarga nginx

### Solo actualizar backend:

```bash
sudo systemctl restart fpvcopilot-sky
```

### Solo actualizar frontend:

```bash
cd /opt/FPVCopilotSky/frontend/client
npm run build
# Nginx automáticamente sirve el nuevo build
```

## 🔧 Configuración

### Backend (Systemd)

Editar: `/etc/systemd/system/fpvcopilot-sky.service`

Después de editar:
```bash
sudo systemctl daemon-reload
sudo systemctl restart fpvcopilot-sky
```

### Nginx

Editar: `/etc/nginx/sites-available/fpvcopilot-sky`

Después de editar:
```bash
sudo nginx -t  # Verificar sintaxis
sudo systemctl reload nginx
```

### Variables de entorno

Editar servicio systemd para añadir variables:
```ini
[Service]
Environment="VARIABLE=valor"
Environment="OTRA_VAR=otro_valor"
```

## 🐛 Troubleshooting

### Ve "Welcome to nginx" en lugar de la aplicación

**Causa:** El site por defecto de nginx está habilitado y tiene prioridad.

**Solución:**
```bash
# Opción 1: Correr script de fix
bash /opt/FPVCopilotSky/scripts/fix-nginx.sh

# Opción 2: Manual
sudo rm /etc/nginx/sites-enabled/default
sudo systemctl reload nginx
```

**Verificar que está arreglado:**
```bash
curl http://localhost/
# Debería devolver el HTML del React app (no "Welcome to nginx")
```

### El servicio no inicia

```bash
# Ver logs detallados
sudo journalctl -u fpvcopilot-sky -xe

# Verificar que el puerto 8000 esté libre
sudo lsof -i :8000

# Probar backend manualmente
cd /opt/FPVCopilotSky
source venv/bin/activate
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Nginx muestra error 502 Bad Gateway

El backend no está corriendo:
```bash
sudo systemctl status fpvcopilot-sky
sudo systemctl start fpvcopilot-sky
```

### Frontend no carga

```bash
# Verificar que el build existe
ls -la /opt/FPVCopilotSky/frontend/client/dist/

# Si no existe, compilar
cd /opt/FPVCopilotSky/frontend/client
npm run build

# Verificar permisos
sudo chown -R www-data:www-data /opt/FPVCopilotSky/frontend/client/dist/

# Redeployer
bash /opt/FPVCopilotSky/scripts/deploy.sh
```

### WebSocket no conecta

Verificar configuración nginx:
```bash
sudo nginx -t
sudo tail -f /var/log/nginx/fpvcopilot-sky-error.log
```

## 📱 Puertos Utilizados

| Servicio | Puerto | Uso |
|----------|--------|-----|
| Nginx | 80 | Frontend + Proxy (Producción) |
| Backend Prod | 8000 | FastAPI (via systemd) |
| Backend Dev | 8001 | FastAPI (desarrollo) |
| Frontend Dev | 5173 | Vite dev server |

## 🔐 Seguridad

### Para producción externa (internet):

1. **Agregar HTTPS con Let's Encrypt:**
```bash
sudo apt-get install certbot python3-certbot-nginx
sudo certbot --nginx -d tu-dominio.com
```

2. **Firewall:**
```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

## ✅ Checklist de Producción

- [ ] Ejecutar `install-production.sh`
- [ ] Ejecutar `deploy.sh`
- [ ] Verificar servicio: `systemctl status fpvcopilot-sky`
- [ ] Verificar nginx: `systemctl status nginx`
- [ ] Acceder desde navegador: `http://radxa-ip`
- [ ] Verificar auto-inicio: `sudo reboot` y comprobar que todo inicia

## 💡 Tips

1. **Logs en tiempo real durante desarrollo:**
   ```bash
   sudo journalctl -u fpvcopilot-sky -f
   ```

2. **Modo desarrollo sin conflictos:**
   - Detén producción: `sudo systemctl stop fpvcopilot-sky`
   - Usa script dev: `bash scripts/dev.sh`
   - Reinicia producción: `sudo systemctl start fpvcopilot-sky`

3. **Backup antes de updates:**
   ```bash
   cp -r /opt/FPVCopilotSky /opt/FPVCopilotSky.backup
   ```

4. **Monitorear recursos:**
   ```bash
   # CPU/Memoria del servicio
   systemctl status fpvcopilot-sky
   
   # Procesos Python
   ps aux | grep python
   
   # htop para vista general
   htop
   ```
