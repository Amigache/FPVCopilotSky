# 🩺 Auditoría y Plan de Refactorización — FPV Copilot Sky

**Fecha:** 2026-09-20
**Rama auditada:** `dev-junio` (commit `2fc599e`)
**Alcance:** backend `app/` (108 módulos, ~34 000 líneas), frontend `frontend/client/src` (87 ficheros, ~17 400 líneas), `tests/` (49 ficheros), infra (`install.sh`, `scripts/`, `systemd/`, nginx, sudoers) y CI.
**Estado:** auditoría **de solo lectura**. No se modificó ningún fichero del proyecto salvo la creación de este documento.

---

## 1. Veredicto ejecutivo

El proyecto tiene una **arquitectura por capas bien pensada**, una **capa de ejecución de comandos ejemplar** y una **base de tests amplia y hoy en verde** en el backend. El principal problema no es la calidad del código Python (lint limpio, formato consistente), sino la **postura de seguridad**: es un sistema que controla un dron y la red, expuesto en claro, **sin autenticación**, con un usuario de servicio que dispone de root sin contraseña. A esto se suman deuda de rendimiento en el frontend y una suite de tests que oculta fallos reales.

### Estado medido hoy (no los badges)

| Área                        | Resultado                                                                    |
| --------------------------- | ---------------------------------------------------------------------------- |
| Backend — tests             | **866 passed / 19 skipped / 0 failed** (140 s, sin `test_mavlink_bridge.py`) |
| Backend — cobertura real    | **52.16 %** (gate 50 % ✅)                                                   |
| `coverage.xml` del repo     | **19.96 %** → **obsoleto**, no refleja la realidad                           |
| Frontend — tests            | **342 passed / 3 failed / 13 skipped** ❌                                    |
| `black --check`             | ✅ 160 ficheros sin cambios                                                  |
| `flake8 app/ tests/`        | ✅ 0 errores                                                                 |
| `eslint . --max-warnings 0` | ✅ 0 warnings                                                                |

> ⚠️ El árbol de trabajo ya contenía `frontend/client/src/components/Pages/VideoView/VideoView.jsx` modificado **antes** de esta auditoría (ver §6). No es un cambio de la auditoría.

---

## 2. ✅ Lo que está bien

- **Arquitectura por capas clara**: `api/routes` ↔ `services` ↔ `providers` (ABC en `app/providers/base/`), registro de providers en `main.py:330-356`. Fácil de extender.
- **Capa de ejecución de comandos ejemplar** (`app/utils/cmd.py`): timeout obligatorio, no lanza excepciones, retorna `(stdout, stderr, returncode)`, reintentos con backoff y variante async real (`create_subprocess_exec`, mata el proceso al expirar) que no bloquea el event loop.
- **Jerarquía de excepciones tipada** (`app/exceptions.py`) con `category`, `context` y `to_dict()`, usada correctamente en varios módulos de red.
- **Arranque cuidadoso con el event loop**: `main.py` desofila `gst-inspect`/`v4l2`/`psutil`/`systemctl` mediante `run_in_executor` y tiene instrumentación de “slow tick” (`main.py:850-967`).
- **Preferencias robustas** (`app/services/preferences.py`): singleton con `RLock`, escritura atómica con `fsync`, merge con defaults y backup en el reset.
- **WebSocketManager** deduplica payloads y limpia sockets muertos; `tests/test_websocket_manager.py` verifica comportamiento real (dedup, cache, errores).
- **Infra de operación**: `scripts/status.sh`, `preflight-check.sh`, `deploy.sh` con health-check; pre-commit con hooks pinneados; nginx con headers de seguridad y upstream en `127.0.0.1`.
- **i18n bien montado** (ES/EN, ~797 claves) y contexts React que fallan ruidosamente si se usan fuera del provider.
- **`requirements.lock`** existe (pinned, 2026-02-17).

---

## 3. ❌ Hallazgos por severidad

### 🔴 Crítico — Seguridad (bloqueante antes de exponer a Internet)

