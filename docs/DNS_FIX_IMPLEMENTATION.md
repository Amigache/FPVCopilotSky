# Implementación de Preservación de DNS

## Problema Resuelto

Cuando se cambiaban las prioridades/métricas de red mediante la API `/api/network/priority`, las sesiones SSH/VSCode/Copilot perdían conectividad porque los comandos `ip route del` eliminaban la configuración DNS de `/etc/resolv.conf`.

## Solución Implementada

Se añadieron **3 métodos auxiliares** y se actualizaron **2 métodos existentes** en [app/services/network_service.py](../app/services/network_service.py) para preservar la configuración DNS durante los cambios de red.

### Nuevos Métodos

#### 1. `_get_current_dns()` (Línea ~692)
```python
async def _get_current_dns(self) -> List[str]:
    """Get current DNS servers from resolv.conf"""
```
- Lee `/etc/resolv.conf` y extrae los servidores DNS actuales
- Retorna una lista de direcciones IP de DNS
- Usado antes de cualquier cambio de ruta para preservar la configuración

#### 2. `_restore_dns()` (Línea ~707)
```python
async def _restore_dns(self, dns_servers: List[str]) -> bool:
    """Restore DNS servers if they were lost"""
```
- Verifica si la configuración DNS se perdió durante los cambios de ruta
- Si se perdió, la restaura escribiendo un archivo temporal y copiándolo con sudo
- Registra advertencias en logs cuando detecta pérdida de DNS
- Retorna `True` si el DNS está OK o fue restaurado exitosamente

#### 3. `_set_interface_metric_manual()` (Línea ~751)
```python
async def _set_interface_metric_manual(self, interface: str, metric: int) -> Dict:
    """Set metric using NetworkManager (preserves DNS)"""
```
- Cambia métricas usando NetworkManager en lugar de comandos `ip route` manuales
- NetworkManager maneja automáticamente la preservación de DNS
- Usado preferentemente cuando no hay VPN activa
- Reactiva la conexión para aplicar cambios

### Métodos Actualizados

#### 1. `_set_interface_metric_smooth()` (Línea ~784)

**Mejoras implementadas:**

1. **Preservación de DNS** (Paso 1):
   - Captura la configuración DNS actual antes de cualquier cambio
   - `current_dns = await self._get_current_dns()`

2. **Uso de NetworkManager cuando es seguro** (Paso 2):
   - Si no hay VPN activa, intenta usar NetworkManager primero
   - NetworkManager es más seguro y preserva DNS automáticamente
   - Fallback a método manual si NetworkManager falla

3. **Cambios atómicos de rutas** (Paso 3):
   - Usa `ip route change` en lugar de `del` + `add`
   - Evita la ventana temporal sin ruta donde se pierde DNS
   - Con VPN activa: agrega nueva ruta antes de eliminar la antigua
   - Sin VPN: cambio atómico o fallback controlado

4. **Restauración de DNS** (Paso 4):
   - Después de cambios de ruta: `await self._restore_dns(current_dns)`
   - Verifica si DNS se perdió y lo restaura automáticamente

5. **Manejo de errores robusto**:
   - Try/except con restauración de DNS incluso en caso de error
   - Logs detallados de cada operación

#### 2. `_set_modem_metric_smooth()` (Línea ~1003)

**Mejoras implementadas:**

Las mismas 5 mejoras que `_set_interface_metric_smooth()`, pero aplicadas específicamente para el módem USB 4G:

1. Preservación de DNS antes de cambios
2. Uso de `ip route change` para actualizaciones atómicas
3. Con VPN: transición suave (add → wait → delete old)
4. Sin VPN: cambio atómico con fallback
5. Restauración automática de DNS si se pierde

## Cómo Funciona

### Flujo de Ejecución

```
1. Usuario cambia prioridad de red → API /api/network/priority
2. Backend: _set_interface_metric_smooth() o _set_modem_metric_smooth()
3. Capturar DNS actual → _get_current_dns()
4. Intentar cambio vía NetworkManager (si es seguro)
5. Si falla, usar comandos ip route con 'change' (atómico)
6. Si 'change' falla, usar add → wait → delete (transición suave)
7. Restaurar DNS si se perdió → _restore_dns()
8. Persistir cambios en NetworkManager
9. Retornar éxito/error
```

### Estrategias de Cambio de Ruta

