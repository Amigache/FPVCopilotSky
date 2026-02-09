# 📖 Guía de Usuario

Guía completa para usar FPV Copilot Sky desde la interfaz web. Cubre cada pestaña, flujos de configuración típicos y solución de problemas.

---

## 1. Acceso a la WebUI

Abre en un navegador:

```
http://<IP-DE-TU-SBC>
```

La interfaz funciona en cualquier dispositivo (PC, tablet, móvil). No requiere instalar ninguna app.

### Barra superior (Header)

La barra superior muestra el estado global en tiempo real:

| Badge                                          | Significado                                |
| ---------------------------------------------- | ------------------------------------------ |
| 🟢 **Stream Online**                           | Video streaming activo                     |
| 🟢 **FC Conectado**                            | Controlador de vuelo conectado por MAVLink |
| 🟡 **Desarmado** / 🟠 **Armado**               | Estado de armado del drone                 |
| 🟢 **VPN Conectado** / 🔴 **VPN Desconectado** | Estado de la VPN Tailscale                 |

Todos los badges se actualizan en tiempo real vía WebSocket.

---

## 2. Pestaña: Controlador de Vuelo

Gestiona la conexión MAVLink con el controlador de vuelo.

### Conexión automática

El sistema auto-detecta el puerto serie del FC al arrancar. Si no lo detecta:

1. Selecciona el **puerto** (`/dev/ttyAML0`, `/dev/ttyUSB0`…)
2. Selecciona el **baudrate** (115200 es el más común)
3. Pulsa **Conectar**

### Telemetría en tiempo real

Cuando conecta verás:

- **GPS**: coordenadas, satélites, fix type
- **Actitud**: roll, pitch, yaw
- **Altitud**: relativa y absoluta
- **Velocidad**: aérea y terrestre
- **Batería**: voltaje, corriente, porcentaje
- **Estado**: modo de vuelo, armado, mensajes del sistema

### Salidas MAVLink (Telemetry Routing)

Puedes crear múltiples salidas simultáneas para enviar telemetría a distintos GCS:

| Tipo       | Uso típico      | Ejemplo               |
| ---------- | --------------- | --------------------- |
| UDP        | QGroundControl  | `192.168.1.100:14550` |
| TCP Server | Mission Planner | Puerto 5760           |
| TCP Client | Servidor remoto | `servidor:5760`       |

**Selector de peers VPN**: Si tienes Tailscale conectado, el input de IP muestra un desplegable con los nodos de tu red VPN para seleccionar la IP rápidamente.

---

## 3. Pestaña: Video

Configura y controla el streaming de video HD con baja latencia.

### Estado del sistema

La barra de estado superior muestra en todo momento:

- **Estado**: Detenido / Emitiendo / Error
- **Destino actual**: IP:puerto, grupo multicast o URL RTSP según el modo elegido

### Fuente de vídeo

1. **Cámara**: selecciona entre las cámaras USB / CSI detectadas automáticamente
2. **Resolución**: las resoluciones disponibles se adaptan a cada cámara
3. **FPS**: framerate del stream (se adapta según las capacidades de la cámara)

### Codificación

- **Codec**: seleccionado automáticamente entre los disponibles en el sistema (H.264 hardware, H.264 software, MJPEG…)
- **Calidad MJPEG**: slider de calidad (1-100) — visible solo con codec MJPEG
- **Bitrate H.264**: selector de bitrate — visible solo con codecs H.264
- **GOP Size**: intervalo de keyframes — visible solo con codecs H.264

> 💡 **Ajuste en vivo**: calidad, bitrate, GOP size y framerate se pueden modificar **mientras se emite** sin reiniciar el stream (etiqueta `LIVE`).

### Modos de emisión (streaming)

| Modo            | Descripción                                        | Caso de uso                                |
| --------------- | -------------------------------------------------- | ------------------------------------------ |
| **UDP Unicast** | Envío directo a una IP:puerto                      | FPV punto a punto, mínima latencia         |
| **Multicast**   | Envío a un grupo multicast (224.x.x.x – 239.x.x.x) | Múltiples receptores en la misma red       |
| **RTSP**        | Servidor RTSP embebido                             | Clientes a demanda, compatible con VLC/OBS |

