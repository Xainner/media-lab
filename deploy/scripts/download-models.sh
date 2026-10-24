#!/usr/bin/env bash
set -euo pipefail

REPO="Comfy-Org/Qwen-Image-2.1"
REV="7562a343278731b94b18803d7de6d660cb56f841"
ROOT="$HOME/models/media-lab"
mkdir -p "$ROOT"/{diffusion_models,text_encoders,vae}

download() {
  local relative="$1"
  local target="$ROOT/$relative"
  if [ -s "$target" ]; then
    echo "[cached] $relative"
    return
  fi
  local url="https://huggingface.co/$REPO/resolve/$REV/$relative?download=true"
  if command -v aria2c >/dev/null; then
    aria2c --continue=true --max-connection-per-server=16 --split=16 \
      --min-split-size=64M --file-allocation=none --auto-file-renaming=false \
      --dir="$(dirname "$target")" --out="$(basename "$target").part" "$url"
    mv "$target.part" "$target"
  elif command -v hf >/dev/null; then
    hf download "$REPO" "$relative" --revision "$REV" --local-dir "$ROOT"
  else
    command -v curl >/dev/null || { echo "Install hf or curl first."; exit 2; }
    curl --fail --location --retry 8 --retry-all-errors --continue-at - \
      --output "$target.part" \
      "$url"
    mv "$target.part" "$target"
  fi
}

download text_encoders/qwen3vl_8b_int8_convrot.safetensors
download diffusion_models/qwen_image_2.1_int8_convrot.safetensors
download vae/qwen_image_2.1_vae_bf16.safetensors

cd "$ROOT"
printf '%s  %s\n' \
  'cb74113cb03faecd79611b01fd7fd642f0aa60d6f0b95086abee214d75eaa57d' 'diffusion_models/qwen_image_2.1_int8_convrot.safetensors' \
  '8bfd0f6e12abf2d2d697ecc888e5e90b0d6741d6708f05799f53afa560452e8f' 'text_encoders/qwen3vl_8b_int8_convrot.safetensors' \
  'bb21f7473051e1ac368515dd3f2e15cd44d7a11748ee8823e1ddca3e4876b7c9' 'vae/qwen_image_2.1_vae_bf16.safetensors' > checksums.sha256
sha256sum -c checksums.sha256

python3 - "$ROOT" "$REPO" "$REV" <<'PY'
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
paths = [
    "diffusion_models/qwen_image_2.1_int8_convrot.safetensors",
    "text_encoders/qwen3vl_8b_int8_convrot.safetensors",
    "vae/qwen_image_2.1_vae_bf16.safetensors",
]
manifest = {
    "bundle": "qwen-image-2.1",
    "source_repo": sys.argv[2],
    "source_revision": sys.argv[3],
    "license": {
        "id": "qwen-research",
        "commercial_use": False,
        "url": "https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE",
    },
    "artifacts": [],
}
for relative in paths:
    path = root / relative
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    manifest["artifacts"].append({
        "path": relative,
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    })
(root / "bundle-manifest.json").write_text(
    json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
)
PY

echo "Bundle manifest: $ROOT/bundle-manifest.json"
