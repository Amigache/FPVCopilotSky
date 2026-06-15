# GitHub Issues Pack - 30D Reliability and Efficiency

This document contains the Epic and 13 issues for the 30-day technical hardening plan.
Use `scripts/create_github_issues_30d.sh` to create all items automatically.

## Epic

Title: Robustez y Eficiencia 30D para FPVCopilotSky
Labels: epic, reliability, performance, quality

Goal:

- Improve in-flight stability and post-flight reliability
- Reduce CPU/memory overhead on SBC hardware
- Increase observability and diagnosability
- Raise quality gates in CI

Target KPIs:

- Backend coverage >= 50%
- Crash-free runtime >= 99.5%
- Backend CPU idle with open UI: -20%
- Broadcast loop p95 <= 120ms
- MTTR diagnosis: -40%

## Issues

### 01 - Baseline de rendimiento y fiabilidad en hardware objetivo

Labels: p0, performance, reliability, observability
Estimate: 5

Scope:

- Capture baseline for CPU, RAM, endpoint latency, and broadcast timings
- Define repeatable measurement method

Acceptance criteria:

- Baseline v1 document with p50/p95 metrics
- Repeatable script/procedure
- Weekly comparison table template

### 02 - Migrar prints criticos a logging estructurado

Labels: p0, reliability, observability, backend
Estimate: 8

Scope:

- Replace critical prints in core services with structured logger
- Standardize fields and levels

Acceptance criteria:

- No prints in prioritized core services
- Logs include operation, duration_ms, outcome, error_type
- Compatible with journalctl output flow

### 03 - Reducir manejo de errores genericos en rutas criticas

Labels: p0, reliability, backend, tech-debt
Estimate: 8

Scope:

- Replace broad exception captures with specific exceptions in network/video/modem/vpn routes
- Improve error messages for diagnosis

Acceptance criteria:

- Critical routes return typed/coherent errors
- Root-cause traceability maintained
- Error-path tests updated

### 04 - Optimizar loop periodico de broadcast WebSocket

Labels: p1, performance, websocket, backend
Estimate: 5

Scope:

- Reduce expensive periodic work
- Avoid unnecessary recomputation and heavy calls

Acceptance criteria:

- Measurable CPU reduction while UI is connected
- No dashboard functional regressions
- Loop timing metrics available

### 05 - Unificar ejecucion de comandos de sistema con timeout y retry policy

Labels: p1, reliability, performance, backend
Estimate: 8

Scope:

- Create shared sync/async command execution layer with timeout/retry/backoff and logging
- Migrate critical network/modem/vpn paths

Acceptance criteria:

- Critical modules migrated to shared helper
- Timeout/retry policy documented
- Fewer intermittent/blocking failures in tests

### 06 - Refactor fase 1 del servicio de video para reducir complejidad

Labels: p1, refactor, video, backend
Estimate: 13

Scope:

- Split video service responsibilities into internal modules
- Preserve public API behavior

Acceptance criteria:

- Reduced complexity and file size
- Existing behavior unchanged in tests
- New tests for extracted components

### 07 - Refactor de startup y ciclo de vida de aplicacion

Labels: p1, refactor, backend, reliability
Estimate: 8

Scope:

- Separate provider init, optional services init, and background tasks
- Improve startup/shutdown sequence reliability

Acceptance criteria:

- Startup code organized by domain
- Startup time does not regress
- Clean shutdown validated by tests

### 08 - Aumentar cobertura backend a 35% en dominios criticos

Labels: p0, testing, quality, backend
Estimate: 8

Scope:

- Add tests for high-risk routes/services
- Prioritize network, video, startup, failover

Acceptance criteria:

- Global backend coverage >= 35%
- New degraded/error path tests
- CI stable

### 09 - Implementar tests de contrato para providers

Labels: p1, testing, architecture, providers
Estimate: 8

Scope:

- Define and implement conformance suite for modem, vpn, video source, encoder providers

Acceptance criteria:

- Contract matrix defined and running in CI
- At least one provider per type validated
- Contract failures block merge

### 10 - Endurecer seguridad de CORS y configuracion por entorno

Labels: p1, security, backend, ops
Estimate: 3

Scope:

- Replace permissive CORS with env-configurable allowlist
- Different defaults for dev and production

Acceptance criteria:

- CORS configured via env vars
- Safe production defaults
- Deployment docs updated

### 11 - Suite E2E de workflows de vuelo con red degradada

Labels: p1, testing, e2e, reliability
Estimate: 8

Scope:

- Validate auto-connect, failover, stream recovery, reconnection
- Simulate connectivity loss and timeout scenarios

Acceptance criteria:

- Reproducible E2E suite for critical scenarios
- Success rate and recovery-time report
- At least 3 degradation scenarios covered

### 12 - Gate de calidad progresivo en CI hasta cobertura 50%

Labels: p0, ci, quality, testing
Estimate: 5

Scope:

- Gradually raise coverage fail-under
- Enforce required lint/test checks

Acceptance criteria:

- Coverage gate rollout plan applied
- Branch protections with required checks
- End-of-cycle minimum coverage >= 50%

### 13 - Runbooks operativos para incidencias criticas

Labels: p2, docs, ops, reliability
Estimate: 3

Scope:

- Create runbooks for MAVLink down, modem instability, stream drop
- Include diagnosis and rollback steps

Acceptance criteria:

- 3 complete runbooks published
- Incident simulation validated
- Improved diagnosis time in internal drills
