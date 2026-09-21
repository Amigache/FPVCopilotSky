# 🔬 Revisión Funcional: Video, Network y Telemetría

Revisión a fondo de las tres funcionalidades principales y su optimización según el
**tipo de conexión** (LAN/WiFi, 4G/LTE, VPN/Tailscale). Base: **v1.1.1**.
Este documento es la fuente de seguimiento; las tareas van marcándose aquí.

---

## 🧭 Visión por tipo de conexión (lo que falta)

No existe un **modelo de perfil de enlace** compartido; hoy todo está optimizado para LAN.

| Enlace            | Ideal                                                                                                                                    |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| **LAN/WiFi**      | UDP, bitrate/resolución altos, telemetría a full rate, sin shaper.                                                                       |
| **4G/LTE**        | WebRTC o SRT/RIST, bitrate/resolución bajos y adaptativos, **CAKE de subida calibrado**, telemetría reducida (`SR1_*`), DSCP sin `wash`. |
| **VPN/Tailscale** | MTU explícito (1280), no publicar URL tailnet inalcanzable en LAN, health-check con umbrales de túnel y jitter.                          |

Falta: **estimación de throughput** (no solo RTT), **latencia/pérdida reales por interfaz**,
**un único orquestador de rutas** y **perfiles automáticos** que fijen modo de vídeo +
stream rates de telemetría + tuning de red según el enlace detectado.

---

## 🎥 1) Video Stream

### Bugs duros

- [x] **V1** `self.preferences_service` no existe → `AttributeError` en `start()` si autodetecta cámara (`gstreamer_service.py:1733-1735`).
- [x] **V2** `_attach_webrtc_appsink` llamado pero no definido (inalcanzable hoy) (`gstreamer_service.py:1416`).
- [x] **V3** `h264_passthrough` (preferido por la UI) se degrada a MJPEG en `VideoConfig` (`video_config.py:151`).
- [x] **V4** Stats inventadas: probes no-op; FPS/bitrate estimados de la config (`gstreamer_service.py:882-906,1518-1605`). _(RTSP real; UDP/WebRTC estimado por defecto — ver validación)_
- [x] **V5** Adaptación de red no aplica en WebRTC ni RTSP (`gstreamer_service.py:2140-2148`).

### Mejoras

- [ ] GOP coherente por perfil (hoy 15/30/2/2 dispares).
- [ ] WebRTC: `queue leaky` (backpressure) + `videoscale`/caps según config.
- [ ] RTSP: no pisar `config-interval=-1`; `rtpjitterbuffer`; revisar `aggregate-mode`.
- [ ] OpenCV: limitar FPS/resolución de procesado.
- [ ] MTU real por interfaz (hoy 1300/1400 hardcode).
- [ ] Realimentación pérdida/RTT (RTCP RR) a UDP/RTSP; valorar SRT/RIST.

### Sobra

- [ ] Probes no-op, `WebRTCVideoAdapter`, `_attach_webrtc_appsink`, codecs fantasma (`h264_v4l2`/`h264_omx`/`h264_x264`), `_create_fallback_udp_sink`, pipeline RTSP duplicado.

---

## 🌐 2) Network

### Bugs duros

- [x] **N1** Deadlock en AutoFailover: lock no reentrante (`auto_failover.py:231/246` + `:360`).
- [x] **N2** `mode="auto"` deja WiFi y módem en `metric 200` → sin primaria (`status.py:368,397`).
- [x] **N3** `ModemPool` borra **todas** las default routes (`modem_pool.py:604-610`).
- [ ] **N4** Tres escritores de rutas se pisan (`modem_pool`, `set_priority_mode`, `set_metric`).
- [x] **N5** CAKE mal calibrado: burst al gateway, solo subida, bajada fija 30, `ifb0` compartido (`network_optimizer.py:307-379,54,413-433`).
- [x] **N6** DSCP inútil: se marca EF-46 y CAKE subida aplica `wash` (`network_optimizer.py:132-173` vs `:414`).
- [x] **N7** Latencia no es por interfaz (`ping` sin `-I`; `interface` solo etiqueta) (`latency_monitor.py:200-206,302-345`).

### Mejoras

- [ ] Un único orquestador de rutas (`PolicyRoutingManager`) como dueño de defaults/métricas.
- [ ] Cooldown/anti-flapping unificado.
- [ ] Estimación de throughput (no solo RTT).
- [x] MTU/overlay VPN (1280) y health-check con umbrales de túnel.
- [ ] sysctl: quitar `tcp_rto_min`, añadir `fq`, `tcp_rmem/wmem`; restaurar todo bien.
- [ ] DNS cache: parser real; no pisar `resolv.conf` gestionado; no `apt-get` en vuelo.
- [x] vpn_health_checker: arreglar condición de precedencia (`:244`).

### Sobra

- [ ] MPTCP (no aplica a UDP), DSCP+`wash`, `_configure_vpn_policy_routing` duplicado, endpoint stub `auto_adjust_priority`, `_get_latency_metrics`, detección de módem triplicada.

---

## 📡 3) Telemetría (MAVLink)

### Bugs duros

- [x] **T1** `/api/mavlink-router/restart` llama a `restart()` inexistente → 500 siempre (`router.py:365` vs `mavlink_router.py:278`).
- [x] **T2** Broadcast WS por **cada** mensaje (7 puntos) → ~20-30 fps con snapshot completo (`mavlink_bridge.py:689-753`).
- [x] **T3** `get_telemetry()` hace `deepcopy`+JSON por mensaje en el hilo lector (`mavlink_bridge.py:825-830`).
- [x] **T4** El router mantiene el lock durante `sendall` bloqueante → un TCP lento bloquea el lector serial (`mavlink_router.py:90-133`).
- [ ] **T5** Carreras en `_param_list_*` y `mav_sender` sin lock (`mavlink_bridge.py:785-799,487; mavlink.py:221-225`).