#### Sin VPN Activa
```bash
# Método 1: NetworkManager (preferido)
nmcli connection modify <conn> ipv4.route-metric <metric>
nmcli connection down <conn> && nmcli connection up <conn>

# Método 2: Cambio atómico
ip route change default via <gw> dev <iface> metric <metric>

# Método 3: Fallback
ip route del default via <gw> dev <iface>
ip route add default via <gw> dev <iface> metric <metric>
```

#### Con VPN Activa
```bash
# Método 1: Cambio atómico (preferido)
ip route change default via <gw> dev <iface> metric <metric>

# Método 2: Transición suave (fallback)
ip route add default via <gw> dev <iface> metric <new_metric>  # Nueva ruta
sleep 2  # Esperar migración de conexiones
ip route del default via <gw> dev <iface> metric <old_metric>  # Eliminar antigua
```

## Pruebas

### 1. Hacer Backup (Recomendado)
```bash
sudo cp app/services/network_service.py app/services/network_service.py.backup
```

### 2. Reiniciar el Servicio
```bash
sudo systemctl restart fpvcopilot-sky
```

### 3. Monitorear Logs
```bash
sudo journalctl -u fpvcopilot-sky -f
```

Buscar mensajes como:
- `Current DNS servers: ['8.8.8.8', '1.1.1.1']`
- `Metric for wlan0 set to 100 (VPN-aware: True, DNS preserved)`
- `DNS was lost, restoring: ['8.8.8.8']` (solo si hubo pérdida)
- `DNS configuration restored successfully`

### 4. Probar Cambio de Prioridad

**Desde el Frontend:**
1. Ir a la vista Network
2. Cambiar la prioridad de red (Primary ↔ Secondary)
3. Verificar que SSH/VSCode/Copilot siguen funcionando
4. Comprobar logs para mensajes de DNS

**Desde la API:**
```bash
# Cambiar a modo primary
curl -X POST http://localhost:8000/api/network/priority \
  -H "Content-Type: application/json" \
  -d '{"mode": "primary"}'

# Verificar DNS
cat /etc/resolv.conf

# Cambiar a modo secondary
curl -X POST http://localhost:8000/api/network/priority \
  -H "Content-Type: application/json" \
  -d '{"mode": "secondary"}'

# Verificar DNS nuevamente
cat /etc/resolv.conf
```

### 5. Probar con VPN Activa

```bash
# Iniciar VPN
sudo systemctl start tailscale

# Cambiar prioridad mientras VPN está activa
curl -X POST http://localhost:8000/api/network/priority \
  -H "Content-Type: application/json" \
  -d '{"mode": "vpn"}'

# Verificar conectividad SSH/VSCode
# Verificar logs para "VPN active: Changing route metric"
```

## Rollback (Si es Necesario)

Si hay algún problema, restaurar el backup:
```bash
sudo cp app/services/network_service.py.backup app/services/network_service.py
sudo systemctl restart fpvcopilot-sky
```

## Beneficios

✅ **DNS Preservado**: SSH/VSCode/Copilot mantienen conectividad durante cambios de red
✅ **VPN Segura**: Transiciones suaves para túneles VPN sin pérdida de conexión
✅ **NetworkManager**: Usa la herramienta correcta para gestión de red
✅ **Cambios Atómicos**: `ip route change` evita ventanas temporales sin ruta
✅ **Auto-Recuperación**: Restaura DNS automáticamente si se pierde
✅ **Logs Detallados**: Seguimiento completo de operaciones para debugging
✅ **Manejo de Errores**: Recuperación robusta incluso en caso de fallos

## Notas Técnicas

- Los métodos preservan la lista completa de servidores DNS (puede haber múltiples)
- Se usa archivo temporal para escritura segura de `/etc/resolv.conf`
- NetworkManager tiene prioridad cuando es seguro (mejor integración del sistema)
- Con VPN, se usa `ROUTE_TRANSITION_DELAY` (2s) para permitir migración de conexiones
- Los cambios se persisten en NetworkManager para sobrevivir reinicios
- Todos los métodos tienen try/except con restauración DNS en caso de error

## Referencias

- [NETWORK_MANAGEMENT.md](NETWORK_MANAGEMENT.md) - Gestión general de red
- [NETWORK_IMPROVEMENTS.md](NETWORK_IMPROVEMENTS.md) - Mejoras de red
- [VPN_INTEGRATION.md](VPN_INTEGRATION.md) - Integración VPN
- NetworkManager docs: https://networkmanager.dev/
- Linux routing: `man ip-route`
