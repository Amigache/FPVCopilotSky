# E2E Degraded Workflows

This document defines the reproducible E2E degraded-workflow process for Issue #37.

## Goal

Validate critical reliability workflows under degraded conditions:

- Auto-reconnect behavior for VPN connect workflow
- Network failover behavior under route update timeouts
- Stream recovery after transient start failures
- Recovery after temporary connectivity loss in network status path

## Reproducible Suite

Run:

```bash
bash scripts/run-e2e-degraded.sh
```

Defaults:

- `OUT_DIR=docs/baselines`
- Suite: `tests/test_e2e_degraded_workflows.py`

## Produced Outputs

For each run:

- `docs/baselines/e2e-degraded-YYYYMMDD-HHMMSS.xml` (JUnit)
- `docs/baselines/e2e-degraded-YYYYMMDD-HHMMSS.json`
- `docs/baselines/e2e-degraded-YYYYMMDD-HHMMSS.md`

The JSON and Markdown reports include:

- Success rate across degradation scenarios
- Recovery timing summary (`p50`, `p95`, mean, max)
- Per-scenario table with attempts to recover and recovery time
- Weekly comparison template

## Acceptance Mapping (Issue #37)

- Reproducible E2E suite: `tests/test_e2e_degraded_workflows.py`
- Success-rate and recovery-time report: `scripts/run-e2e-degraded.sh` outputs
- Minimum 3 degradation scenarios: suite includes 4 scenarios
