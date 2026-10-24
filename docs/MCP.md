# Account-scoped MCP

Media Lab exposes a remote MCP server at `https://media.example.com/mcp`.
Each token operates only on its owner's jobs, conversations, media and quotas.
The server's instructions, tool descriptions, prompt templates, examples and model
control metadata are in English. Model-facing descriptive prompts must be in English;
user requests and literal lyrics, visible text and dialogue are preserved separately.
The web interface can remain in Spanish.

## Connect

1. Open **Cuenta → Conexiones MCP** in the web UI and enable MCP.
2. Create a named token with expiration and scopes. Confirm your password and,
   when enabled, your current 2FA or recovery code.
3. Copy the token before closing the dialog. Only its SHA-256 digest is stored.
4. Configure **Streamable HTTP** at the endpoint above with
   `Authorization: Bearer <token>`. Downloaded `mcpServers` configurations contain
   the credential; store them accordingly and adapt the structure to your client.
5. Reconnect the client after server updates to refresh cached instructions/tools.
   Have the agent read `capabilities` and `prompt_guide` before generation.
6. Always use the public https URL, also from the local network: the server checks the
   Host header and does not answer on IP addresses or other names.

The web page also offers copyable English **agent instructions** (no token inside) that
explain the remote server and the file flow; paste them into the agent's own instructions.

Clients need configurable Bearer headers. This server uses personal tokens, not
interactive OAuth. Browser cookies and internal service keys do not authenticate MCP.
The token is accepted only on `/mcp` and `/mcp/media`, not browser/admin APIs.
Transfer links under `/mcp/files/` authenticate by themselves (see Media below).

## Complete English documentation

[MCP-GUIDE.md](MCP-GUIDE.md) is the complete shipped agent guide: every tool,
model prompt writing, references, uploads, file formats, encoders, advanced options,
actual defaults, constraints, workflows and English tool-call examples.
[MODEL-CONTROLS.md](MODEL-CONTROLS.md) contains the same model-control reference.
Both are generated from `mcp_server.GUIDES` and the validated runtime catalog:

```powershell
python deploy/scripts/sync-mcp-guides.py
python deploy/scripts/sync-mcp-guides.py --check
```

`tools/list` derives input schemas from real request contracts. Read `capabilities`
for installed weights, verified profiles and account-independent hardware gates;
tool existence does not guarantee model readiness. `account_profile` reports own quotas.
The live `capabilities` MCP response translates control labels/help into English
without changing the Spanish UI or translating users' prompts, lyrics or library data.

Server instructions are a compact overview (workflow, language policy, model essentials
and the tool catalog); the complete guide is fetched on demand so it does not occupy the
client's context on every turn.

`prompt_guide(topic=...)` supports `all` (default), `overview`, `prompts`, `formats`,
`controls`, `workflows` and one topic per model: `image` (Qwen-Image-2.1 text-to-image),
`edit` (Qwen editing), `video` (MiniMax H3), `music` (YuE2) and `director`. The model
guides live in `services/runtime/src/media_lab/model_guides.py`, built from each model's
official sources (Qwen prompt rewriters, the MiniMax H3 prompt-writing skill, the YuE2-3B
protocol, the MOSS-Image prompt enhancer, BFL's FLUX 3 Klein upsampler and prompting guides, the
Kandinsky 6 beautifier, the ACE-Step 1.5 tutorial, Stability's Stable Audio 3 guide and the
Qwen3-TTS documentation; the docstring lists them with their dates).
Readable Markdown resources, one per `prompt_guide` topic:

- `media-lab://guides/all`: the full guide.
- `media-lab://guides/formats`: uploads, references, encoding, export and downloads.
- `media-lab://guides/controls`: complete controls, limits, defaults and resolution tables.
- `media-lab://guides/image` (Qwen, MOSS, FLUX 3 Klein), `media-lab://guides/edit` (Qwen, FLUX),
  `media-lab://guides/video` (H3, Kandinsky 6), `media-lab://guides/music` (YuE2, ACE-Step),
  `media-lab://guides/sound` (Stable Audio 3), `media-lab://guides/speech` (Qwen3-TTS) and
  `media-lab://guides/director`.

Prompt templates: `creative_brief(goal, medium)`, `image_prompt(goal, references)`,
`video_prompt(goal, inputs, seconds)`, `music_prompt(goal)` and `music_video(goal)`.
Each embeds the matching guide and keeps the original goal as user data. Prompt language
does not override literal lyrics, names, quoted text or dialogue the user asked for.

