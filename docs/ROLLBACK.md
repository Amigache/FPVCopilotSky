# 🔄 Rollback de Mejoras de Red

## Script de Rollback

Si necesitas revertir las mejoras de gestión de red, usa el script de rollback incluido.

## 🚀 Uso Rápido

```bash
sudo bash /opt/FPVCopilotSky/scripts/rollback-network-improvements.sh
```

## 📋 Opciones Disponibles

El script ofrece un menú interactivo con las siguientes opciones:

### 1. Rollback Completo
Revierte todos los cambios:
- ✅ Restaura archivos desde git (si disponible)
- ✅ Deshabilita auto-ajuste automático
- ✅ Elimina documentación nueva
- ✅ Restaura permisos sudoers
- ✅ Reinicia el servicio

**Usa esta opción si quieres volver completamente al estado anterior.**

### 2. Deshabilitar Solo Auto-Ajuste
Mantiene las mejoras pero deshabilita el auto-ajuste cada 30 segundos:
- ✅ Crea backup de archivos actuales
- ✅ Comenta el código de auto-ajuste en `main.py`
- ✅ Reinicia el servicio
- ❌ Mantiene transiciones suaves VPN
- ❌ Mantiene endpoints de API

**Usa esta opción si las mejoras funcionan pero no quieres auto-ajuste.**

### 3. Eliminar Solo Documentación
Elimina los archivos de documentación creados:
- `docs/NETWORK_MANAGEMENT.md`
- `docs/NETWORK_IMPROVEMENTS.md`
- `docs/NETWORK_QUICKSTART.md`
- `scripts/test-network-management.sh`

**Usa esto si solo quieres limpiar documentación.**

### 4. Restaurar Sudoers
Restaura el archivo sudoers eliminando permisos de rutas:
- ✅ Mantiene permisos de systemctl
- ✅ Elimina permisos de `ip route add/del/change`

**Usa esto si consideras los permisos de rutas un riesgo de seguridad.**

### 5. Crear Backup Solo
Crea backup de archivos actuales sin hacer cambios:
- Guarda en: `/opt/FPVCopilotSky/backups/network_improvements_TIMESTAMP/`

**Usa esto antes de probar cambios manuales.**

### 6. Ver Estado Git
Muestra el estado de git del proyecto (archivos modificados).

## 📖 Ejemplos de Uso

### Rollback Completo
```bash
sudo bash /opt/FPVCopilotSky/scripts/rollback-network-improvements.sh
# Seleccionar opción 1
# Confirmar con 'y'
```

### Solo Deshabilitar Auto-Ajuste
```bash
sudo bash /opt/FPVCopilotSky/scripts/rollback-network-improvements.sh
# Seleccionar opción 2
```

### Crear Backup de Seguridad
```bash
sudo bash /opt/FPVCopilotSky/scripts/rollback-network-improvements.sh
# Seleccionar opción 5
```

## 🔙 Restauración Manual desde Git

Si tienes git y prefieres hacerlo manualmente:

```bash
cd /opt/FPVCopilotSky

# Ver archivos modificados
git status

# Restaurar archivos específicos
git checkout HEAD -- app/services/network_service.py
git checkout HEAD -- app/api/routes/network.py
git checkout HEAD -- app/main.py
git checkout HEAD -- scripts/setup-system-sudoers.sh

# Reiniciar servicio
sudo systemctl restart fpvcopilot-sky
```

## 🔙 Restauración Manual desde Backup

Si el script creó un backup:

```bash
# Listar backups disponibles
ls -la /opt/FPVCopilotSky/backups/

# Restaurar desde backup específico
BACKUP_DIR="/opt/FPVCopilotSky/backups/network_improvements_20260206_120000"

cp "$BACKUP_DIR/network_service.py" /opt/FPVCopilotSky/app/services/
cp "$BACKUP_DIR/network.py" /opt/FPVCopilotSky/app/api/routes/
cp "$BACKUP_DIR/main.py" /opt/FPVCopilotSky/app/
cp "$BACKUP_DIR/setup-system-sudoers.sh" /opt/FPVCopilotSky/scripts/

# Reiniciar servicio
sudo systemctl restart fpvcopilot-sky
```

