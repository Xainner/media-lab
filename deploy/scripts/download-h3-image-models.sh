#!/usr/bin/env bash
# Install MiniMax-H3-Image (MiniMax-H3-Image Community License, Comfy-Org repack) for the core
# ComfyUI nodes: the pruned int8 ConvRot DiT and the image VAE, plus the prompt-expansion task
# prompts of MiniMax-H3-Image-PE, at pinned revisions, verifying every SHA-256. The text encoder
# (qwen3vl_32b_minimax_h3_nvfp4_awq) comes with the h3 group and the expander
# (qwen3.5_9b_w4a8_gptq) with the moss group. About 22 GB. Resumable.
#
# Licence: providing this model to third parties (web, API or any remote access) needs a prior
# written authorization from MiniMax (section IV.1); see the LICENSE in MiniMaxAI/MiniMax-H3-Image.
set -euo pipefail

ROOT="${MEDIA_LAB_MODELS_DIR:-$HOME/models/media-lab}"

fetch() { # repo revision remote-path local-dir sha256
  local repo=$1 rev=$2 remote=$3 expected=$5
  local target="$ROOT/$4/$(basename "$remote")"
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

IMAGE="Comfy-Org/MiniMax-H3-Image"
IMAGE_REV="892de7cb61df49753bf15145a711154803a355cb"
PE="MiniMaxAI/MiniMax-H3-Image-PE"
PE_REV="35603d4b63949afa12cb098227fffefedf081afa"

fetch "$PE" "$PE_REV" prompt/t2i/system_prompt.txt prompts/h3_image/t2i \
  818ab3f652ec36b3b489b55c29f072f87e14af703cd11a4f3bff75f423d0beac
fetch "$PE" "$PE_REV" prompt/t2i/task_prompt.txt prompts/h3_image/t2i \
  890213ad61e143bbd5b7906a802430296e82ca5c61ba16df717dcef5477bbcf4
fetch "$PE" "$PE_REV" prompt/edit/task_prompt.txt prompts/h3_image/edit \
  c5695dbfc07a9e65555cef67d92467c613371cc2039b96f057022246a30a57b2
fetch "$IMAGE" "$IMAGE_REV" vae/minimax_h3_image_vae_fp16.safetensors vae \
  d80e9c2e5cfc9844869961ff5a58c9a9e52182df6bfb30b26018dd7f348721af
fetch "$IMAGE" "$IMAGE_REV" diffusion_models/minimax_h3_image_pruned_int8_convrot.safetensors diffusion_models \
  83eb140f1ff95c068f8a6886e6d3f3d0d4ab2e07bb2fe6d2ef992a51146ee622

echo "MiniMax-H3-Image ready in $ROOT"