`check_prompt(body={model, prompt, lyrics, mode, seconds, first_frame, last_frame,
images, videos, videos_with_audio, audios})` (scope `read`) validates structure without
calling any model: H3 fields and order, labels against the inputs that will be sent,
shot timestamps against the effective duration, `<d>` tags and speech density; Qwen
edit tags; YuE2 sections. For H3 it returns the exact text the encoder receives,
including the keyframe alignment line the runtime adds for I2VA/FL2VA/L2VA.
`improve_prompt` (scope `agent`) now targets `t2i`, `i2i`, `t2v`, `i2v`, `r2v` or `song`.

## Permissions and token lifecycle

| Scope | Access |
| --- | --- |
| read | Required. Capabilities/status, own profile/jobs/media/conversations, provider discovery without keys, guides, inspection, analysis, export and downloads. |
| create | Direct image/edit/video/music/Director, uploads, messages and own-job cancellation/resumption. |
| agent | Rinari runs and provider-assisted improvement/review/storyboard. Can generate media and consume quota. |
| delete | Permanent deletion of owned files after user confirmation. Not selected by default. |

Tokens last 1–365 days (UI presets 7/30/90/365); at most 20 active per account.
Rotation revokes the previous token transactionally. Disabling MCP revokes all tokens;
re-enabling requires new tokens. Password changes/resets, role changes and disabling
an account revoke external credentials. Account deletion purges MCP tokens/preferences
once inflight requests have drained. Revocation blocks following requests; jobs already
admitted continue unless explicitly cancelled. Audit records contain action identifiers,
not passwords, tokens or provider keys.

## Media and execution

The server is remote: models, GPUs and encoders run on Saturno and agents install
nothing. Files move by owned `{uri, sha256}` references.

**Sending files (0.10.0).** An LLM cannot practically write megabytes of base64 into a
tool call and usually does not hold the Bearer token its client uses, so files travel
over plain HTTP with temporary links:

1. `create_uploads(files=[{name}, ...], session_id?)` (scope `create`) returns 1–50
   upload links, valid 2 hours. At most 200 unused links per account.
2. The agent sends each file with `curl -sS -T ./file "<url>"` (raw PUT) or
   `curl -sS -F "file=@./file" "<url>"` (multipart). No Authorization header.
3. The reply contains `reference` (uri/sha256), `kind`, `content_type` and details.
   `get_uploads(ids)` recovers results. A failed upload keeps the link usable; a
   successful one consumes it.

The type comes from the bytes. PNG/JPEG/WebP become normalized PNG and other
Pillow-readable images (GIF, BMP, TIFF…) are converted to PNG (20 MiB, 50 MP). WAV/
FLAC/MP3/Ogg/Opus are kept and other audio (M4A/AAC, AIFF…) becomes FLAC (1–900 s).
MP4/MOV/MKV/WebM are kept and other containers are remuxed to MKV without re-encoding
(1–600 s, so long clips can be upscaled). Audio and video accept up to 500 MiB; the NPM
proxy allows 501 MiB with request buffering off. Each tool keeps its own limits;
`capabilities.inputs` lists formats and how many references every tool accepts
(edit 1–10 images; H3 first/last frame, up to 9 images, 3 videos of 2–15 s and 3
audios of 1–15 s in r2v; one cover source; one upscale source; Director song plus one
image/video per scene; 16 references for prompt improvement and agent runs).

`upload_reference`, `upload_audio` and `upload_video` remain as inline base64 fallbacks
for clients without HTTP (20 MiB decoded, 32 MiB request), practical only for small files.

**Getting results.** `get_download_links(references)` (scope `read`) returns 1–50 GET
links valid 1 hour, reusable within that time, with Range support and no headers:
`curl -sS -o out "<url>"`. `get_media` returns the same `temporary_url` plus the
permanent `download_url`, which needs `Authorization: Bearer <token>`.

**Link security.** Links are random 256-bit secrets stored only as SHA-256 digests,
bound to the owner, the minting token and (for downloads) one artifact. Every request
re-checks that the token is unrevoked, unexpired, still has the needed scope and that
MCP and the account are enabled, so revoking or disabling stops them immediately. They
appear in proxy access logs like any URL, hence the short lifetime; agents must not
publish or share them. Rate limits (180/min per token, 300/min per IP) still apply.

