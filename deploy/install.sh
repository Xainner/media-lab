#!/usr/bin/env bash
# Media Lab server installer and operator tool.
#
# Checks the host (Linux, Docker + NVIDIA Container Toolkit, GPUs, disk, Hugging Face token),
# downloads the selected model groups with the pinned, SHA-256-verified deploy/scripts/download-*.sh,
# creates the private TLS origin certificate and keys, builds the images and starts
# deploy/compose.yml + deploy/compose.web.yml with a generated host override. Every step is
# idempotent: re-running it resumes downloads and keeps existing secrets and data.
#
# Run deploy/install.sh --help for the commands and options.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY="$REPO_ROOT/deploy"
SCRIPTS="$DEPLOY/scripts"
PROGRAM="deploy/install.sh"

# Default paths written literally in the download scripts. The download step maps them to this
# installation's directories (single quotes: they are matched as text, not expanded).
REF_MODELS='$HOME/models/media-lab'
REF_SHARED='$HOME/models/comfyui/models'
REF_FUSED='/opt/maestro/repo/app/ckpts'

RUNTIME_CONTAINER="media-lab-runtime"   # container_name in deploy/compose.yml
CONTAINER_UID=1000           # deploy/Dockerfile.web and Dockerfile.agent run as 1000:1000
MIN_COMPOSE="2.24.4"         # compose.web.yml uses the !override merge tag
MIN_DRIVER=580               # the ComfyUI image is built on CUDA 13
MIN_VRAM_MIB=23000           # tested on 24 GB RTX 3090s
IMAGES_GB=40                 # room for the ComfyUI, web and agent images and build cache

# ---------------------------------------------------------------------------------------------
# Model groups. Each group runs existing download scripts (script:arg passes one argument);
# sizes are approximate downloads.
# ---------------------------------------------------------------------------------------------
GROUP_ORDER=(qwen qwen-bf16 qwen-control moss flux3 h3 h3-turbo h3-omni h3-control video-edit
             scail2 kandinsky6 yue2 ace-step stable-audio3 tts stems)
declare -A G_SCRIPTS=(
  [qwen]="download-models.sh download-turbo-flashvsr.sh"
  [qwen-bf16]="download-bf16.sh"
  [qwen-control]="download-qwen-control-models.sh"
  [moss]="download-moss-image-models.sh"
  [flux3]="download-flux3-klein-models.sh"
  [h3]="download-h3-models.sh"
  [h3-turbo]="download-h3-turbo-models.sh"
  [h3-omni]="download-fasth3-omni.sh"
  [h3-control]="download-h3-control-models.sh"
  [video-edit]="download-swap-models.sh download-face-models.sh download-remover-models.sh"
  [scail2]="download-scail2-models.sh download-shared-comfy-models.sh:scail2"
  [kandinsky6]="download-kandinsky6-models.sh download-shared-comfy-models.sh:kandinsky6"
  [yue2]="download-creative-models.sh"
  [ace-step]="download-ace-step-models.sh"
  [stable-audio3]="download-stable-audio3-models.sh"
  [tts]="download-qwen3-tts-models.sh"
  [stems]="download-stems-model.sh"
)
declare -A G_GB=(
  [qwen]=44 [qwen-bf16]=14 [qwen-control]=8 [moss]=13 [flux3]=24 [h3]=84 [h3-turbo]=4
  [h3-omni]=22 [h3-control]=5 [video-edit]=5 [scail2]=27 [kandinsky6]=18 [yue2]=5
  [ace-step]=20 [stable-audio3]=18 [tts]=14 [stems]=1
)
declare -A G_DEPS=(
  [qwen-bf16]="qwen" [qwen-control]="qwen" [h3-turbo]="h3" [h3-omni]="h3"
  [h3-control]="h3 qwen-control" [video-edit]="h3" [scail2]="qwen video-edit" [kandinsky6]="moss"
)
declare -A G_DESC=(
  [qwen]="Qwen-Image 2.1 + Turbo (image, edit, background removal) and FlashVSR upscaler (required)"
  [qwen-bf16]="Qwen-Image 2.1 BF16 diffusion weights (higher precision; enables ENABLE_BF16)"
  [qwen-control]="Qwen structure control (pose/edges/depth) and QMA camera angles"
  [moss]="MOSS-Image: posters and legible in-image text"
  [flux3]="FLUX 3 Klein: fast photorealism and editing (GATED: accept the licence on Hugging Face)"
  [h3]="MiniMax H3 video with audio (Base + Fused Turbo profiles)"
  [h3-turbo]="H3 Turbo profile (LightX2V 8-step LoRAs)"
  [h3-omni]="FastH3 Omni 8-step reference video"
  [h3-control]="Follow a video's pose, edges or depth (H3 Fun ControlNet-Union 2.0)"
  [video-edit]="Character swap, head swap, face refine and person removal"
  [scail2]="SCAIL-2 character replacement"
  [kandinsky6]="Kandinsky 6: 5 s clips with audio and lip-sync"
  [yue2]="YuE2 3B songs, ABC scores and covers (needs the hf CLI)"
  [ace-step]="ACE-Step 1.5 XL Turbo: full songs of exact length"
  [stable-audio3]="Stable Audio 3: instrumental music, loops, SFX and one-shots"
  [tts]="Qwen3-TTS: preset, designed and (with consent) cloned voices"
  [stems]="Hybrid Demucs stem separation"
)
declare -A G_LICENSE=(
  [qwen]="Qwen Research License (non-commercial); FlashVSR Apache-2.0"
  [qwen-bf16]="Qwen Research License (non-commercial)"
  [qwen-control]="Qwen Research License; Apache-2.0; MIT"
  [moss]="Apache-2.0"
  [flux3]="FLUX Kommunity License (gated)"
  [h3]="MiniMax H3 Community License; Fused Turbo merge: research use"
  [h3-turbo]="MiniMax H3 Community License"
  [h3-omni]="MiniMax H3 Community License"
  [h3-control]="MiniMax H3 Community License; RT-DETR: see upstream"
  [video-edit]="MiniMax H3 Community License; Meta SAM License; Apache-2.0; others: see upstream"
  [scail2]="MIT; Wan 2.1 encoder and VAE Apache-2.0; LightX2V LoRA and CLIP vision: see upstream"
  [kandinsky6]="MIT; Qwen2.5-VL Apache-2.0; MMAudio VAE CC-BY-NC-4.0 (non-commercial)"
  [yue2]="See the m-a-p/YuE2-3B model card"
  [ace-step]="Apache-2.0"
  [stable-audio3]="Stability AI Community License"
  [tts]="Apache-2.0"
  [stems]="MIT"
)
PRESET_MINIMAL="qwen"
PRESET_RECOMMENDED="qwen qwen-control moss flux3 h3 h3-turbo ace-step stable-audio3 tts stems"
PRESET_ALL="${GROUP_ORDER[*]}"

