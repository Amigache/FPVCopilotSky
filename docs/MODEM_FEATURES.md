# 📶 Funcionalidades Avanzadas del Módem

Guía completa de las funcionalidades avanzadas del módem 4G integradas en FPV Copilot Sky.

## 🎯 Características Principales

FPV Copilot Sky incluye un sistema completo de gestión de módem 4G con funcionalidades avanzadas para optimizar el streaming de video y telemetría en vuelo.

### 📊 Monitorización en Tiempo Real

El sistema proporciona métricas detalladas del módem:

- **Información del Operador**: Nombre, MCC-MNC, tipo de red (4G/LTE)
- **Señal LTE**: RSSI, RSRP, RSRQ, SINR, Cell ID, PCI
- **Tráfico de Datos**: Subida/bajada actual y total
- **Estado de Conexión**: Roaming, DNS, icono de señal

### 🎥 Modo Video Optimizado

El **Modo Video** configura automáticamente el módem para streaming:

```
Optimizaciones aplicadas:
✓ 4G Only (desactiva 3G/2G)
✓ Banda prioritaria para video
✓ TTL optimizado para evitar throttling
✓ QoS mejorado para UDP
```

#### Cómo Activar Modo Video:

1. Ve a la pestaña **Módem**
2. Verás un banner en la parte superior
3. Haz clic en **"Activar Modo Video"**
4. El módem cambiará automáticamente a la configuración óptima

**⚠️ Nota:** El modo video fuerza 4G Only. Si estás en área sin 4G, perderás conexión.

### 📡 Gestión de Bandas LTE

El sistema incluye presets de bandas LTE configurables:

- **Todas**: Permite todas las bandas disponibles
- **B3+B7**: Bandas principales en España (Movistar, Vodafone, Orange)
- **B20**: Banda de baja frecuencia (mejor cobertura, menor velocidad)
- **Presets personalizados**: Configurables según operador

#### Cambiar Banda LTE:

1. En la pestaña **Módem** → sección **Configuración**
2. Ver la sección **Banda LTE**
3. Selecciona un preset
4. Espera 5-10 segundos hasta que el módem reconecte

### 📈 Evaluación de Calidad Video

El sistema evalúa automáticamente la calidad de la conexión para streaming:

| Nivel | SINR (dB) | RSRP (dBm) | Bitrate Max | Resolución Recomendada |
|-------|-----------|------------|-------------|------------------------|
| **Excelente** | >13 | >-85 | 5000 kbps | 1080p @ 30fps |
| **Buena** | 7-13 | -95 a -85 | 2500 kbps | 720p @ 30fps |
| **Moderada** | 0-7 | -105 a -95 | 1500 kbps | 480p @ 30fps |
| **Pobre** | -3 a 0 | -115 a -105 | 800 kbps | 480p @ 15fps |
| **Crítica** | <-3 | <-115 | 400 kbps | MJPEG bajo |

La evaluación se muestra en tiempo real en la sección **Métricas de Rendimiento**.

### ⏱️ Test de Latencia

Prueba la latencia de la conexión 4G con ping a `8.8.8.8`:

- **Excelente**: < 50ms
- **Buena**: 50-80ms
- **Moderada**: 80-120ms
- **Pobre**: 120-200ms
- **Crítica**: > 200ms

#### Ejecutar Test de Latencia:

1. En **Módem** → **Métricas de Rendimiento**
2. Sección **Latencia** → botón 🔄
3. Espera 3-5 segundos
4. Se mostrarán: ping promedio, mínimo, máximo y jitter

### 📶 Modos de Red

Cambia el modo de red del módem:

- **Auto (00)**: 4G/3G/2G automático
- **4G Only (03)**: Solo 4G LTE (recomendado para video)
- **3G Only (02)**: Solo 3G (backup si no hay 4G)

**Recomendación:** Usa "4G Only" cuando tengas buena cobertura 4G para evitar cambios de red durante el vuelo.

### ✈️ Sesión de Vuelo

Registra estadísticas de red durante el vuelo para análisis posterior:

#### Iniciar Sesión:

1. **Antes del vuelo**, ve a **Módem** → **Configuración**
2. Sección **Sesión de Vuelo** → **Iniciar**
3. El sistema comienza a muestrear cada 5 segundos:
   - SINR (calidad de señal)
   - RSRP (potencia de señal)
   - Latencia
   - Bandas activas
   - Cambios de banda

#### Detener Sesión:

1. **Después del vuelo**, haz clic en **Detener**
2. Aparecerá un resumen con:
   - Duración total
   - Número de muestras
   - Rangos de SINR y RSRP
   - Latencia promedio
   - Número de cambios de banda

