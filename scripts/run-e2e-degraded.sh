#!/usr/bin/env bash
set -euo pipefail

# Reproducible degraded E2E runner for Issue #37.
# Generates:
# - JUnit XML with per-scenario properties
# - JSON summary with success rate and recovery-time percentiles
# - Markdown report with scenario table

OUT_DIR="${OUT_DIR:-docs/baselines}"
PYTEST_BIN="${PYTEST_BIN:-python3 -m pytest}"
SUITE_PATH="${SUITE_PATH:-tests/test_e2e_degraded_workflows.py}"

mkdir -p "$OUT_DIR"

TS="$(date +%Y%m%d-%H%M%S)"
JUNIT_OUT="$OUT_DIR/e2e-degraded-${TS}.xml"
JSON_OUT="$OUT_DIR/e2e-degraded-${TS}.json"
MD_OUT="$OUT_DIR/e2e-degraded-${TS}.md"

echo "Running degraded E2E suite: $SUITE_PATH"
# shellcheck disable=SC2086
$PYTEST_BIN "$SUITE_PATH" -q --no-cov -o junit_family=legacy --junitxml "$JUNIT_OUT"

python3 - <<PY
import json
import statistics
import xml.etree.ElementTree as ET
from datetime import datetime

junit_file = "$JUNIT_OUT"
json_out = "$JSON_OUT"
md_out = "$MD_OUT"

tree = ET.parse(junit_file)
root = tree.getroot()

scenarios = []
for testcase in root.findall(".//testcase"):
    props = {p.get("name"): p.get("value") for p in testcase.findall("./properties/property")}
    scenario_name = props.get("scenario")
    if not scenario_name:
        continue

    failed = testcase.find("failure") is not None or testcase.find("error") is not None
    skipped = testcase.find("skipped") is not None
    success = (not failed) and (not skipped)

    recovery_ms = float(props.get("recovery_ms", "0") or 0.0)
    attempts = int(float(props.get("attempts_to_recover", "0") or 0))
    degradation_type = props.get("degradation_type", "unknown")

    scenarios.append(
        {
            "scenario": scenario_name,
            "degradation_type": degradation_type,
            "success": success,
            "attempts_to_recover": attempts,
            "recovery_ms": round(recovery_ms, 3),
        }
    )

total = len(scenarios)
passed = sum(1 for s in scenarios if s["success"])
success_rate = (passed / total * 100.0) if total else 0.0

recovery_values = sorted([s["recovery_ms"] for s in scenarios if s["success"]])

def pct(values, p):
    if not values:
        return 0.0
    idx = int((len(values) - 1) * p)
    return float(values[idx])

summary = {
    "generated_at": datetime.now().isoformat(),
    "suite": "tests/test_e2e_degraded_workflows.py",
    "total_scenarios": total,
    "passed_scenarios": passed,
    "success_rate_pct": round(success_rate, 2),
    "recovery_time_ms": {
        "p50": round(pct(recovery_values, 0.50), 3),
        "p95": round(pct(recovery_values, 0.95), 3),
        "mean": round(statistics.mean(recovery_values), 3) if recovery_values else 0.0,
        "max": round(max(recovery_values), 3) if recovery_values else 0.0,
    },
    "scenarios": scenarios,
}

with open(json_out, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2)

lines = []
lines.append("# E2E Degraded Workflow Report")
lines.append("")
lines.append(f"- Generated: {summary['generated_at']}")
lines.append(f"- Suite: {summary['suite']}")
lines.append(f"- Total scenarios: {summary['total_scenarios']}")
lines.append(f"- Passed scenarios: {summary['passed_scenarios']}")
lines.append(f"- Success rate: {summary['success_rate_pct']:.2f}%")
lines.append("")
lines.append("## Recovery Time Summary")
lines.append("")
lines.append(f"- p50: {summary['recovery_time_ms']['p50']:.3f} ms")
lines.append(f"- p95: {summary['recovery_time_ms']['p95']:.3f} ms")
lines.append(f"- Mean: {summary['recovery_time_ms']['mean']:.3f} ms")
lines.append(f"- Max: {summary['recovery_time_ms']['max']:.3f} ms")
lines.append("")
lines.append("## Scenario Results")
lines.append("")
lines.append("| Scenario | Degradation Type | Success | Attempts | Recovery (ms) |")
lines.append("|---|---|---:|---:|---:|")
for s in scenarios:
    lines.append(
        f"| {s['scenario']} | {s['degradation_type']} | {str(s['success']).lower()} | {s['attempts_to_recover']} | {s['recovery_ms']:.3f} |"
    )

lines.append("")
lines.append("## Weekly Comparison Template")
lines.append("")
lines.append("| Week | Date | Success Rate (%) | Recovery p50 (ms) | Recovery p95 (ms) | Notes |")
lines.append("|---|---|---:|---:|---:|---|")
lines.append("| W1 | | | | | |")
lines.append("| W2 | | | | | |")
lines.append("| W3 | | | | | |")
lines.append("| W4 | | | | | |")

with open(md_out, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print(f"Report JSON: {json_out}")
print(f"Report Markdown: {md_out}")
PY

echo "JUnit XML: $JUNIT_OUT"
echo "Done."
