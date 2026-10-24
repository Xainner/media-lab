# ComfyUI v0.37.0 → v0.39.0

Prepared 2026-10-07 on branch `chore/comfyui-v0.39.0` (based on `codex/creative-studio`) and
deployed the same day following the plan below; results are in [RELEASE-0.7.3.md](RELEASE-0.7.3.md).

## Change

| | Before | After |
| --- | --- | --- |
| `COMFYUI_REF` (Dockerfile + compose) | `73c9bad4d21e…` (v0.37.0, 2026-09-20) | `b0b743566f65…` (v0.39.0, 2026-10-05) |
| ComfyUI image tag | `rinari-visual-lab-comfyui:0.5.0` | `rinari-visual-lab-comfyui:0.6.0` |
| Launch flag | `--disable-api-nodes` | `--offline` (same behaviour; the old flag is a deprecated alias since `17059405`) |
| Base image, custom-node pins | unchanged | unchanged |

`0.5.0` stays on Saturno as the rollback image. v0.39.1/v0.39.2 only add partner (API)
nodes and workflow templates; API nodes are disabled here, so they are not needed.

Requirements delta: frontend 1.52.7→1.53.10, workflow-templates 0.11.66→0.11.76,
embedded-docs 0.5.12→0.5.13, comfy-kitchen 0.2.35→0.2.37, `torchaudio` removed.

## Native node schemas used by the runtime

Checked by diffing the defining files between the two tags (98 upstream commits).

| Node(s) | Defining file | Schema change |
| --- | --- | --- |
| MiniMaxH3ImageToVideo, MiniMaxH3ReferenceToVideo, MiniMaxH3SigmaShift | `nodes_minimax_h3.py` | none (torchaudio→`comfy.audio`, Fun-control v2 inpaint fix) |
| YuE2GenerateABC, YuE2GenerateMusic, EmptyYuE2LatentAudio | `nodes_yue2.py` | file unchanged |
| SheetSage2AudioToABC, AudioEncoderLoader | `nodes_audio_encoder.py` | file unchanged |
| TextEncodeQwenImage21, QwenImage21Cache | `nodes_qwen.py` | file unchanged |
| SaveVideo, CreateVideo, LoadVideo, GetVideoComponents | `nodes_video.py` | only `crf` defaults (see below) |
| SaveAudioAdvanced, LoadAudio, VAEDecodeAudio | `nodes_audio.py` | none (torchaudio→`comfy.audio`) |
| UNETLoader, CLIPLoader, VAELoader, CheckpointLoaderSimple, KSampler, … | `nodes.py` | none (VAELoader gains `taeqi2_1`) |
| RandomNoise, BasicScheduler, KSamplerSelect, BasicGuider, SamplerCustomAdvanced | `nodes_custom_sampler.py` | file unchanged |
| SaveText | `nodes_text.py` | file unchanged |

`comfy/samplers.py` and `k_diffusion/sampling.py` are unchanged, so `SAMPLERS` /
`SCHEDULERS` in `model_options.py` stay valid. `comfy_api` only adds `DynamicGroup`;
DynamicCombo/Autogrow key naming (`format.codec.encoding.crf`, `ref_images.ref_image_N`)
is unchanged.

**Graph changes required: none.** `creative_workflows.py` and `workflows.py` stay as they are.

## Behaviour changes to expect (no code change needed)

- **H3 MP4 size/quality:** `SaveVideo` now encodes with CRF 18 (H.264) / 24 (AV1) when
  no CRF is given, instead of the encoder defaults of 23 and 30 (upstream `a65316bd`). The
  runtime only sets CRF when the user fills "Calidad de compresión", so default H3
  outputs become visibly larger and higher quality. To keep the old sizes, send CRF 23
  explicitly. I don't recommend doing that.
- **YuE2 speed:** the AR sampler now runs on the GPU and reads tokens back every 16 steps
  (`7fbcfa8b`). The repetition-penalty window is now a ring buffer padded with the masked
  EOD token, which gives the same token counts, so sampling is equivalent. Seeds may still
  not reproduce bit-for-bit because the sampling head is now graph-captured.
- **YuE2 cover (song-cover):** SheetSage2 ABC generation was resynced with upstream YuE
  (`66b68a33`, key-aware chord spelling), so extracted scores will differ from 0.37.
