#!/usr/bin/env bash
# Install the Hybrid Demucs weights behind torchaudio's HDEMUCS_HIGH_MUSDB_PLUS bundle (Meta, MIT)
# for the in-house Media Lab Stems node, verifying their SHA-256. About 335 MB. Resumable.
set -euo pipefail

ROOT="${MEDIA_LAB_MODELS_DIR:-$HOME/models/media-lab}"
NAME="hdemucs_high_trained.pt"
SHA="a004b2790d73ffeaa535db458a1a79b539dfdbafbccc31f275d07e632ebd7816"
TARGET="$ROOT/stems/$NAME"

mkdir -p "$(dirname "$TARGET")"
if printf '%s  %s\n' "$SHA" "$TARGET" | sha256sum --check --status 2>/dev/null; then
  echo "[OK] $NAME already verified"; exit 0
fi
curl --fail --location --retry 8 --retry-all-errors --continue-at - \
  --output "$TARGET" "https://download.pytorch.org/torchaudio/models/$NAME"
printf '%s  %s\n' "$SHA" "$TARGET" | sha256sum --check --status \
  || { echo "[FAIL] SHA-256 mismatch: $TARGET" >&2; exit 1; }
echo "[OK] $NAME"
echo "Stems model ready in $ROOT"
