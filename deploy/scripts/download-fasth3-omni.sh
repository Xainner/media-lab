#!/usr/bin/env bash
# Install FastH3 Omni 8-step (FastVideo + Nuva Lab DMD distillation of MiniMax H3 Ref2VA; MiniMax H3
# Community License) as the pruned INT8 ConvRot ComfyUI checkpoint, at a pinned revision, verifying its
# SHA-256. The text encoder and VAEs are the existing H3 install. About 22 GB. Resumable.
set -euo pipefail

ROOT="${MEDIA_LAB_MODELS_DIR:-$HOME/models/media-lab}"
REPO="FastVideo/FastH3-Omni-Comfy"
REV="82eff2a6eee6c962846879f4bab52610a4df24d3"
NAME="fasth3_omniref_8step_pruned_int8_convrot.safetensors"
SHA="851b2dc9670ed864b7f1e951ac9da047d83b1c04ded9bfcc1a9e5bba0ee33f80"
TARGET="$ROOT/diffusion_models/$NAME"

mkdir -p "$(dirname "$TARGET")"
if printf '%s  %s\n' "$SHA" "$TARGET" | sha256sum --check --status 2>/dev/null; then
  echo "[OK] $NAME already verified"; exit 0
fi
curl --fail --location --retry 8 --retry-all-errors --continue-at - \
  --output "$TARGET" "https://huggingface.co/$REPO/resolve/$REV/diffusion_models/$NAME"
printf '%s  %s\n' "$SHA" "$TARGET" | sha256sum --check --status \
  || { echo "[FAIL] SHA-256 mismatch: $TARGET" >&2; exit 1; }
echo "[OK] $NAME"
echo "FastH3 Omni ready in $ROOT"
