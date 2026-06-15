#!/usr/bin/env bash
set -euo pipefail

# FPVCopilotSky - Baseline collection script
# Collects endpoint latency statistics (p50/p95), status codes, and system snapshot.
#
# Usage:
#   bash scripts/collect-baseline.sh
#   BASE_URL=http://localhost:8000 SAMPLES=20 bash scripts/collect-baseline.sh
#
# Environment variables:
#   BASE_URL       API base URL (default: http://localhost:8000)
#   SAMPLES        Number of samples per endpoint (default: 15)
#   OUT_DIR        Output directory (default: docs/baselines)
#   ENDPOINTS      Space-separated endpoint list (optional override)

BASE_URL="${BASE_URL:-http://localhost:8000}"
SAMPLES="${SAMPLES:-15}"
OUT_DIR="${OUT_DIR:-docs/baselines}"

DEFAULT_ENDPOINTS=(
  "/api/status/health"
  "/api/system/status"
  "/api/network/status"
  "/api/video/config"
  "/api/vpn/status"
)

if [[ -n "${ENDPOINTS:-}" ]]; then
  # shellcheck disable=SC2206
  TARGET_ENDPOINTS=(${ENDPOINTS})
else
  TARGET_ENDPOINTS=("${DEFAULT_ENDPOINTS[@]}")
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "ERROR: curl is required"
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required"
  exit 1
fi

mkdir -p "$OUT_DIR"

TS="$(date +%Y%m%d-%H%M%S)"
JSON_OUT="$OUT_DIR/baseline-${TS}.json"
MD_OUT="$OUT_DIR/baseline-${TS}.md"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

SYSTEM_CPU_MODEL="$(grep -m1 'model name\|Hardware' /proc/cpuinfo 2>/dev/null | sed 's/^[^:]*: *//' || echo unknown)"
SYSTEM_KERNEL="$(uname -r 2>/dev/null || echo unknown)"
SYSTEM_HOSTNAME="$(hostname 2>/dev/null || echo unknown)"
LOADAVG="$(cat /proc/loadavg 2>/dev/null || echo unknown)"
MEMORY_LINE="$(free -m 2>/dev/null | awk 'NR==2 {print $2"MB_total,"$3"MB_used,"$4"MB_free"}' || echo unknown)"
DISK_LINE="$(df -h / 2>/dev/null | awk 'NR==2 {print $2" total, "$3" used, "$4" avail"}' || echo unknown)"

UVICORN_PIDS="$(pgrep -f 'uvicorn app.main:app|uvicorn main:app|fpvcopilot-sky' || true)"
UVICORN_SNAPSHOT="[]"
if [[ -n "$UVICORN_PIDS" ]]; then
  UVICORN_SNAPSHOT="$(echo "$UVICORN_PIDS" | xargs -I{} ps -p {} -o pid=,%cpu=,%mem=,rss=,etime= | awk '{printf "{\"pid\":%s,\"cpu_percent\":%s,\"mem_percent\":%s,\"rss_kb\":%s,\"etime\":\"%s\"}\n", $1, $2, $3, $4, $5}' | python3 -c 'import json,sys; rows=[json.loads(l) for l in sys.stdin if l.strip()]; print(json.dumps(rows))')"
fi

{
  echo "{"
  echo "  \"metadata\": {"
  echo "    \"timestamp\": \"$(date -Iseconds)\","
  echo "    \"base_url\": \"$BASE_URL\","
  echo "    \"samples_per_endpoint\": $SAMPLES"
  echo "  },"
  echo "  \"system\": {"
  echo "    \"hostname\": \"$SYSTEM_HOSTNAME\","
  echo "    \"kernel\": \"$SYSTEM_KERNEL\","
  echo "    \"cpu_model\": \"$SYSTEM_CPU_MODEL\","
  echo "    \"loadavg\": \"$LOADAVG\","
  echo "    \"memory\": \"$MEMORY_LINE\","
  echo "    \"disk_root\": \"$DISK_LINE\","
  echo "    \"app_processes\": $UVICORN_SNAPSHOT"
  echo "  },"
  echo "  \"endpoints\": ["
} > "$JSON_OUT"

FIRST=1
for endpoint in "${TARGET_ENDPOINTS[@]}"; do
  sample_file="$TMP_DIR/${endpoint//\//_}.txt"
  : > "$sample_file"

  success_count=0
  failure_count=0

  for _ in $(seq 1 "$SAMPLES"); do
    raw="$(curl -sS -o /dev/null -w '%{http_code} %{time_total}' "$BASE_URL$endpoint" || echo '000 0')"
    code="$(echo "$raw" | awk '{print $1}')"
    sec="$(echo "$raw" | awk '{print $2}')"

    # Convert seconds to milliseconds with python for consistent decimals
    ms="$(python3 - <<PY