| #   | Hallazgo                                                                                                                                                                                                                           | Evidencia                                                                                           |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| C1  | **Cero autenticación en toda la API.** Sin `HTTPBearer`/`Depends(auth)`/sesión/token. Endpoints destructivos abiertos: update/rollback ejecutan `git reset --hard`, `git checkout --force`, `pip install`, `npm build` y reinicio. | `app/main.py:592-598`; `app/api/routes/system.py:31-60`; `app/services/system_service.py:258-424`   |
| C2  | **Expuesto en `0.0.0.0:8000`, HTTP sin TLS, CORS `*`.**                                                                                                                                                                            | `systemd/fpvcopilot-sky.service:16`; `systemd/fpvcopilot-sky.nginx:10`; `app/main.py:572-575`       |
| C3  | **Sudoers con wildcards → root trivial.** El instalador invoca el script obsoleto que concede `NOPASSWD: /usr/bin/tee *` (escribir cualquier fichero como root), `sysctl -w *`, `ip -force -batch *`.                              | `install.sh:411`; `scripts/setup-system-sudoers.sh:42,58,74,76`; `scripts/setup-sudoers.sh:117-118` |
| C4  | **El usuario del servicio está en `sudo`** y tiene shell `/bin/bash`, mientras la app corre sin autenticación con ese usuario.                                                                                                     | `install.sh:44,59,75`                                                                               |
| C5  | **Código fuente escribible por el servicio** (`chown -R` + `g+rw` + setgid) → un backend comprometido se reescribe y persiste.                                                                                                     | `install.sh:92-98`                                                                                  |
| C6  | **Scripts remotos pipeados a root sin verificación.**                                                                                                                                                                              | `install.sh:345,361`                                                                                |

### 🟠 Alto

| #   | Hallazgo                                                                                                                                                                                                      | Evidencia                                                                 |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| A1  | **Bloqueo del event loop en rutas `async`**: `check_for_updates` (HTTP 10 s), `apply_update`/`rollback` (git+pip+npm, minutos), `psutil`/`systemctl` síncronos. Contraste: `main.py:894-914` sí los desofila. | `app/api/routes/system.py:20-131`; `app/services/system_service.py:114`   |
| A2  | **447 `except Exception`**, muchos con `pass` silencioso (fallos invisibles).                                                                                                                                 | `app/main.py:432-459`; `app/services/gstreamer_service.py` (~20)          |
| A3  | **Mutación de estado privado sin lock**: `prefs._preferences[...]` + `_save()` saltándose el `RLock`. Riesgo de corrupción de `preferences.json`.                                                             | `app/api/routes/system.py:161,178,180`                                    |
| A4  | **God objects sin cobertura**: `gstreamer_service.py` (2709), `network_event_bridge.py` (1681), `system_service.py` (1413), `mavlink_bridge.py` (1273), `main.py` (1215).                                     | `app/services/`                                                           |
| A5  | **Re-render storm del frontend**: el contexto WebSocket recrea `messages` y el `value` en cada frame → re-render de todos los consumidores a 10-50 Hz.                                                        | `frontend/client/src/contexts/WebSocketContext.jsx:75-78,144-152`         |
| A6  | **Componentes monolíticos y sin code-splitting**: `NetworkView.jsx` (1259), `StatusView.jsx` (1204), `FlightControllerView.jsx` (869). Cero `React.lazy`.                                                     | `frontend/client/src/components/Pages/`; `components/Content/Content.jsx` |
| A7  | **Tests frontend en rojo (3)**: `FlightControllerView.test.jsx` busca `vehicleTitle.{copter,plane}` que el componente ya no renderiza → tests obsoletos.                                                      | `FlightControllerView.test.jsx:487-507`                                   |

### 🟡 Medio

