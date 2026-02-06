# 🔄 Mejoras en Gestión de Red y Métricas - Resumen de Cambios

## Fecha: 6 de febrero de 2026

## 🎯 Problema Identificado

El sistema de gestión de red tenía los siguientes problemas:

1. **Cambios abruptos de rutas**: Eliminaba rutas activas sin verificar conexiones VPN
2. **Sin coordinación con VPN**: Los cambios de red interrumpían Tailscale
3. **Sin prioridad automática 4G**: No priorizaba automáticamente el módem 4G sobre WiFi
4. **Cambios muy frecuentes**: No había cooldown, causando inestabilidad

## ✅ Solución Implementada

### 1. Transiciones Suaves (VPN-Aware) ⭐

**Archivos modificados:**
- `app/services/network_service.py`

**Cambios:**
- ✅ Detecta automáticamente si Tailscale está activo
- ✅ Si VPN activa: Agrega nueva ruta ANTES de eliminar la antigua
- ✅ Período de transición de 2 segundos para migración
- ✅ Evita interrupciones en túneles VPN

**Métodos nuevos:**
```python
async def _is_vpn_active() -> Tuple[bool, Optional[str]]
async def _set_interface_metric_smooth(interface, metric, vpn_active)
async def _set_modem_metric_smooth(metric, vpn_active)
```

**Flujo de transición:**
```
VPN Activa:
1. Detectar VPN (tailscale0)
2. Agregar ruta nueva con métrica deseada
3. Esperar 2 segundos (conexiones migran)
4. Eliminar ruta antigua
5. Persistir en NetworkManager

Sin VPN:
1. Eliminar ruta antigua
2. Agregar ruta nueva
3. Persistir en NetworkManager
```

### 2. Métricas Actualizadas

**Antes:**
```python
METRIC_PRIMARY = 50      # Principal
METRIC_SECONDARY = 100   # Secundario
METRIC_TERTIARY = 600    # Terciario
```

**Ahora:**
```python
METRIC_VPN = 10          # VPN (máxima prioridad)
METRIC_PRIMARY = 100     # 4G Módem
METRIC_SECONDARY = 200   # WiFi Backup
METRIC_TERTIARY = 600    # Backup adicional
```

**Justificación:**
- Métrica 10 reservada para VPN (Tailscale gestiona esto)
- 100 para red primaria (4G)
- 200 para red secundaria (WiFi)
- Mayor separación entre métricas para mejor control

### 3. Modo Auto y Auto-Ajuste 🤖

**Archivos modificados:**
- `app/services/network_service.py`
- `app/api/routes/network.py`
- `app/main.py`

**Nuevo método:**
```python
async def auto_adjust_priority() -> Dict
```

**Características:**
- ✅ Detecta qué interfaces están UP y con IP
- ✅ Prioriza 4G sobre WiFi automáticamente
- ✅ Solo cambia si es necesario (no cambios innecesarios)
- ✅ Integrado en loop periódico (cada 30 segundos)

**Modo 'auto' añadido:**
```python
# API ahora acepta 3 modos:
POST /api/network/priority
{
  "mode": "auto"  // "wifi" | "modem" | "auto"
}
```

**Comportamiento auto:**
- Si 4G disponible → 4G primario (100), WiFi backup (200)
- Si solo WiFi → WiFi primario (100)

### 4. Cooldown y Rate Limiting ⏱️

**Propiedades agregadas:**
```python
self._last_priority_change = 0  # Timestamp
self._priority_change_cooldown = 5  # Segundos
```

**Comportamiento:**
- Mínimo 5 segundos entre cambios de prioridad
- Previene "flapping" de red
- Flag `force=True` para bypass si necesario

### 5. API Endpoints Nuevos

**Endpoint de auto-ajuste:**
```bash
POST /api/network/priority/auto-adjust
```

Ajusta prioridad basándose en disponibilidad actual.

**Respuesta mejorada:**
```json
{
  "success": true,
  "mode": "modem",
  "wifi_metric": 200,
  "modem_metric": 100,
  "vpn_active": true,
  "vpn_interface": "tailscale0",
  "reason": "4G modem available (primary)",
  "changed": true
}
```

### 6. Monitoreo Automático en Background

**Archivo modificado:** `app/main.py`

**Funcionalidad:**
- Auto-ajuste cada 30 segundos en `periodic_stats_broadcast()`
- Solo registra log si hubo cambio real
- Broadcast automático de nuevo estado a WebSockets