sec = float("$sec") if "$sec" else 0.0
print(f"{sec * 1000:.3f}")
PY
)"

    echo "$code $ms" >> "$sample_file"

    if [[ "$code" =~ ^[2345][0-9][0-9]$ && "$code" != "000" ]]; then
      success_count=$((success_count + 1))
    else
      failure_count=$((failure_count + 1))
    fi
  done

  stats_json="$(python3 - <<PY
import json
from statistics import mean

vals = []
codes = {}
for line in open("$sample_file", "r", encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    code_s, ms_s = line.split()
    code = int(code_s)
    ms = float(ms_s)
    vals.append(ms)
    codes[code] = codes.get(code, 0) + 1

vals_sorted = sorted(vals)
if not vals_sorted:
    out = {
        "count": 0,
        "min_ms": 0,
        "p50_ms": 0,
        "p95_ms": 0,
        "max_ms": 0,
        "mean_ms": 0,
        "status_codes": codes,
    }
else:
    def perc(p: float) -> float:
        idx = int((len(vals_sorted) - 1) * p)
        return vals_sorted[idx]

    out = {
        "count": len(vals_sorted),
        "min_ms": round(vals_sorted[0], 3),
        "p50_ms": round(perc(0.50), 3),
        "p95_ms": round(perc(0.95), 3),
        "max_ms": round(vals_sorted[-1], 3),
        "mean_ms": round(mean(vals_sorted), 3),
        "status_codes": {str(k): v for k, v in sorted(codes.items())},
    }

print(json.dumps(out))
PY
)"

  if [[ $FIRST -eq 0 ]]; then
    echo "    ," >> "$JSON_OUT"
  fi
  FIRST=0

  echo "    {" >> "$JSON_OUT"
  echo "      \"endpoint\": \"$endpoint\"," >> "$JSON_OUT"
  echo "      \"success_count\": $success_count," >> "$JSON_OUT"
  echo "      \"failure_count\": $failure_count," >> "$JSON_OUT"
  echo "      \"stats\": $stats_json" >> "$JSON_OUT"
  echo "    }" >> "$JSON_OUT"
done

{
  echo "  ]"
  echo "}"
} >> "$JSON_OUT"

python3 - <<PY
import json
from datetime import datetime

json_file = "$JSON_OUT"
md_file = "$MD_OUT"

with open(json_file, "r", encoding="utf-8") as f:
    data = json.load(f)

lines = []
lines.append("# Baseline Run")
lines.append("")
lines.append(f"- Timestamp: {data['metadata']['timestamp']}")
lines.append(f"- Base URL: {data['metadata']['base_url']}")
lines.append(f"- Samples per endpoint: {data['metadata']['samples_per_endpoint']}")
lines.append("")
lines.append("## System Snapshot")
lines.append("")
sys = data["system"]
lines.append(f"- Hostname: {sys['hostname']}")
lines.append(f"- Kernel: {sys['kernel']}")
lines.append(f"- CPU: {sys['cpu_model']}")
lines.append(f"- Loadavg: {sys['loadavg']}")
lines.append(f"- Memory: {sys['memory']}")
lines.append(f"- Disk (/): {sys['disk_root']}")
lines.append("")
lines.append("## Endpoint Latency")
lines.append("")
lines.append("| Endpoint | Count | p50 (ms) | p95 (ms) | Mean (ms) | Max (ms) | Failures |")
lines.append("|---|---:|---:|---:|---:|---:|---:|")
for ep in data["endpoints"]:
    s = ep["stats"]
    lines.append(
        f"| {ep['endpoint']} | {s['count']} | {s['p50_ms']:.3f} | {s['p95_ms']:.3f} | {s['mean_ms']:.3f} | {s['max_ms']:.3f} | {ep['failure_count']} |"
    )

lines.append("")
lines.append("## Weekly Comparison Template")
lines.append("")
lines.append("| Week | Date | p95 /api/status/health | p95 /api/network/status | CPU idle (%) | Memory used (MB) | Notes |")
lines.append("|---|---|---:|---:|---:|---:|---|")
lines.append("| W1 | | | | | | |")
lines.append("| W2 | | | | | | |")
lines.append("| W3 | | | | | | |")
lines.append("| W4 | | | | | | |")

with open(md_file, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
PY

echo "Baseline JSON: $JSON_OUT"
echo "Baseline Markdown: $MD_OUT"
echo "Done."