# ---------------------------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------------------------
if [[ -t 1 ]]; then
  C_B=$'\e[1m' C_DIM=$'\e[2m' C_OK=$'\e[32m' C_WARN=$'\e[33m' C_ERR=$'\e[31m' C_ACC=$'\e[38;5;202m' C_0=$'\e[0m'
else
  C_B="" C_DIM="" C_OK="" C_WARN="" C_ERR="" C_ACC="" C_0=""
fi
step() { printf '\n%s==>%s %s%s%s\n' "$C_ACC" "$C_0" "$C_B" "$*" "$C_0"; }
info() { printf '    %s\n' "$*"; }
ok()   { printf '    %s[ok]%s %s\n' "$C_OK" "$C_0" "$*"; }
warn() { printf '    %s[warn]%s %s\n' "$C_WARN" "$C_0" "$*" >&2; WARNINGS=$((WARNINGS + 1)); }
fail() { printf '    %s[fail]%s %s\n' "$C_ERR" "$C_0" "$*" >&2; FAILURES=$((FAILURES + 1)); }
die()  { printf '%serror:%s %s\n' "$C_ERR" "$C_0" "$*" >&2; exit 1; }
WARNINGS=0 FAILURES=0

# Commands that change the host go through run(); --dry-run prints them instead.
run() {
  if [[ $DRY_RUN == 1 ]]; then
    printf '    %s[dry-run]%s %s\n' "$C_DIM" "$C_0" "$(printf '%q ' "$@")"
  else
    "$@"
  fi
}

usage() {
  cat <<EOF
Media Lab installer — self-hosted image, video, music and voice studio.

Usage: $PROGRAM [command] [options]

Commands:
  install       Check the host, download models, create secrets, build and start (default).
                Safe to re-run: it resumes downloads and keeps existing secrets and data.
  models        Only download (or verify) the selected model groups.
  list-models   Show the model groups, sizes and licences.
  start | stop | restart | status | logs
                Manage the running stack. stop refuses while jobs are active (--force to override).
  bootstrap     Print the one-time link that creates the first administrator.
  update        Back up the database, keep the current images for rollback, git pull --ff-only,
                then re-run install with the saved settings (add --skip-models to skip
                re-verifying every model file, which reads them all).
  rollback      Return to the code, images and (with --restore-db) database saved by the last update.
  renew-cert    Reissue the origin certificate if it expires within 30 days, then reload the web.

Options:
  --origin URL           Public HTTPS origin users open, e.g. https://media.example.com
                         (a host name or LAN IPv4, optionally with :port; required on first install).
  --models LIST          Comma-separated groups or a preset: minimal, recommended, all.
                         Dependencies are added automatically and groups add to the ones
                         installed before (nothing is deleted). Default: recommended.
  --home DIR             Installation directory for settings, state, secrets and models
                         (default: $MEDIA_LAB_HOME or ~/media-lab-data).
  --models-dir DIR       Media Lab model store         (default: HOME/models/media-lab)
  --shared-models-dir DIR  Shared ComfyUI model store (H3) (default: HOME/models/shared)
  --h3-fused-dir DIR     H3 Fused Turbo weights         (default: HOME/models/h3-fused)
  --loras-dir DIR        Per-account LoRA library       (default: HOME/loras)
  --listen ADDR          127.0.0.1 (default, behind a reverse proxy on this host) or 0.0.0.0.
  --port N               HTTPS port of the web/API/MCP server (default: 8390).
  --hf-token-file PATH   Hugging Face token (default: \$HF_TOKEN_FILE or ~/.cache/huggingface/token).
  --enable-2k            Allow native 2K image creation (ENABLE_2K=true).
  --single-gpu           Allow hosts with one GPU: only the GPU 0 worker is started (untested).
  --skip-models          Do not download models.
  --skip-build           Do not build images (use the ones already present).
  --no-start             Prepare everything but do not start the stack.
  --restore-db           rollback: also restore the database backed up by the last update.
  --force                stop/update/rollback: do not wait for active jobs to finish.
  -y, --yes              Non-interactive: accept defaults and saved settings, never prompt.
  -n, --dry-run          Show what would be done; change nothing.
  -h, --help             Show this help.

Examples:
  $PROGRAM --origin https://media.example.com --models recommended
  $PROGRAM --dry-run --origin https://media.example.com --models all
  $PROGRAM models --models qwen,flux3,tts
  $PROGRAM update

Secrets: the installer never asks for or stores passwords. It reads the Hugging Face token
from its standard file (create it with: hf auth login) and generates its own keys under
HOME/secrets (0700). Model licences are yours to accept: run '$PROGRAM list-models'.
EOF
}

# ---------------------------------------------------------------------------------------------
# Arguments and saved settings
# ---------------------------------------------------------------------------------------------
COMMAND="install"
DRY_RUN=0 ASSUME_YES=0 SKIP_MODELS=0 SKIP_BUILD=0 NO_START=0 FORCE=0 RESTORE_DB=0
OPT_ORIGIN="" OPT_MODELS="" OPT_HOME="" OPT_MODELS_DIR="" OPT_SHARED_DIR="" OPT_FUSED_DIR=""
OPT_LORAS_DIR="" OPT_LISTEN="" OPT_PORT="" OPT_TOKEN_FILE="" OPT_2K="" OPT_SINGLE_GPU=""

need_value() { [[ $# -ge 2 && -n $2 ]] || die "$1 needs a value (see --help)"; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    install|models|list-models|start|stop|restart|status|logs|bootstrap|update|rollback|renew-cert)
      COMMAND="$1" ;;
    --origin) need_value "$@"; OPT_ORIGIN="$2"; shift ;;
    --models) need_value "$@"; OPT_MODELS="$2"; shift ;;
    --home) need_value "$@"; OPT_HOME="$2"; shift ;;
    --models-dir) need_value "$@"; OPT_MODELS_DIR="$2"; shift ;;
    --shared-models-dir) need_value "$@"; OPT_SHARED_DIR="$2"; shift ;;
    --h3-fused-dir) need_value "$@"; OPT_FUSED_DIR="$2"; shift ;;
    --loras-dir) need_value "$@"; OPT_LORAS_DIR="$2"; shift ;;
    --listen) need_value "$@"; OPT_LISTEN="$2"; shift ;;
    --port) need_value "$@"; OPT_PORT="$2"; shift ;;
    --hf-token-file) need_value "$@"; OPT_TOKEN_FILE="$2"; shift ;;
    --enable-2k) OPT_2K=true ;;
    --single-gpu) OPT_SINGLE_GPU=1 ;;
    --skip-models) SKIP_MODELS=1 ;;
    --skip-build) SKIP_BUILD=1 ;;
    --no-start) NO_START=1 ;;
    --restore-db) RESTORE_DB=1 ;;
    --force) FORCE=1 ;;
    -y|--yes) ASSUME_YES=1 ;;
    -n|--dry-run) DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1 (see --help)" ;;
  esac
  shift
