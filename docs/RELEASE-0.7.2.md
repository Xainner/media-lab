# Web 0.7.2 — model guides, MCP and Director lip-sync

Released to Saturno on 2026-10-07 as `20261007-model-guides-2e31152`
(commits `2fa458a`, `b5a8d21`, `2e31152`). Only the web runtime and agent images
changed; both ComfyUI workers kept running.

## Changes
- Per-model English guides (`model_guides.py`) shared by MCP, Rinari agent, prompt
  improver, image review and Director planner. See [MCP.md](MCP.md).
- MCP `0.7.2-mcp-en.2`: compact instructions, per-model topics/resources/templates,
  `check_prompt`, `account_preferences`, `improve_prompt` for H3 and YuE2.
- Runtime prepends the official H3 keyframe alignment line (I2VA/FL2VA/L2VA).
- Director `lip_sync` scenes: r2v with the keyframe as `<Picture 1>` and the song
  excerpt as `<Audio 1>` (excerpt stored as a library source).
- Qwen edits limited to 10 references; H3 Base/Fused usage notes in the UI.

## Validation
Local: 170 runtime tests, 40 Electron/agent tests, 18 renderer and 13 web tests, web
build. Saturno: queues idle before and after, firewall rule present, runtime healthy,
public site 200, MCP rejects unauthenticated calls (401), new tools and guides present
in the running containers. No GPU generation was run for this release; lip-sync output
quality is untested.

MCP clients must reconnect to refresh the cached instructions and tool list.

## Rollback
Backup and previous image IDs: `~/.rinari/releases/20261007-model-guides-2e31152/`.

```bash
cd ~/rinari-visual-lab
deploy/visual-lab-web.sh check-idle
docker tag rinari-visual-lab-web:rollback-20261007-model-guides-2e31152 rinari-visual-lab-web:0.7.2
docker tag rinari-visual-lab-agent:rollback-20261007-model-guides-2e31152 rinari-visual-lab-agent:0.7.2
docker compose --env-file deploy/.web.env -f deploy/compose.yml -f deploy/compose.web.yml up -d --no-build runtime agent
```
Restore the source tree from `source-before.tgz` if the files must match as well.
