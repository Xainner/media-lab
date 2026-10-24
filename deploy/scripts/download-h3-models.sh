#!/usr/bin/env bash
# Install the MiniMax H3 weights at the host paths compose.yml/compose.web.yml mount.
# On Saturno these already exist (shared with other ComfyUI stacks and Maestro);
# this script is for rebuilding the stack on a new host. Pinned and SHA-verified.
set -euo pipefail

SHARED="${H3_SHARED_ROOT:-$HOME/models/comfyui/models}"
FUSED="${H3_FUSED_HOST_ROOT:-/opt/maestro/repo/app/ckpts}"

download() {  # repo revision remote-path target sha256
  local repo="$1" rev="$2" remote="$3" target="$4" sha="$5"
  if [ -s "$target" ]; then
    echo "[cached] $target"
  else
    mkdir -p "$(dirname "$target")"
    local url="https://huggingface.co/$repo/resolve/$rev/$remote?download=true"
    if command -v aria2c >/dev/null; then
      aria2c --continue=true --max-connection-per-server=16 --split=16 \
        --min-split-size=64M --file-allocation=none --auto-file-renaming=false \
        --dir="$(dirname "$target")" --out="$(basename "$target").part" "$url"
    else
      curl --fail --location --retry 8 --retry-all-errors --continue-at - \
        --output "$target.part" "$url"
    fi
    mv "$target.part" "$target"
  fi
  echo "$sha  $target" | sha256sum -c -
}

# H3 Base profile + shared conditioner/audio VAE (Comfy-Org repackage).
H3="Comfy-Org/MiniMax-H3"
H3_REV="0543966fbdce5ba05709a8f2031c94bdba629b4a"
download "$H3" "$H3_REV" diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors \
  "$SHARED/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors" \
  e889202c41dafb67b10d67b97f0d8541508036a6090af23425a5c2615d03c47a
download "$H3" "$H3_REV" diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors \
  "$SHARED/diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors" \
  9255f52b6677845ad238f20dfaafa94727053694127ab7f255c048f0f9365779
download "$H3" "$H3_REV" text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors \
  "$SHARED/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors" \
  35a88d51044231fe332301d7a62aa81e3f2cba62febeb446e2c1e3e0ef76f2c6
download "$H3" "$H3_REV" vae/minimax_h3_video_vae_fp16.safetensors \
  "$SHARED/vae/minimax_h3_video_vae_fp16.safetensors" \
  7c1f131492e7eddacaac9069a61b81bdd39de5cc96561e677c5eab1cdce5e522
download "$H3" "$H3_REV" vae/minimax_h3_audio_vae_fp32.safetensors \
  "$SHARED/vae/minimax_h3_audio_vae_fp32.safetensors" \
  8e505d95dd1561d47abd43d4238fd40d9bb1ae9e147ed0a4cba778d76ae4db48

# H3 Fused Turbo profile (see docs/H3-FUSED-0.7.1.md for licence/notice).
download MATLOWAI/minimax-h3-fused-turbo-int8-convrot 3b51096a1bf67608d98131116558202208fcf195 \
  diffusion_models/minimax_h3_fused_refdelta_r1024_turbo8_mystic07_int8_convrot.safetensors \
  "$FUSED/minimax_h3_fused_refdelta_r1024_turbo8_mystic07_int8_convrot.safetensors" \
  4262e4e9963c553fa00016bbe83961407a4fc0a888be95fd836c8d4f2304e48b
download Kijai/MiniMax-H3-experimental a3e7d8da4ae7ba8df0779094cf5ab9d6ee855fe4 \
  minimax_h3_video_vae_int8_convrot.safetensors \
  "$FUSED/minimax_h3/vae/minimax_h3_video_vae_int8_convrot.safetensors" \
  9bb2d96f218c76babd85e0611b85ca8fb330a90546c01a0005e8a58a59593410

echo "MiniMax H3 weights ready (shared: $SHARED, fused: $FUSED)"
