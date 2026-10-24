#!/usr/bin/env bash
# Install Qwen3-TTS 12Hz 1.7B (Qwen, Apache-2.0) for the in-house media_lab_tts node: Base (voice
# cloning from a reference clip, used only with the speaker's permission), CustomVoice (nine preset
# speakers with style instructions) and VoiceDesign (a voice described in words). Each folder is a
# full snapshot at a pinned revision with its own 12 Hz speech tokenizer; every SHA-256 is verified.
# About 13.6 GB. Resumable.
set -euo pipefail

ROOT="${MEDIA_LAB_MODELS_DIR:-$HOME/models/media-lab}"
TOKEN_FILE="${HF_TOKEN_FILE:-$HOME/.cache/huggingface/token}"
AUTH=()
[[ -r "$TOKEN_FILE" ]] && AUTH=(--header "Authorization: Bearer $(<"$TOKEN_FILE")")

fetch() { # remote-path local-dir sha256 (uses the current REPO and REV)
  local remote=$1 target="$ROOT/$2/$(basename "$1")" expected=$3
  mkdir -p "$(dirname "$target")"
  if printf '%s  %s\n' "$expected" "$target" | sha256sum --check --status 2>/dev/null; then
    echo "[OK] $2/$(basename "$target") already verified"; return
  fi
  curl --fail --location --retry 8 --retry-all-errors --continue-at - "${AUTH[@]}" \
    --output "$target" "https://huggingface.co/$REPO/resolve/$REV/$remote"
  printf '%s  %s\n' "$expected" "$target" | sha256sum --check --status \
    || { echo "[FAIL] SHA-256 mismatch: $target" >&2; exit 1; }
  echo "[OK] $2/$(basename "$target")"
}

REPO="Qwen/Qwen3-TTS-12Hz-1.7B-Base"
REV="fd4b254389122332181a7c3db7f27e918eec64e3"
fetch config.json tts/Qwen3-TTS-12Hz-1.7B-Base \
  b4f01752d15a488abde3e1ab44723ae4f4b9e68a4037257b098b3737893cc1f9
fetch generation_config.json tts/Qwen3-TTS-12Hz-1.7B-Base \
  f1b90b4513f3b34c62851049e2492d7b4c5940daf1276f89c82b8ef04127f3aa
fetch merges.txt tts/Qwen3-TTS-12Hz-1.7B-Base \
  599bab54075088774b1733fde865d5bd747cbcc7a547c5bc12610e874e26f5e3
fetch model.safetensors tts/Qwen3-TTS-12Hz-1.7B-Base \
  38fc7fc51c5e776e840414b6fd443962e9411b9654888fd7913e4da643cb857c
fetch preprocessor_config.json tts/Qwen3-TTS-12Hz-1.7B-Base \
  efdde1022ea9d76928bf7a9cd53139138f5ba2e466e837f08f6105ab1af1c119
fetch tokenizer_config.json tts/Qwen3-TTS-12Hz-1.7B-Base \
  dc3c31c3bdaedd5016382bb3cbe07323026775ad51f5a4fb564505992ae4a670
fetch vocab.json tts/Qwen3-TTS-12Hz-1.7B-Base \
  ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910
fetch speech_tokenizer/config.json tts/Qwen3-TTS-12Hz-1.7B-Base/speech_tokenizer \
  ee65bb901c876664ab8707c487157aa1a6ee57c65969b28fb5ec9dc211e68167
fetch speech_tokenizer/configuration.json tts/Qwen3-TTS-12Hz-1.7B-Base/speech_tokenizer \
  6bc26d64eb5024b4d1dab5a52371958b429256d6c9d59787f1f5294a54e0cebd
fetch speech_tokenizer/model.safetensors tts/Qwen3-TTS-12Hz-1.7B-Base/speech_tokenizer \
  836b7b357f5ea43e889936a3709af68dfe3751881acefe4ecf0dbd30ba571258
fetch speech_tokenizer/preprocessor_config.json tts/Qwen3-TTS-12Hz-1.7B-Base/speech_tokenizer \
  fcb3805e597e786d4067706e602f6688524640f8d3396790e2e09b5942fcbdfb
REPO="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
REV="0c0e3051f131929182e2c023b9537f8b1c68adfe"
fetch config.json tts/Qwen3-TTS-12Hz-1.7B-CustomVoice \
  17a07f527a1c25ea30b4e023a184482a23d3e279d697b1dc81b1bde498d29cf9
fetch generation_config.json tts/Qwen3-TTS-12Hz-1.7B-CustomVoice \
  f1b90b4513f3b34c62851049e2492d7b4c5940daf1276f89c82b8ef04127f3aa