| #   | Hallazgo                                                                                                                                                                                                             | Evidencia                                                              |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| M1  | **Cobertura inflada por omisión**: se excluyen **todos** `app/providers/*` (43 ficheros) + 4 servicios grandes (6330 líneas): threading, sudo, framing MAVLink y pipelines. 46 de 108 módulos fuera del denominador. | `pyproject.toml:46-57`                                                 |
| M2  | **~115 assertions permisivas** que aceptan `[200, 404, 500]`; `test_websocket_integration.py` envuelve casi todo en `try/except: pytest.skip` (un endpoint roto = “skip”).                                           | `tests/test_video_pipeline.py`; `tests/test_websocket_integration.py`  |
| M3  | **CI con checks no bloqueantes**: mypy, Trivy, Safety, `npm audit` en `continue-on-error`; `provider-contracts` sube un `coverage.xml` que no genera.                                                                | `.github/workflows/ci.yml:54,209-219,318-336`                          |
| M4  | **Gate de cobertura frontend inexistente** (`vitest.config.js` sin `thresholds`); CI **excluye** `StatusView.test.jsx`.                                                                                              | `frontend/client/vitest.config.js:14-18`; `ci.yml:252`                 |
| M5  | **Dependencias sin fijar** (`>=` en todo); `requirements.lock` nunca se instala.                                                                                                                                     | `requirements.txt`; `install.sh:339-340`; `system_service.py:364-367`  |
| M6  | **Puertos serie `chmod 666`** → cualquier usuario local inyecta MAVLink al FC.                                                                                                                                       | `scripts/setup-serial-ports.sh:190-202`                                |
| M7  | **systemd sin `NoNewPrivileges`** ni `ProtectSystem=strict`/`ReadWritePaths`/`CapabilityBoundingSet`.                                                                                                                | `systemd/fpvcopilot-sky.service:31-43`                                 |
| M8  | **Thread-safety en `MAVLinkBridge`**: threads de lectura/heartbeat mutan `stats`, `connected`, `telemetry_data` sin lock.                                                                                            | `app/services/mavlink_bridge.py:99-238`                                |
| M9  | **i18n incompleto**: strings hardcodeados (`NetworkView.jsx`, `ArmedBanner.jsx`, `PeerSelector.jsx`, `StatusView.jsx`), fechas fijas a `es-ES`, y **2 claves solo en `es.json`**.                                    | `es.json`/`en.json`; `router.presetTCPListen`, `router.presetUDPLocal` |
| M10 | **Fugas de timers**: `setTimeout` recursivo sin cleanup; refetch de preferencias y rebind de listener en cada cambio de pestaña.                                                                                     | `ModemView.jsx:141-170`; `ToastContext.jsx:24`; `App.jsx:21-50`        |
| M11 | **WebSocket frágil**: reconexión fija a 3 s sin backoff/jitter; URL con puerto `:8000` hardcodeado.                                                                                                                  | `WebSocketContext.jsx:27,100`                                          |
| M12 | **`fetch` sin comprobar `response.ok`** antes de `.json()`.                                                                                                                                                          | `FlightControllerView.jsx` (varios); `services/api.js:43-68`           |

### ⚪ Bajo / higiene

- `app/config.py` es una línea de comentario sin importaciones (código muerto). Igual `ArmedGuard.jsx` (nunca importado). Hay un `__pycache__/chat.pyc` huérfano sin `chat.py`.
- **Documentación desincronizada**: `docs/INDEX.md:14` enlaza `RUNBOOKS.md` (está en `docs/archive/`); el README se declara **React 19** pero `package.json` fija **React ^18.3.1**; el README dice licencia MIT pero **no existe `LICENSE`**; referencia la sección `#-multi-modem--advanced-networking`, inexistente.
- Credenciales por defecto en código: `app/providers/modem/router.py:26,142` (`password="admin"`).
- Solo 1 TODO en `app/` (positivo), pero ~1 `except Exception` por cada 20 líneas.
- Falta integración real (contenedores de red/GStreamer/serial): la degradación solo se simula.

---

## 4. 🛠️ Plan de refactorización

### Fase 0 — Seguridad (bloqueante, antes de exponer a Internet)

