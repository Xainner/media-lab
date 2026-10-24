#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MODEL_ROOT="$HOME/models/media-lab"
REV="7562a343278731b94b18803d7de6d660cb56f841"

relative="text_encoders/qwen3vl_8b_w4a8.safetensors"
target="$MODEL_ROOT/$relative"
if [ ! -s "$target" ]; then
  url="https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/$REV/$relative?download=true"
  if command -v aria2c >/dev/null; then
    aria2c --continue=true --max-connection-per-server=8 --split=8 \
      --min-split-size=64M --file-allocation=none --auto-file-renaming=false \
      --dir="$(dirname "$target")" --out="$(basename "$target").part" "$url"
    mv "$target.part" "$target"
  elif command -v hf >/dev/null; then
    hf download Comfy-Org/Qwen-Image-2.1 "$relative" \
      --revision "$REV" --local-dir "$MODEL_ROOT"
  else
    curl --fail --location --retry 8 --retry-all-errors --continue-at - \
      --output "$target.part" \
      "$url"
    mv "$target.part" "$target"
  fi
fi
echo '7754425e55e7bea2bfde4dde59a4cc236cb44e5ee9c215ea66ef8d47012824eb  text_encoders/qwen3vl_8b_w4a8.safetensors' \
  >> "$MODEL_ROOT/checksums.sha256"
(cd "$MODEL_ROOT" && sha256sum -c --ignore-missing checksums.sha256)

python3 - "$MODEL_ROOT" <<'PY'
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
path = root / "text_encoders/qwen3vl_8b_w4a8.safetensors"
digest = hashlib.sha256()
with path.open("rb") as stream:
    for chunk in iter(lambda: stream.read(16 * 1024 * 1024), b""):
        digest.update(chunk)
manifest_path = root / "bundle-manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["artifacts"] = [item for item in manifest["artifacts"] if item["path"] != str(path.relative_to(root)).replace("\\", "/")]
manifest["artifacts"].append({
    "path": "text_encoders/qwen3vl_8b_w4a8.safetensors",
    "bytes": path.stat().st_size,
    "sha256": digest.hexdigest(),
    "fallback": True,
})
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
PY

python3 - "$ROOT/deploy/.env" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
lines = p.read_text().splitlines() if p.exists() else []
key = "QWEN21_ENCODER="
lines = [line for line in lines if not line.startswith(key)]
lines.append(key + "qwen3vl_8b_w4a8.safetensors")
p.write_text("\n".join(lines) + "\n")
PY
echo "W4A8 encoder selected. Recreate the runtime to apply it."
