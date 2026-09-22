# 🧪 Testing, Coverage & CI

## Cómo ejecutar

```bash
# Backend (desde la raíz, con el venv activado)
source venv/bin/activate
pytest                              # todo (con cobertura, gate 50%)
pytest -m "not slow"                # suite rápida (la que corre CI en el job principal)
pytest -m "slow"                    # suites de timing/e2e (job no bloqueante)
pytest tests/test_foo.py -v         # un fichero

# Frontend (frontend/client)
npm run test                        # vitest
npm run test:coverage               # vitest + cobertura (umbrales)
npm run lint                        # eslint --max-warnings 0
```

## Marcadores

| Marcador      | Uso                                                                                                                                                                                                            |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `slow`        | Suites de rendimiento/timing y e2e (ver `test_performance_profiling.py`, `test_e2e_workflows.py`, `test_e2e_degraded_workflows.py`). Son flaky por naturaleza: corren en el job `test-slow` **no bloqueante**. |
| `e2e`         | Flujos end-to-end.                                                                                                                                                                                             |
| `integration` | Requieren servicios/infra reales.                                                                                                                                                                              |
| `contract`    | Conformidad de proveedores (`tests/test_provider_contracts.py`).                                                                                                                                               |

El job principal de CI ejecuta `pytest tests/ -m "not slow"` con el **gate de cobertura**; `test-slow` ejecuta `-m "slow"` con `continue-on-error: true`.

## Cobertura

- **Backend**: `fail_under = 50` (`pyproject.toml`). Actual ≈ 52 %.
- **Frontend**: umbrales en `frontend/client/vitest.config.js` (40/70/49/40). Actual ≈ 41.3/74.4/51.7/41.3.

### Alcance medido y módulos excluidos

`pyproject.toml` **excluye del denominador** los módulos acoplados a hardware/proceso, que no son testeables en CI (sin GStreamer, sin serial, sin red real):

- `app/providers/*` (modem, VPN, interfaces de red, encoders y fuentes de vídeo)
- `app/services/gstreamer_service.py`
- `app/services/mavlink_bridge.py`

**Por qué**: dependen de hardware (Rockchip MPP, cámaras V4L2/libcamera, modem USB, puerto serie) o de procesos externos, por lo que un test unitario solo podría mockear el 100 % del comportamiento — dando una cobertura ficticia.

**Cómo se mitiga el riesgo**:

1. **Tests de contrato de proveedores** (`tests/test_provider_contracts.py`, matrix en CI): verifican que cada proveedor cumple su ABC (firmas, formas de retorno).
2. **Extracción de lógica pura a helpers testeables**: `app/services/gstreamer_helpers.py` (`format_uptime`, `calculate_health`) y el propio `mavlink_router`/`network_event_bridge` (ya en cobertura).
3. **Validación en el equipo**: la suite `deploy.sh` + `preflight-check.sh` + `status.sh`, y las validaciones manuales documentadas en los runbooks.

> Los módulos excluidos representan el mayor riesgo no cubierto y se recomienda, a futuro, extraer más lógica pura (construcción de pipelines, framing MAVLink) para poder testearla.

## Pendiente (documentado, no bloqueante)

- **Integración real** con contenedores (red/GStreamer/serial): pendiente; hoy la degradación se simula en los e2e.
- **mypy**: corre en CI pero `continue-on-error` (~190 errores preexistentes). Ver `AGENTS.md`.
- **Escaneos de seguridad** (Trivy/Safety/`npm audit`): no bloqueantes por ahora.
