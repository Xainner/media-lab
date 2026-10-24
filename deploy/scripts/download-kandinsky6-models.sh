#!/usr/bin/env bash
# Install Kandinsky 6.0 Lite Distill (Kandinsky Lab, MIT) for the pinned kandinsky6 ComfyUI
# extension: the 10-step transformer, CLIP-L and the HunyuanVideo VAE, the MMAudio 44k audio VAE
# (CC-BY-NC-4.0, personal use) and the BigVGAN v2 vocoder (MIT). The Qwen2.5-VL text encoder
# (/shared-models) comes from download-shared-comfy-models.sh, the Qwen3.5 9B prompt writer from
# download-moss-image-models.sh.
# Pinned revisions, every SHA-256 verified. About 8.8 GB. Resumable.
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

REPO="kandinskylab/Kandinsky-6.0-Lite-distill-5s-Diffusers"
REV="4c487e8b4aeeb9059e5a77905aa2ddb59ec28f81"
fetch transformer/diffusion_pytorch_model.safetensors diffusion_models/Kandinsky-6.0-Lite-distill-5s-Diffusers/transformer \
  b1b52668561d9138d93bb4da13c9999e615bf569be9f8cf65732d54652447f53
fetch transformer/config.json diffusion_models/Kandinsky-6.0-Lite-distill-5s-Diffusers/transformer \
  4de144f71528df712a020dabc79001aa4d353fd807a6456930397b115567992c
REPO="Comfy-Org/HunyuanVideo_repackaged"
REV="533a43813f01517d9e624f9e824a85bb94094120"
fetch split_files/text_encoders/clip_l.safetensors text_encoders \
  660c6f5b1abae9dc498ac2d21e1347d2abdb0cf6c0c0c8576cd796491d9a6cdd
fetch split_files/vae/hunyuan_video_vae_bf16.safetensors vae \
  e8f8553275406d84ccf22e7a47601650d8f98bdb8aa9ccfdd6506b57a9701aed
REPO="hkchengrex/MMAudio"
REV="eb13a1a98fdbec91753775c57b074ccdfc60587c"
fetch ext_weights/v1-44.pth audio_vae \
  ab6cc15dc31947675f75c950c41f4dcfd0d6d1817555ac871f809ec388e4651a
REPO="nvidia/bigvgan_v2_44khz_128band_512x"
REV="95a9d1dcb12906c03edd938d77b9333d6ded7dfb"
fetch bigvgan_generator.pt audio_vae/bigvgan_vocoder \
  d9fe7ec6bd0b44ed9d66973d5012d8181c1570b01e5c72df51973e241dccd357
fetch config.json audio_vae/bigvgan_vocoder \
  65b7f487bfaf15256056a75f6667ef5f640214c981922a111927873705ea4ddb
echo "Kandinsky 6.0 Lite Distill ready in $ROOT"