fetch merges.txt tts/Qwen3-TTS-12Hz-1.7B-CustomVoice \
  599bab54075088774b1733fde865d5bd747cbcc7a547c5bc12610e874e26f5e3
fetch model.safetensors tts/Qwen3-TTS-12Hz-1.7B-CustomVoice \
  38b1d5971bdbd982b561cccec982669a53b0537c3cf5e9bd4778ed07bb2f5137
fetch preprocessor_config.json tts/Qwen3-TTS-12Hz-1.7B-CustomVoice \
  efdde1022ea9d76928bf7a9cd53139138f5ba2e466e837f08f6105ab1af1c119
fetch tokenizer_config.json tts/Qwen3-TTS-12Hz-1.7B-CustomVoice \
  dc3c31c3bdaedd5016382bb3cbe07323026775ad51f5a4fb564505992ae4a670
fetch vocab.json tts/Qwen3-TTS-12Hz-1.7B-CustomVoice \
  ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910
fetch speech_tokenizer/config.json tts/Qwen3-TTS-12Hz-1.7B-CustomVoice/speech_tokenizer \
  ee65bb901c876664ab8707c487157aa1a6ee57c65969b28fb5ec9dc211e68167
fetch speech_tokenizer/configuration.json tts/Qwen3-TTS-12Hz-1.7B-CustomVoice/speech_tokenizer \
  6bc26d64eb5024b4d1dab5a52371958b429256d6c9d59787f1f5294a54e0cebd
fetch speech_tokenizer/model.safetensors tts/Qwen3-TTS-12Hz-1.7B-CustomVoice/speech_tokenizer \
  836b7b357f5ea43e889936a3709af68dfe3751881acefe4ecf0dbd30ba571258
fetch speech_tokenizer/preprocessor_config.json tts/Qwen3-TTS-12Hz-1.7B-CustomVoice/speech_tokenizer \
  fcb3805e597e786d4067706e602f6688524640f8d3396790e2e09b5942fcbdfb
REPO="Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
REV="5ecdb67327fd37bb2e042aab12ff7391903235d3"
fetch config.json tts/Qwen3-TTS-12Hz-1.7B-VoiceDesign \
  aecd2cc4c1fe9edef1cb7ca7c401685a43879ad43f3f9e883f1c6760b61731e0
fetch generation_config.json tts/Qwen3-TTS-12Hz-1.7B-VoiceDesign \
  f1b90b4513f3b34c62851049e2492d7b4c5940daf1276f89c82b8ef04127f3aa
fetch merges.txt tts/Qwen3-TTS-12Hz-1.7B-VoiceDesign \
  599bab54075088774b1733fde865d5bd747cbcc7a547c5bc12610e874e26f5e3
fetch model.safetensors tts/Qwen3-TTS-12Hz-1.7B-VoiceDesign \
  391e8db219f292c515297cdceeb43e4eae67cdde35fa57e79a6a8a532fca0522
fetch preprocessor_config.json tts/Qwen3-TTS-12Hz-1.7B-VoiceDesign \
  efdde1022ea9d76928bf7a9cd53139138f5ba2e466e837f08f6105ab1af1c119
fetch tokenizer_config.json tts/Qwen3-TTS-12Hz-1.7B-VoiceDesign \
  dc3c31c3bdaedd5016382bb3cbe07323026775ad51f5a4fb564505992ae4a670
fetch vocab.json tts/Qwen3-TTS-12Hz-1.7B-VoiceDesign \
  ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910
fetch speech_tokenizer/config.json tts/Qwen3-TTS-12Hz-1.7B-VoiceDesign/speech_tokenizer \
  ee65bb901c876664ab8707c487157aa1a6ee57c65969b28fb5ec9dc211e68167
fetch speech_tokenizer/configuration.json tts/Qwen3-TTS-12Hz-1.7B-VoiceDesign/speech_tokenizer \
  6bc26d64eb5024b4d1dab5a52371958b429256d6c9d59787f1f5294a54e0cebd
fetch speech_tokenizer/model.safetensors tts/Qwen3-TTS-12Hz-1.7B-VoiceDesign/speech_tokenizer \
  836b7b357f5ea43e889936a3709af68dfe3751881acefe4ecf0dbd30ba571258
fetch speech_tokenizer/preprocessor_config.json tts/Qwen3-TTS-12Hz-1.7B-VoiceDesign/speech_tokenizer \
  fcb3805e597e786d4067706e602f6688524640f8d3396790e2e09b5942fcbdfb
echo "Qwen3-TTS ready in $ROOT/tts"
