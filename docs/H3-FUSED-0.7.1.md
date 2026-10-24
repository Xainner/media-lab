# H3 Fused Turbo — 0.7.1

Adds an explicit video profile to Video, Director and the private external agent.
Base remains the default (20 steps, permitted 8–40); Fused defaults to 4 steps
with an experimental 4–12 range. Old jobs/productions without a profile retain
their base workflow. New Director clips inherit `video_profile`/`video_steps`;
reused clips and completed partial scenes are not regenerated.

## Existing assets, no download or duplication

Read-only individual-file bind mounts, shared by both dedicated ComfyUI workers
and the runtime; no access to Maestro's outputs, settings or other checkpoints.
Missing files fail container creation rather than silently creating directories.

- Transformer: `/opt/maestro/repo/app/ckpts/minimax_h3_fused_refdelta_r1024_turbo8_mystic07_int8_convrot.safetensors`
- SHA-256: `4262e4e9963c553fa00016bbe83961407a4fc0a888be95fd836c8d4f2304e48b`
- Revision: `3b51096a1bf67608d98131116558202208fcf195`
- Video VAE: `/opt/maestro/repo/app/ckpts/minimax_h3/vae/minimax_h3_video_vae_int8_convrot.safetensors`
- SHA-256: `9bb2d96f218c76babd85e0611b85ca8fb330a90546c01a0005e8a58a59593410`
- VAE revision: `a3e7d8da4ae7ba8df0779094cf5ab9d6ee855fe4`

Source: <https://huggingface.co/MATLOWAI/minimax-h3-fused-turbo-int8-convrot>.
This is an experimental community merge, not an official MiniMax release. Retain
the upstream MiniMax/component license and NOTICE obligations; research use only.

## Workflow

Native `UNETLoader` with `default` dtype; same fused transformer for T2V/I2V/R2V,
INT8 video VAE, existing Qwen3-VL conditioner and audio VAE. `res_multistep/simple`,
native `MiniMaxH3SigmaShift` video 12/audio 3, `BasicGuider` without CFG. Existing
canvas, frame grid, duration, memory and queue limits are unchanged.

**Attention is dense, not SLA.** Installed T8 SLA nodes also apply another Turbo
LoRA and must not be stacked on this baked checkpoint. No nodes or services are
installed/updated for this profile. Dense inference is admitted by the model
author but may produce different/softer audio and different motion than Maestro.
No automatic model fallback, retries or corrective generations.

Provenance records profile, steps, attention, workflow, checkpoint and revision.
Capabilities expose per-profile readiness/bounds; API and agent validate before
admission. All existing user ownership, nested references and idempotency remain
in force. API keys/provider and multimedia never leave their existing boundaries.

## Validation

Local: 79 runtime tests, 36 shared-engine Node tests, 2 private-service lifecycle
tests, 15 renderer tests and TypeScript/Vite web
build passed. Both existing asset hashes were verified in Saturno.

Real isolated authenticated API/GPU validation passed on 2026-09-30:

| Mode | GPU | Steps | Video duration | Observed job wall time |
| --- | --- | --- | --- | --- |
| T2V | 0 | 4 | 5.167 s | 52.4 s |
| I2V | 1 | 4 | 5.167 s | 58.4 s |
| R2V, one reference | 0 | 4 | 5.167 s | 55.5 s |

All three produced MP4 video plus audio at the existing conservative canvas.
Verified actual frame inspection, authenticated Range downloads, another user's
reference/job/download/cancellation rejection, idempotent replay, base-at-4 and
fused-at-13 rejection. No OOM or automatic retry. Timings are observations, not
a performance SLA or a human visual/audio-quality comparison with Maestro.

The first harness attempt failed before any GPU submission because TestClient's
default peer is not loopback; the harness was corrected to model the private
service boundary. Authentication was not relaxed. Accounts/data remain isolated
in `visual-lab-h3-071-validation`, never imported into production.

During guarded maintenance, the old agent retained a stale boot-recovery flag
after runtime startup retries. All persisted runs and jobs were terminal; the
private service now tracks pending account reconciliation and clears each entry
on successful later recovery. Filesystem/unknown recovery remains fail-closed.
The guarded launcher subsequently accepted the idle stop; no force shutdown.

Production 0.7.1 was published and left running on 2026-09-30. HTTPS health returns
0.7.1; both model/VAEs are visible on both workers. The runtime and both ComfyUI
containers mount exactly the two Maestro assets read-only, with `create_host_path`
disabled. All four dedicated services run with `unless-stopped`; the proxy-only
firewall is unchanged, with ComfyUI and Node bound to loopback.

The non-generating production continuity check passed: two accounts retained,
configured provider retained, previous agent run restored with no duplicate jobs,
six protected Range downloads, original PNG export unchanged, anonymous library
401 and foreign-origin mutation 403. Both profiles report ready; base remains the
default. Added a read-only `check-idle` launcher command and verified launchers'
syntax and guard. Base request canonicalization preserves pre-0.7.1 idempotency
keys for videos and Director; changing to Fused with the same key remains conflict.

Rollback source-only archive:
`~/backups/rinari-visual-lab-0.7.0-before-h3-code.tar`. It contains only
the replaced source/configuration, never SQLite, credentials or multimedia. Old
images are retained; no Docker prune, volume removal or model modification.

No account/state reset or desktop packaging is part of this release. No manual
quality equivalence to Maestro/SLA or authenticated multi-browser UI acceptance
is claimed. Renderer interactions and payloads are covered by automated tests.
