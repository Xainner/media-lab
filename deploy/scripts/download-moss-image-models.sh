#!/usr/bin/env bash
# Install MOSS-Image SFT (OpenMOSS, Apache-2.0, Comfy-Org repack) for the core ComfyUI nodes: the
# int8 ConvRot 5B DiT, the Qwen3.5 9B w4a8 text encoder and the small FLUX.2 VAE, at a pinned
# revision, verifying every SHA-256. About 13 GB. Resumable.
set -euo pipefail

ROOT="${MEDIA_LAB_MODELS_DIR:-$HOME/models/media-lab}"
REPO="Comfy-Org/MOSS-Image"
REV="24147db865fcdc207270f844777587223fed8d6e"

fetch() { # remote-path local-dir sha256
  local remote=$1 target="$ROOT/$2/$(basename "$1")" expected=$3
  mkdir -p "$(dirname "$target")"
  if printf '%s  %s\n' "$expected" "$target" | sha256sum --check --status 2>/dev/null; then
    echo "[OK] $(basename "$target") already verified"; return
  fi
  curl --fail --location --retry 8 --retry-all-errors --continue-at - \
    --output "$target" "https://huggingface.co/$REPO/resolve/$REV/$remote"
  printf '%s  %s\n' "$expected" "$target" | sha256sum --check --status \
    || { echo "[FAIL] SHA-256 mismatch: $target" >&2; exit 1; }
  echo "[OK] $(basename "$target")"
}

fetch vae/flux2-vae_small.safetensors vae \
  d8d52ba036475f5fb07c8b435e176d3d97ebfa82f0d1a1c317f9cc1e25bd013b
fetch text_encoders/qwen3.5_9b_w4a8_gptq.safetensors text_encoders \
  4cc6a1543ad2061806da46f35f90cadb4801dcba246c44782cf42ec0feb6407c
fetch diffusion_models/moss_image_sft_int8_convrot.safetensors diffusion_models \
  b4d1475bc7eeffd7b809e82ea13a1fba1fb85c4e18365af3813722faa5c0fe4f

echo "MOSS-Image SFT ready in $ROOT"
