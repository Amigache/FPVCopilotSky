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
- [x] **V4** Stats inventadas: probes no-op; FPS/bitrate estimados de la config (`gstreamer_service.py:882-906,1518-1605`).
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
- [ ] **N5** CAKE mal calibrado: burst al gateway, solo subida, bajada fija 30, `ifb0` compartido (`network_optimizer.py:307-379,54,413-433`).
- [ ] **N6** DSCP inútil: se marca EF-46 y CAKE subida aplica `wash` (`network_optimizer.py:132-173` vs `:414`).
- [ ] **N7** Latencia no es por interfaz (`ping` sin `-I`; `interface` solo etiqueta) (`latency_monitor.py:200-206,302-345`).

### Mejoras

- [ ] Un único orquestador de rutas (`PolicyRoutingManager`) como dueño de defaults/métricas.
- [ ] Cooldown/anti-flapping unificado.
- [ ] Estimación de throughput (no solo RTT).
- [ ] MTU/overlay VPN (1280) y health-check con umbrales de túnel.
- [ ] sysctl: quitar `tcp_rto_min`, añadir `fq`, `tcp_rmem/wmem`; restaurar todo bien.
- [ ] DNS cache: parser real; no pisar `resolv.conf` gestionado; no `apt-get` en vuelo.
- [ ] vpn_health_checker: arreglar condición de precedencia (`:244`).

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

- [ ] Perfiles LAN/4G/VPN (vídeo + `SRx_*` + red) · CAKE real · latencia por interfaz · MTU/VPN · orquestador único de rutas

### P3 — Limpieza y frontend

- [ ] Quitar MPTCP/DSCP+wash/VPN policy duplicado/TCP server/probes muertos · `useMemo` en `ParamCacheContext` · memoizar Dashboard/MapView · caché de tiles

---

_Documento de seguimiento de la revisión funcional (v1.1.1). Las tareas se marcan a medida que se implementan._
