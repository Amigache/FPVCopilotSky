# 🌐 Gestión de Red y Métricas

## Resumen

El sistema de gestión de red de FPVCopilotSky maneja automáticamente múltiples conexiones de red (4G y WiFi) con soporte completo para VPN, asegurando prioridad correcta y transiciones suaves que no interrumpen conexiones activas.

## 🎯 Características Principales

### 1. Prioridad Inteligente de Red
- **4G Módem**: Siempre es la red primaria cuando está disponible
- **WiFi**: Actúa como backup cuando 4G no está disponible
- **VPN**: Siempre tiene la máxima prioridad en el routing

### 2. Transiciones Suaves (VPN-Aware)
Cuando hay una VPN activa (Tailscale), el sistema implementa **transiciones suaves**:
- Se agrega la nueva ruta ANTES de eliminar la antigua
- Período de transición de 2 segundos para migración de conexiones
- Previene la interrupción de túneles VPN activos

### 3. Detección Automática
- Auto-detección de interfaces de red (4G, WiFi)
- Ajuste automático de prioridades basado en disponibilidad
- Cooldown de 5 segundos entre cambios para evitar flapping

## 📊 Métricas de Routing

El sistema usa métricas de Linux para determinar prioridad de rutas (menor = mayor prioridad):

```
METRIC_VPN = 10          # VPN (reservado para Tailscale)
METRIC_PRIMARY = 100     # Red primaria (4G cuando disponible)
METRIC_SECONDARY = 200   # Red secundaria (WiFi backup)
METRIC_TERTIARY = 600    # Red terciaria (backup adicional)
```

## 🔄 Modos de Operación

### Modo Auto (Recomendado)
```bash
POST /api/network/priority
{
  "mode": "auto"
}
```
- 4G módem como primario si está disponible
- WiFi como backup automático
- Cambio automático cuando cambia disponibilidad

### Modo Modem (4G Forzado)
```bash
POST /api/network/priority
{
  "mode": "modem"
}
```
- Fuerza 4G como primario (metric 100)
- WiFi queda como backup (metric 200)

### Modo WiFi (WiFi Forzado)
```bash
POST /api/network/priority
{
  "mode": "wifi"
}
```
- Fuerza WiFi como primario (metric 100)
- 4G queda como backup (metric 200)

## 🚀 API Endpoints

### Obtener Estado de Red
```bash
GET /api/network/status
```
Devuelve:
- Interfaces detectadas (WiFi, 4G)
- Interface primaria actual
- Modo activo
- Rutas configuradas
- Estado del módem

### Configurar Prioridad
```bash
POST /api/network/priority
{
  "mode": "auto|wifi|modem"
}
```

### Auto-Ajuste de Prioridad
```bash
POST /api/network/priority/auto-adjust
```
Ajusta automáticamente según disponibilidad. Útil para triggers o cron jobs.

### Ver Rutas
```bash
GET /api/network/routes
```
Lista todas las rutas default configuradas con sus métricas.

## 🔒 Integración con VPN

### Detección de VPN Activa
El sistema detecta automáticamente si Tailscale está activo:
```python
vpn_active, vpn_interface = await service._is_vpn_active()
```

### Transición Suave
Cuando VPN está activa, el cambio de rutas sigue este flujo:

```
1. Detectar VPN activa (tailscale0)
2. Agregar NUEVA ruta con métrica deseada
3. Esperar 2 segundos (ROUTE_TRANSITION_DELAY)
4. Eliminar ruta ANTIGUA
5. Persistir cambios en NetworkManager
```

Esto asegura que:
- La VPN no pierde conectividad
- Los paquetes en tránsito no se pierden
- Las conexiones persistentes (WebSocket, streaming) no se interrumpen

### Sin VPN
Si no hay VPN activa, el cambio es inmediato (más rápido):
```
1. Eliminar ruta antigua
2. Agregar ruta nueva con métrica deseada
3. Persistir en NetworkManager
```

## ⚡ Cooldown y Rate Limiting

Para prevenir cambios frecuentes (flapping) que puedan desestabilizar conexiones:

- **Cooldown**: 5 segundos entre cambios de prioridad
- **Force flag**: `force=True` omite el cooldown si es necesario
- **Debouncing**: Solo se ejecuta cambio si realmente hay diferencia

## 🛠️ Ejemplos de Uso

### 1. Configurar Prioridad Automática al Inicio
```python
from services.network_service import get_network_service

async def initialize_network():
    service = get_network_service()
    result = await service.set_connection_priority('auto')
    print(f"Network priority: {result}")
```

### 2. Monitorear y Auto-Ajustar
```python
async def monitor_and_adjust():
    service = get_network_service()
    
    while True:
        # Auto-ajustar cada 30 segundos
        result = await service.auto_adjust_priority()
        
        if result.get('changed'):
            logger.info(f"Network changed: {result['reason']}")
        
        await asyncio.sleep(30)
```

### 3. Cambiar a 4G Manualmente
```bash
curl -X POST http://localhost:8000/api/network/priority \
  -H "Content-Type: application/json" \
  -d '{"mode": "modem"}'
```

## 🔍 Troubleshooting

### Ver Rutas Actuales
```bash
ip route show default
```

### Ver Métricas
```bash
ip route show default | grep metric
```

### Verificar VPN
```bash
ip link show | grep tailscale
tailscale status
```

### Logs del Servicio
```bash
journalctl -u fpvcopilot-sky -f | grep -i network
```

### Problemas Comunes

#### VPN se desconecta al cambiar de red
✅ **Solucionado**: El sistema ahora implementa transiciones suaves

#### Cambios muy frecuentes de red
- Verifica el cooldown (5s por defecto)
- Usa modo 'modem' o 'wifi' forzado si auto no es estable

#### Módem no detectado
```bash
# Verificar interfaces con IP 192.168.8.x
ip addr show | grep "192.168.8"

# Forzar re-detección
curl -X GET http://localhost:8000/api/network/status
```

## 📝 Notas Técnicas

### NetworkManager Persistencia
Los cambios se persisten en NetworkManager usando:
```bash
nmcli connection modify <connection> ipv4.route-metric <metric>
```

### Sudo Requerido
Los cambios de rutas requieren privilegios sudo. Asegúrate de que el usuario ejecutando el servicio tenga permisos configurados en sudoers.

### Compatibilidad
- Linux kernel 3.10+
- NetworkManager
- iproute2
- Tailscale 1.x+

## 🚦 Estados del Sistema

| Estado | Descripción | Métrica 4G | Métrica WiFi |
|--------|-------------|------------|--------------|
| Auto + 4G disponible | 4G primario | 100 | 200 |
| Auto + solo WiFi | WiFi primario | N/A | 100 |
| Modem forzado | 4G primario | 100 | 200 |
| WiFi forzado | WiFi primario | 200 | 100 |

## 🔐 Seguridad

- Los comandos de red requieren sudo
- Rate limiting previene abuso de API
- Validación de parámetros en API
- Logs de todos los cambios de red

## 📚 Referencias

- [Linux Advanced Routing](https://lartc.org/)
- [NetworkManager Documentation](https://networkmanager.dev/)
- [Tailscale Network Topology](https://tailscale.com/kb/1019/subnets/)
