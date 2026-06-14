# 📑 FPV Copilot Sky — Wiki

Bienvenido a la documentación de **FPV Copilot Sky**. Aquí encontrarás todo lo necesario para instalar, usar y contribuir al proyecto.

---

## Guías

| #   | Documento                                   | Descripción                                                                                                 | Audiencia            |
| --- | ------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | -------------------- |
| 1   | [📥 Guía de Instalación](INSTALLATION.md)   | Requisitos, instalación paso a paso, configuración de producción, verificación                              | Todos                |
| 2   | [📖 Guía de Usuario](USER_GUIDE.md)         | Uso de la WebUI, cada pestaña explicada, configuración de video/telemetría/VPN/modem, solución de problemas | Pilotos / Usuarios   |
| 3   | [🛠️ Guía de Desarrollo](DEVELOPER_GUIDE.md) | Arquitectura, stack tecnológico, estructura del proyecto, cómo añadir proveedores, convenciones de código   | Desarrolladores      |
| 4   | [🚨 Runbooks Operativos](RUNBOOKS.md)       | Procedimientos de diagnóstico y recuperación para incidencias críticas (MAVLink, modem, stream)             | Operadores / Pilotos |

---

## Red Avanzada — Multi-Modem & Policy Routing

La documentación de las fases de red avanzada (FASE 1-3) se encuentra integrada en las guías principales:

| Tema                                          | Documento                                | Sección                                                                                        |
| --------------------------------------------- | ---------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Resumen arquitectura FASE 1/2/3               | [README.md](../README.md)                | [§ Multi-Modem & Advanced Networking](../README.md#-multi-modem--advanced-networking)          |
| Instalación / sudoers / reglas dinámicas      | [Guía de Instalación](INSTALLATION.md)   | [§ Advanced Networking Setup (FASE 1-3)](INSTALLATION.md#5-advanced-networking-setup-fase-1-3) |
| Uso del Pool de Modems (UI)                   | [Guía de Usuario](USER_GUIDE.md)         | [§ Multi-Modem Management](USER_GUIDE.md#10-multi-modem-management)                            |
| Protección VPN durante switches               | [Guía de Usuario](USER_GUIDE.md)         | [§ VPN Health Protection](USER_GUIDE.md#11-vpn-health-protection)                              |
| FASE 1: ModemPool (API, scoring, config)      | [Guía de Desarrollo](DEVELOPER_GUIDE.md) | [§ FASE 1: ModemPool](DEVELOPER_GUIDE.md#fase-1-modempool)                                     |
| FASE 2: PolicyRoutingManager (tablas, fwmark) | [Guía de Desarrollo](DEVELOPER_GUIDE.md) | [§ FASE 2: PolicyRoutingManager](DEVELOPER_GUIDE.md#fase-2-policyroutingmanager)               |
| FASE 3: VPNHealthChecker (rollback, API)      | [Guía de Desarrollo](DEVELOPER_GUIDE.md) | [§ FASE 3: VPNHealthChecker](DEVELOPER_GUIDE.md#fase-3-vpnhealthchecker)                       |
| Tests FASE 1-3 y PreferencesView              | [CONTRIBUTING.md](../CONTRIBUTING.md)    | [§ Tests de Red Avanzada](../CONTRIBUTING.md#tests-de-red-avanzada-fase-1-3)                   |

---

## Referencia rápida

### CLI de Gestión (Recomendado)

```bash
./fpv    # Menú interactivo con todas las operaciones
```

El CLI proporciona acceso guiado a:

- 📦 Instalación y Despliegue
- 🛠️ Modo Desarrollo
- 📊 Diagnóstico y Estado del Sistema
- ⚙️ Configuración (Modem, Puertos Serie, Permisos)
- 🔧 Mantenimiento y Recuperación

### Comandos manuales

```bash
bash scripts/status.sh                   # Estado completo del sistema
sudo journalctl -u fpvcopilot-sky -f     # Logs en tiempo real
sudo systemctl restart fpvcopilot-sky    # Reiniciar servicio
bash scripts/deploy.sh                   # Compilar frontend + reiniciar
bash scripts/dev.sh                      # Desarrollo con hot-reload
bash scripts/configure-modem.sh          # Configurar modem USB 4G
```

### Endpoints útiles

```bash
curl http://localhost:8000/api/status/health               # Health check
curl http://localhost:8000/api/mavlink/status               # Estado MAVLink
curl http://localhost:8000/api/video/status                 # Estado video
curl http://localhost:8000/api/vpn/status                   # Estado VPN
curl http://localhost:8000/api/network/modem/status         # Estado modem (legacy)
curl http://localhost:8000/api/network/modems               # Pool multi-modem
curl http://localhost:8000/api/network/policy-routing/status # Policy routing
curl http://localhost:8000/api/network/vpn-health/status    # VPN health checker
```

---

[← Volver al README](../README.md)
