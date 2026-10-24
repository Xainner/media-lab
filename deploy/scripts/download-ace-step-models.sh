#!/usr/bin/env bash
# Install ACE-Step 1.5 XL Turbo (Apache-2.0, Comfy-Org repack) for the core ComfyUI ACE nodes: the
# 4B XL Turbo DiT, the 0.6B + 4B Qwen planners/encoders and the 1.5 VAE, at a pinned revision,
# verifying every SHA-256. About 20 GB. Resumable.
set -euo pipefail

ROOT="${MEDIA_LAB_MODELS_DIR:-$HOME/models/media-lab}"
REPO="Comfy-Org/ACE-Step-1.5"
REV="6707deb277e9e0907fd9c14ce6b6f1d695c6a3fc"

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

fetch split_files/vae/ace_1.5_vae.safetensors vae \
  6de92e3a862acd287e08b024ac90f0783a8635451b728721a33ff03565bcb2bb
fetch split_files/text_encoders/qwen_0.6b_ace15.safetensors text_encoders \
  fd4590c82153b8ddb67e15a2e7aaa8afa8b83a858c8a9b82a4831063156aa7a7
fetch split_files/text_encoders/qwen_4b_ace15.safetensors text_encoders \
  ffe5ffb855086c2ab55e467e9859fb01894781020a0376484dd19de166b79873
fetch split_files/diffusion_models/acestep_v1.5_xl_turbo_bf16.safetensors diffusion_models \
  86a1afb0a1f711f0e3304ff65d874df3ae6783db683dcf982513fb9b6d14ae71

echo "ACE-Step 1.5 XL Turbo ready in $ROOT"
