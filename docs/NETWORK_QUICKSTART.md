# 🌐 Guía Rápida: Gestión de Red Mejorada

## ¿Qué ha cambiado?

El sistema ahora gestiona automáticamente la prioridad de red (4G vs WiFi) de forma inteligente, con soporte completo para VPN sin interrupciones.

## 🚀 Uso Rápido

### 1. Modo Auto (Recomendado)

El sistema ajustará automáticamente la prioridad cada 30 segundos:
- **4G disponible** → Usa 4G como primario
- **Solo WiFi** → Usa WiFi
- **Cambios suaves** → No interrumpe VPN

**No necesitas hacer nada, está activo por defecto.**

### 2. Forzar Prioridad Manualmente

#### Desde la API:

**Modo 4G (Módem primario):**
```bash
curl -X POST http://localhost:8000/api/network/priority \
  -H "Content-Type: application/json" \
  -d '{"mode": "modem"}'
```

**Modo WiFi (WiFi primario):**
```bash
curl -X POST http://localhost:8000/api/network/priority \
  -H "Content-Type: application/json" \
  -d '{"mode": "wifi"}'
```

**Modo Auto (El sistema decide):**
```bash
curl -X POST http://localhost:8000/api/network/priority \
  -H "Content-Type: application/json" \
  -d '{"mode": "auto"}'
```

### 3. Ver Estado de Red

```bash
curl -s http://localhost:8000/api/network/status | python3 -m json.tool
```

Muestra:
- Interfaces detectadas (WiFi, 4G)
- Interface primaria actual
- Rutas configuradas
- Estado del módem

### 4. Ver Rutas

```bash
curl -s http://localhost:8000/api/network/routes | python3 -m json.tool
```

O directamente desde el sistema:
```bash
ip route show default
```

## 🧪 Testing

Ejecuta el script de pruebas:

```bash
/opt/FPVCopilotSky/scripts/test-network-management.sh
```

Este script verifica:
- ✅ Estado de red actual
- ✅ Rutas configuradas
- ✅ VPN activa
- ✅ Auto-ajuste funcional
- ✅ Cooldown de cambios
- ✅ Modo auto

## 📊 Monitoreo en Tiempo Real

### Ver Logs de Red:
```bash
journalctl -u fpvcopilot-sky -f | grep -i network
```

### Monitorear Estado Cada 5 Segundos:
```bash
watch -n 5 'curl -s http://localhost:8000/api/network/status | python3 -m json.tool'
```

### Ver Cambios de Auto-Ajuste:
```bash
journalctl -u fpvcopilot-sky -f | grep "auto-adjusted"
```

## 🔧 Configuración Avanzada

### Cambiar Frecuencia de Auto-Ajuste

Editar [app/main.py](../app/main.py):

```python
# Línea ~166
if counter % 30 == 0:  # Cambiar 30 a 60 para cada minuto
    result = await network_service.auto_adjust_priority()
```

### Cambiar Tiempo de Transición VPN

Editar [app/services/network_service.py](../app/services/network_service.py):

```python
# Línea ~74
ROUTE_TRANSITION_DELAY = 2  # Segundos (aumentar si VPN se cae)
```

### Cambiar Cooldown

Editar [app/services/network_service.py](../app/services/network_service.py):

```python
# Línea ~81
self._priority_change_cooldown = 5  # Segundos mínimos entre cambios
```

## ❓ Preguntas Frecuentes

### ¿Por qué mi VPN no se cae al cambiar de red?
El sistema detecta cuando Tailscale está activo y hace transiciones suaves:
1. Agrega la nueva ruta con la métrica deseada
2. Espera 2 segundos (las conexiones migran)
3. Elimina la ruta antigua
4. La VPN se mantiene conectada durante todo el proceso

### ¿Qué son las métricas?
Las métricas determinan qué ruta usa Linux (menor = preferida):
- **10**: Reservada para VPN (Tailscale)
- **100**: Red primaria (4G cuando está disponible)
- **200**: Red secundaria (WiFi como backup)
- **600**: Red terciaria (backup adicional)

### ¿Puedo deshabilitar el auto-ajuste?
Sí, simplemente fuerza un modo específico:
```bash
# Forzar modem siempre
curl -X POST http://localhost:8000/api/network/priority \
  -d '{"mode": "modem"}'
```

El auto-ajuste no sobreescribirá modos forzados si las interfaces están UP.

### ¿Cada cuánto ajusta automáticamente?
Cada 30 segundos, pero solo si detecta que es necesario un cambio.

### ¿Qué pasa si cambio muy rápido?
Hay un cooldown de 5 segundos entre cambios para evitar inestabilidad.

## 🐛 Troubleshooting

### VPN se sigue cayendo al cambiar de red

1. Aumentar el tiempo de transición:
   ```python
   # En network_service.py
   ROUTE_TRANSITION_DELAY = 5  # Aumentar a 5 segundos
   ```

2. Verificar que Tailscale está realmente activo:
   ```bash
   tailscale status
   ip link show | grep tailscale
   ```

3. Ver logs durante el cambio:
   ```bash
   journalctl -u fpvcopilot-sky -f | grep -E "VPN|route|metric"
   ```

### Cambios muy frecuentes (flapping)

1. Verificar interfaces:
   ```bash
   ip addr show
   ```

2. Aumentar cooldown:
   ```python
   # En network_service.py
   self._priority_change_cooldown = 10  # 10 segundos
   ```

3. Usar modo forzado en lugar de auto:
   ```bash
   curl -X POST http://localhost:8000/api/network/priority \
     -d '{"mode": "modem"}'
   ```

### Módem 4G no detectado

1. Verificar conexión USB:
   ```bash
   lsusb | grep -i modem
   ```

2. Verificar IP 192.168.8.x:
   ```bash
   ip addr show | grep "192.168.8"
   ```

3. Forzar re-detección:
   ```bash
   curl http://localhost:8000/api/network/status
   ```

## 📚 Documentación Completa

- [NETWORK_MANAGEMENT.md](./NETWORK_MANAGEMENT.md) - Guía técnica completa
- [NETWORK_IMPROVEMENTS.md](./NETWORK_IMPROVEMENTS.md) - Resumen de cambios
- [VPN_INTEGRATION.md](./VPN_INTEGRATION.md) - Integración con Tailscale

## 🆘 Soporte

Si encuentras problemas:

1. **Revisa los logs:**
   ```bash
   journalctl -u fpvcopilot-sky -n 100
   ```

2. **Ejecuta el test:**
   ```bash
   /opt/FPVCopilotSky/scripts/test-network-management.sh
   ```

3. **Verifica routing:**
   ```bash
   ip route show default
   ```

4. **Crea un issue** en el repositorio con:
   - Output del test script
   - Logs relevantes
   - Configuración de red (`ip addr show`)
