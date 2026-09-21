#!/usr/bin/env bash
set -euo pipefail

# Bulk-create Epic + 13 issues in GitHub using REST API.
# Requirements:
#   - GITHUB_TOKEN with repo scope
#   - Optional: GITHUB_OWNER, GITHUB_REPO (defaults from git remote)
#
# Usage:
#   export GITHUB_TOKEN=ghp_xxx
#   bash scripts/create_github_issues_30d.sh

if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "ERROR: GITHUB_TOKEN is not set"
  exit 1
fi

# Detect owner/repo from git remote if not provided.
if [[ -z "${GITHUB_OWNER:-}" || -z "${GITHUB_REPO:-}" ]]; then
  remote_url="$(git remote get-url origin)"
  # Supports https://github.com/owner/repo(.git)
  if [[ "$remote_url" =~ github.com[:/]+([^/]+)/([^/.]+)(\.git)?$ ]]; then
    GITHUB_OWNER="${GITHUB_OWNER:-${BASH_REMATCH[1]}}"
    GITHUB_REPO="${GITHUB_REPO:-${BASH_REMATCH[2]}}"
  else
    echo "ERROR: Could not parse GitHub owner/repo from origin URL: $remote_url"
    echo "Set GITHUB_OWNER and GITHUB_REPO manually."
    exit 1
  fi
fi

API_BASE="https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}"

create_label() {
  local name="$1"
  local color="$2"
  local description="$3"

  local payload
  payload=$(cat <<JSON
{"name":"$name","color":"$color","description":"$description"}
JSON
)

  # 201 Created or 422 Unprocessable Entity (already exists)
  status=$(curl -sS -o /tmp/label_resp.json -w "%{http_code}" \
    -X POST \
    -H "Accept: application/vnd.github+json" \
    -H "Authorization: Bearer ${GITHUB_TOKEN}" \
    "$API_BASE/labels" \
    -d "$payload")

  if [[ "$status" != "201" && "$status" != "422" ]]; then
    echo "ERROR creating label $name (HTTP $status)"
    cat /tmp/label_resp.json
    exit 1
  fi
}