Esta información es útil para:
- Identificar zonas con mala cobertura
- Optimizar configuración de bandas
- Diagnosticar problemas de conexión
- Comparar operadores

### 🔄 Reconexión y Reinicio

#### Reconexión Rápida:

Botón 🔁 en la sección **Banda LTE** para reconectar sin reiniciar el módem.

#### Reinicio Completo:

1. En **Módem** → **Reinicio**
2. Haz clic en **Reiniciar Módem**
3. Confirma la acción
4. El sistema espera 30-60 segundos hasta que el módem vuelva
5. Te notifica cuando está online

**Cuándo reiniciar:**
- Módem no responde
- Cambios de configuración no aplicados
- Velocidades anormalmente bajas
- Después de cambiar SIM

## 🔧 API Endpoints

### Obtener Estado Completo

```bash
GET /api/network/hilink/status/enhanced
```

Devuelve todo: dispositivo, operador, señal, tráfico, modo video, calidad video, latencia.

### Activar Modo Video

```bash
POST /api/network/hilink/video-mode/enable
```

Configura el módem para streaming óptimo.

### Desactivar Modo Video

```bash
POST /api/network/hilink/video-mode/disable
```

Vuelve a configuración estándar.

### Cambiar Banda LTE

```bash
POST /api/network/hilink/band
{
  "preset": "b3b7"
}
```

### Cambiar Modo de Red

```bash
POST /api/network/hilink/mode
{
  "mode": "03"  // 00=Auto, 03=4G Only, 02=3G Only
}
```

### Test de Latencia

```bash
GET /api/network/hilink/latency
```

### Iniciar Sesión de Vuelo

```bash
POST /api/network/hilink/flight-session/start
```

### Muestra en Sesión de Vuelo

```bash
POST /api/network/hilink/flight-session/sample
```

### Detener Sesión de Vuelo

```bash
POST /api/network/hilink/flight-session/stop
```

Devuelve el resumen completo de la sesión.

### Reconectar Red

```bash
POST /api/network/hilink/reconnect
```

### Reiniciar Módem

```bash
POST /api/network/hilink/reboot
```

## 📖 Configuración de Presets de Banda

Los presets de banda se definen en el backend (`hilink_service.py`):

```python
BAND_PRESETS = {
    "all": {
        "name": "Todas",
        "bands": [],  # Vacío = todas
        "description": "Permite todas las bandas LTE"
    },
    "b3b7": {
        "name": "B3+B7",
        "bands": [3, 7],
        "description": "Bandas principales España"
    },
    "b20": {
        "name": "B20",
        "bands": [20],
        "description": "Cobertura rural"
    }
}
```

Puedes agregar presets personalizados según tu operador y región.

## 🚀 Mejores Prácticas

### Para Streaming de Video:

1. ✅ Activa **Modo Video** antes del vuelo
2. ✅ Usa **4G Only** si tienes buena cobertura
3. ✅ Configura bandas específicas (B3+B7 en España)
4. ✅ Verifica **Calidad Video** antes de armar
5. ✅ Haz un **Test de Latencia** pre-vuelo

### Para Telemetría:

1. ✅ Configura MavLink con tasas bajas (2-4 Hz)
2. ✅ Usa UDP en lugar de TCP cuando sea posible
3. ✅ Prioriza mensajes críticos (actitud, GPS, batería)

### Para Diagnóstico:

1. ✅ Usa **Sesión de Vuelo** para registrar datos
2. ✅ Compara diferentes configuraciones de banda
3. ✅ Anota SINR/RSRP mínimos durante el vuelo
4. ✅ Identifica zonas con cambios de banda frecuentes

## ⚠️ Limitaciones Conocidas

- **HiLink Compatible Solo**: Funciona con modems Huawei HiLink (E3372, E8372, etc.)
- **Requiere API HiLink**: El módem debe exponer API HTTP (192.168.8.1)
- **Algunos comando requieren root**: Modo video necesita permisos elevados
- **Reinicio puede tardar**: El módem puede tardar hasta 60 segundos en volver

## 🆘 Solución de Problemas

### Módem no detectado:

```bash
# Verificar si el módem está visible
lsusb | grep Huawei

# Verificar interfaz de red
ip link show

# Ping al módem
ping 192.168.8.1
```

### Modo Video no funciona:

- Verifica que el usuario tenga permisos sudo
- Algunos modems no soportan TTL modificado
- Verifica logs: `sudo journalctl -u fpvcopilot-sky -f`

### Cambio de banda no aplica:

- Espera 10-15 segundos
- El módem debe reconectar completamente
- Si no funciona, usa **Reiniciar Módem**

---

**¿Necesitas más ayuda?** Consulta la documentación principal o abre un issue en GitHub.
