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

### C3 — Sudoers peligrosos (parcial)

- `scripts/setup-system-sudoers.sh` **neutralizado**: ya no escribe wildcards
  peligrosos (`tee *`, `sysctl -w *`, `mkdir -p *`, `ethtool -s *`). Ahora es un
  shim que delega en `scripts/setup-sudoers.sh` (política unificada y mínima).
- `install.sh`: el fallback de permisos de red ya no invoca el script obsoleto,
  sino el endurecido (`scripts/setup-sudoers.sh`). Ese script además **elimina**
  los ficheros legacy `/etc/sudoers.d/fpvcopilot-system` y `-wifi`/`tailscale`.
- `scripts/status.sh` y docs apuntan al script endurecido.

> **Pendiente C3**: `setup-sudoers.sh` aún concede `ip -force -batch *` y
> `ip rule *`. No permiten ejecución arbitraria como root (a diferencia de
> `tee *`), pero sí toda la configuración de red. Mitigación propuesta: sustituir
> por un helper privilegiado validado (ver _Arquitectura de privilegios_).

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

1. Backend a `127.0.0.1:8000` (quitar `0.0.0.0` del unit systemd y del arranque
   manual); dejar nginx como única entrada.
2. TLS en nginx (`listen 443 ssl`): certificados de **Tailscale** (`tailscale
cert`) o self-signed; redirigir 80→443.
3. CORS por allowlist (`FPV_CORS_ALLOW_ORIGINS`), nunca `*` en producción.
4. Rate limiting (`limit_req`) y `access_log` activado.

### C5 — Código fuente escribible por el servicio

Acoplado al **updater** (hace `git reset/checkout` dentro de `/opt`).

Diseño: separar **usuario de despliegue** (root/admin) de **usuario de
servicio**. El directed fix de Fase 0: mantener `/opt/FPVCopilotSky` propiedad de
`root:fpvcopilotsky` con `g+rX` (sin escritura) y ejecutar el updater mediante una
unidad systemd de un solo uso o un sudoers acotado que haga el checkout como
root, no como el usuario que corre la web.

### C6 — Instaladores remotos sin verificación

`install.sh` usa `curl … | sudo bash` (NodeSource) y `curl … | sh` (Tailscale).
Mitigación: fijar versión y verificar GPG/checksum; instalar claves de repo por
`apt` en lugar de ejecutar scripts remotos. Requiere ventanas de mantenimiento.

### M5 — Dependencias sin fijar

`requirements.lock` existe pero no se usa. Cambiar `install.sh` y el updater a
`pip install -r requirements.lock` (regenerando el lock antes). Riesgo: el lock
actual es de feb-2026; regenerarlo y validar en CI.

### Arquitectura de privilegios (habilita M7)

`systemd` no puede activar `NoNewPrivileges=true` (rompería `sudo`) ni
`ProtectSystem=strict` (rompería el updater). La solución de fondo es dejar de
usar `sudo` desde la app y sustituirlo por un **helper privilegiado** (servicio
systemd/IPC o polkit) que valide operaciones concretas. Solo entonces se podrá
endurecer el sandbox y eliminar las reglas NOPASSWD.

---

## Verificación

- `bash -n` sobre `install.sh`, `scripts/setup-system-sudoers.sh`,
  `scripts/setup-serial-ports.sh`.
- En una máquina de pruebas: `sudo bash scripts/setup-sudoers.sh` y
  `visudo -c`; comprobar que no existe `/etc/sudoers.d/fpvcopilot-system`.
- `ls -l /dev/ttyUSB*` → `crw-rw---- … dialout`.
- CI: el job de lint no cubre scripts; se propone añadir un chequeo que falle si
  reaparecen patrones `tee *`, `sysctl -w *` en los sudoers.

---

## Estado

| Hallazgo                | Estado                                                                |
| ----------------------- | --------------------------------------------------------------------- |
| C1 Auth API             | ⏳ diseño listo, sin implementar                                      |
| C2 TLS / bind           | ⏳ diseño listo, sin implementar                                      |
| C3 Sudoers wildcards    | 🟡 mitigado (script obsoleto neutralizado); `ip` wildcards pendientes |
| C4 Grupo sudo           | ✅ aplicado                                                           |
| C5 Código escribible    | ⏳ acoplado al updater                                                |
| C6 Instaladores remotos | ⏳ pendiente                                                          |
| M5 Lock deps            | ⏳ pendiente                                                          |
| M6 Serial 666           | ✅ aplicado                                                           |
| M7 Sandbox systemd      | ⏳ acoplado a C1/`sudo`                                               |