## ⚠️ Advertencias

### Antes del Rollback
- ✅ Crear backup actual (opción 5)
- ✅ Anotar configuración de red actual
- ✅ Verificar que no hay streaming activo
- ✅ Cerrar conexiones de telemetría

### Después del Rollback
- ✅ Verificar que el servicio inició: `systemctl status fpvcopilot-sky`
- ✅ Comprobar red: `curl http://localhost:8000/api/network/status`
- ✅ Verificar rutas: `ip route show default`
- ✅ Probar VPN si está activa: `tailscale status`

## 🔍 Verificación Post-Rollback

### Verificar Servicio
```bash
sudo systemctl status fpvcopilot-sky
```

### Verificar API
```bash
curl -s http://localhost:8000/api/network/status | python3 -m json.tool
```

### Verificar Rutas
```bash
ip route show default
```

### Verificar Logs
```bash
sudo journalctl -u fpvcopilot-sky -n 50 --no-pager
```

## 🐛 Problemas Comunes

### Servicio No Inicia Después del Rollback

**Síntoma**: `systemctl status fpvcopilot-sky` muestra failed

**Solución**:
```bash
# Ver error específico
sudo journalctl -u fpvcopilot-sky -n 50 --no-pager

# Si hay error de sintaxis Python, restaurar desde backup completo
sudo bash /opt/FPVCopilotSky/scripts/rollback-network-improvements.sh
# Opción 1 (rollback completo)
```

### Git No Disponible

**Síntoma**: "No git repository found"

**Solución**: El rollback automático no funcionará completamente. Necesitas:
1. Usar backup creado (opción 5 primero)
2. O restaurar desde instalación limpia
3. O editar manualmente los archivos

### Permisos Sudo No Funcionan

**Síntoma**: "sudo: a password is required"

**Solución**:
```bash
# Restaurar sudoers manualmente
sudo bash /opt/FPVCopilotSky/scripts/setup-system-sudoers.sh
```

### Rutas No Se Restablecen

**Síntoma**: Métricas incorrectas después del rollback

**Solución**:
```bash
# Reiniciar NetworkManager
sudo systemctl restart NetworkManager

# O reiniciar sistema completo
sudo reboot
```

## 📦 Archivos Afectados por Rollback

| Archivo | Cambios Revertidos |
|---------|-------------------|
| `app/services/network_service.py` | Elimina VPN-aware, auto-adjust, transiciones suaves |
| `app/api/routes/network.py` | Elimina endpoint auto-adjust, modo 'auto' |
| `app/main.py` | Elimina auto-ajuste en periodic_stats_broadcast |
| `scripts/setup-system-sudoers.sh` | Elimina permisos de rutas |
| `docs/NETWORK_*.md` | Documentación eliminada |
| `scripts/test-network-management.sh` | Script de pruebas eliminado |

## 🔐 Seguridad

El script de rollback:
- ✅ Requiere sudo (verifica EUID)
- ✅ Crea backup antes de cambios
- ✅ Valida sintaxis de sudoers
- ✅ Muestra advertencias claras
- ✅ Permite cancelar en cualquier momento

## 📞 Soporte

Si el rollback falla o tienes problemas:

1. **Revisar logs**:
   ```bash
   sudo journalctl -u fpvcopilot-sky -n 100
   ```

2. **Contactar soporte** con:
   - Output del script de rollback
   - Logs del servicio
   - Estado de red actual (`ip addr`, `ip route`)

3. **Reinstalación limpia** (última opción):
   ```bash
   cd /opt/FPVCopilotSky
   sudo bash install.sh
   ```

## ✅ Confirmación de Rollback Exitoso

Después del rollback, verifica que:

- [ ] Servicio fpvcopilot-sky está activo
- [ ] API responde en http://localhost:8000
- [ ] Endpoint `/api/network/status` funciona
- [ ] No hay errores en logs recientes
- [ ] Rutas de red están configuradas
- [ ] VPN (si activa) sigue funcionando

Si todos los checks pasan, el rollback fue exitoso.
