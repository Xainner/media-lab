#!/usr/bin/env bash
# Install only the missing native YuE2 files. H3 weights are reused read-only
# from $HOME/models/comfyui/models via extra_model_paths.yaml.
set -euo pipefail

ROOT="${MEDIA_LAB_MODELS_DIR:-$HOME/models/media-lab}"
HF="${HF_CMD:-${HOME}/.local/bin/hf}"
REV="2f76ca75e6ee094169de899cc7fc99d6887e2196"
test -x "$HF" || { echo "hf CLI missing: $HF" >&2; exit 1; }
mkdir -p "$ROOT/checkpoints" "$ROOT/audio_encoders"

for file in checkpoints/yue2_3b_int8_convrot.safetensors audio_encoders/sheetsage2_bf16.safetensors; do
  if [[ ! -s "$ROOT/$file" ]]; then
    "$HF" download Comfy-Org/YuE2 "$file" --revision "$REV" --local-dir "$ROOT"
  fi
  test -s "$ROOT/$file"
done

echo "YuE2 native weights ready in $ROOT"
