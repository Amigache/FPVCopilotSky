# 🔐 Plan de Endurecimiento de Seguridad — Fase 0

Rama: `fix/security-hardening` (base `develop` @ `71d4f6d`)
Referencia: [`AUDIT_AND_REFACTOR_PLAN.md`](./AUDIT_AND_REFACTOR_PLAN.md) §3 (hallazgos C1–C6).

---

## Objetivo

Cerrar los hallazgos críticos de seguridad. Es un bloqueante de Fase 0 porque el
sistema controla un dron y la red, y hoy es accesible sin autenticación.

Varias correcciones están **acopladas a la arquitectura actual** y no se pueden
aplicar sin rediseño. Este documento separa lo **ya aplicado** de lo **pendiente
con diseño**, para no romper el appliance.

---

## ✅ Aplicado en esta rama

### C3 — Sudoers peligrosos

✅ **Resuelto.** `scripts/setup-system-sudoers.sh` está neutralizado (shim) y
`scripts/setup-sudoers.sh` ahora **elimina** todas las reglas NOPASSWD
(`/etc/sudoers.d/fpvcopilot-*`, `tailscale`). Las operaciones privilegiadas se
resuelven con el helper `fpvcopilot-privd` (whitelist en
`app/security/privd_policy.py`), sin wildcards amplios.

### C4 — Usuario del servicio fuera del grupo `sudo`

- `install.sh` ya no añade `fpvcopilotsky` al grupo `sudo`. Los permisos
  NOPASSWD son por usuario (no requieren pertenencia al grupo), por lo que la
  app sigue funcionando con el conjunto mínimo de comandos.

### M6 — Puertos serie no world-writable

- `scripts/setup-serial-ports.sh`: `chmod 666` → `chgrp dialout` + `chmod 660`.
  Evita que cualquier usuario local inyecte tramas MAVLink al controlador.

---

## ⏳ Pendiente con diseño

### C1 — Autenticación en la API (la corrección más importante)

Diseño propuesto, **compatible y por fases**:

1. **API key de servicio** vía variable de entorno (`FPV_API_TOKEN`). Si está
   definida, un middleware/dependencia FastAPI exige
   `Authorization: Bearer <token>`; si no, se comporta como hoy (modo dev).
2. **Endpoints sensibles** (`/api/system/version/update|rollback`,
   `restart`, `preferences`, VPN logout, modem/WiFi connect) requieren token
   **siempre**, aunque el modo global esté desactivado.
3. **WebSocket `/ws`**: autenticar con token en query (`?token=`) o
   subprotocolo; rechazar con `4401` si falta.
4. **Frontend**: guardar el token en `localStorage`/prompt y añadirlo a
   `api.js` y a la URL del WebSocket.
5. **Nginx**: bloquear `/docs` y `/openapi.json` en producción.

### C2 — Exposición de red y TLS

✅ **Resuelto.** Backend escuchando en `127.0.0.1` (nginx es la única entrada),
`/docs`/`/redoc`/`/openapi.json` bloqueados, CORS configurable por entorno. TLS
disponible con `scripts/setup-tls.sh` (self-signed para LAN o `--tailscale`):
genera el certificado, instala `systemd/fpvcopilot-sky.tls.nginx` (443 + redirección
80→443) y recarga nginx. `deploy.sh` conserva el config TLS mientras exista el
certificado.

### C5 — Código fuente escribible por el servicio

El updater actual ejecuta `git reset/checkout`, `pip install` y `npm build`
**dentro del proceso**, así que necesita escritura sobre `/opt/FPVCopilotSky`. No
hay arreglo parcial: si el árbol pasa a ser de solo lectura sin más, el updater
se rompe.

**Plan por etapas (seguro y validable en el equipo):**

1. **Etapa 1 — updater privilegiado con fallback.** Añadir
   `systemd/fpvcopilot-update.service` (oneshot, `User=root`) y
   `scripts/privileged-update.sh`, que lee el objetivo desde
   `/var/lib/fpvcopilot-sky/update-request.env` (validado con regex antes de
   usarlo) y hace checkout/pip/npm/restart como root. `SystemService.apply_update`
   escribe la petición y lanza `sudo -n systemctl start fpvcopilot-update`, con
   **fallback** al método actual si la unidad no está instalada. No cambia aún
   los permisos → retrocompatible y validable con una actualización real.
2. **Etapa 2 — árbol de solo lectura.** ✅ **Implementada.**
   `scripts/harden-ownership.sh` deja `/opt/FPVCopilotSky` en `root:fpvcopilotsky`
   con lectura/ejecución para el servicio (nunca escritura); `install.sh` la
   aplica al final de la instalación. El updater privilegiado **preserva** el
   ownership existente, así que sigue funcionando en modo desarrollo. Para
   volver al modo desarrollo: `sudo bash scripts/harden-ownership.sh --revert`.
   `deploy.sh` compila el frontend como root y deja `dist` legible por nginx.
