# ComfyUI v0.39.0 → v0.42.5

Prepared 2026-10-23 on branch `chore/comfyui-v0.42`, based on `main`. Results are in
[RELEASE-0.12.0.md](RELEASE-0.12.0.md).

## Change

| | Before | After |
| --- | --- | --- |
| `COMFYUI_REF` (Dockerfile + compose) | `b0b743566f65…` (v0.39.0) | `483dae432635…` (v0.42.5) |
| ComfyUI image tag | `rinari-visual-lab-comfyui:0.7.0` | `rinari-visual-lab-comfyui:0.8.0` |
| Base image, custom-node pins, launch flags | unchanged | unchanged |

There are 117 upstream commits between the two tags. Requirements delta:
- frontend 1.53.10 → 1.55.18
- workflow-templates 0.11.76 → 0.11.96
- embedded-docs 0.5.13 → 0.5.14
- comfy-kitchen 0.2.37 → 0.2.39
- comfy-aimdo 0.5.5 → 0.5.6

## What the upgrade brings (used by the Media Lab roadmap)

- **MOSS-Image**: `nodes_moss_image.py`, CLIPLoader type `moss_image`, `MOSSImageControl` and `MOSSImageLayoutPrompt` (color-depth control).
- **FLUX 3 Image**: CLIPLoader type `flux3`, `Flux3LayoutPrompt`.
- **Camera control**: `CameraAngle` and `CreateCameraInfo`, for the Qwen 2.1 Multiple-Angles LoRA.
- **Native LoRA stack loaders**: `LoadLoraModel` and `LoadLoraTextEncoder`, which the LoRA library will use.
- **References**: `ReferenceMultiLatent`.
- **Latents**: `GetLatentSize`, `GetAudioLatentSize` and `LatentOperationBlend`.
- **MiniMax H3**:
  - LightVAE support;
  - single-head LoRAs applied to the PDD head banks;
  - models with PDD baked in;
  - single images decode as the first latent of a clip.
- **Qwen 2.1**: fix for its low-VRAM issue ("rogues"); performance improvements for the Qwen 3.x text encoders.

## Native node schemas used by the runtime

I compared `/object_info` from a CPU-only canary of 0.8.0 with the production gpu1 worker (0.7.0) for every node the runtime uses:
- Qwen, YuE2, SheetSage2 and MiniMax H3;
- video and audio I/O;
- loaders, samplers and FlashVSR.

- **No node is missing, and no input or output changed.**
- The only differences are option lists:
  - CLIPLoader gains the `flux3` and `moss_image` types;
  - the file lists depend on the mounts. The CPU canary did not have the input/output volumes or the two fused H3 bind mounts from `compose.web.yml`. Those mounts are unchanged in production.
- 11 nodes were added; none were removed.

**Graph changes required: none.**

## Behaviour notes

- **Assets system:** off unless `--enable-assets` is given. We don't pass it, so nothing scans the model or output folders.
- **Custom-node governance (`app/governance.py`):** only active when a signed policy file exists. There is none here, so the packs load as before.
- **Agent feature (`--enable-agent`):** off by default.

## Custom node packs (pins unchanged)

All five pinned commits still exist upstream. None of them references the APIs that changed: `DynamicGroup` became internal, and `PreviewUI3DAdvanced` was refactored.

Import gate on the built image (CPU-only, no network):
- HEAD is `483dae43…`;
- torchaudio is `2.11.0+cu130` and torch `2.12.1+cu130`;
- comfy-kitchen is 0.2.39 and comfy-aimdo 0.5.6;
- all five packs load, with no `IMPORT FAILED`.

## Rollout

1. Build `rinari-visual-lab-comfyui:0.8.0` from the Dockerfile. There is no build context, because the Dockerfile has no `COPY`.
2. Run the import gate and the CPU schema gate on `127.0.0.1:8399`, then remove the canary.
3. **GPU canary:**
   - after `check-idle`, switch only `comfyui-gpu1` to 0.8.0;
   - run `creative-smoke.py` against `:8389` for `qwen`, `qwen-edit`, `song`, `song-abc`, `song-plan`, `song-cover`, `h3-t2v`, `h3-i2v` and `h3-r2v`.
4. **Promote:**
   - switch `comfyui` (gpu0) and the runtime/agent 0.12.0 images;
   - check health, the firewall, a web 200 and an MCP 401.

## Rollback

Each service has a rollback tag `rollback-20261023-media-lab-4e6a692`: comfyui is 0.7.0, web is 0.11.0 and agent is 0.11.0. The release folder `~/.rinari/releases/20261023-media-lab-4e6a692/` holds the previous sources.

To roll back:
1. Restore the image tags in compose.
2. Run `up -d --no-deps --no-build` for the affected services.

Models, volumes and runtime state are untouched by this upgrade.
