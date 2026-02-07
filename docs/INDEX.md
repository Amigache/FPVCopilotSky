# 📑 FPV Copilot Sky — Wiki

Bienvenido a la documentación de **FPV Copilot Sky**. Aquí encontrarás todo lo necesario para instalar, usar y contribuir al proyecto.

---

## Guías

| # | Documento | Descripción | Audiencia |
|---|-----------|-------------|-----------|
| 1 | [📥 Guía de Instalación](INSTALLATION.md) | Requisitos, instalación paso a paso, configuración de producción, verificación | Todos |
| 2 | [📖 Guía de Usuario](USER_GUIDE.md) | Uso de la WebUI, cada pestaña explicada, configuración de video/telemetría/VPN/modem, solución de problemas | Pilotos / Usuarios |
| 3 | [🛠️ Guía de Desarrollo](DEVELOPER_GUIDE.md) | Arquitectura, stack tecnológico, estructura del proyecto, cómo añadir proveedores, convenciones de código | Desarrolladores |

---

## Referencia rápida

### Comandos habituales

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
curl http://localhost:8000/api/status/health        # Health check
curl http://localhost:8000/api/mavlink/status        # Estado MAVLink
curl http://localhost:8000/api/video/status          # Estado video
curl http://localhost:8000/api/vpn/status            # Estado VPN
curl http://localhost:8000/api/network/modem/status  # Estado modem
```

---

[← Volver al README](../README.md)
