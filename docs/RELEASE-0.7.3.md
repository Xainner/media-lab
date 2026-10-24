# Web 0.7.3 + ComfyUI 0.39 workers

Released to Saturno on 2026-10-07 as `20261007-comfyui039-31e1969`.
Commits: `ff34142` (ComfyUI v0.39.0 pin), `2b44512` (prompt improve in Video and Music) and `31e1969` (web tag).
The agent image stayed at 0.7.2.

| Service | Before | After |
| --- | --- | --- |
| `comfyui`, `comfyui-gpu1` | `comfyui:0.5.0` (ComfyUI v0.37.0) | `comfyui:0.6.0` (ComfyUI v0.39.0, `--offline`) |
| `runtime` | `web:0.7.2` | `web:0.7.3` |
| `agent` | `agent:0.7.2` | unchanged |

## Changes
- ComfyUI v0.39.0. No graph changes. See [UPGRADE-COMFYUI-0.39.md](UPGRADE-COMFYUI-0.39.md).
- "Proponer mejora externa" now also appears in Vídeo (t2v, i2v and r2v, with the duration
  and frames/references) and Música (style and lyrics). Proposals are applied only on accept.

## Validation
Local checks:
- 0.7.3 test suites: all runtime tests pass (2 skipped), 40 Electron, 22 renderer and 15 web.
- The desktop and web builds succeed.

Saturno gates, in order:
1. **Import gate:** a throwaway CPU container showed HEAD `b0b7435` and torchaudio 2.11.0+cu130.
   All four packs loaded with no `IMPORT FAILED`.
2. **Schema gate:** a CPU canary's `/object_info` was compared with the 0.5.0 worker. Every
   runtime node is present. The only differences are the SaveVideo CRF defaults and
   environment-only option lists.
3. **GPU canary:** gpu1 ran 0.6.0 while gpu0 stayed on 0.5.0. `creative-smoke.py` passed 9/9.

| Smoke (gpu) | 0.39 | 0.37 baseline |
| --- | ---: | ---: |
| YuE2 song (direct, 10 s/4 steps) | 8.5 s | 11.9 s |
| YuE2 cover (SheetSage2) | 4.9 s | 6.0 s |
| H3 i2v 480², 5 s/8 steps | 81.0 s | 85.1 s |
| H3 r2v 480², 5 s/8 steps | 83.7 s | 82.4 s |
| Peak VRAM during the suite | 23,995 MiB | 24,023 MiB |
| H3 i2v MP4 | 328 KB, crf=18 | 198 KB, crf=23 |

Also passed on the canary: Qwen t2i 15.1 s, Qwen edit 3.7 s, YuE2 ABC 2.6 s, YuE2 plan 5.4 s
and H3 t2v 79.5 s. "YuE2 semantic reached its token budget" appears on both versions with the
10-second smoke.

After promotion:
- gpu0 on 0.39: Qwen 14.4 s, song 8.1 s, H3 t2v 74.2 s. Qwen and song hashes are identical across both GPUs.
- Public `/` and `/health` return 200, and unauthenticated MCP returns 401.
- The new bundle is served, the proxy-only firewall is present and the queues are idle.

Expect larger default H3 files (CRF 18). Setting "Calidad de compresión" restores smaller ones.

## Rollback
Backup, changed-file list and before/after image IDs are in `~/.rinari/releases/20261007-comfyui039-31e1969/`.

```bash
cd ~/rinari-visual-lab
deploy/visual-lab-web.sh check-idle
tar xzf ~/.rinari/releases/20261007-comfyui039-31e1969/source-before.tgz
docker tag rinari-visual-lab-comfyui:rollback-20261007-comfyui039-31e1969 rinari-visual-lab-comfyui:0.5.0
docker tag rinari-visual-lab-web:rollback-20261007-comfyui039-31e1969 rinari-visual-lab-web:0.7.2
docker compose --env-file deploy/.web.env -f deploy/compose.yml -f deploy/compose.web.yml up -d --no-deps --no-build comfyui comfyui-gpu1 runtime
```
