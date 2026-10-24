#!/usr/bin/env bash
# Install H3 Character Swap v1.5 (akatz-ai, MiniMax H3 Community License) and the FL2V Turbo
# 8-step 768p LoRA it was tested with (lightx2v), plus the Head Swap v1.0 LoRA (Alissonerdx; not
# covered by that repo's BFS Character Swap license) and the Taomate 3-step LoRA its workflow uses,
# at pinned revisions, verifying every SHA-256. The Ref2VA base, text encoder and VAEs are the
# existing H3 install. Resumable.
set -euo pipefail

ROOT="${MEDIA_LAB_MODELS_DIR:-$HOME/models/media-lab}"
SWAP_REPO="akatz-ai/MiniMax-H3-Character-Swap-LoRA"
SWAP_REV="96ea3407b230b6f7df71c58c70e31df96bd7e533"
TURBO_REPO="lightx2v/Minimax-h3-Turbo"
TURBO_REV="30f485ed874aa44c8183348ad361c5eabad318da"
HEAD_REPO="Alissonerdx/Minimax-H3-ComfyUI"
HEAD_REV="37d7d8b302ec4168ff30467c900c588db253cad9"
TAOMATE_REPO="Kijai/MiniMax-H3_comfy"
TAOMATE_REV="098f8c48fccead9a93191c166ca31a130659d3bd"

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

fetch "$SWAP_REPO" "$SWAP_REV" h3_character_swap_v1.5.safetensors \
  "$ROOT/loras/h3_character_swap_v1.5.safetensors" \
  8f2c3c3eba161df8d0c6099598b4730f641f5ce01e04cd16d2427cff8a35218f
fetch "$TURBO_REPO" "$TURBO_REV" minimax_h3_fl2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors \
  "$ROOT/loras/minimax_h3_fl2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors" \
  08cfe946033af7d27719b964b6e0a0e50c32138daabbd6ce4137e23df6bf9980
fetch "$HEAD_REPO" "$HEAD_REV" loras/minimax_h3_head_swap_v1.0_r32.safetensors \
  "$ROOT/loras/minimax_h3_head_swap_v1.0_r32.safetensors" \
  ea97bd1a8178460661055784d63b4cb560732196fd15d5d7f33bfd214b65ab00
fetch "$TAOMATE_REPO" "$TAOMATE_REV" loras/minimax_h3_taomate_3step_lora_avg_rank_19_bf16.safetensors \
  "$ROOT/loras/minimax_h3_taomate_3step_lora_avg_rank_19_bf16.safetensors" \
  de9663d974a884b477556748239c6f28239f7ca1825be270f98f023ff5dab6a7

echo "H3 Character Swap and Head Swap ready in $ROOT/loras"