#### UDP Unicast

- **IP Destino**: dirección del receptor (usa el selector de peers VPN si tienes Tailscale)
- **Puerto UDP**: típicamente 5600

#### Multicast

- **Grupo multicast**: dirección IP en rango 224.0.0.0 – 239.255.255.255
- **Puerto**: puerto del grupo
- **TTL**: saltos de red permitidos (1 = solo red local)

#### RTSP

- **URL RTSP**: se genera automáticamente con la IP de la placa (ej. `rtsp://192.168.1.145:8554/stream`)
- **Transporte**: TCP (fiable) o UDP (menor latencia)

### Controles de stream

- **Aplicar + Iniciar**: guarda la configuración y arranca el pipeline GStreamer
- **Detener**: para el stream
- **Reiniciar**: aplica cambios y reinicia
- **Inicio automático**: toggle para que el stream se inicie automáticamente al arrancar el sistema

### Pipeline GStreamer

Cuando el stream está activo, se muestra la cadena GStreamer completa. Puedes copiar la pipeline al portapapeles para depuración.

### Estadísticas en vivo

Durante la emisión se muestran en tiempo real:

- Tiempo de emisión (uptime)
- FPS y bitrate actuales
- Codec en uso y resolución
- Errores acumulados
- Clientes RTSP conectados (solo en modo RTSP)

### Recibir video en tu GCS

#### Mission Planner

El sistema envía automáticamente el mensaje MAVLink `VIDEO_STREAM_INFORMATION` (ID 269). Mission Planner lo detecta y muestra el video automáticamente.

Si no lo detecta automáticamente:

1. Ve a **Ctrl+F** → **Video**
2. Introduce la URI: `rtp://TU_IP:5600`
3. Pulsa **Start**

#### QGroundControl

1. Ve a **Ajustes de la aplicación** → **Video**
2. Fuente: **UDP h.264**
3. Puerto: **5600**

#### VLC / ffplay

```bash
# UDP Unicast / Multicast
vlc rtp://@:5600
ffplay -fflags nobuffer -flags low_delay -probesize 32 -analyzeduration 0 rtp://@:5600

# RTSP
vlc rtsp://IP_DE_LA_PLACA:8554/stream
ffplay -fflags nobuffer -rtsp_transport tcp rtsp://IP_DE_LA_PLACA:8554/stream
```

---

## 4. Pestaña: Red

Gestiona las interfaces de red, WiFi, priorización de conexiones, y optimizaciones para streaming 4G.

### Interfaces

Vista de todas las interfaces de red activas (WiFi, Ethernet, modem 4G, VPN) con IP, estado y métricas de ruta.

### WiFi

- **Escanear redes**: busca SSIDs disponibles con indicador de señal
- **Conectar**: selecciona una red, introduce la contraseña y conecta (conexión real vía NetworkManager)
- **Desconectar**: desconecta de la red WiFi actual

### Priorización de red

El sistema gestiona automáticamente la prioridad de las interfaces:

| Prioridad  | Interfaz              | Métrica |
| ---------- | --------------------- | ------- |
| 1 (máxima) | VPN Tailscale         | 10      |
| 2          | Red principal (4G)    | 100     |
| 3          | Red secundaria (WiFi) | 200     |

**Modos de operación**:

- **Auto** (recomendado): el sistema decide la mejor interfaz
- **Modem forzado**: prioriza 4G siempre
- **WiFi forzado**: prioriza WiFi siempre

### Flight Mode (Modo Vuelo) 🛩️

**Flight Mode** es una optimización integral del sistema para maximizar la calidad del streaming por 4G. Combina configuraciones del modem con ajustes del sistema operativo.

**Activación**: Botón **Flight Mode** en el banner de la pestaña Red (aparece con fondo naranja cuando está activo).

**Optimizaciones aplicadas**:

| Componente | Ajuste                            | Beneficio                       |
| ---------- | --------------------------------- | ------------------------------- |
| Modem      | 4G Only Mode (evita caídas a 3G)  | Latencia estable                |
| Modem      | Bandas optimizadas (B3+B7 España) | Máxima velocidad en ciudad      |
| Red        | MTU 1420 (evita fragmentación)    | -15% latencia                   |
| Red        | QoS DSCP EF (46) en puertos video | Prioridad máxima para el stream |
| TCP        | TCP BBR congestion control        | Mejor throughput en pérdidas    |
| TCP        | Buffers 25MB (send/recv)          | Manejo de ráfagas               |
| Power      | Ethernet power saving OFF         | Latencia consistente            |

**Cuándo usar Flight Mode**:

- ✅ Vuelos FPV por 4G donde la latencia es crítica
- ✅ Streaming en áreas urbanas con bandas B3+B7 disponibles
- ✅ Cuando detectes micro-cortes o jitter en el video

**Cuándo NO usar Flight Mode**:

- ❌ En zonas rurales con solo banda B20 (desactiva B20)
- ❌ Si tu operadora no usa B3+B7
- ❌ Streaming por WiFi (las optimizaciones son específicas para 4G)

**Métricas**: El botón muestra métricas en tiempo real cuando está activo (buffer sizes, TCP algorithm, MTU actual).

### Latency Monitoring (avanzado)

Monitoreo continuo de latencia a múltiples destinos (Google DNS 8.8.8.8, Cloudflare 1.1.1.1, Quad9 9.9.9.9) para detectar degradación de red.

- **Inicio automático**: se activa con Auto-Failover
- **Métricas**: latencia promedio, mínima, máxima, packet loss
- **Histórico**: mantiene 30 muestras (1 minuto de datos)

**Acceso manual** (API):

```bash
# Iniciar monitoreo
curl -X POST http://IP_PLACA:8000/api/network/latency/start

# Ver estadísticas actuales
curl http://IP_PLACA:8000/api/network/latency/current

# Detener monitoreo
curl -X POST http://IP_PLACA:8000/api/network/latency/stop
```

### Auto-Failover (avanzado)

Sistema automático de cambio entre WiFi ↔ 4G basado en latencia para garantizar continuidad del stream.

**Funcionamiento**:

1. Monitorea latencia cada 2 segundos
2. Si latencia > 200ms durante 30 segundos consecutivos → switch automático a interfaz alternativa
3. Hysteresis de 30 segundos evita cambios rápidos (flapping)
4. Restaura automáticamente al modo preferido (4G) cuando la latencia mejora

**Configuración** (valores por defecto):

- Threshold de latencia: **200 ms**
- Ventana de decisión: **15 muestras malas** (30 segundos)
- Cooldown entre switches: **30 segundos**
- Delay antes de restore: **60 segundos**
- Modo preferido: **4G/Modem**

**Acceso manual** (API):

```bash
# Iniciar auto-failover
curl -X POST http://IP_PLACA:8000/api/network/failover/start?initial_mode=modem

# Ver estado
curl http://IP_PLACA:8000/api/network/failover/status

# Cambiar configuración (ejemplo: threshold a 250ms)
curl -X POST -H "Content-Type: application/json" \
  -d '{"latency_threshold_ms": 250}' \
  http://IP_PLACA:8000/api/network/failover/config

# Detener
curl -X POST http://IP_PLACA:8000/api/network/failover/stop
```

**Logs**: Los switches automáticos se registran en el log del servicio:

```bash
sudo journalctl -u fpvcopilot-sky -f | grep -i failover
```

### DNS Caching

Caché DNS local con `dnsmasq` para reducir latencia de resolución de nombres (útil para RTSP, telemetría a hostnames).

**Instalación y activación**:

```bash
# Instalar dnsmasq
curl -X POST http://IP_PLACA:8000/api/network/dns/install

# Iniciar servicio
curl -X POST http://IP_PLACA:8000/api/network/dns/start

# Verificar estado
curl http://IP_PLACA:8000/api/network/dns/status
```

**Beneficio**: Reduce latencia de DNS lookups de ~50ms a ~2ms (95% mejora).

---

## 5. Pestaña: Modem 4G

Panel completo de gestión del modem Huawei HiLink. Requiere un modem compatible conectado por USB.