done

[[ $COMMAND == list-models ]] || [[ $(uname -s) == Linux ]] || die "Media Lab servers run on Linux (found $(uname -s))."
(( BASH_VERSINFO[0] >= 4 )) || die "bash 4 or newer is required."

INTERACTIVE=0
if [[ -t 0 && -t 1 && $ASSUME_YES == 0 ]]; then INTERACTIVE=1; fi

MEDIA_HOME="$(realpath -m "${OPT_HOME:-${MEDIA_LAB_HOME:-$HOME/media-lab-data}}")"
CONF="$MEDIA_HOME/media-lab.conf"
ENV_FILE="$MEDIA_HOME/compose.env"
OVERRIDE="$MEDIA_HOME/compose.override.yml"

# Saved settings from a previous run; command-line options win.
ORIGIN="" MODEL_GROUPS="" MODELS_DIR="" SHARED_DIR="" FUSED_DIR="" LORAS_DIR="" LISTEN="" PORT=""
HF_TOKEN_PATH="" ENABLE_2K="" SINGLE_GPU=""
if [[ -f $CONF ]]; then
  # shellcheck source=/dev/null
  source "$CONF"
fi
ORIGIN="${OPT_ORIGIN:-$ORIGIN}"
SAVED_GROUPS="$MODEL_GROUPS"
MODELS_DIR="$(realpath -m "${OPT_MODELS_DIR:-${MODELS_DIR:-$MEDIA_HOME/models/media-lab}}")"
SHARED_DIR="$(realpath -m "${OPT_SHARED_DIR:-${SHARED_DIR:-$MEDIA_HOME/models/shared}}")"
FUSED_DIR="$(realpath -m "${OPT_FUSED_DIR:-${FUSED_DIR:-$MEDIA_HOME/models/h3-fused}}")"
LORAS_DIR="$(realpath -m "${OPT_LORAS_DIR:-${LORAS_DIR:-$MEDIA_HOME/loras}}")"
STATE_DIR="$MEDIA_HOME/state"
SECRETS_DIR="$MEDIA_HOME/secrets"
BACKUPS="$STATE_DIR/backups"
LISTEN="${OPT_LISTEN:-${LISTEN:-127.0.0.1}}"
PORT="${OPT_PORT:-${PORT:-8390}}"
HF_TOKEN_PATH="${OPT_TOKEN_FILE:-${HF_TOKEN_PATH:-${HF_TOKEN_FILE:-$HOME/.cache/huggingface/token}}}"
ENABLE_2K="${OPT_2K:-${ENABLE_2K:-false}}"
SINGLE_GPU="${OPT_SINGLE_GPU:-${SINGLE_GPU:-0}}"

for dir in "$MEDIA_HOME" "$MODELS_DIR" "$SHARED_DIR" "$FUSED_DIR" "$LORAS_DIR"; do
  [[ $dir =~ ^/[A-Za-z0-9._/-]+$ ]] || die "use plain absolute paths (letters, digits, . _ - /): $dir"
done
[[ $LISTEN == 127.0.0.1 || $LISTEN == 0.0.0.0 ]] || die "--listen must be 127.0.0.1 or 0.0.0.0"
if [[ ! $PORT =~ ^[0-9]+$ ]] || (( PORT < 1024 || PORT > 65535 )); then die "--port must be 1024-65535"; fi
(( PORT != 8388 && PORT != 8389 && PORT != 8392 )) || die "ports 8388, 8389 and 8392 are used by the ComfyUI workers and the agent"

COMPOSE=(docker compose --env-file "$ENV_FILE" -f "$DEPLOY/compose.yml" -f "$DEPLOY/compose.web.yml" -f "$OVERRIDE")
SERVICES=(comfyui comfyui-gpu1 runtime agent)
if [[ $SINGLE_GPU == 1 ]]; then SERVICES=(comfyui runtime agent); fi

# ---------------------------------------------------------------------------------------------
# Model selection
# ---------------------------------------------------------------------------------------------
is_group() { [[ -n ${G_SCRIPTS[$1]+x} ]]; }

# Expands presets, validates names, adds dependencies and keeps GROUP_ORDER.
resolve_groups() {
  local raw="${1//,/ }" name dep changed=1
  declare -A chosen=([qwen]=1)
  for name in $raw; do
    case "$name" in
      minimal) for dep in $PRESET_MINIMAL; do chosen[$dep]=1; done ;;
      recommended) for dep in $PRESET_RECOMMENDED; do chosen[$dep]=1; done ;;
      all) for dep in $PRESET_ALL; do chosen[$dep]=1; done ;;
      none) ;;
      *) is_group "$name" || die "unknown model group '$name' (see: $PROGRAM list-models)"; chosen[$name]=1 ;;
    esac
  done
  while [[ $changed == 1 ]]; do
    changed=0
    for name in "${!chosen[@]}"; do
      for dep in ${G_DEPS[$name]:-}; do
        [[ -n ${chosen[$dep]:-} ]] || { chosen[$dep]=1; changed=1; }
      done
    done
  done
  local out=()
  for name in "${GROUP_ORDER[@]}"; do
    if [[ -n ${chosen[$name]:-} ]]; then out+=("$name"); fi
  done
  echo "${out[*]}"
}

groups_gb() { local total=0 g; for g in $1; do total=$((total + G_GB[$g])); done; echo "$total"; }

list_models() {
  printf '%s%-14s %5s  %s%s\n' "$C_B" "GROUP" "GB" "CONTENTS / LICENCE" "$C_0"
  local g
  for g in "${GROUP_ORDER[@]}"; do
    printf '%-14s %5s  %s\n' "$g" "~${G_GB[$g]}" "${G_DESC[$g]}"
    printf '%-14s %5s  %s%s%s\n' "" "" "$C_DIM" "${G_LICENSE[$g]}" "$C_0"
  done
  cat <<EOF

Presets: minimal = $PRESET_MINIMAL (~$(groups_gb "$PRESET_MINIMAL") GB)
         recommended = $PRESET_RECOMMENDED (~$(groups_gb "$PRESET_RECOMMENDED") GB)
         all = every group (~$(groups_gb "$PRESET_ALL") GB)

Every licence must be read and accepted by whoever installs the weights. Several are
non-commercial or research-only, and FLUX 3 Klein is gated on Hugging Face.
EOF
}

choose_groups() {
  local answer="$OPT_MODELS"
  if [[ -z $answer && -z $SAVED_GROUPS && $INTERACTIVE == 1 ]]; then
    echo
    list_models
    echo
    read -r -p "Model groups to install [recommended]: " answer
  fi
  [[ -n $answer || -n $SAVED_GROUPS ]] || answer="recommended"
  MODEL_GROUPS="$(resolve_groups "$SAVED_GROUPS $answer")"
}