- **H3 decode:** VAE tiles now blend against neighbours that are already blended, which
  removes seams (`fc584aaa`). The offload fixes (`912fca4f`, `83071e1a`) apply too. The
  video VAE now reads its layer count from the checkpoint (`986c4d15`). Saturno's
  `minimax_h3_video_vae_fp16` and `…_int8_convrot` headers both have 36 decoder blocks,
  matching the old hard-coded value.
- **Resampling:** `torchaudio.functional.resample` was replaced by `comfy.audio.resample`
  (LoadAudio → H3 reference audio, SheetSage input). Expect tiny numeric differences.

## Custom node packs (pins unchanged)

All four pinned commits still exist upstream. Every ComfyUI module, name and attribute
the packs reference (tests excluded) was resolved against both trees with an AST
check. v0.39.0 introduces no unresolved symbols. It also adds
`sheetsage2_abc.correct_chord_spelling` / `normalize_key_name`, which ComfyUI-YuE2's
legacy shim already looks up in a guarded import.

`torchaudio` is still available after the bump. In the running 0.5.0 image,
`torchaudio 2.11.0+cu130` belongs to the `pytorch/pytorch:2.12.1-cuda13.0` base image
(installed 2026-06-18 together with torch), not to ComfyUI's requirements. Removing it
from `requirements.txt` therefore uninstalls nothing. minimax-h3-audio-T8 imports it at
module level, so the import gate below re-checks this.

Runtime graphs use only native nodes. The packs only matter for the embedded graph editor.

## Validation plan (each Saturno step needs explicit approval)

0. **Pre-flight (read-only):** `deploy/visual-lab-web.sh check-idle`; record the
   `rinari-visual-lab-comfyui:0.5.0` image ID in the release folder.
1. **Build (no service impact):** from a staging copy of this branch on Saturno:
   ```bash
   docker build -f deploy/Dockerfile.comfyui --build-arg COMFYUI_REF=b0b743566f65daafc423b4fea8a2fbda94b3384a -t rinari-visual-lab-comfyui:0.6.0 .
   ```
2. **Import gate (CPU-only throwaway container, no GPU):**
   ```bash
   docker run --rm rinari-visual-lab-comfyui:0.6.0 bash -lc "git rev-parse HEAD && python -c 'import torchaudio, comfy_kitchen; print(torchaudio.__version__)' && ! python main.py --cpu --offline --quick-test-for-ci 2>&1 | tee /dev/stderr | grep -q 'IMPORT FAILED'"
   ```
   Pass: HEAD `b0b7435…`, torchaudio `2.11.0+cu130`, no `IMPORT FAILED` among the four packs.
3. **Schema gate (CPU canary on a spare loopback port, models mounted read-only):** start
   the 0.6.0 image with `--cpu` on `127.0.0.1:8399`. Diff `/object_info` against
   production worker `:8389` for every runtime node (list in `creative-smoke.py`, plus
   loaders/samplers). Expected diff: only the SaveVideo `crf` defaults and the
   VAELoader option list.
4. **GPU canary on gpu1 (short window, gpu0 stays on 0.5.0):** with queues idle, switch
   `comfyui-gpu1` to 0.6.0 (`up -d --no-deps --no-build comfyui-gpu1`), then run
   `deploy/scripts/creative-smoke.py` against `:8389` for `qwen`, `qwen-edit`, `song`,
   `song-abc`, `song-plan`, `song-cover`, `h3-t2v`, `h3-i2v`, `h3-r2v`. Also run the H3
   Fused Turbo profile. Compare with a 0.5.0 run: completion, wall time, peak VRAM (H3 at
   1.1 MP must not OOM), YuE2 tokens/s (should rise), H3 MP4 size (should rise, CRF 18),
   no tile seams. Caveat: real user jobs routed to gpu1 during the window run on 0.39.
5. **Promote:** switch `comfyui` (gpu0), then run `smoke-dual-gpu.py` and
   `production-smoke.py`. Check that https://media.example.com returns 200 and the
   runtime is healthy. Open the embedded ComfyUI editor once, since the frontend moved
   to 1.53.
6. **Rollback:** restore `image: rinari-visual-lab-comfyui:0.5.0` in compose and run
   `docker compose … up -d --no-deps --no-build comfyui comfyui-gpu1`. Models, volumes
   and runtime state are untouched by this upgrade.
