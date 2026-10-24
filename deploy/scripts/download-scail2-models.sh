#!/usr/bin/env bash
# Install SCAIL-2 character replacement (Zhipu AI, MIT; Comfy-Org INT8 ConvRot repack and DPO LoRA), the
# LightX2V Wan 2.1 I2V step-distill LoRA (Kijai repack) and the Wan 2.1 CLIP vision encoder, at pinned
# revisions, verifying every SHA-256. The Wan 2.1 UMT5 text encoder and VAE come from the shared ComfyUI
# models (download-shared-comfy-models.sh); SAM 3.1 from download-remover-models.sh. About 19.9 GB.
set -euo pipefail

ROOT="${MEDIA_LAB_MODELS_DIR:-$HOME/models/media-lab}"

fetch() { # repo revision remote-path local-dir sha256
  local repo=$1 rev=$2 remote=$3 target="$ROOT/$4/$(basename "$3")" expected=$5
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

fetch Comfy-Org/SCAIL-2 fe3c728bc793ba21ca674688f822afb709ad44fb \
  diffusion_models/wan2.1_14B_SCAIL_2_int8_convrot.safetensors diffusion_models \
  a2114c18a811243185f103765cd5004b61652141aa55a9016d3bdceebceb5ac0
fetch Comfy-Org/SCAIL-2 fe3c728bc793ba21ca674688f822afb709ad44fb \
  loras/wan2.1_SCAIL_2_DPO_lora_bf16.safetensors loras \
  b106522036f64e50f5f8ae3b808973515ff442cc2fac27b65d875eafb95b89e2
fetch Kijai/WanVideo_comfy 8260d429d19fd7a72304cad059160b95d843913f \
  Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors loras \
  85c4a61c30e0497aa44b91d93a893b624708461a56fe5485183b28fa07e2dfb3
fetch Comfy-Org/Wan-2.1 123acf1cc74bccbb9bfff8ac1ee72edc08c2341d \
  split_files/clip_vision/clip_vision_h.safetensors clip_vision \
  64a7ef761bfccbadbaa3da77366aac4185a6c58fa5de5f589b42a65bcc21f161

echo "SCAIL-2 ready in $ROOT"
