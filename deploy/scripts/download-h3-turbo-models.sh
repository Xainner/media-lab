#!/usr/bin/env bash
# Install the LightX2V MiniMax-H3 Turbo LoRAs (ModelTC; MiniMax H3 Community License applies) for the
# "turbo" video profile: FL2VA 8-step v1.0 768p (T2VA/I2VA, the one LightX2V Studio serves) and Ref2VA
# 8-step v1.1 768p, at a pinned revision, verifying every SHA-256. The base checkpoints, text encoder
# and VAEs are the existing H3 install (download-h3-models.sh). About 3.9 GB. Resumable.
set -euo pipefail

ROOT="${MEDIA_LAB_MODELS_DIR:-$HOME/models/media-lab}"
REPO="lightx2v/Minimax-h3-Turbo"
REV="30f485ed874aa44c8183348ad361c5eabad318da"

fetch() { # remote-name sha256
  local target="$ROOT/loras/$1" expected=$2
  mkdir -p "$(dirname "$target")"
  if printf '%s  %s\n' "$expected" "$target" | sha256sum --check --status 2>/dev/null; then
    echo "[OK] $1 already verified"; return
  fi
  curl --fail --location --retry 8 --retry-all-errors --continue-at - \
    --output "$target" "https://huggingface.co/$REPO/resolve/$REV/$1"
  printf '%s  %s\n' "$expected" "$target" | sha256sum --check --status \
    || { echo "[FAIL] SHA-256 mismatch: $target" >&2; exit 1; }
  echo "[OK] $1"
}

fetch minimax_h3_fl2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors \
  08cfe946033af7d27719b964b6e0a0e50c32138daabbd6ce4137e23df6bf9980
fetch minimax_h3_ref2v_turbo_8step_v1.1_768p_comfyui_bf16.safetensors \
  e56863a7524e0300729cbb7b64cc8b548d90698c1abbf7d83898b0122fbe1e81

echo "H3 Turbo LoRAs ready in $ROOT"