3. **Etapa 3 — sandbox + helper de red.** ✅ **Implementada (M7 Incrementos
   1-3):** helper privilegiado `fpvcopilot-privd`, reglas NOPASSWD eliminadas y
   sandbox activado en `fpvcopilot-sky.service` (`NoNewPrivileges`,
   `ProtectSystem=strict`, `CapabilityBoundingSet=`).

### C6 — Instaladores remotos sin verificación

✅ **Implementado (PR #46).** `install.sh` ya no ejecuta scripts remotos: usa los
repositorios APT firmados de NodeSource y Tailscale (keyrings GPG). No queda
`curl | bash`/`curl | sh` en el repositorio.

### M5 — Dependencias sin fijar

✅ **Implementado.** `install.sh`, `scripts/privileged-update.sh` y el fallback
en proceso usan `requirements.lock` (pinned) cuando está presente, con
`requirements.txt` como fallback. El lock actual cubre runtime y dev.
Regeneración: `pip freeze --exclude-editable` desde un entorno con
`--system-site-packages` (excluyendo `pip`, `setuptools`, `wheel`).

### Arquitectura de privilegios (habilita M7)

Helper privilegiado **`fpvcopilot-privd`** (root, socket unix
`/run/fpvcopilot-priv.sock` `0660 root:fpvcopilotsky`), con whitelist de comandos
en `app/security/privd_policy.py`. El cliente (`app/security/privileged.py`) y el
routing en `app/utils/cmd.py` sustituyen `sudo` por el helper cuando el socket
existe, con fallback a `sudo` si no.

- **Incremento 1 (hecho y validado en el equipo)**: daemon
  (`app/security/privd_daemon.py`), política, cliente, unidad
  `systemd/fpvcopilot-privd.service`, routing central y tests. Validado en el
  equipo: socket `root:fpvcopilotsky 0660`, `ip route show` permitido, comandos
  peligrosos denegados (rc=126) y la app en marcha enruta `iw scan` / `ip route`
  por el helper (log `exec:` / `denied:`).
- **Incremento 2 (hecho)**: migración total de los caminos que no pasaban por
  `cmd.py` — `policy_routing_manager` (stdin), `dns_cache._exec`,
  `latency_monitor` (ping), `system_service` (`Popen` → hilo de fondo) y
  `gstreamer_service`. `run_cmd`/`run_cmd_async` soportan stdin. Escaneo AST:
  todos los `sudo` literales cubiertos por la whitelist.
- **Incremento 3 (hecho)**: `deploy.sh` instala y habilita `fpvcopilot-privd`;
  `setup-sudoers.sh` elimina todas las reglas NOPASSWD; `fpvcopilot-sky.service`
  activa `NoNewPrivileges`, `ProtectSystem=strict` (+ `ReadWritePaths`),
  `CapabilityBoundingSet=` vacío y varias protecciones más. El servicio ya no
  usa `sudo` en absoluto. **Validado en el equipo (2026-09-21):** sandbox activo,
  sin reglas sudoers, helper operativo con stdin y sin errores en el journal.

> Rollback del sandbox: revertir `systemd/fpvcopilot-sky.service` (quitar
> `NoNewPrivileges`/`ProtectSystem`), `daemon-reload` y reiniciar. El helper
> `fpvcopilot-privd` es imprescindible: sin él no hay operaciones privilegiadas.

---

## Verificación

- `bash -n` sobre `install.sh`, `scripts/setup-system-sudoers.sh`,
  `scripts/setup-serial-ports.sh`.
- En una máquina de pruebas: `sudo bash scripts/setup-sudoers.sh`; comprobar que
  no existe ningún `/etc/sudoers.d/fpvcopilot-*` y que `fpvcopilot-privd` está
  activo.
- `ls -l /dev/ttyUSB*` → `crw-rw---- … dialout`.
- CI: el job de lint no cubre scripts; se propone añadir un chequeo que falle si
  reaparecen patrones `tee *`, `sysctl -w *` en los sudoers.

---

## Estado

| Hallazgo                | Estado                                                                      |
| ----------------------- | --------------------------------------------------------------------------- |
| C1 Auth API             | ✅ implementado (PR #44): opt-in `FPV_API_TOKEN` + WebSocket                |
| C2 TLS / bind           | ✅ implementado: bind `127.0.0.1`, docs bloqueados, TLS vía `setup-tls.sh`  |
| C3 Sudoers wildcards    | ✅ resuelto: sin NOPASSWD; operaciones privilegiadas vía `fpvcopilot-privd` |
| C4 Grupo sudo           | ✅ aplicado                                                                 |
| C5 Código escribible    | ✅ Etapas 1-3 implementadas (updater root, ownership, helper + sandbox)     |
| C6 Instaladores remotos | ✅ implementado (PR #46): repos APT firmados                                |
| M5 Lock deps            | ✅ implementado: lock usado en install/updater/fallback                     |
| M6 Serial 666           | ✅ aplicado                                                                 |
| M7 Sandbox systemd      | ✅ implementado y validado en el equipo                                     |
