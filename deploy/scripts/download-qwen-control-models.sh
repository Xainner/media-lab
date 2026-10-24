#!/usr/bin/env bash
# Install the Qwen-Image 2.1 extras for the core ComfyUI nodes: the alibaba-pai Fun ControlNet Union
# (qwen-research licence, Comfy-Org int8 ConvRot repack) as a model patch, and the QMA camera-angles
# edit LoRA (gribbliest, Apache-2.0), plus depth and pose estimators. Pinned revisions, every SHA-256
# verified. About 7.4 GB. Resumable.
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

fetch Comfy-Org/Qwen-Image-2.1 0217efd1d9c9452e84f6448903d6e21bfa171ffd \
  model_patches/qwen_image_2.1_fun_controlnet_union_int8_convrot.safetensors model_patches \
  07aa961570ac0e03d4ca936aecd76854d077a33cde69b5092399afba01b3715d
fetch gribbliest/qwen-image-2.1-qma-camera-angles 13007eec2648c09529e930164c2ccc9c8c12428c \
  qwen-image-2.1-qma-camera-angles.safetensors loras \
  ad2c20e0e103b6ad3ffffc56ab4e89c0822263c488aa4dd70e7e03091ff37b8d
# Control maps from a plain photo: Depth Anything 3 Mono-Large (Apache-2.0) and SDPose Wholebody (MIT).
fetch Comfy-Org/Depth-Anything-3 1aaeea516f22fb2f4c7fae761c8ed470c6cf9f93 \
  geometry_estimation/depth_anything_3_mono_large.safetensors geometry_estimation \
  9b44eda5bedba5b4e125686fdb79d1db309c1b9785277576eb930f885b008f96
fetch Comfy-Org/SDPose acb43fbe8142b54d9ebd52b720b81dd4e14c8d81 \
  checkpoints/sdpose_wholebody_fp16.safetensors checkpoints \
  63d01f9a7494560693b24767f4469d59c9d3266b31ff0a253e74d1e611442721

echo "Qwen ControlNet Union and camera angles ready in $ROOT"
