# Performance Baseline Procedure

This document defines the reproducible baseline process for Issue #27.

## Goal

Collect a weekly, comparable snapshot of:

- API endpoint latency (p50, p95)
- Request success/failure counts
- Host and process context (kernel, loadavg, memory, disk, app process snapshot)

## Script

Use:

```bash
bash scripts/collect-baseline.sh
```

Defaults:

- BASE_URL: `http://localhost:8000`
- SAMPLES: `15` requests per endpoint
- OUT_DIR: `docs/baselines`

Optional custom run:

```bash
BASE_URL=http://localhost:8000 \
SAMPLES=25 \
ENDPOINTS="/api/status/health /api/network/status /api/video/config" \
bash scripts/collect-baseline.sh
```

## Output Files

For each run, the script generates:

- `docs/baselines/baseline-YYYYMMDD-HHMMSS.json`
- `docs/baselines/baseline-YYYYMMDD-HHMMSS.md`

JSON includes machine-readable metrics. Markdown includes a human summary and a weekly comparison table template.

## Weekly Execution Standard

1. Run baseline under similar conditions each week.
2. Keep the same endpoint set for trend comparability.
3. Record contextual notes (service restarts, network conditions, active stream mode).
4. Compare p95 and failure counts against previous week.

## Suggested KPI Tracking

Track at minimum:

- `p95 /api/status/health`
- `p95 /api/network/status`
- Failure count per endpoint
- Host memory used and loadavg

## Acceptance Mapping (Issue #27)

- Baseline v1 with p50/p95 metrics: provided by generated JSON/MD reports
- Repeatable script/procedure: `scripts/collect-baseline.sh` + this document
- Weekly comparison table template: embedded in generated Markdown report
