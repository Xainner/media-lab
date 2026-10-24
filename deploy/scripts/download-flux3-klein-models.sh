#!/usr/bin/env bash
# Install FLUX 3 Image Klein (Black Forest Labs, FLUX Kommunity License) for the core ComfyUI
# nodes: the 16-step distilled and the 50-step base int8 ConvRot DiTs, the Qwen3-VL 4B text
# encoder, the official Qwen3.5 9B w4a8 prompt upsampler and the FLUX.2 VAE. The repository is
# gated: accept its licence on Hugging Face with the account whose token is in
# ~/.cache/huggingface/token (or HF_TOKEN_FILE), with gated-repo read access. Pinned revision,
# every SHA-256 verified. About 23.6 GB. Resumable.
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

REPO="black-forest-labs/flux-3-image-klein-comfy"
REV="feef60b0aaf63a4773ace96636ebbcf43b881312"
fetch diffusion_models/flux3-image-klein-int8-convrot.safetensors diffusion_models \
  847d8933548afd93df4af2cac2498e70891bf28d9dae06d695f536992e168fe2
fetch diffusion_models/flux3-image-klein-base-int8-convrot.safetensors diffusion_models \
  8949ecfc1bf3871b08be02cf43ec7276a4914e1a86eade6b5eb8f4204426bc92
fetch text_encoders/qwen3vl_4b_int8_convrot.safetensors text_encoders \
  32de113cbf8282b02cbff0794b637b9d6676da09314a1db5a30bcea9bf4ee01c
fetch text_encoders/qwen3.5_9b_flux3_prompt_upsampler_w4a8.safetensors text_encoders \
  e5d85a7421d197bf5a12474511936ecabce19a833252f16e9310a983194a4458
fetch vae/flux2-vae.safetensors vae \
  868fe7b343cc8f3a19dbcfcafbc3d5f888802be3f89bd81b65b3621a066ce8f3
echo "FLUX 3 Image Klein ready in $ROOT"