create_issue() {
  local title="$1"
  local labels_csv="$2"
  local body="$3"

  local labels_json="[]"
  IFS=',' read -r -a labels <<< "$labels_csv"
  if [[ ${#labels[@]} -gt 0 ]]; then
    labels_json="["
    for i in "${!labels[@]}"; do
      lbl="${labels[$i]}"
      lbl="${lbl## }"
      lbl="${lbl%% }"
      if [[ $i -gt 0 ]]; then
        labels_json+=","
      fi
      labels_json+="\"$lbl\""
    done
    labels_json+="]"
  fi

  local body_escaped
  body_escaped=$(printf '%s' "$body" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')

  local payload
  payload="{\"title\":\"$title\",\"body\":$body_escaped,\"labels\":$labels_json}"

  status=$(curl -sS -o /tmp/issue_resp.json -w "%{http_code}" \
    -X POST \
    -H "Accept: application/vnd.github+json" \
    -H "Authorization: Bearer ${GITHUB_TOKEN}" \
    "$API_BASE/issues" \
    -d "$payload")

  if [[ "$status" != "201" ]]; then
    echo "ERROR creating issue: $title (HTTP $status)"
    cat /tmp/issue_resp.json
    exit 1
  fi

  issue_url=$(python3 - <<'PY'
import json
with open('/tmp/issue_resp.json','r',encoding='utf-8') as f:
    data=json.load(f)
print(data.get('html_url',''))
PY
)
  echo "CREATED: $issue_url"
}

echo "Creating labels in ${GITHUB_OWNER}/${GITHUB_REPO}..."
create_label "epic" "5319e7" "Epic-level tracking issue"
create_label "p0" "b60205" "Highest priority"
create_label "p1" "d93f0b" "High priority"
create_label "p2" "fbca04" "Medium priority"
create_label "reliability" "1d76db" "Stability and resilience"
create_label "performance" "0e8a16" "Performance optimization"
create_label "quality" "0052cc" "Testing and quality gates"
create_label "observability" "5319e7" "Logging and diagnostics"
create_label "backend" "0366d6" "Backend changes"
create_label "websocket" "6f42c1" "WebSocket and realtime"
create_label "tech-debt" "c2e0c6" "Technical debt reduction"
create_label "refactor" "bfd4f2" "Codebase refactor"
create_label "video" "a2eeef" "Video pipeline"
create_label "testing" "f9d0c4" "Automated testing"
create_label "architecture" "7057ff" "Architecture and design"
create_label "providers" "c5def5" "Provider system"
create_label "security" "e99695" "Security hardening"
create_label "ops" "fef2c0" "Operations and deployment"
create_label "e2e" "bfdadc" "End-to-end workflows"
create_label "ci" "cfd3d7" "CI pipeline"
create_label "docs" "0075ca" "Documentation"

echo "Creating Epic and issues..."

create_issue \
  "Robustez y Eficiencia 30D para FPVCopilotSky" \
  "epic,reliability,performance,quality" \
  "## Objetivo\n\nMejorar estabilidad en vuelo, eficiencia en SBC, observabilidad y gates de calidad.\n\n## KPIs de salida\n\n- Cobertura backend >= 50%\n- Crash-free runtime >= 99.5%\n- CPU backend en idle con UI abierta: -20%\n- p95 loop de broadcast <= 120ms\n- MTTR diagnostico: -40%\n\n## Alcance\n\nBackend FastAPI, servicios de video/red, testing, hardening operativo."

create_issue \
  "Baseline de rendimiento y fiabilidad en hardware objetivo" \
  "p0,performance,reliability,observability" \
  "## Estimacion\n5 puntos\n\n## Scope\n- Capturar baseline de CPU, RAM, latencia de endpoints criticos y tiempos de broadcast\n- Definir metodologia reproducible\n\n## Acceptance Criteria\n- Baseline v1 con metricas p50/p95\n- Script/procedimiento reproducible\n- Tabla de comparacion semanal"

create_issue \
  "Migrar prints criticos a logging estructurado" \
  "p0,reliability,observability,backend" \
  "## Estimacion\n8 puntos\n\n## Scope\n- Reemplazar prints en servicios core por logger estructurado\n- Estandarizar formato y niveles\n\n## Acceptance Criteria\n- 0 prints en servicios core priorizados\n- Campos: operation, duration_ms, outcome, error_type\n- Compatible con journalctl"

create_issue \
  "Reducir manejo de errores genericos en rutas criticas" \
  "p0,reliability,backend,tech-debt" \
  "## Estimacion\n8 puntos\n\n## Scope\n- Reemplazar capturas amplias por excepciones especificas en network/video/modem/vpn\n- Mejorar mensajes de error\n\n## Acceptance Criteria\n- Errores tipados y coherentes en rutas criticas\n- Trazabilidad de causa raiz\n- Tests de error actualizados"

create_issue \
  "Optimizar loop periodico de broadcast WebSocket" \
  "p1,performance,websocket,backend" \
  "## Estimacion\n5 puntos\n\n## Scope\n- Reducir trabajo periodico caro\n- Evitar recomputaciones y llamadas pesadas innecesarias\n\n## Acceptance Criteria\n- Reduccion medible de CPU con UI conectada\n- Sin regresiones funcionales\n- Metricas de tiempos del loop"

create_issue \
  "Unificar ejecucion de comandos de sistema con timeout y retry policy" \
  "p1,reliability,performance,backend" \
  "## Estimacion\n8 puntos\n\n## Scope\n- Crear capa comun sync/async con timeout/retry/backoff y logging\n- Migrar rutas criticas de network/modem/vpn\n\n## Acceptance Criteria\n- Modulos criticos migrados\n- Politica documentada\n- Menos fallos intermitentes/bloqueos"

create_issue \
  "Refactor fase 1 del servicio de video para reducir complejidad" \
  "p1,refactor,video,backend" \
  "## Estimacion\n13 puntos\n\n## Scope\n- Separar responsabilidades del servicio de video\n- Mantener API publica\n\n## Acceptance Criteria\n- Menor complejidad y tamano por archivo\n- Sin cambios de comportamiento\n- Nuevos tests de componentes extraidos"

create_issue \
  "Refactor de startup y ciclo de vida de aplicacion" \
  "p1,refactor,backend,reliability" \
  "## Estimacion\n8 puntos\n\n## Scope\n- Separar inicializacion de providers/servicios opcionales/tareas background\n- Mejorar secuencia startup/shutdown\n\n## Acceptance Criteria\n- Startup organizado por dominios\n- Sin regresion de tiempo de arranque\n- Shutdown limpio validado por tests"

create_issue \
  "Aumentar cobertura backend a 35% en dominios criticos" \
  "p0,testing,quality,backend" \
  "## Estimacion\n8 puntos\n\n## Scope\n- Agregar tests en rutas/servicios de alto riesgo\n- Priorizar network, video, startup, failover\n\n## Acceptance Criteria\n- Cobertura global backend >= 35%\n- Tests de degradacion/error\n- CI estable"

create_issue \
  "Implementar tests de contrato para providers" \
  "p1,testing,architecture,providers" \
  "## Estimacion\n8 puntos\n\n## Scope\n- Definir suite de conformidad para modem/vpn/video source/encoder\n\n## Acceptance Criteria\n- Matriz de contrato en CI\n- Al menos 1 provider por tipo cubierto\n- Fallos de contrato bloquean merge"

create_issue \
  "Endurecer seguridad de CORS y configuracion por entorno" \
  "p1,security,backend,ops" \
  "## Estimacion\n3 puntos\n\n## Scope\n- Reemplazar CORS permisivo por allowlist configurable\n- Diferenciar defaults de dev/prod\n\n## Acceptance Criteria\n- CORS por variables de entorno\n- Defaults seguros en produccion\n- Documentacion de despliegue actualizada"

create_issue \
  "Suite E2E de workflows de vuelo con red degradada" \
  "p1,testing,e2e,reliability" \
  "## Estimacion\n8 puntos\n\n## Scope\n- Validar auto-connect, failover, recovery de stream, reconexion\n- Simular perdida de conectividad y timeouts\n\n## Acceptance Criteria\n- Suite E2E reproducible\n- Reporte de tasa de exito y tiempos de recuperacion\n- Minimo 3 escenarios de degradacion"

create_issue \
  "Gate de calidad progresivo en CI hasta cobertura 50%" \
  "p0,ci,quality,testing" \
  "## Estimacion\n5 puntos\n\n## Scope\n- Subir gradualmente fail-under de cobertura\n- Endurecer checks obligatorios de lint/test\n\n## Acceptance Criteria\n- Plan escalonado aplicado\n- Branch protection con checks obligatorios\n- Cobertura minima final >= 50%"

create_issue \
  "Runbooks operativos para incidencias criticas" \
  "p2,docs,ops,reliability" \
  "## Estimacion\n3 puntos\n\n## Scope\n- Crear runbooks para MAVLink down, modem inestable, stream caido\n- Incluir diagnostico y rollback\n\n## Acceptance Criteria\n- 3 runbooks completos publicados\n- Simulacion de incidente validada\n- Mejora de tiempo de diagnostico en drills"

echo "Done. Epic + 13 issues created in ${GITHUB_OWNER}/${GITHUB_REPO}."
