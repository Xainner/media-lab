#!/usr/bin/env bash
# Install the shared ComfyUI files Kandinsky 6 and SCAIL-2 read from /shared-models, from the
# Comfy-Org repackages at pinned revisions, verifying every SHA-256:
#   kandinsky6  Qwen2.5-VL 7B FP8 text encoder (Apache-2.0), about 9.4 GB
#   scail2      Wan 2.1 UMT5-XXL FP8 text encoder and VAE (Apache-2.0), about 7.0 GB
# Pass the groups to install (default: both). Resumable.
set -euo pipefail

SHARED="${H3_SHARED_ROOT:-$HOME/models/comfyui/models}"

fetch() { # repo revision remote-path local-dir sha256
  local repo=$1 rev=$2 remote=$3 target="$SHARED/$4/${3##*/}" expected=$5
  mkdir -p "$SHARED/$4"
  if printf '%s  %s\n' "$expected" "$target" | sha256sum --check --status 2>/dev/null; then
    echo "[OK] $4/${3##*/} already verified"; return
  fi
  curl --fail --location --retry 8 --retry-all-errors --continue-at - \
    --output "$target" "https://huggingface.co/$repo/resolve/$rev/$remote"
  printf '%s  %s\n' "$expected" "$target" | sha256sum --check --status \
    || { echo "[FAIL] SHA-256 mismatch: $target" >&2; exit 1; }
  echo "[OK] $4/${3##*/}"
}

kandinsky6() {
  fetch Comfy-Org/Qwen-Image_ComfyUI 1f12b17be14c89b026c51a91d67c32f84bb047bc \
    split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors text_encoders \
    cb5636d852a0ea6a9075ab1bef496c0db7aef13c02350571e388aea959c5c0b4
}

scail2() {
  fetch Comfy-Org/Wan-2.1 123acf1cc74bccbb9bfff8ac1ee72edc08c2341d \
    split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors text_encoders \
    c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68
  fetch Comfy-Org/Wan-2.1 123acf1cc74bccbb9bfff8ac1ee72edc08c2341d \
    split_files/vae/wan_2.1_vae.safetensors vae \
    2fc39d31359a4b0a64f55876d8ff7fa8d780956ae2cb13463b0223e15148976b
}

groups=("$@")
[[ $# -gt 0 ]] || groups=(kandinsky6 scail2)
for group in "${groups[@]}"; do
  case "$group" in
    kandinsky6|scail2) "$group" ;;
    *) echo "usage: $0 [kandinsky6] [scail2]" >&2; exit 2 ;;
  esac
done

echo "Shared ComfyUI files ready in $SHARED"