- [ ] Añadir autenticación a la API (token/`HTTPBearer` + dependencia global); deshabilitar `/docs` en producción; proteger update/rollback/restart.
- [ ] No publicar el puerto 8000: escuchar solo `127.0.0.1`, servir por nginx; añadir TLS (o Tailscale `serve`); fijar CORS a orígenes concretos.
- [ ] Purga de sudoers: eliminar `setup-system-sudoers.sh` (referencia en `install.sh:411`), quitar `tee *`, `sysctl -w *`, `ip -force -batch *`; sacar a `fpvcopilotsky` del grupo `sudo`; validar con `visudo -c` en CI.
- [ ] systemd: `NoNewPrivileges=true`, `ProtectSystem=strict` + `ReadWritePaths=/var/lib/fpvcopilot-sky`, `CapabilityBoundingSet`.
- [ ] Verificar checksums/GPG de instaladores remotos; serial `0660 group=dialout` en vez de `666`; mover credenciales de modem a config.

### Fase 1 — Corrección y CI verde (1-2 semanas)

- [ ] Arreglar los 3 tests frontend obsoletos (`FlightControllerView.test.jsx`).
- [ ] Hacer obligatorios mypy, Trivy, Safety y `npm audit`.
- [ ] Añadir `coverage.thresholds` en `vitest.config.js`; dejar de excluir `StatusView.test.jsx`; arreglar el upload de coverage de `provider-contracts`.
- [ ] Desofilar con `run_in_executor`/`run_cmd_async` las llamadas síncronas de `system.py`.
- [ ] Unificar manejo de errores con `HTTPException` (no 200 + `{"error"}`); middleware común de errores.
- [ ] Usar setters con lock en `system.py` (eliminar acceso a `_preferences`).
- [ ] Sustituir `except Exception: pass` por excepciones concretas + `logger.warning(..., exc_info=True)`.

### Fase 2 — Rendimiento y calidad (1 mes)

- [ ] Partir `WebSocketContext` (contextos por sector + `useMemo`/selectores) para eliminar el re-render storm.
- [ ] Trocear vistas grandes con `React.lazy`/`Suspense` y `manualChunks` (leaflet/framer-motion aparte); memoizar tarjetas.
- [ ] Empezar a dividir los god services (builder de pipeline, RTSP, stats en `gstreamer_service.py`).
- [ ] Backoff exponencial + jitter en la reconexión WS; limpieza de timers; tests de contextos/hooks/`api.js`.
- [ ] Cerrar brechas i18n y sincronizar docs (RUNBOOKS, React 18/19, LICENSE, anchors).

### Fase 3 — Extraer el código no cubierto (continuo)

- [ ] Incluir `providers/*` y los 4 servicios grandes en cobertura con tests unitarios sobre los mocks existentes.
- [ ] Subir el gate progresivamente (55 % → 65 %); mover `slow`/`e2e` a un job no bloqueante.
- [ ] Sustituir las ~115 assertions permisivas por códigos exactos (prohibir `500` como válido).
- [ ] Capa de integración real (contenedores) y tests de seguridad (auth, CSRF, sanitización).

---

## 5. 📋 Cambios propuestos por prioridad

| Prioridad | Cambio                                          | Impacto                       |
| --------- | ----------------------------------------------- | ----------------------------- |
| P0        | Auth de API + TLS + cerrar puerto               | Elimina RCE remoto            |
| P0        | Limpieza de sudoers + sacar de `sudo`           | Elimina escalada a root       |
| P0        | Quitar `chmod 666` en serial                    | Evita inyección MAVLink       |
| P1        | Arreglar tests frontend + CI bloqueante         | Recupera confianza en CI      |
| P1        | Desofilar rutas `system.py`                     | Elimina cuelgues del servidor |
| P2        | Refactor de `WebSocketContext` + code-splitting | UI fluida en hardware modesto |
| P2        | Dividir god services                            | Mantenibilidad y testabilidad |
| P3        | `requirements.lock` + actualizar docs           | Reproducibilidad              |