### Información

Dos columnas con datos del operador y del dispositivo:

- **Operador**: nombre, tipo de red (4G/LTE), MCC-MNC, DNS, roaming, señal
- **Dispositivo**: modelo, IMEI, versión hardware/firmware

### Métricas de señal (KPI)

| Métrica | Descripción              | Rangos           |
| ------- | ------------------------ | ---------------- |
| RSSI    | Fuerza de señal recibida | > -70 dBm bueno  |
| RSRP    | Potencia de referencia   | > -100 dBm bueno |
| RSRQ    | Calidad de referencia    | > -10 dB bueno   |
| SINR    | Relación señal/ruido     | > 10 dB bueno    |

### Tráfico

Datos de uso en tiempo real: bytes enviados/recibidos, tasa de transferencia.

### Latencia

Test de latencia automático al entrar en la pestaña. Muestra:

- **Promedio**, mínimo, máximo, jitter
- **Calificación**: Excelente / Bueno / Aceptable / Pobre
- Botón 🔄 para repetir el test

### Calidad de video

Evaluación automática de la calidad del streaming según la señal:

| SINR     | RSRP        | Calidad   | Bitrate máx. | Resolución |
| -------- | ----------- | --------- | ------------ | ---------- |
| > 15 dB  | > -90 dBm   | Excelente | 5000 kbps    | 1280×720   |
| 10-15 dB | -90 a -100  | Bueno     | 3000 kbps    | 854×480    |
| 5-10 dB  | -100 a -110 | Moderado  | 1500 kbps    | 640×360    |
| < 5 dB   | < -110 dBm  | Pobre     | 500 kbps     | 426×240    |

### Configuración de bandas LTE

Presets rápidos para seleccionar bandas según la situación:

| Preset              | Bandas          | Uso                          |
| ------------------- | --------------- | ---------------------------- |
| **Todas**           | B1+B3+B7+B8+B20 | Búsqueda general             |
| **Urbano** (España) | B3+B7           | Ciudad, máxima velocidad     |
| **Rural** (España)  | B20             | Cobertura extendida, campo   |
| **Solo 4G**         | Modo LTE Only   | Forzar LTE, evitar caer a 3G |

### Modo video optimizado

Activa ajustes del modem optimizados para streaming de video:

- Prioriza estabilidad sobre velocidad
- Reduce intervalos de búsqueda de celdas
- Ideal para vuelos de larga distancia

### Sesión de vuelo

Grabación de métricas durante el vuelo para análisis post-vuelo:

- **Iniciar sesión**: pulsa **Start** para comenzar a registrar métricas
- **Detener sesión**: pulsa **Stop** → muestra resumen con nº de muestras y duración
- **Auto-inicio al armar**: activa el toggle para que la sesión inicie/pare automáticamente al armar/desarmar el vehículo (preferencia persistente)

Los datos se guardan en archivos CSV en `~/flight-records/`:

```
~/flight-records/flight-2026-02-08_17-30-36.csv
```

**Cabeceras CSV:**

```
timestamp, latitude, longitude, altitude_msl, ground_speed_ms, air_speed_ms,
climb_rate_ms, armed, flight_mode, vehicle_type, rssi, rsrp_dbm, rsrq_db,
sinr_db, cell_id, pci, band, network_type, operator, latency_ms
```

- Se registra una muestra cada **5 segundos** combinando telemetría GPS + señal del modem
- El directorio de logs es configurable en `preferences.json` → `flight_session.log_directory`

**Verificar registros:**

```bash
ls -lh ~/flight-records/
tail -5 ~/flight-records/flight-*.csv
wc -l ~/flight-records/flight-*.csv
```

---

## 6. Pestaña: VPN

Gestiona la conexión Tailscale para acceso remoto seguro.

### Primera conexión

1. Pulsa **Conectar** (o el botón **Abrir URL de autenticación**)
2. Se genera una URL de autenticación de Tailscale
3. Abre esa URL en cualquier navegador (PC, móvil)
4. Inicia sesión con tu cuenta Tailscale (Google, Microsoft, GitHub…)
5. El dispositivo aparece en tu red Tailscale
6. El badge del header cambia a 🟢 **VPN Conectado**

