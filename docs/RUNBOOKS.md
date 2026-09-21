<!-- Documentation file for FPV Copilot Sky Operational Runbooks -->

# 🚨 Runbooks Operativos - Incidencias Críticas

Procedimientos paso a paso para diagnosticar y recuperarse de incidentes críticos en FPV Copilot Sky. Diseñados para minimizar MTTR (Mean Time To Recovery) en vuelos operacionales.

---

## 📋 Índice de Runbooks

1. [MAVLink Desconectado](#1-mavlink-desconectado)
2. [Modem Inestable](#2-modem-inestable)
3. [Stream de Video Caído](#3-stream-de-video-caído)

---

## 1. MAVLink Desconectado

**Severidad:** 🔴 Crítica — Pérdida de telemetría y control del vehículo.

**Síntomas:**

- Indicador MAVLink en rojo en la WebUI
- Sin datos de altitud, velocidad, batería en la pestaña Telemetría
- Hearbeat timeout en los logs: `MAVLinkBridge: No heartbeat received for X seconds`
- Vehicle no responde a comandos de control

### 1.1 Detección rápida (30 segundos)

```bash
# Verificar estado de MAVLink Bridge
curl http://IP_PLACA:8000/api/mavlink/status

# Salida esperada: {"connected": true, "armed": false, "mode": "STABILIZE"}
# Indicador de error: {"connected": false, "error": "Connection timeout"}
```

### 1.2 Diagnóstico (1-2 minutos)

**Paso 1: Verificar conexión física**

```bash
# ¿Puerto serial existe?
ls -l /dev/ttyAML0 /dev/ttyUSB0 /dev/ttyACM0 2>/dev/null | head -3

# ¿Está en uso por otro proceso?
sudo fuser -v /dev/ttyAML0 2>/dev/null
# (Si hay output, alguien más está usando el puerto)
```

**Paso 2: Verificar servicio FPVCopilotSky**

```bash
# ¿Servicio corriendo?
sudo systemctl is-active fpvcopilot-sky
# Salida: active (OK) o inactive (ERROR)

# Ver logs de startup
sudo journalctl -u fpvcopilot-sky -n 50 --no-pager | grep -E "MAVLink|serial|error"
```

**Paso 3: Verificar configuración de puerto serial**

```bash
# ¿Cuál es el puerto configurado?
sqlite3 ~/.fpvcopilot/preferences.db "SELECT * FROM preferences WHERE key='serial_port';"

# ¿Existe realmente?
ls -l /dev/ttyAML0  # Si no existe, búscalo con: dmesg | tail -20
```

**Paso 4: Verificar comunicación en bruto**

```bash
# Leer datos directamente del puerto (baudrate típico: 57600)
# Ctr+C para salir
timeout 5 cat /dev/ttyAML0 | od -c | head -20
# Salida esperada: caracteres binarios MAVLink ($, contenido)
# Si sale vacío: el device no está enviando datos
```

**Paso 5: Revisar estado del receptor (Flight Controller)**

```bash
# Si usas un controlador remoto (no integrado en el SBC):
# a) ¿Cable USB conectado? (si es USB)
# b) ¿Está en modo bootloader? (luz parpadeando rápido vs normal)
# c) ¿Batería cargada? (algunos FC dan error silencioso con batería baja)
```

### 1.3 Recuperación (decision tree)

**Si el puerto no existe o no responde:**

```bash
# Opción A: Reiniciar servicio
sudo systemctl restart fpvcopilot-sky
sleep 2
curl http://IP_PLACA:8000/api/mavlink/status

# Si sigue sin funcionar → Opción B
```

**Opción B: Fuerza re-escaneo de puertos seriales**

```bash
# Ejecutar detector de puerto serial
python3 -c "from app.services.serial_detector import get_detector; print(get_detector().detect_available_ports())"

# Actualizar preferences con el puerto correcto
sqlite3 ~/.fpvcopilot/preferences.db \
  "UPDATE preferences SET value='/dev/ttyUSB0' WHERE key='serial_port';"

# Reiniciar servicio
sudo systemctl restart fpvcopilot-sky
sleep 3
curl http://IP_PLACA:8000/api/mavlink/status
```

**Opción C: Reinicio completo del sistema (último recurso)**

```bash
# Si nada funciona, el hardware puede estar en estado inconsistente
sudo systemctl stop fpvcopilot-sky
sudo reboot
# Esperar a que el sistema arranque (2-3 min)
# Verificar: curl http://IP_PLACA:8000/api/mavlink/status
```

### 1.4 Validación de recuperación

```bash
# Verificar que MAVLink esté conectado
curl http://IP_PLACA:8000/api/mavlink/status | grep -q "\"connected\": true" && echo "✅ MAVLink OK" || echo "❌ MAVLink FAIL"

# Ver heartbeat rate en logs (debe ser ~1 Hz)
sudo journalctl -u fpvcopilot-sky -f --grep="heartbeat" | head -3

# (Ctr+C para salir)
```

### 1.5 Rollback (si necesitas volver a estado anterior)

MAVLink es un servicio de entrada; no modifica configuración persistente. Una vez reparada la conexión física, no hay rollback necesario.

---

## 2. Modem Inestable

**Severidad:** 🟠 Alta — Degradación de latencia/ancho de banda, posibles drops de video.

**Síntomas:**

- Latencia en la pestaña Network sube a >150 ms
- Jitter picos >50 ms
- SINR oscilante (baja a < -5 dB)
- Modem aparece con badge naranja `NO SALUDABLE` en el pool
- Video pixelado o congelado intermitentemente

### 2.1 Detección rápida (15 segundos)

```bash
# Ver métricas en tiempo real
curl http://IP_PLACA:8000/api/network/modems

# Ejemplo de salida con modem inestable:
# {
#   "modems": [{
#     "interface": "enx001122334455",
#     "operator": "Movistar",
#     "sinr_db": -8,        ← SINR bajo
#     "latency_ms": 180,    ← Latencia alta
#     "jitter_ms": 65,      ← Jitter alto
#     "health": "unhealthy" ← Flag rojo
#   }]
# }
```

### 2.2 Diagnóstico (2-5 minutos)

**Paso 1: Verificar si es problema de señal celular**

```bash
# Ver historial de SINR en los últimos 5 minutos
sudo journalctl -u fpvcopilot-sky --since "5 min ago" | grep -i sinr | tail -10

# Si SINR está consistentemente < -10 dB → Problema de cobertura (no es software)
```

**Paso 2: Revisar si hay interferencia RF o carga de red**

```bash
# ¿Otros dispositivos usando el mismo modem USB?
lsusb | grep -i "huawei\|sierra\|option"

# ¿Puerto USB en hub con muchos dispositivos?
# (Desconectar otros dispositivos puede ayudar)

# ¿Ancho de banda saturado?
# Comprobar en el router local: ¿cuántos MB/s está usando FPVCopilot?
# (Si > 20 MB/s en upload constante, revisar video bitrate)
```

**Paso 3: Revisar health checks del modem**

```bash
# Ver último health check
curl http://IP_PLACA:8000/api/network/modems/health

# Salida: {"modem": "enx001122334455", "last_check": "2026-06-15T10:30:45Z", "failures": 1}
# Si failures >= 3 → Modem está a punto de ser removido del pool
```

**Paso 4: Monitorear cambios de modos automáticos**

```bash
# ¿El sistema está switcheando entre modems?
sudo journalctl -u fpvcopilot-sky -f --grep="Switching\|failover" | head -10

# (Ctr+C para salir)
# Si hay switches frecuentes (> 1 por minuto) → Anti-flapping issue
```

### 2.3 Recuperación (escalada)

**Paso 1: Intervención manual - Cambiar a mejor modem (si hay más de uno)**

```bash
# Ver pool de modems disponibles
curl http://IP_PLACA:8000/api/network/modems

# Cambiar manualmente al modem con mejor score
curl -X POST http://IP_PLACA:8000/api/network/modems/switch \
  -H "Content-Type: application/json" \
  -d '{"interface": "enx002233445566", "mode": "manual"}'

# Verificar cambio en 5 segundos
curl http://IP_PLACA:8000/api/network/modems
```

**Paso 2: Reducir bitrate de video (aliviar congestión)**

```bash
# Si solo hay un modem, reducir carga:
curl -X POST http://IP_PLACA:8000/api/video/config/video \
  -H "Content-Type: application/json" \
  -d '{"h264_bitrate": 1500}'

# O activar auto-adaptive bitrate si no está activo
curl -X POST http://IP_PLACA:8000/api/video/config/auto-adaptive-bitrate \
  -d '{"enabled": true}'
```

**Paso 3: Reiniciar interfaz del modem (soft reset)**

```bash
# Desactivar y reactivar la interfaz
sudo ip link set enx001122334455 down
sleep 2
sudo ip link set enx001122334455 up
sleep 5

# Monitorear recuperación
curl http://IP_PLACA:8000/api/network/modems | jq '.modems[0] | {sinr_db, latency_ms, jitter_ms}'
```

**Paso 4: Reset del modem (hard reset, si lo permite)**

```bash
# Algunos modems soportan AT commands para reset:
# (requiere acceso directo al puerto de AT del modem, cuidado)
#
# Alternativa más segura: reiniciar servicio fpvcopilot-sky
sudo systemctl restart fpvcopilot-sky
sleep 3

# Monitorear SINR en logs
sudo journalctl -u fpvcopilot-sky -f --grep="SINR" | head -5
```

### 2.4 Validación de recuperación

```bash
# Latencia debe estar < 120 ms
curl http://IP_PLACA:8000/api/network/modems | jq '.modems[0].latency_ms'

# Jitter debe estar < 30 ms
curl http://IP_PLACA:8000/api/network/modems | jq '.modems[0].jitter_ms'

# Health debe cambiar a "healthy"
curl http://IP_PLACA:8000/api/network/modems | jq '.modems[0].health'

# Todas las condiciones OK → Modem recuperado
```

### 2.5 Rollback (revertir a configuración previa)

**Si redujiste el bitrate y quieres restaurarlo:**

```bash
# Ver bitrate actual
curl http://IP_PLACA:8000/api/video/status | jq '.config.h264_bitrate'

# Restaurar a bitrate normal (ej. 2500 kbps)
curl -X POST http://IP_PLACA:8000/api/video/config/video \
  -H "Content-Type: application/json" \
  -d '{"h264_bitrate": 2500}'

# Verificar cambio
curl http://IP_PLACA:8000/api/video/status | jq '.config.h264_bitrate'
```

**Si activaste auto-adaptive bitrate y quieres desactivarlo:**

```bash
curl -X POST http://IP_PLACA:8000/api/video/config/auto-adaptive-bitrate \
  -d '{"enabled": false}'
```

---

## 3. Stream de Video Caído

**Severidad:** 🟠 Alta — Pérdida de video en tiempo real.

**Síntomas:**

- Indicador Stream en rojo en la WebUI
- Pantalla de video negra o "sin señal"
- Logs: `GStreamerService: Pipeline EOS (End Of Stream)` o `Connection refused on UDP 5600`
- Mission Planner/QGC no recibe video

### 3.1 Detección rápida (10 segundos)

```bash
# Verificar estado del stream
curl http://IP_PLACA:8000/api/video/status

# Esperado: {"streaming": true, ...}
# Error: {"streaming": false, "error": "Pipeline error"}
```

### 3.2 Diagnóstico (2-3 minutos)

**Paso 1: Verificar que la cámara está conectada**

```bash
# Listar cámaras disponibles
v4l2-ctl --list-devices

# Salida esperada: /dev/video0, /dev/video1, etc.
# Si nada aparece → Cámara desconectada o sin driver

# Alternativamente, via API:
curl http://IP_PLACA:8000/api/video/cameras | jq '.cameras'
```

**Paso 2: Verificar que GStreamer está corriendo**

```bash
# ¿Proceso gstreamer activo?
ps aux | grep gstreamer | grep -v grep

# Si no hay output → GStreamer crasheó
```

**Paso 3: Verificar puerto UDP de salida**

```bash
# ¿Puerto 5600 escuchando? (o el puerto configurado)
sudo lsof -i :5600 | grep gstreamer

# Si no hay output → El pipeline no está escuchando
# Verificar puerto configurado:
curl http://IP_PLACA:8000/api/video/status | jq '.streaming_config.udp_port'
```

**Paso 4: Revisar logs de GStreamer**

```bash
# Errores recientes en el servicio
sudo journalctl -u fpvcopilot-sky -n 100 --no-pager | grep -i "gstream\|pipeline\|video"

# Buscar errores específicos:
sudo journalctl -u fpvcopilot-sky -n 100 --no-pager | grep -E "error|failed|crash" | tail -5
```

**Paso 5: Verificar conectividad de red (para flujo UDP)**

```bash
# ¿Interfaz de red UP y con IP?
ip addr show | grep -E "^[0-9]+:|inet " | head -10

# ¿Ruta por defecto existe?
ip route show | grep default

# ¿Puedes ping a ti mismo? (loopback)
ping -c 1 127.0.0.1

# ¿Puedes ping a la interfaz de red?
ping -c 1 $(hostname -I | awk '{print $1}')
```

### 3.3 Recuperación (escalada)

**Opción A: Reiniciar el stream (simple)**

```bash
# Detener stream
curl -X POST http://IP_PLACA:8000/api/video/stop

# Esperar 2 segundos
sleep 2

# Reiniciar stream
curl -X POST http://IP_PLACA:8000/api/video/start

# Verificar
curl http://IP_PLACA:8000/api/video/status | jq '.streaming'
```

**Opción B: Reiniciar servicio de video completo**

```bash
# Si Opción A no funciona, reiniciar el servicio GStreamer backend
sudo systemctl restart fpvcopilot-sky

# Esperar startup (3-5 segundos)
sleep 5

# Iniciar stream
curl -X POST http://IP_PLACA:8000/api/video/start

# Monitorear:
curl http://IP_PLACA:8000/api/video/status
```

**Opción C: Cambiar cámara (si hay múltiples)**

```bash
# Ver cámaras disponibles
curl http://IP_PLACA:8000/api/video/cameras | jq '.cameras[].device'

# Cambiar a cámara alternativa
curl -X POST http://IP_PLACA:8000/api/video/config/video \
  -H "Content-Type: application/json" \
  -d '{"device": "/dev/video1"}'

# Reiniciar stream
curl -X POST http://IP_PLACA:8000/api/video/stop && sleep 2 && curl -X POST http://IP_PLACA:8000/api/video/start

# Verificar
curl http://IP_PLACA:8000/api/video/status | jq '.streaming'
```

**Opción D: Reducir resolución o framerate (si problema es de recursos)**

```bash
# Ver configuración actual
curl http://IP_PLACA:8000/api/video/status | jq '.config | {width, height, framerate}'

# Reducir a 720p 24fps (si está en 1080p 30fps)
curl -X POST http://IP_PLACA:8000/api/video/config/video \
  -H "Content-Type: application/json" \
  -d '{"width": 1280, "height": 720, "framerate": 24}'

# Reiniciar stream
curl -X POST http://IP_PLACA:8000/api/video/stop && sleep 2 && curl -X POST http://IP_PLACA:8000/api/video/start
```

**Opción E: Verificar que la cámara no está colgada**

```bash
# Intentar capturar un frame directo con ffmpeg
timeout 3 ffmpeg -f v4l2 -i /dev/video0 -vframes 1 -pix_fmt yuvj420p /tmp/test.jpg 2>&1 | head -10

# Si sale error "Operation timed out" → Cámara colgada, requiere reboot
```

### 3.4 Validación de recuperación

```bash
# Verificar stream activo
curl http://IP_PLACA:8000/api/video/status | jq '.streaming'
# Salida: true ✅

# Verificar FPS
curl http://IP_PLACA:8000/api/video/stats | jq '.pipeline.current_fps'
# Debe estar cerca del target fps (30, 24, etc.)

# Verificar bitrate
curl http://IP_PLACA:8000/api/video/stats | jq '.pipeline.current_bitrate_kbps'
# Debe ser > 500 kbps

# Conectar cliente y verificar
# En Mission Planner / QGC → Add Camera Feed → UDP 192.168.X.X:5600
```

### 3.5 Rollback (restaurar configuración de video previa)

```bash
# Ver configuración actual
curl http://IP_PLACA:8000/api/video/status | jq '.config'

# Si modificaste resolución, volver a 1920x1080
curl -X POST http://IP_PLACA:8000/api/video/config/video \
  -H "Content-Type: application/json" \
  -d '{"width": 1920, "height": 1080, "framerate": 30}'

# Reiniciar stream
curl -X POST http://IP_PLACA:8000/api/video/stop && sleep 2 && curl -X POST http://IP_PLACA:8000/api/video/start

# Verificar
curl http://IP_PLACA:8000/api/video/stats | jq '.pipeline | {current_fps, current_bitrate_kbps}'
```

---

## 🔧 Herramientas de diagnóstico rápido

Guarda este script para diagnóstico de emergencia:

```bash
#!/bin/bash
# fpv-emergency-diagnostics.sh

echo "=== FPV Copilot Sky - Emergency Diagnostics ==="
echo ""

echo "1. Service Status"
sudo systemctl is-active fpvcopilot-sky

echo -e "\n2. MAVLink Status"
curl -s http://localhost:8000/api/mavlink/status | jq '.connected'

echo -e "\n3. Network Modems"
curl -s http://localhost:8000/api/network/modems | jq '.modems[] | {interface, sinr_db, latency_ms, health}'

echo -e "\n4. Video Stream Status"
curl -s http://localhost:8000/api/video/status | jq '.streaming'

echo -e "\n5. Video Stats (FPS, Bitrate)"
curl -s http://localhost:8000/api/video/stats | jq '.pipeline | {current_fps, current_bitrate_kbps}'

echo -e "\n6. Recent Errors (last 10)"
sudo journalctl -u fpvcopilot-sky -n 50 --no-pager | grep -i error | head -10

echo -e "\n=== End Diagnostics ==="
```

Usar:

```bash
chmod +x fpv-emergency-diagnostics.sh
./fpv-emergency-diagnostics.sh
```

---

## 📊 Métricas de salud esperadas

| Métrica                  | Verde (OK) | Naranja (Warning) | Rojo (Crítico) |
| ------------------------ | ---------- | ----------------- | -------------- |
| **MAVLink Conectado**    | true       | N/A               | false          |
| **SINR Modem (dB)**      | > -5       | -5 a -10          | < -10          |
| **Latencia Modem (ms)**  | < 100      | 100-150           | > 150          |
| **Jitter Modem (ms)**    | < 20       | 20-50             | > 50           |
| **Stream Video**         | true       | N/A               | false          |
| **FPS Video**            | ≥ target   | 80-99% target     | < 80% target   |
| **Bitrate Video (kbps)** | > 500      | 300-500           | < 300          |
| **CPU Idle (%)**         | > 30       | 10-30             | < 10           |

---

## 🚀 Mejora de MTTR (Mean Time To Recovery)

**Acciones preventivas:**

1. **Monitoreo proactivo** — Configura alertas en logs antes de que lleguen a crítico

   ```bash
   # Ejecutar cada 5 minutos en cron
   */5 * * * * curl -s http://localhost:8000/api/network/modems | jq '.modems[0] | select(.latency_ms > 150)' && mail -s "Modem Latency High" ops@example.com
   ```

2. **Redundancia** — Tener 2+ modems/cámaras disponibles

3. **Auto-failover** — Activar en modo operacional

   ```bash
   curl -X POST http://localhost:8000/api/network/failover/start?initial_mode=best_score
   ```

4. **Drills simulados** — Probar recuperación 1x/mes (desconectar USB, etc.)

---

[← Índice Completo](INDEX.md) · [Guía de Usuario](USER_GUIDE.md) · [Guía de Desarrollo](DEVELOPER_GUIDE.md)
