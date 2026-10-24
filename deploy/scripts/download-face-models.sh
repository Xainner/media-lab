#!/usr/bin/env bash
# Install the MediaPipe face detector + landmarker (Comfy-Org repack, Apache-2.0) that the core
# ComfyUI MediaPipe nodes load from models/detection, at a pinned revision, verifying its SHA-256.
# The face refine pass reuses the H3 Ref2VA install and the Taomate LoRA from download-swap-models.sh.
set -euo pipefail

ROOT="${MEDIA_LAB_MODELS_DIR:-$HOME/models/media-lab}"
REPO="Comfy-Org/mediapipe"
REV="f787efc1ad99492ec7d5b6564c0dd6c48d84ee49"
TARGET="$ROOT/detection/mediapipe_face_fp32.safetensors"
SHA256="a98c4806081d40eba35102a0f6dc0000c2e1388b72cf24e691703d0605bd888a"

mkdir -p "$(dirname "$TARGET")"
if printf '%s  %s\n' "$SHA256" "$TARGET" | sha256sum --check --status 2>/dev/null; then
  echo "[OK] $(basename "$TARGET") already verified"; exit 0
fi
curl --fail --location --retry 8 --retry-all-errors --continue-at - \
  --output "$TARGET" "https://huggingface.co/$REPO/resolve/$REV/detection/mediapipe_face_fp32.safetensors"
printf '%s  %s\n' "$SHA256" "$TARGET" | sha256sum --check --status \
  || { echo "[FAIL] SHA-256 mismatch: $TARGET" >&2; exit 1; }
echo "[OK] $(basename "$TARGET")"