---

## 6. 🔍 Fichero modificado en el árbol de trabajo

### `frontend/client/src/components/Pages/VideoView/VideoView.jsx`

**Cambio:** 16 inserciones / 8 borrados, localizado en el `useEffect` que deriva los códecs disponibles (líneas 390-426).

**Comportamiento anterior:** siempre que la cámara soportara `h264_passthrough`, el efecto **forzaba** ese códec, sobrescribiendo el códec guardado/preferido que llega del backend. Como `loadVideoDevices()` se carga de forma diferida (líneas 164-172), el efecto podía ejecutarse **después** de sincronizar la config del backend (`initialLoadDone.current = true`, línea 91) y machacar la preferencia del usuario.

**Comportamiento nuevo:**

1. La preferencia automática por `h264_passthrough` se aplica **solo antes** de que llegue la config del backend (`if (!initialLoadDone.current)`, línea 409). Después, se respeta el códec guardado.
2. Se añade un `return` (línea 417) tras seleccionar passthrough para no caer en el bloque siguiente y reescribir la elección.
3. Se conserva el fallback: si el códec actual no es compatible con el dispositivo, se selecciona el primero compatible (`if (!currentCompatible)`, línea 421).

**Riesgo:** bajo. Es un ajuste de prioridad de selección de códec (frontend). No cambia el pipeline ni la API; como mucho, un stream H.264 con cámara passthrough arrancaría con el códec guardado en lugar de forzar passthrough.

**Mensaje de commit sugerido:**

```
fix(video): respect saved codec after backend config sync

Only auto-select h264_passthrough before the backend config has been
synced (initialLoadDone). Afterwards keep the saved/preferred codec
unless it is incompatible with the selected device.
```

---

## 7. 🌿 Estrategia de ramas y merge

### Estado actual verificado

```
main      f8e12a4  2026-02-19  (ancestro de dev-junio: 0/37)
develop   ec8b3ed  2026-06-15  (1 commit que no está en dev-junio)
dev-junio 2fc599e  2026-06-17  (3 commits por delante de develop)
merge-base dev-junio/develop = aa7e14d
```

- `dev-junio` está **3 commits por delante** de `develop`.
- `develop` tiene **1 merge (PR #40)** que no está en `dev-junio` → el merge **no puede ser fast-forward**, requiere commit de merge.
- **Dry-run de merge** (`git merge-tree --write-tree`):
  - `develop ← dev-junio` → **exit 0, sin conflictos**.
  - `main ← dev-junio` → **exit 0** (además main es ancestro, podría ser fast-forward).

### Flujo recomendado (comandos, sin ejecutar)

```bash
# 1) Commitear el fix de VideoView en dev-junio
git add frontend/client/src/components/Pages/VideoView/VideoView.jsx
git commit -m "fix(video): respect saved codec after backend config sync"
git push origin dev-junio

# 2) Integrar dev-junio en develop (merge no-ff; verificado sin conflictos)
git checkout develop
git pull --ff-only origin develop
git merge --no-ff dev-junio -m "Merge branch 'dev-junio' into develop"
git push origin develop

# 3) Crear la rama nueva para auditoría/mejoras desde develop
git checkout -b refactor/audit-improvements develop
git add docs/AUDIT_AND_REFACTOR_PLAN.md
git commit -m "docs(audit): add audit report and refactorization plan"
git push -u origin refactor/audit-improvements
```

**Recomendaciones:**

- Mantener este `.md` en la rama nueva (`refactor/audit-improvements`), no en `dev-junio`.
- Separar la **Fase 0 (seguridad)** en su propia rama (`fix/security-hardening`) por su criticidad y para facilitar revisión.
- `main` está muy desactualizado (`f8e12a4`, feb 2026). Promover `develop → main` tras validar el merge.
- No se ha ejecutado ningún commit, merge ni push: solo verificación en seco.

---

_Documento generado como resultado de la auditoría de 2026-09-20. No modifica código del proyecto._
