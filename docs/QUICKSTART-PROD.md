# 🚀 FPV Copilot Sky - Quick Start (Producción)

## 1️⃣ Primera vez - Setup (30 minutos)

### Paso 1: Setup de producción
```bash
sudo bash /opt/FPVCopilotSky/scripts/install-production.sh
```
Instala nginx y configura el sistema.

### Paso 2: Deploy
```bash
bash /opt/FPVCopilotSky/scripts/deploy.sh
```
Compila el frontend, activa el servicio, inicia todo.

### Paso 3: Acceder
Abre navegador: **http://192.168.1.145** (sustituye con tu IP de Radxa)

✅ **Listo!** La aplicación estará corriendo y se auto-iniciará al reiniciar.

---

## 2️⃣ Día a día

### Ver estado
```bash
bash /opt/FPVCopilotSky/scripts/status.sh
```

### Ver logs
```bash
sudo journalctl -u fpvcopilot-sky -f
```

### Actualizar
```bash
bash /opt/FPVCopilotSky/scripts/deploy.sh
```

---

## 3️⃣ Desarrollo en paralelo

```bash
# En otra terminal
bash /opt/FPVCopilotSky/scripts/dev.sh
```

Accede en: **http://localhost:5173**

Producción sigue funcionando en **http://192.168.1.145**

---

## 🆘 Si algo no funciona

### Ve "Welcome to nginx"
```bash
bash /opt/FPVCopilotSky/scripts/fix-nginx.sh
```

### Backend no responde
```bash
sudo systemctl restart fpvcopilot-sky
sudo journalctl -u fpvcopilot-sky -f
```

### frontend no aparece
```bash
bash /opt/FPVCopilotSky/scripts/deploy.sh
```

---

## 📋 Comandos útiles

```bash
# Estado completo
bash /opt/FPVCopilotSky/scripts/status.sh

# Logs en tiempo real
sudo journalctl -u fpvcopilot-sky -f

# Reiniciar servicio
sudo systemctl restart fpvcopilot-sky

# Detener servicio
sudo systemctl stop fpvcopilot-sky

# Iniciar servicio
sudo systemctl start fpvcopilot-sky

# Ver estado
sudo systemctl status fpvcopilot-sky

# Deshabilitar auto-inicio
sudo systemctl disable fpvcopilot-sky

# Habilitar auto-inicio
sudo systemctl enable fpvcopilot-sky
```

---

**Más información**: [docs/PRODUCTION.md](../docs/PRODUCTION.md)
