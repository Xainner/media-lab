#!/usr/bin/env bash
# Install Qwen-Image 2.1 Turbo (int8 + BF16, Comfy-Org repackage) and the official
# FlashVSR v1.1 weights (Apache-2.0) at pinned revisions, verifying every SHA-256.
# Resumable: files that already match their hash are skipped.
set -euo pipefail

ROOT="${MEDIA_LAB_MODELS_DIR:-$HOME/models/media-lab}"
QWEN_REPO="Comfy-Org/Qwen-Image-2.1"
QWEN_REV="df94239739eef7205973a145ffa6f441f7b64e84"
VSR_REPO="JunhaoZhuang/FlashVSR-v1.1"
VSR_REV="27561b186ded3402d7c975f4fd722e2885b6135f"

fetch() { # repo revision remote-path local-path sha256
  local repo=$1 rev=$2 remote=$3 target=$4 expected=$5
  mkdir -p "$(dirname "$target")"
  if printf '%s  %s\n' "$expected" "$target" | sha256sum --check --status 2>/dev/null; then
    echo "[OK] $(basename "$target") already verified"; return
  fi
  curl --fail --location --retry 8 --retry-all-errors --continue-at - \
    --output "$target" "https://huggingface.co/$repo/resolve/$rev/$remote"
  printf '%s  %s\n' "$expected" "$target" | sha256sum --check --status \
    || { echo "[FAIL] SHA-256 mismatch: $target" >&2; exit 1; }
  echo "[OK] $(basename "$target")"
}

fetch "$QWEN_REPO" "$QWEN_REV" diffusion_models/qwen_image_2.1_turbo_int8_convrot.safetensors \
  "$ROOT/diffusion_models/qwen_image_2.1_turbo_int8_convrot.safetensors" \
  8144a0182964aa8403ad6dbc011db837304167d235161b9aabaa8532e967314c
fetch "$QWEN_REPO" "$QWEN_REV" diffusion_models/qwen_image_2.1_turbo_bf16.safetensors \
  "$ROOT/diffusion_models/qwen_image_2.1_turbo_bf16.safetensors" \
  8b74237a7f505773e2c66726fa696444b4c704585c93a347cff9044937f7914a

# The FlashVSR node reads <ComfyUI models>/FlashVSR-v1.1 directly.
VSR="$ROOT/FlashVSR-v1.1"
fetch "$VSR_REPO" "$VSR_REV" diffusion_pytorch_model_streaming_dmd.safetensors "$VSR/diffusion_pytorch_model_streaming_dmd.safetensors" \
  bd28180edcf3446c028e32fc6b731a80bf7e4da2ab4caac3186b9499964d37be
fetch "$VSR_REPO" "$VSR_REV" LQ_proj_in.ckpt "$VSR/LQ_proj_in.ckpt" \
  d6d011cdaaba6a52645086caa08fa04124e746f6ca568140a24007591142bfd2
fetch "$VSR_REPO" "$VSR_REV" TCDecoder.ckpt "$VSR/TCDecoder.ckpt" \
  e224bdcf2f52745cbf4d393ff5374c2ba09e90285d5d19062d2bf63b915b6161
fetch "$VSR_REPO" "$VSR_REV" Wan2.1_VAE.pth "$VSR/Wan2.1_VAE.pth" \
  38071ab59bd94681c686fa51d75a1968f64e470262043be31f7a094e442fd981

echo "Qwen-Image 2.1 Turbo and FlashVSR v1.1 ready in $ROOT"
