#!/usr/bin/env bash
# Install the Pika H3 Flex LoRAs (Pika Labs; Model Derivatives of MiniMax H3 under the MiniMax H3
# Community License) for the "flex" video profile: the ComfyUI-format FL2VA (T2VA/I2VA) and Ref2VA
# six-step adapters at a pinned revision, verifying every SHA-256, plus the LICENSE and NOTICE that
# must travel with them. The base checkpoints, text encoder and VAEs are the existing H3 install
# (download-h3-models.sh). About 3.9 GB. Resumable.
set -euo pipefail

ROOT="${MEDIA_LAB_MODELS_DIR:-$HOME/models/media-lab}"
REPO="Pika-Labs/Pika-H3-Flex"
REV="0ddf55ad7067ca1e76812253bd7b4600df87f759"

fetch() { # remote-path local-name sha256
  local target="$ROOT/loras/$2" expected=$3
  mkdir -p "$(dirname "$target")"
  if printf '%s  %s\n' "$expected" "$target" | sha256sum --check --status 2>/dev/null; then
    echo "[OK] $2 already verified"; return
  fi
  curl --fail --location --retry 8 --retry-all-errors --continue-at - \
    --output "$target" "https://huggingface.co/$REPO/resolve/$REV/$1"
  printf '%s  %s\n' "$expected" "$target" | sha256sum --check --status \
    || { echo "[FAIL] SHA-256 mismatch: $target" >&2; exit 1; }
  echo "[OK] $2"
}

fetch comfy/loras/pika_h3_flex_fl2va_comfy_bf16.safetensors pika_h3_flex_fl2va_comfy_bf16.safetensors \
  68783e6447696ec365d13c0554941e070bee4cfea13c37da52498ec4f9a53f89
fetch comfy/loras/pika_h3_flex_ref2va_comfy_bf16.safetensors pika_h3_flex_ref2va_comfy_bf16.safetensors \
  e4d058fbd027377b925a0ee607b514ddd9037873fee3afa05d73b302e6f7f8e1

legal="$ROOT/loras/pika-h3-flex-legal"
mkdir -p "$legal"
for name in LICENSE NOTICE; do
  curl --fail --location --retry 8 --silent --show-error --output "$legal/$name" \
    "https://huggingface.co/$REPO/resolve/$REV/$name"
done
echo "$REPO@$REV" > "$legal/REVISION"

echo "Pika H3 Flex LoRAs ready in $ROOT"
