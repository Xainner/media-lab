#!/usr/bin/env bash
set -euo pipefail

repo="Comfy-Org/Qwen-Image-2.1"
revision="9a44dbdb47cefd046be9c0a13476192f34c8db8e"
relative="diffusion_models/qwen_image_2.1_bf16.safetensors"
target="$HOME/models/media-lab/$relative"
expected="89f4158d066cc33906a199fca85634f766892dd78f49b6698dabf187ac86c4bc"
mkdir -p "$(dirname "$target")"
if ! printf '%s  %s\n' "$expected" "$target" | sha256sum --check --status 2>/dev/null; then
  curl --fail --location --retry 8 --retry-all-errors --continue-at - \
    --output "$target" "https://huggingface.co/$repo/resolve/$revision/$relative"
fi
printf '%s  %s\n' "$expected" "$target" | sha256sum --check --status
echo "[OK] BF16 model SHA-256: $expected"