```python
# Auto-adjust network priority every 30 seconds
if counter % 30 == 0:
    result = await network_service.auto_adjust_priority()
    if result.get('changed'):
        logger.info(f"Network priority auto-adjusted: {result.get('reason')}")
        network_status = await network_service.get_status()
        await websocket_manager.broadcast("network_status", {...})
```

## 📊 Comparación: Antes vs Ahora

| Aspecto | Antes | Ahora |
|---------|-------|-------|
| **VPN Aware** | ❌ No | ✅ Sí (detección automática) |
| **Transición** | Abrupta | Suave (2s overlap) |
| **Prioridad Auto** | ❌ Manual solo | ✅ Auto cada 30s |
| **Cooldown** | ❌ No | ✅ 5 segundos |
| **Modo Auto** | ❌ No | ✅ Sí |
| **Métrica VPN** | No considerada | 10 (reservada) |
| **Métrica 4G** | 50 o 600 | 100 (fijo primario) |
| **Métrica WiFi** | 50 o 600 | 200 (fijo backup) |

## 🚀 Beneficios

### Para el Usuario:
1. **Conexiones VPN estables**: No se caen al cambiar de 4G a WiFi
2. **Prioridad automática**: El sistema siempre usa 4G cuando está disponible
3. **Failover suave**: Cambio a WiFi sin interrupciones
4. **Menor latencia**: Métricas mejor ajustadas

### Para el Sistema:
1. **Fewer route changes**: Cooldown previene cambios frecuentes
2. **Better resource usage**: Solo cambia cuando es necesario
3. **VPN resilience**: Tailscale se mantiene conectado
4. **Logging mejorado**: Trazabilidad de cambios

## 🧪 Testing Recomendado

### Test 1: Cambio de 4G a WiFi con VPN
```bash
# 1. Conectar Tailscale
tailscale up

# 2. Verificar ruta actual (debe ser 4G)
ip route show default

# 3. Desconectar 4G (simular pérdida)
sudo ip link set <modem_interface> down

# 4. Esperar 30s (auto-ajuste)
# 5. Verificar que cambió a WiFi sin caer VPN
tailscale status
```

### Test 2: Cooldown
```bash
# Cambiar a modem
curl -X POST http://localhost:8000/api/network/priority \
  -H "Content-Type: application/json" \
  -d '{"mode": "modem"}'

# Intentar cambiar inmediatamente (debe fallar con cooldown)
curl -X POST http://localhost:8000/api/network/priority \
  -H "Content-Type: application/json" \
  -d '{"mode": "wifi"}'

# Esperar 5 segundos y reintentar (debe funcionar)
```

### Test 3: Auto-Adjust
```bash
# Verificar auto-ajuste
curl -X POST http://localhost:8000/api/network/priority/auto-adjust

# Ver logs
journalctl -u fpvcopilot-sky -f | grep "auto-adjusted"
```

## 📝 Notas de Implementación

### Compatibilidad
- ✅ Compatible con Tailscale 1.x+
- ✅ Compatible con NetworkManager
- ✅ Requiere Linux kernel 3.10+

### Permisos Requeridos
Los comandos de routing requieren sudo:
```bash
sudo ip route add/del default ...
```

Asegurar que el usuario tiene permisos en `/etc/sudoers.d/fpvcopilot-system`

### Configuración Personalizable

Ajustar tiempos en `network_service.py`:
```python
ROUTE_TRANSITION_DELAY = 2  # Segundos de overlap
_priority_change_cooldown = 5  # Segundos entre cambios
```

Ajustar frecuencia de auto-ajuste en `main.py`:
```python
if counter % 30 == 0:  # Cambiar a 60 para cada 1 minuto
    await network_service.auto_adjust_priority()
```

## 📚 Documentación Generada

- ✅ `docs/NETWORK_MANAGEMENT.md` - Guía completa de gestión de red
- ✅ `docs/NETWORK_IMPROVEMENTS.md` - Este documento (resumen de cambios)

## 🔗 Referencias

- Linux Advanced Routing: https://lartc.org/
- Tailscale Docs: https://tailscale.com/kb/
- NetworkManager: https://networkmanager.dev/

## ✨ Próximos Pasos (Opcional)

1. **Métricas de telemetría**: Agregar contador de cambios de red en WebUI
2. **Notificaciones**: Alertar al usuario cuando cambia la red primaria
3. **Dashboard de red**: Visualizar routing table en tiempo real
4. **Ping monitoring**: Monitorear latencia para decidir mejor ruta
5. **Multi-VPN**: Soportar ZeroTier junto con Tailscale

---

**Implementado por:** GitHub Copilot (Claude Sonnet 4.5)  
**Fecha:** 6 de febrero de 2026  
**Versión:** FPVCopilotSky 1.0.0+