### Estado

Muestra: IP de Tailscale (100.x.x.x), hostname, interfaz, peers online.

### Nodos (Peers)

Lista de todos los dispositivos en tu red Tailscale:

- **⭐ Este dispositivo**: el SBC donde corre FPV Copilot Sky
- **Otros nodos**: tus PCs, móviles, servidores
- Estado online/offline
- IPs asignadas por Tailscale
- Sistema operativo

### Selector de peers

En las pestañas de **Video** y **Telemetría**, los campos de IP incluyen un desplegable (▼) que muestra los nodos VPN. Selecciona cualquiera para usar su IP como destino de video o telemetría.

### Controles

- **Conectar**: conectar a la red Tailscale
- **Desconectar**: desconectar (mantiene credenciales)
- **Logout**: cierra sesión completamente (requiere re-autenticación)

---

## 7. Pestaña: Sistema

Información del sistema y servicios.

### Recursos

- **CPU**: uso actual, temperatura, governor
- **RAM**: total, usada, disponible

### Servicios

Estado de los servicios del sistema: fpvcopilot-sky, nginx, NetworkManager, ModemManager, tailscaled.

---

## 8. Flujos de configuración típicos

### Vuelo con 4G (sin WiFi)

1. Conecta el modem 4G y la cámara al SBC
2. Conecta la VPN Tailscale (pestaña VPN)
3. Configura video → IP del nodo VPN destino → puerto 5600 → Iniciar
4. Configura telemetría → salida UDP al nodo VPN destino → puerto 14550
5. En el GCS remoto: abre QGC con video UDP:5600 y telemetría UDP:14550

### Vuelo local con WiFi

1. Conecta a la misma red WiFi que tu portátil (pestaña Red)
2. Configura video → IP del portátil → puerto 5600 → Iniciar
3. Configura telemetría → salida UDP a la IP del portátil → puerto 14550
4. En el portátil: abre QGC/Mission Planner con video y telemetría

### Pre-vuelo con modem 4G

1. Pestaña Modem → revisa señal y calidad
2. Ejecuta test de latencia → verifica < 100 ms
3. Si la señal es pobre, prueba otro **preset de bandas**
4. Activa **Modo Video** si vas a volar lejos
5. Opcionalmente inicia una **Sesión de vuelo** para registrar métricas

---

## 9. Solución de problemas

### No veo la interfaz web

```bash
# Verificar que nginx sirve la app
curl -I http://localhost

# Si dice "Welcome to nginx":
sudo rm /etc/nginx/sites-enabled/default
sudo systemctl reload nginx
```

### El controlador de vuelo no conecta

- Verifica el cable físico
- Prueba otro baudrate (57600, 115200, 921600)
- Comprueba que el puerto no esté ocupado: `sudo fuser /dev/ttyAML0`
- Reinicia el servicio: `sudo systemctl restart fpvcopilot-sky`

### No hay video

- ¿Cámara conectada? `v4l2-ctl --list-devices`
- ¿IP destino correcta?
- ¿Puerto 5600 libre en el receptor?
- Reinicia el stream desde la WebUI

### El modem no aparece

- ¿USB conectado? `lsusb | grep -i huawei`
- ¿Interfaz de red creada? `ip link show | grep enx`
- ¿Responde la API? `ping -c 1 192.168.8.1`
- Ejecuta `bash scripts/configure-modem.sh`

### VPN no conecta

- Verifica que Tailscale está instalado: `which tailscale`
- Comprueba permisos: `sudo -n tailscale status`
- Si pide re-autenticación: pulsa **Logout** y vuelve a **Conectar**
- Verifica conectividad a internet desde el SBC

### La WebUI va lenta

- Comprueba CPU/RAM en la pestaña Sistema
- Reduce la resolución de video
- El SBC necesita al menos 1 GB RAM libre para operar cómodamente

---

[← Índice](INDEX.md) · [Anterior: Instalación](INSTALLATION.md) · [Siguiente: Guía de Desarrollo →](DEVELOPER_GUIDE.md)
