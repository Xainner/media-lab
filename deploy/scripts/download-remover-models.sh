#!/usr/bin/env bash
# Install the H3 Person Remover V1 LoRA (Akatz Labs, MiniMax H3 Community License) and the SAM 3.1
# multiplex checkpoint that tracks the person (Meta SAM License, Comfy-Org repack), at pinned revisions,
# verifying every SHA-256. The Ref2VA base, text encoder and VAEs are the existing H3 install. Only the
# LoRA weights are used; the H3 Relay workflow nodes (GPL-3.0) are not installed. About 1.9 GB. Resumable.
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

fetch akatz-ai/MiniMax-H3-Person-Remover-LoRA fe136b3dc93aea993b9f194d48ea9859fdc2de14 \
  H3-Person-Remover-V1.safetensors loras \
  b01dc9fe888c2f4e455a8eb3b4878dfd4038ee0e2320a7b186c7935e65c93ba5
fetch Comfy-Org/sam3.1 7bb8374780a725b4353ed31f3a9395c9742b5621 \
  checkpoints/sam3.1_multiplex_fp16.safetensors checkpoints \
  9ba99c92703c2e8b4f47de2d34a539bb8e18923049e238b780d70dbe6368eb03

echo "Person Remover ready in $ROOT"
