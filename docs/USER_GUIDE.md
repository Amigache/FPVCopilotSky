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

| Badge | Significado |
|-------|-------------|
| 🟢 **Stream Online** | Video streaming activo |
| 🟢 **FC Conectado** | Controlador de vuelo conectado por MAVLink |
| 🟡 **Desarmado** / 🟠 **Armado** | Estado de armado del drone |
| 🟢 **VPN Conectado** / 🔴 **VPN Desconectado** | Estado de la VPN Tailscale |

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

| Tipo | Uso típico | Ejemplo |
|------|-----------|---------|
| UDP | QGroundControl | `192.168.1.100:14550` |
| TCP Server | Mission Planner | Puerto 5760 |
| TCP Client | Servidor remoto | `servidor:5760` |

**Selector de peers VPN**: Si tienes Tailscale conectado, el input de IP muestra un desplegable con los nodos de tu red VPN para seleccionar la IP rápidamente.

---

## 3. Pestaña: Video

Configura y controla el streaming de video.

### Configuración

1. **Cámara**: selecciona la cámara USB detectada
2. **Codec**: H.264 (mejor calidad) o MJPEG (menor latencia)
3. **Resolución**: desde 480p hasta 1080p
4. **IP destino**: donde enviar el stream (usa el selector de peers VPN)
5. **Puerto**: típicamente 5600

### Controles

- **Iniciar / Detener stream**: arranca o para el pipeline GStreamer
- **Aplicar configuración**: aplica cambios sin detener

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
# VLC
vlc rtp://@:5600

# ffplay (mínima latencia)
ffplay -fflags nobuffer -flags low_delay -probesize 32 -analyzeduration 0 rtp://@:5600
```

---

## 4. Pestaña: Red

Gestiona las interfaces de red, WiFi, y priorización de conexiones.

### Interfaces

Vista de todas las interfaces de red activas (WiFi, Ethernet, modem 4G, VPN) con IP, estado y métricas de ruta.

### WiFi

- **Escanear redes**: busca SSIDs disponibles
- **Conectar**: introduce la contraseña y conecta
- **Desconectar**: desconecta de la red WiFi actual

### Priorización de red

El sistema gestiona automáticamente la prioridad de las interfaces:

| Prioridad | Interfaz | Métrica |
|-----------|----------|---------|
| 1 (máxima) | VPN Tailscale | 10 |
| 2 | Red principal (4G) | 100 |
| 3 | Red secundaria (WiFi) | 200 |

**Modos de operación**:

- **Auto** (recomendado): el sistema decide la mejor interfaz
- **Modem forzado**: prioriza 4G siempre
- **WiFi forzado**: prioriza WiFi siempre

---

## 5. Pestaña: Modem 4G

Panel completo de gestión del modem Huawei HiLink. Requiere un modem compatible conectado por USB.

### Información

Dos columnas con datos del operador y del dispositivo:

- **Operador**: nombre, tipo de red (4G/LTE), MCC-MNC, DNS, roaming, señal
- **Dispositivo**: modelo, IMEI, versión hardware/firmware

### Métricas de señal (KPI)

| Métrica | Descripción | Rangos |
|---------|-------------|--------|
| RSSI | Fuerza de señal recibida | > -70 dBm bueno |
| RSRP | Potencia de referencia | > -100 dBm bueno |
| RSRQ | Calidad de referencia | > -10 dB bueno |
| SINR | Relación señal/ruido | > 10 dB bueno |

### Tráfico

Datos de uso en tiempo real: bytes enviados/recibidos, tasa de transferencia.

### Latencia

Test de latencia automático al entrar en la pestaña. Muestra:

- **Promedio**, mínimo, máximo, jitter
- **Calificación**: Excelente / Bueno / Aceptable / Pobre
- Botón 🔄 para repetir el test

### Calidad de video

Evaluación automática de la calidad del streaming según la señal:

| SINR | RSRP | Calidad | Bitrate máx. | Resolución |
|------|------|---------|-------------|------------|
| > 15 dB | > -90 dBm | Excelente | 5000 kbps | 1280×720 |
| 10-15 dB | -90 a -100 | Bueno | 3000 kbps | 854×480 |
| 5-10 dB | -100 a -110 | Moderado | 1500 kbps | 640×360 |
| < 5 dB | < -110 dBm | Pobre | 500 kbps | 426×240 |

### Configuración de bandas LTE

Presets rápidos para seleccionar bandas según la situación:

| Preset | Bandas | Uso |
|--------|--------|-----|
| **Todas** | B1+B3+B7+B8+B20 | Búsqueda general |
| **Urbano** (España) | B3+B7 | Ciudad, máxima velocidad |
| **Rural** (España) | B20 | Cobertura extendida, campo |
| **Solo 4G** | Modo LTE Only | Forzar LTE, evitar caer a 3G |

### Modo video optimizado

Activa ajustes del modem optimizados para streaming de video:

- Prioriza estabilidad sobre velocidad
- Reduce intervalos de búsqueda de celdas
- Ideal para vuelos de larga distancia

### Sesión de vuelo

Grabación de métricas durante el vuelo:

- **Iniciar sesión**: comienza a registrar RSSI, RSRP, SINR, latencia
- **Detener sesión**: finaliza y muestra resumen
- Útil para analizar cobertura post-vuelo

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
