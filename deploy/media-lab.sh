#!/usr/bin/env bash
set -euo pipefail
ROOT="${MEDIA_LAB_ROOT:-$HOME/media-lab}"
ENV_FILE="$ROOT/deploy/.web.env"
COMPOSE=(docker compose --env-file "$ENV_FILE" -f "$ROOT/deploy/compose.yml" -f "$ROOT/deploy/compose.web.yml")
[[ -f "$ENV_FILE" ]] || { echo '[BLOCKED] Configure .web.env privately first.' >&2; exit 2; }
idle() {
  local name_port name port count
  # A worker whose container is stopped on purpose (e.g. its GPU is lent out) has no queue to check.
  for name_port in media-lab-comfyui:8388 media-lab-comfyui-gpu1:8389; do
    name="${name_port%%:*}" port="${name_port##*:}"
    [[ "$(docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null || true)" == true ]] || continue
    curl -fsS --max-time 5 "http://127.0.0.1:$port/queue" | python3 -c 'import json,sys; q=json.load(sys.stdin); sys.exit(bool(q.get("queue_running") or q.get("queue_pending")))' || return 1
  done
  if [[ "$(docker inspect -f '{{.State.Running}}' media-lab-runtime 2>/dev/null || true)" == true ]]; then
    docker exec media-lab-runtime python -c 'import os,pathlib,httpx,sys; key=pathlib.Path(os.environ["AGENT_SERVICE_KEY_FILE"]).read_bytes().hex(); r=httpx.get("http://127.0.0.1:8392/active-count",headers={"X-Service-Key":key},timeout=5,trust_env=False); r.raise_for_status(); x=r.json(); sys.exit(bool(x["count"] or x["recoveringAtBoot"]))' || return 1
    count="$(docker exec media-lab-runtime python -c 'import os,sqlite3; db=sqlite3.connect(os.environ["DB_PATH"]); print(db.execute("SELECT COUNT(*) FROM jobs WHERE status IN (?,?)",("running","queued")).fetchone()[0] + db.execute("SELECT COUNT(*) FROM agent_runs WHERE status IN (?,?)",("running","recovering")).fetchone()[0])')" || return 1
    [[ "$count" == 0 ]] || return 1
  fi
}
case "${1:-status}" in
  check-idle)
    idle || { echo '[BLOCKED] Active or unknown queue; no service was changed.' >&2; exit 3; }
    echo '[OK] Dedicated queues, persisted jobs and private agent are idle.'
    ;;
  start)
    if docker ps --format '{{.Names}}' | grep -q '^image-studio-lab-'; then echo '[BLOCKED] Image Lab is active.' >&2; exit 3; fi
    sudo -n "$ROOT/deploy/scripts/web-firewall.sh" status || { echo '[BLOCKED] Proxy-only firewall missing.' >&2; exit 3; }
    "${COMPOSE[@]}" up -d --no-build
    ;;
  stop)
    idle || { echo '[BLOCKED] Active or unknown queue; no service was stopped.' >&2; exit 3; }
    "${COMPOSE[@]}" stop agent runtime comfyui comfyui-gpu1
    ;;
  restart) "$0" stop; "$0" start ;;
  status) "${COMPOSE[@]}" ps ;;
  bootstrap) exec "${COMPOSE[@]}" exec runtime python -m media_lab.web_cli bootstrap ;;
  logs) exec "${COMPOSE[@]}" logs -f --tail=100 runtime agent ;;
  *) echo 'Usage: media-lab.sh {start|stop|restart|status|check-idle|bootstrap|logs}' >&2; exit 2 ;;
esac