has_group() { [[ " $MODEL_GROUPS " == *" $1 "* ]]; }

# ---------------------------------------------------------------------------------------------
# Origin
# ---------------------------------------------------------------------------------------------
ORIGIN_HOST="" ORIGIN_NETLOC="" ORIGIN_SAN=""
parse_origin() {
  [[ $ORIGIN =~ ^https://([a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*)(:([0-9]+))?$ ]] \
    || die "--origin must be an exact https origin with a lower-case host name or IPv4 address, e.g. https://media.example.com (no path)"
  ORIGIN_HOST="${BASH_REMATCH[1]}"
  ORIGIN_NETLOC="${ORIGIN#https://}"
  ORIGIN_SAN="DNS:$ORIGIN_HOST"
  if [[ $ORIGIN_HOST =~ ^[0-9.]+$ ]]; then
    # A LAN-only instance may be opened by its address; the certificate then names the IP.
    local octet parts
    IFS=. read -r -a parts <<<"$ORIGIN_HOST"
    [[ ${#parts[@]} == 4 ]] || die "--origin has an invalid IPv4 address: $ORIGIN_HOST"
    for octet in "${parts[@]}"; do
      [[ $octet =~ ^(0|[1-9][0-9]{0,2})$ && $octet -le 255 ]] || die "--origin has an invalid IPv4 address: $ORIGIN_HOST"
    done
    ORIGIN_SAN="IP:$ORIGIN_HOST"
  fi
}

ask_origin() {
  if [[ -z $ORIGIN && $INTERACTIVE == 1 ]]; then
    echo
    info "Media Lab is served over HTTPS at one exact origin: the address people type in the browser."
    info "Behind a reverse proxy use its public name (https://media.example.com); for direct LAN"
    info "access use a name that resolves to this server, or its LAN IPv4, plus the port (https://medialab.lan:$PORT)."
    read -r -p "Public origin: " ORIGIN
  fi
  [[ -n $ORIGIN ]] || die "--origin is required on the first install (e.g. --origin https://media.example.com)"
  parse_origin
}

# ---------------------------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------------------------
version_ge() { [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" == "$2" ]]; }

free_gb() { # free space of the nearest existing ancestor of $1, in GB
  local path="$1"
  while [[ ! -e $path ]]; do path="$(dirname "$path")"; done
  df -Pk "$path" | awk 'NR==2 {print int($4 / 1048576)}'
}

stack_running() { [[ "$(docker inspect -f '{{.State.Running}}' "$RUNTIME_CONTAINER" 2>/dev/null || true)" == true ]]; }

preflight() {
  step "Checking the host"
  local cmd missing=() docker_ok=0
  for cmd in curl sha256sum openssl awk sed sort df realpath; do
    command -v "$cmd" >/dev/null || missing+=("$cmd")
  done
  if [[ ${#missing[@]} == 0 ]]; then
    ok "Linux, bash ${BASH_VERSION%%(*}, base tools"
  else
    fail "missing commands: ${missing[*]}"
  fi

  local g s
  for g in $MODEL_GROUPS; do
    for s in ${G_SCRIPTS[$g]}; do
      [[ -f $SCRIPTS/${s%%:*} ]] || fail "group $g needs $SCRIPTS/${s%%:*}, which this checkout does not have"
    done
  done

  if ! command -v docker >/dev/null; then
    fail "Docker is not installed (Docker Engine with the compose plugin)"
  elif ! docker info >/dev/null 2>&1; then
    fail "cannot talk to Docker: start it and add $(id -un) to the docker group (then log in again)"
  else
    docker_ok=1
    local compose_version
    compose_version="$(docker compose version --short 2>/dev/null | sed 's/^v//; s/[+-].*//')"
    if [[ -z $compose_version ]]; then
      fail "Docker Compose v2 (the 'docker compose' plugin) is required"
    elif ! version_ge "$compose_version" "$MIN_COMPOSE"; then
      fail "Docker Compose $MIN_COMPOSE or newer is required (found $compose_version)"
    else
      ok "Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null), Compose $compose_version"
    fi
    if docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q nvidia || command -v nvidia-ctk >/dev/null; then
      ok "NVIDIA Container Toolkit"
    else
      fail "NVIDIA Container Toolkit not found (install it, then: sudo nvidia-ctk runtime configure --runtime=docker)"
    fi
  fi

  if ! command -v nvidia-smi >/dev/null; then
    fail "nvidia-smi not found: install the NVIDIA driver ($MIN_DRIVER or newer)"
  else
    local gpus=() line name mem driver count
    mapfile -t gpus < <(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits 2>/dev/null)
    count=${#gpus[@]}
    if (( count == 0 )); then
      fail "no NVIDIA GPU visible to nvidia-smi"
    else
      for line in "${gpus[@]}"; do
        IFS=',' read -r name mem driver <<<"$line"
        mem="${mem// /}" driver="${driver// /}"
        if (( mem < MIN_VRAM_MIB )); then
          warn "GPU ${name# } has ${mem} MiB; Media Lab is tested on 24 GB cards and large models may not fit"
        else
          ok "GPU ${name# } (${mem} MiB)"
        fi
      done
      if (( ${driver%%.*} >= MIN_DRIVER )); then
        ok "driver $driver (CUDA 13)"
      else
        fail "driver $driver is too old: the ComfyUI image needs CUDA 13 (driver $MIN_DRIVER+)"
      fi
      if (( count < 2 )); then
        if [[ $SINGLE_GPU == 1 ]]; then
          warn "one GPU: only the GPU 0 worker will run (untested configuration)"
        else
          fail "Media Lab runs one ComfyUI worker per GPU and expects 2 GPUs (use --single-gpu to try with one)"
        fi
      fi
    fi
  fi

  local uid; uid="$(id -u)"
  if [[ $uid != "$CONTAINER_UID" && $uid != 0 ]]; then
    fail "the web and agent containers run as uid $CONTAINER_UID; run the installer as that user (or as root, which hands the data directories to uid $CONTAINER_UID)"
  else
    ok "user $(id -un) (uid $uid)"
  fi

  local need have
  need=$(( $(groups_gb "$MODEL_GROUPS") ))
  if [[ $SKIP_MODELS == 1 ]]; then need=0; fi
  have="$(free_gb "$MODELS_DIR")"
  if (( have < need )); then
    fail "about $need GB of models selected but only $have GB free at $MODELS_DIR (verified files are not downloaded again)"
  else
    ok "disk: ~$need GB of models selected, $have GB free at $MODELS_DIR"
  fi
  if [[ $SKIP_BUILD == 0 && $docker_ok == 1 ]]; then
    local docker_root; docker_root="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo /var/lib/docker)"
    have="$(free_gb "$docker_root")"
    if (( have >= IMAGES_GB )); then
      ok "disk: $have GB free for images at $docker_root"
    else
      warn "only $have GB free at $docker_root; building the images needs about $IMAGES_GB GB"
    fi
  fi

  check_hf_token

  # Compose project and container names are fixed: one Media Lab per host. Never take over a
  # deployment this installer did not create (the reference host runs deploy/media-lab.sh).
  if [[ -f $DEPLOY/.web.env ]]; then
    fail "this checkout is deployed by deploy/media-lab.sh (deploy/.web.env exists); the installer would replace that deployment"
  elif [[ $docker_ok == 1 && ! -f $CONF ]] && docker inspect "$RUNTIME_CONTAINER" >/dev/null 2>&1; then
    fail "a Media Lab stack not created by this installer exists on this host ($RUNTIME_CONTAINER); only one installation per host is supported"
  fi

  if [[ $docker_ok == 0 ]] || ! stack_running; then
    local port
    for port in 8388 8389 "$PORT" 8392; do
      if ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq "[:.]$port\$"; then
        fail "TCP port $port is already in use"
      fi
    done
  fi

  if (( FAILURES > 0 )); then
    [[ $DRY_RUN == 1 ]] || die "$FAILURES check(s) failed; fix them and run the installer again."
    warn "$FAILURES check(s) failed: a real run would stop here (continuing the dry run)"
  fi
}

hf_cli() { command -v hf 2>/dev/null || { [[ -x $HOME/.local/bin/hf ]] && echo "$HOME/.local/bin/hf"; } || true; }

check_hf_token() {
  if has_group yue2 && [[ $SKIP_MODELS == 0 ]]; then
    if [[ -n $(hf_cli) ]]; then
      ok "hf CLI ($(hf_cli))"
    else
      fail "the yue2 group downloads with the Hugging Face CLI: install it (e.g. pipx install 'huggingface_hub[cli]')"
    fi
  fi
  if [[ ! -r $HF_TOKEN_PATH ]]; then
    if has_group flux3 && [[ $SKIP_MODELS == 0 ]]; then
      fail "FLUX 3 Klein is gated: accept its licence on Hugging Face, then save a read token with 'hf auth login' (expected at $HF_TOKEN_PATH)"
    else
      info "no Hugging Face token at $HF_TOKEN_PATH (only needed for gated models such as FLUX 3 Klein)"
    fi
    return
  fi
  local mode; mode="$(stat -c '%a' "$HF_TOKEN_PATH" 2>/dev/null || echo '?')"
  [[ $mode == 600 || $mode == 400 ]] || warn "$HF_TOKEN_PATH is mode $mode; restrict it with: chmod 600 $HF_TOKEN_PATH"
  # The token travels in a curl config read from stdin, so it never appears in the process list.
  local who
  if who="$(printf 'header = "Authorization: Bearer %s"\n' "$(tr -d '[:space:]' <"$HF_TOKEN_PATH")" \
      | curl -fsS --max-time 15 --config - https://huggingface.co/api/whoami-v2 2>/dev/null)"; then
    who="$(grep -o '"name":"[^"]*"' <<<"$who" | head -1 | cut -d'"' -f4)"
    ok "Hugging Face token valid${who:+ (user $who)}"
    if has_group flux3; then
      info "FLUX 3 Klein is gated: make sure ${who:-this account} accepted its licence on Hugging Face"
    fi
  else
    if has_group flux3 && [[ $SKIP_MODELS == 0 ]]; then
      fail "the Hugging Face token at $HF_TOKEN_PATH was rejected (or Hugging Face is unreachable)"
    else
      warn "the Hugging Face token at $HF_TOKEN_PATH was rejected (or Hugging Face is unreachable)"
    fi
  fi
}

# ---------------------------------------------------------------------------------------------
# Settings, directories, secrets
# ---------------------------------------------------------------------------------------------
write_file() { # path mode content
  local path="$1" mode="$2" content="$3" line
  if [[ $DRY_RUN == 1 ]]; then
    printf '    %s[dry-run]%s write %s (mode %s):\n' "$C_DIM" "$C_0" "$path" "$mode"
    while IFS= read -r line; do printf '        | %s\n' "$line"; done <<<"$content"
    return
  fi
  local tmp; tmp="$(mktemp "$path.XXXXXX")"
  printf '%s\n' "$content" >"$tmp"
  chmod "$mode" "$tmp"
  mv -f "$tmp" "$path"
}

save_settings() {
  step "Saving settings in $MEDIA_HOME"
  run mkdir -p "$MEDIA_HOME" "$BACKUPS"
  local key conf="# Media Lab installer settings (no secrets). Edit with $PROGRAM options, then re-run it."
  for key in ORIGIN MODEL_GROUPS MODELS_DIR SHARED_DIR FUSED_DIR LORAS_DIR LISTEN PORT HF_TOKEN_PATH ENABLE_2K SINGLE_GPU; do
    conf+=$'\n'"$(printf '%s=%q' "$key" "${!key}")"
  done
  write_file "$CONF" 600 "$conf"
  local bf16=false
  if has_group qwen-bf16; then bf16=true; fi
  write_file "$ENV_FILE" 600 "# Generated by $PROGRAM. Non-secret compose variables.
MEDIA_LAB_ORIGIN=$ORIGIN
MEDIA_LAB_HOST=$ORIGIN_HOST
MEDIA_LAB_LISTEN=$LISTEN
MEDIA_LAB_PORT=$PORT
MEDIA_LAB_STATE_DIR=$STATE_DIR
MEDIA_LAB_SECRETS_DIR=$SECRETS_DIR
MEDIA_LAB_MODELS_DIR=$MODELS_DIR
MEDIA_LAB_SHARED_MODELS_DIR=$SHARED_DIR
MEDIA_LAB_LORAS_DIR=$LORAS_DIR
MEDIA_LAB_FUSED_DIR=$FUSED_DIR
ENABLE_2K=$ENABLE_2K
ENABLE_BF16=$bf16
QWEN21_ENCODER=qwen3vl_8b_int8_convrot.safetensors"
  ok "settings: $CONF"
}

prepare_dirs() {
  step "Preparing directories"
  run mkdir -p "$MODELS_DIR" "$SHARED_DIR"/{diffusion_models,text_encoders,vae,loras} \
    "$FUSED_DIR/minimax_h3/vae" "$LORAS_DIR/loras" "$STATE_DIR/artifacts" "$STATE_DIR/agent-runs"
  if [[ $(id -u) == 0 ]]; then
    run chown -R "$CONTAINER_UID:$CONTAINER_UID" "$STATE_DIR" "$LORAS_DIR"
  fi
  ok "models: $MODELS_DIR"
  ok "shared models: $SHARED_DIR, H3 fused: $FUSED_DIR"
  ok "state: $STATE_DIR, LoRAs: $LORAS_DIR"
}

cert_needs_issue() {
  local crt="$SECRETS_DIR/origin.crt"
  [[ -f $crt ]] || return 0
  openssl x509 -in "$crt" -noout -checkend $((30 * 86400)) >/dev/null || return 0
  openssl x509 -in "$crt" -noout -ext subjectAltName 2>/dev/null | sed 's/IP Address:/IP:/g' | grep -qwF "$ORIGIN_SAN" || return 0
  return 1
}

# Mirrors deploy/scripts/provision-web.py (same files, modes and key sizes) for any host name.
issue_cert() {
  local dir="$SECRETS_DIR" ext
  if [[ $DRY_RUN == 1 ]]; then
    info "[dry-run] issue origin certificate for $ORIGIN_HOST and localhost (365 days)"
    return
  fi
  (
    umask 077
    ext="$(mktemp)"
    printf '%s\n' "subjectAltName=$ORIGIN_SAN,DNS:localhost" "basicConstraints=critical,CA:FALSE" \
      "keyUsage=critical,digitalSignature,keyEncipherment" "extendedKeyUsage=serverAuth" \
      "subjectKeyIdentifier=hash" "authorityKeyIdentifier=keyid,issuer" >"$ext"
    [[ -s $dir/origin.key ]] || openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$dir/origin.key" 2>/dev/null
    openssl req -new -key "$dir/origin.key" -subj "/CN=$ORIGIN_HOST" -out "$dir/origin.csr"
    openssl x509 -req -in "$dir/origin.csr" -CA "$dir/origin-ca.crt" -CAkey "$dir/origin-ca.key" \
      -set_serial "0x1$(openssl rand -hex 15)" -days 365 -sha256 -extfile "$ext" -out "$dir/origin.crt.new" 2>/dev/null
    rm -f "$ext" "$dir/origin.csr"
    mv -f "$dir/origin.crt.new" "$dir/origin.crt"
  )
  ok "origin certificate for $ORIGIN_HOST, valid until $(openssl x509 -in "$dir/origin.crt" -noout -enddate | cut -d= -f2)"
}

prepare_secrets() {
  step "Private keys and origin certificate"
  local dir="$SECRETS_DIR" name
  if [[ $DRY_RUN == 0 ]]; then
    (umask 077; mkdir -p "$dir")
    chmod 700 "$dir"
  fi
  # Never replaced once created: master.key decrypts stored credentials.
  for name in master.key agent.key; do
    if [[ -s $dir/$name ]]; then
      ok "$name kept"
    elif [[ $DRY_RUN == 1 ]]; then
      info "[dry-run] create $dir/$name (32 random bytes, mode 600)"
    else
      (umask 077; head -c 32 /dev/urandom >"$dir/$name")
      ok "$name created"
    fi
  done
  if [[ -s $dir/origin-ca.key && -s $dir/origin-ca.crt ]]; then
    ok "origin CA kept"
  elif [[ $DRY_RUN == 1 ]]; then
    info "[dry-run] create a private origin CA (RSA 3072, 5 years)"
  else
    (umask 077
     openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$dir/origin-ca.key" 2>/dev/null
     openssl req -x509 -new -key "$dir/origin-ca.key" -sha256 -days 1825 -subj "/CN=Media Lab Origin CA" \
       -addext "basicConstraints=critical,CA:TRUE,pathlen:0" -addext "keyUsage=critical,keyCertSign,cRLSign" \
       -out "$dir/origin-ca.crt" 2>/dev/null)
    rm -f "$dir/origin.crt"   # a new CA needs a new leaf
    ok "origin CA created"
  fi
  if cert_needs_issue; then issue_cert; else ok "origin certificate valid for $ORIGIN_HOST"; fi
  if [[ $(id -u) == 0 ]]; then run chown -R "$CONTAINER_UID:$CONTAINER_UID" "$dir"; fi
  if [[ -f $dir/civitai.token ]]; then
    ok "Civitai token present (LoRA links from Civitai)"
  else
    info "optional: put a Civitai API token in $dir/civitai.token (mode 600) to add LoRAs from Civitai"
  fi
}

# ---------------------------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------------------------
# Runs an existing download script ("name.sh" or "name.sh:arg") with this installation's
# directories. Scripts that still hard-code the reference host paths get them rewritten in a
# temporary copy; URLs, revisions and SHA-256 values are untouched.
run_download() {
  local name="${1%%:*}" args=() copy
  [[ $1 != *:* ]] || args=("${1#*:}")
  local script="$SCRIPTS/$name"
  [[ -f $script ]] || die "missing $script"
  if [[ $DRY_RUN == 1 ]]; then
    info "[dry-run] $name ${args[*]}"
    return
  fi
  copy="$(mktemp "${TMPDIR:-/tmp}/media-lab-$name.XXXXXX")"
  sed -e "s#$REF_MODELS#$MODELS_DIR#g" -e "s#$REF_SHARED#$SHARED_DIR#g" -e "s#$REF_FUSED#$FUSED_DIR#g" "$script" >"$copy"
  local hf; hf="$(command -v hf || true)"
  if ! MEDIA_LAB_MODELS_DIR="$MODELS_DIR" H3_SHARED_ROOT="$SHARED_DIR" H3_FUSED_HOST_ROOT="$FUSED_DIR" \
      HF_TOKEN_FILE="$HF_TOKEN_PATH" HF_CMD="${hf:-hf}" bash "$copy" "${args[@]}"; then
    rm -f "$copy"
    die "$name failed. Re-run the installer to resume; a 401/403 from Hugging Face means the licence was not accepted or the token lacks access."
  fi
  rm -f "$copy"
}

download_models() {
  step "Models: $MODEL_GROUPS"
  info "Pinned revisions, every file verified by SHA-256; interrupted downloads resume."
  local g s
  for g in $MODEL_GROUPS; do
    printf '\n    %s%s%s — %s\n' "$C_B" "$g" "$C_0" "${G_DESC[$g]}"
    for s in ${G_SCRIPTS[$g]}; do run_download "$s"; done
  done
}

# ---------------------------------------------------------------------------------------------
# Compose override, images, services
# ---------------------------------------------------------------------------------------------
write_override() {
  step "Compose override for this host"
  local resolve="127.0.0.1"
  local comfy_common
  comfy_common="      - $MODELS_DIR:/workspace/ComfyUI/models
      - $SHARED_DIR:/shared-models:ro
      - $LORAS_DIR:/user-loras:ro
      - $DEPLOY/extra_model_paths.yaml:/workspace/ComfyUI/extra_model_paths.yaml:ro
      - $FUSED_DIR:/fused-models/diffusion_models:ro
      - $FUSED_DIR/minimax_h3/vae:/fused-models/vae:ro"
  write_file "$OVERRIDE" 644 "# Generated by $PROGRAM for $ORIGIN — re-run the installer to change it.
# Replaces the reference host's paths and origin in deploy/compose.yml + compose.web.yml.
services:
  comfyui:
    volumes: !override
$comfy_common
      - comfy-input:/workspace/ComfyUI/input
      - comfy-output:/workspace/ComfyUI/output
      - comfy-user:/workspace/ComfyUI/user
  comfyui-gpu1:
    volumes: !override
$comfy_common
      - comfy-gpu1-input:/workspace/ComfyUI/input
      - comfy-gpu1-output:/workspace/ComfyUI/output
      - comfy-gpu1-user:/workspace/ComfyUI/user
  runtime:
    command: [\"uvicorn\", \"media_lab.web:create_app\", \"--factory\", \"--host\", \"$LISTEN\", \"--port\", \"$PORT\", \"--no-proxy-headers\", \"--no-access-log\", \"--ssl-certfile\", \"/run/media-lab/origin.crt\", \"--ssl-keyfile\", \"/run/media-lab/origin.key\"]
    environment:
      PUBLIC_ORIGIN: $ORIGIN
    volumes: !override
      - $STATE_DIR:/data
      - $SECRETS_DIR:/run/media-lab:ro
      - $MODELS_DIR:/models:ro
      - $SHARED_DIR:/h3-models:ro
      - $LORAS_DIR:/user-loras
      - $FUSED_DIR:/fused-models/diffusion_models:ro
      - $FUSED_DIR/minimax_h3/vae:/fused-models/vae:ro
    healthcheck:
      test: [\"CMD\", \"curl\", \"-fsS\", \"--cacert\", \"/run/media-lab/origin-ca.crt\", \"--connect-to\", \"$ORIGIN_HOST:$PORT:$resolve:$PORT\", \"-H\", \"Host: $ORIGIN_NETLOC\", \"https://$ORIGIN_HOST:$PORT/health\"]
  agent:
    environment:
      PUBLIC_ORIGIN: $ORIGIN
      RUNTIME_PORT: \"$PORT\"
    volumes: !override
      - $STATE_DIR/agent-runs:/agent-state
      - $SECRETS_DIR:/run/media-lab:ro"
  if [[ $DRY_RUN == 0 ]]; then
    "${COMPOSE[@]}" config --quiet || die "docker compose rejected the generated configuration ($OVERRIDE)"
    ok "compose configuration valid"
  fi
}

compose_images() { "${COMPOSE[@]}" config --images 2>/dev/null | sort -u; }

build_images() {
  step "Building images (the first ComfyUI build takes a while)"
  run "${COMPOSE[@]}" build comfyui runtime agent
}

start_stack() {
  step "Starting ${SERVICES[*]}"
  run "${COMPOSE[@]}" up -d --no-build "${SERVICES[@]}"
  [[ $DRY_RUN == 1 ]] && return
  local health
  for _ in $(seq 1 60); do
    health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$RUNTIME_CONTAINER" 2>/dev/null || true)"
    [[ $health == healthy ]] && { ok "web runtime healthy"; return; }
    sleep 5
  done
  warn "the web runtime is not healthy yet; check with: $PROGRAM logs"
}

# Run inside the web runtime container (python, the database and the agent key live there).
# Prints a reason and fails when ComfyUI queues, persisted jobs or agent runs are active.
IDLE_CHECK="$(cat <<'PY'
import json, os, pathlib, sqlite3, sys, urllib.request
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
busy = []
for port in (8388, 8389):
    try:
        with opener.open(f"http://127.0.0.1:{port}/queue", timeout=5) as r:
            q = json.load(r)
    except OSError:
        continue
    if q.get("queue_running") or q.get("queue_pending"):
        busy.append(f"ComfyUI :{port} queue")
try:
    db = sqlite3.connect(f"file:{os.environ['DB_PATH']}?mode=ro", uri=True)
    if db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]:
        busy.append("queued or running jobs")
    if db.execute("SELECT COUNT(*) FROM agent_runs WHERE status IN ('running','recovering')").fetchone()[0]:
        busy.append("agent runs")
except sqlite3.OperationalError:
    pass
try:
    key = pathlib.Path(os.environ["AGENT_SERVICE_KEY_FILE"]).read_bytes().hex()
    req = urllib.request.Request("http://127.0.0.1:8392/active-count", headers={"X-Service-Key": key})
    with opener.open(req, timeout=5) as r:
        a = json.load(r)
    if a.get("count") or a.get("recoveringAtBoot"):
        busy.append("agent work")
except OSError:
    pass
if busy:
    print(", ".join(busy))
    sys.exit(1)
PY
)"
ADMIN_CHECK="$(cat <<'PY'
import os, sqlite3, sys
db = sqlite3.connect(f"file:{os.environ['DB_PATH']}?mode=ro", uri=True)
sys.exit(0 if db.execute("SELECT 1 FROM users WHERE role='admin'").fetchone() else 1)
PY
)"
DB_BACKUP="$(cat <<'PY'
import os, sqlite3, sys
src, dst = sqlite3.connect(os.environ["DB_PATH"]), sqlite3.connect(sys.argv[1])
src.backup(dst)
dst.close()
PY
)"

ensure_idle() {
  [[ $FORCE == 1 ]] && return
  stack_running || return 0
  local reason
  if ! reason="$(docker exec "$RUNTIME_CONTAINER" python -c "$IDLE_CHECK" 2>&1)"; then
    die "Media Lab is busy (${reason:-unknown state}); nothing was changed. Wait, or use --force to interrupt."
  fi
}

admin_exists() { docker exec "$RUNTIME_CONTAINER" python -c "$ADMIN_CHECK" 2>/dev/null; }

bootstrap_admin() {
  if [[ $DRY_RUN == 1 ]]; then info "[dry-run] create the first-administrator link if there is no administrator"; return; fi
  stack_running || die "the stack is not running; start it with: $PROGRAM start"
  if admin_exists; then ok "an administrator already exists"; return; fi
  step "First administrator"
  if [[ ! -t 1 || $ASSUME_YES == 1 ]] && [[ $COMMAND != bootstrap ]]; then
    info "No administrator yet. From a terminal, run: $PROGRAM bootstrap"
    return
  fi
  info "Open this single-use link (valid 30 minutes) to create the administrator account."
  info "It is shown only here; do not paste it into chats or logs."
  docker exec "$RUNTIME_CONTAINER" python -m media_lab.web_cli bootstrap
}

summary() {
  if [[ $NO_START == 1 ]]; then step "Media Lab is prepared"; else step "Media Lab is ready"; fi
  info "Origin:   $ORIGIN"
  info "Listens:  https://$LISTEN:$PORT (TLS with the private origin CA: $SECRETS_DIR/origin-ca.crt)"
  info "MCP:      $ORIGIN/mcp (create a token in Account → MCP connections)"
  info "Settings: $CONF"
  if [[ $LISTEN == 127.0.0.1 ]]; then
    info "Point your reverse proxy at https://127.0.0.1:$PORT, keep the Host header, verify with the"
    info "origin CA (server name $ORIGIN_HOST), allow 501 MB uploads and 600 s timeouts, no buffering."
  else
    info "Port $PORT is open on every interface: restrict it with your firewall to the proxy or LAN."
    info "Browsers must trust $SECRETS_DIR/origin-ca.crt when they connect directly."
  fi
  (( WARNINGS == 0 )) || info "${C_WARN}$WARNINGS warning(s) above.${C_0}"
}

# ---------------------------------------------------------------------------------------------
# Update and rollback
# ---------------------------------------------------------------------------------------------
backup_database() { # dest-dir
  local dest="$1"
  run mkdir -p "$dest"
  if [[ $(id -u) == 0 ]]; then run chown "$CONTAINER_UID:$CONTAINER_UID" "$BACKUPS" "$dest"; fi
  if stack_running; then
    # Online backup through SQLite, written by the container into the same state directory.
    run docker exec "$RUNTIME_CONTAINER" python -c "$DB_BACKUP" "/data/backups/$(basename "$dest")/media-lab.db"
  elif [[ -f $STATE_DIR/media-lab.db ]]; then
    run cp -p "$STATE_DIR/media-lab.db" "$dest/media-lab.db"
  fi
}

cmd_update() {
  [[ -f $CONF ]] || die "no installation found at $MEDIA_HOME (run $PROGRAM install first)"
  if ! command -v git >/dev/null || ! git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
    die "update needs a git clone of the repository at $REPO_ROOT"
  fi
  [[ -z "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=no)" ]] \
    || die "the checkout has local changes; commit or stash them before updating"
  ensure_idle
  local stamp dest
  stamp="$(date +%Y%m%d-%H%M%S)"
  dest="$STATE_DIR/backups/$stamp"
  step "Backing up before the update ($dest)"
  backup_database "$dest"
  write_file "$BACKUPS/last-update" 600 "STAMP=$stamp
COMMIT=$(git -C "$REPO_ROOT" rev-parse HEAD)"
  local image
  while read -r image; do
    if [[ -n $image ]] && docker image inspect "$image" >/dev/null 2>&1; then
      run docker tag "$image" "${image%:*}:rollback"
    fi
  done < <(compose_images)
  ok "database and current images saved for rollback"
  step "Pulling the latest code"
  run git -C "$REPO_ROOT" pull --ff-only
  local next=(install --yes --home "$MEDIA_HOME")
  if [[ $SKIP_MODELS == 1 ]]; then next+=(--skip-models); fi
  if [[ $FORCE == 1 ]]; then next+=(--force); fi
  if [[ $DRY_RUN == 1 ]]; then
    info "[dry-run] continue with: $PROGRAM ${next[*]}"
    return
  fi
  # git replaced this file; continue with the new installer and the saved settings.
  exec bash "$REPO_ROOT/deploy/install.sh" "${next[@]}"
}

cmd_rollback() {
  [[ -f $BACKUPS/last-update ]] || die "no update to roll back (missing $BACKUPS/last-update)"
  local STAMP="" COMMIT=""
  # shellcheck source=/dev/null
  source "$BACKUPS/last-update"
  ensure_idle
  step "Rolling back to $COMMIT"
  if [[ -n $(git -C "$REPO_ROOT" status --porcelain --untracked-files=no) ]]; then
    die "the checkout has local changes; commit or stash them first"
  fi
  run git -C "$REPO_ROOT" checkout --detach "$COMMIT"
  info "Return to the latest code later with: git -C $REPO_ROOT checkout - && $PROGRAM install"
  local image
  while read -r image; do
    if [[ -n $image ]] && docker image inspect "${image%:*}:rollback" >/dev/null 2>&1; then
      run docker tag "${image%:*}:rollback" "$image"
    fi
  done < <(compose_images)
  if [[ $RESTORE_DB == 1 ]]; then
    local saved="$STATE_DIR/backups/$STAMP/media-lab.db"
    [[ -f $saved ]] || die "missing database backup $saved"
    run "${COMPOSE[@]}" stop agent runtime
    run cp -p "$saved" "$STATE_DIR/media-lab.db"
    run rm -f "$STATE_DIR/media-lab.db-wal" "$STATE_DIR/media-lab.db-shm"
    ok "database restored from $STAMP (work created after the update is no longer listed)"
  fi
  start_stack
}

cmd_renew_cert() {
  [[ -f $CONF ]] || die "no installation found at $MEDIA_HOME"
  parse_origin
  if ! cert_needs_issue; then
    ok "origin certificate valid until $(openssl x509 -in "$SECRETS_DIR/origin.crt" -noout -enddate | cut -d= -f2)"
    return
  fi
  ensure_idle
  issue_cert
  if [[ $(id -u) == 0 ]]; then run chown "$CONTAINER_UID:$CONTAINER_UID" "$SECRETS_DIR/origin.crt"; fi
  if stack_running; then run docker restart "$RUNTIME_CONTAINER" >/dev/null; fi
  ok "web runtime reloaded"
}

require_installed() { [[ -f $CONF && -f $OVERRIDE ]] || die "no installation found at $MEDIA_HOME (run $PROGRAM install, or pass --home)"; }

# ---------------------------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------------------------
case "$COMMAND" in
  list-models)
    list_models
    ;;
  install)
    printf '%sMedia Lab installer%s  %s\n' "$C_ACC$C_B" "$C_0" "$C_DIM$REPO_ROOT$C_0"
    if [[ $DRY_RUN == 1 ]]; then info "Dry run: nothing will be changed."; fi
    ask_origin
    choose_groups
    preflight
    save_settings
    prepare_dirs
    prepare_secrets
    if [[ $SKIP_MODELS == 1 ]]; then info "Skipping models (--skip-models)."; else download_models; fi
    write_override
    if [[ $SKIP_BUILD == 1 ]]; then info "Skipping the image build (--skip-build)."; else build_images; fi
    if [[ $NO_START == 1 ]]; then
      info "Not starting (--no-start). Start later with: $PROGRAM start"
    else
      ensure_idle
      start_stack
      bootstrap_admin
    fi
    summary
    ;;
  models)
    choose_groups
    preflight
    save_settings
    prepare_dirs
    download_models
    ;;
  start)
    require_installed
    start_stack
    ;;
  stop)
    require_installed
    ensure_idle
    run "${COMPOSE[@]}" stop agent runtime comfyui comfyui-gpu1
    ;;
  restart)
    require_installed
    ensure_idle
    run "${COMPOSE[@]}" stop agent runtime comfyui comfyui-gpu1
    start_stack
    ;;
  status)
    require_installed
    "${COMPOSE[@]}" ps
    ;;
  logs)
    require_installed
    exec "${COMPOSE[@]}" logs -f --tail=200 runtime agent
    ;;
  bootstrap)
    require_installed
    bootstrap_admin
    ;;
  update)
    require_installed
    cmd_update
    ;;
  rollback)
    require_installed
    cmd_rollback
    ;;
  renew-cert)
    require_installed
    cmd_renew_cert
    ;;
esac
