#!/usr/bin/env bash
# Install MiniMax H3 Fun ControlNet-Union 2.0 (Alibaba PAI, MiniMax H3 Community License; Comfy-Org's
# pruned INT8 ConvRot repack) and the RT-DETR v4 person detector that SDPose uses on video (Comfy-Org
# SDPose repack), at pinned revisions, verifying every SHA-256. SDPose itself comes from
# download-qwen-control-models.sh; the H3 base, encoder and VAEs are the existing install. About 4.7 GB.
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

fetch Comfy-Org/MiniMax-H3 e5eb578a89295337b8ff433a035929ce0279e0b6 \
  model_patches/minimax_h3_fun_controlnet_union_2.0_pruned_int8_convrot.safetensors model_patches \
  890af58bb350f0c2f6c409b1c67ea8f4196654297d037769b72de1e6f504c612
fetch Comfy-Org/SDPose acb43fbe8142b54d9ebd52b720b81dd4e14c8d81 \
  diffusion_models/rt_detr_v4-x-hgnet_fp16.safetensors diffusion_models \
  581f9af9bbabb664d1891cbccd823308b176ecd409146f954dfa39af3bec2476

echo "H3 video control ready in $ROOT"