Creation takes `body` and optional sibling `idempotency_key`, returning a job receipt.
Poll with pauses, use `find_job` to recover lost receipts, and obtain media only after
completion. Never auto-retry failed GPU jobs. Resuming jobs/agent runs and deleting
files require explicit user authorization. Never add the token to a URL or present
private URLs as public. Native MCP image previews support visual clients;
video inspection returns six timestamped frames, audio analysis technical metadata.

Provider configuration, activation, testing and all user administration remain in the
web UI. MCP cannot read provider secrets or other accounts' private data. Active
provider/model remains consistent during an agent run.

## Python client

Example for the project's pinned official SDK (`mcp==2.2.0`):

```python
import asyncio
import os
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

async def main():
    async with httpx2.AsyncClient(
        headers={"Authorization": "Bearer " + os.environ["RVL_MCP_TOKEN"]},
        timeout=60,
    ) as http:
        transport = streamable_http_client(
            "https://media.example.com/mcp", http_client=http
        )
        async with Client(transport, cache=None) as rinari:
            catalog = await rinari.list_tools()
            guide = await rinari.call_tool("prompt_guide", {"topic": "all"})
            print([tool.name for tool in catalog.tools])
            print(guide)

asyncio.run(main())
```

## Implementation and validation

The official SDK serves stateless Streamable HTTP with JSON responses and current/
legacy protocol negotiation. Host must match the configured origin; any Origin header
must match too. Limits: 180 requests/minute per token, 300/minute per IP. Existing
multimedia quotas still apply. Responses and downloads use `Cache-Control: no-store`.

Runtime MCP tests cover English initialization/tools/resources/templates, complete
control/schema/format discovery, owned uploads and Range downloads, invalid MIME/
duration, transfer links (single use, failed-upload retry, size limit, type detection and
FLAC/MKV normalization with real ffmpeg, expiry, revocation, scope), scopes, concurrent account isolation, quotas, idempotency, CSRF, 2FA,
rotation, expiration, revocation and account lifecycle. Native agent tests verify the
English model-prompt policy while preserving original Spanish user requests.
Physical GPU execution is mocked in admission tests; no generation or mail is sent.

## Release history

The initial MCP release was `20261001-mcp-d47393a8`; deployment evidence and rollback
backup are retained under `artifacts/deploy/20261001-mcp-d47393a8` locally and
`~/media-lab-data/releases/20261001-mcp-d47393a8/backup-verified` on the reference host.
The model-controls release `20261003-model-controls-02adeb1e` added advanced
image/H3/YuE2/Director contracts. The English guide revision adds video uploads and
synchronized documentation without altering existing token identities or permissions.
The 0.7.2 guide revision (`0.7.2-mcp-en.2`) adds the per-model guides, compact
instructions, `check_prompt`, `account_preferences`, model prompt templates and the
automatic H3 keyframe alignment line. The Rinari agent, prompt improver, image review
and Director planner receive the same guides through `agent-prompts.cjs`.
Media Lab 0.10.0 (`0.10.0-mcp-en.1`) adds upload and download links
(`create_uploads`, `get_uploads`, `get_download_links`, `get_media.temporary_url`),
format detection and normalization, `capabilities.inputs`, uploads of videos up to
600 seconds, the "How this server works" section in the server instructions and the
copyable agent instructions in the web UI.
Media Lab 0.10.1 (`0.10.1-mcp-en.1`) shows the studio's rejection reason in tool errors, adds
`wait_for_job` and uniform `outputs` on completed jobs, describes every creation field in
the tool schemas and tells agents the exact call shape and to never fall back to scripts.
Media Lab 0.10.2 (`0.10.2-mcp-en.1`) serves `prompt_guide` as plain text (no generated output
schema), clarifies that `artifact://` URIs are studio identifiers, adds a download `url` to each
`wait_for_job` output and an `X-Content-SHA256` header on transfer downloads.
Media Lab 0.11.0 (`0.11.0-mcp-en.1`) adds read-only/destructive annotations to every tool, lets
`wait_for_job` wait up to 600 s while streaming `notifications/progress` when the call carries a
`progressToken` (answered as SSE; everything else stays JSON), returns a compact running state, and
passes the real reason of agent/provider failures through to tool errors.
Media Lab 0.12.0 (`0.12.0-mcp-en.1`) renames the server to **Media Lab** (`serverInfo.name`)
and runs on ComfyUI v0.42.5. Tools, schemas and the endpoint are unchanged.