### Mejoras

- [ ] Coalescer telemetría en backend (tasa fija 2-5 Hz / dirty set).
- [ ] Adaptación por enlace: `SET_MESSAGE_INTERVAL`/`SRx_*` automáticos.
- [ ] Router: filtrado por salida + colas no bloqueantes con drop.
- [ ] Refrescar `mavlink_status` periódicamente.
- [ ] `parse_buffer` en vez de `parse_char` byte a byte.
- [ ] Parámetros: respetar `timeout` y TTL de caché.
- [ ] Frontend: `useMemo` en `ParamCacheContext`; memoizar `Dashboard`/`MapView`; caché de tiles.

### Sobra

- [ ] Servidor TCP embebido del bridge (`tcp_port=0`), aliases de parámetros, `quick_probe`, constantes de severidad duplicadas.

---

## 🚦 Priorización

### P0 — Correctitud (bugs que rompen función)

- [x] N1 · N2 · N3 · T1 · V1 · V3 · V2

### P1 — Ancho de banda y CPU

- [x] T2 · T3 · T4 · V4 · V5

### P2 — Adaptación por enlace

- [x] **P2a** Perfiles LAN/4G/VPN (vídeo) + tasas de telemetría (`SET_MESSAGE_INTERVAL`, opt-in) + robustez UDP (`buffer-size`)
- [x] **P2b** CAKE/DSCP coherente + ifb por interfaz · latencia por interfaz · MTU/VPN · fix detección VPN
- [ ] **P2c** Orquestador único de rutas (N4) + anti-flapping unificado

### P3 — Limpieza y frontend

- [ ] Quitar MPTCP/DSCP+wash/VPN policy duplicado/TCP server/probes muertos · `useMemo` en `ParamCacheContext` · memoizar Dashboard/MapView · caché de tiles

---

## 🧪 Validación en hardware (Radxa, 1080p30 H.264)

Resultados medidos sobre el equipo real con Mission Planner conectado:

| Ítem                        | Resultado                                                                          |
| --------------------------- | ---------------------------------------------------------------------------------- |
| T2/T3 telemetría coalescida | ✅ **~7 msg/s** (tope 10 Hz); antes ~20-30/s                                       |
| T4 router                   | ✅ cliente TCP lento (`clients:1`) sin bloquear la telemetría (7 msg/s, 0 errores) |
| V5 live-update UDP          | ✅ aplica (`bitrate` hardware)                                                     |
| V5 live-update RTSP         | ✅ aplica; contador real ≈27 frames/s                                              |
| V5 live-update WebRTC       | ✅ resuelve `webrtc_h264enc`                                                       |
| V4 métricas reales          | ⚠️ RTSP real; **UDP/WebRTC desactivado por defecto** (ver abajo)                   |

### Hallazgo V4 — el contador `identity` inline provocaba flashes grises

- El `identity name=stats_counter` insertado **en la ruta de paquetes RTP**
  añadía jitter suficiente para que, con ráfagas de keyframes, se perdieran
  paquetes UDP → flash gris en Mission Planner (cada pocos segundos).
- Con el contador **desactivado** (deploy `60b7bfb`) los flashes pasaron a ser
  muy esporádicos. El pipeline de proveedor queda **idéntico a v1.1.1**.
- Decisión: **`FPV_VIDEO_STATS_COUNTER` por defecto OFF** en UDP/multicast/WebRTC
  (se vuelve a la estimación); RTSP conserva su contador preexistente.
  `FPV_VIDEO_STATS_COUNTER=1` lo re-activa para A/B.

### Flash residual = congestión WiFi (no del código)

Con el pipeline idéntico a v1.1.1 todavía aparece un flash ocasional:

- **Canal 7 (2.4 GHz, 20 MHz)**, señal -65 dBm.
- RTT medio **129 ms**, picos de **790 ms** mientras el stream va a 6.2 Mbps.
- 0 % pérdida ICMP ⇒ pérdida por saturación de aire/decodificador.

Opciones (base para **P2 - adaptación por enlace**):

- Pasar a **5 GHz** o bajar bitrate/resolución cuando el enlace es marginal.
- Robustez UDP: `udpsink buffer-size`, o **RTSP/TCP · WebRTC** (retransmisión) en enlaces con pérdidas.
- Perfiles de enlace que ajusten **modo + bitrate + resolución** automáticamente.

### P2a — Validación de perfiles de enlace

| Prueba                   | Resultado                                                                                                                       |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------- |
| Auto en LAN              | ✅ `active_profile lan`; `bitrate:6000` live-update (sin reiniciar)                                                             |
| Override `vpn`           | ✅ `bitrate:4000` + `udp_buffer:2MB`, sin reiniciar                                                                             |
| Override `modem`         | ✅ reinicio a WebRTC (`resolution-kept:1920x1080` + `video-restart:webrtc`) y vuelta a `lan` (udp) — `streaming: True` en ambos |
| Evento WS `link_profile` | ✅                                                                                                                              |
| Resolución no soportada  | ✅ la cámara solo ofrece 4K/1080p, así que el manager **mantiene la actual** en vez de fallar                                   |

Hallazgos corregidos durante la validación: (1) el reinicio de pipeline requería más margen para liberar la cámara; (2) validar la resolución contra la cámara antes de reiniciar. El perfil es la base y el adaptativo de red ajusta en vivo (opción A).

---

_Documento de seguimiento de la revisión funcional (v1.1.1). Las tareas se marcan a medida que se implementan._
