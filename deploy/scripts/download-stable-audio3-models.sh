#!/usr/bin/env bash
# Install Stable Audio 3 (Stability AI Community License, Comfy-Org repack) for the core ComfyUI
# nodes: Medium (instrumental music up to 6:20) and Small SFX (sound effects), the shared
# T5Gemma text encoder, and Qwen3.5 2B for the official category-aware prompt expansion. Pinned
# revisions, every SHA-256 verified. About 17.2 GB. Resumable.
set -euo pipefail

ROOT="${MEDIA_LAB_MODELS_DIR:-$HOME/models/media-lab}"
TOKEN_FILE="${HF_TOKEN_FILE:-$HOME/.cache/huggingface/token}"
AUTH=()
[[ -r "$TOKEN_FILE" ]] && AUTH=(--header "Authorization: Bearer $(<"$TOKEN_FILE")")

fetch() { # remote-path local-dir sha256 (uses the current REPO and REV)
  local remote=$1 target="$ROOT/$2/$(basename "$1")" expected=$3
  mkdir -p "$(dirname "$target")"
  if printf '%s  %s\n' "$expected" "$target" | sha256sum --check --status 2>/dev/null; then
    echo "[OK] $2/$(basename "$target") already verified"; return
  fi
  curl --fail --location --retry 8 --retry-all-errors --continue-at - "${AUTH[@]}" \
    --output "$target" "https://huggingface.co/$REPO/resolve/$REV/$remote"
  printf '%s  %s\n' "$expected" "$target" | sha256sum --check --status \
    || { echo "[FAIL] SHA-256 mismatch: $target" >&2; exit 1; }
  echo "[OK] $2/$(basename "$target")"
}

REPO="Comfy-Org/stable-audio-3"
REV="75aad8836271cb5a5123fb58304fae5d3bb4b0f9"
fetch checkpoints/stable_audio_3_medium.safetensors checkpoints \
  48d9c65e290e7bcd5194e0633bfc2424a59ee9683f5c2d58762d997b7d8ce0b5
fetch checkpoints/stable_audio_3_small_sfx.safetensors checkpoints \
  ed9cf1b6172f1a8c2921a9560c21109ff3239524563ced9dce6dcdef41e2f515
fetch text_encoders/t5gemma_b_b_ul2.safetensors text_encoders \
  1e1eba25be8872edb0d3c6335c6658fd6388e7b14b60da6e454e404cfcd8150e
REPO="Comfy-Org/Qwen3.5"
REV="5d50a2252bf1bcd49e5fee9b5f296986d442682b"
fetch text_encoders/qwen3.5_2b_bf16.safetensors text_encoders \
  aa33250c4fc64891ddfaba3a314fd9542ea371843c387178b425fbcc5ed680b1
echo "Stable Audio 3 ready in $ROOT"
