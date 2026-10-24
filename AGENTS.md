# Agent guide

## Installing Media Lab on a server

Use this when a user asks you to install, update or repair their own Media Lab. The supported
path is `deploy/install.sh`; do not hand-assemble Docker commands or edit `deploy/compose.yml`
for a new host. `README.md` explains the product and every option.

### Before you run anything

1. **Confirm the host.** Linux with Docker Engine, Docker Compose 2.24.4+, the NVIDIA Container
   Toolkit, an NVIDIA driver 580+ (CUDA 13) and, as tested, two 24 GB GPUs (one ComfyUI worker
   per GPU; a job never spans both). Run the installer as the user with uid 1000 (the web and
   agent containers run as 1000:1000) or as root.
2. **One Media Lab per host.** Compose project and container names are fixed. If a Media Lab
   stack already runs there (for example the reference host deployed with
   `deploy/media-lab.sh` and `deploy/.web.env`), stop and ask; the installer refuses anyway.
3. **Choose the origin with the user**: the exact HTTPS address people will open, a host name
   (not an IP), e.g. `https://media.example.com` behind their reverse proxy, or
   `https://medialab.lan:8390` with `--listen 0.0.0.0` for direct LAN access.
4. **Choose the model groups with the user.** Run `deploy/install.sh list-models` and show the
   table: sizes go from ~44 GB (`minimal`) to ~326 GB (`all`), ~230 GB for `recommended`.
5. **Licences are the user's decision, not yours.** Tell the user which licences the chosen
   groups carry and that they must read and accept them: Qwen-Image 2.1 is non-commercial
   (Qwen Research License), the Kandinsky 6 MMAudio VAE is CC-BY-NC-4.0, the H3 Fused Turbo merge
   is research-only, MiniMax H3, Stable Audio 3 and SAM 3.1 have their own community licences.
   Never accept a licence on the user's behalf.

### Hugging Face token and gated models

- **FLUX 3 Klein (`flux3`) is gated.** The user must open its Hugging Face page while logged in,
  accept the FLUX Kommunity License, and create a read token (fine-grained tokens need read
  access to public gated repositories).
- The token lives only in Hugging Face's standard file, `~/.cache/huggingface/token` (or the
  path in `HF_TOKEN_FILE` / `--hf-token-file`). Ask the user to run `hf auth login`
  themselves. **Never ask for the token in chat, echo it, pass it on a command line, write it to
  another file, or put it in a URL.** The installer validates it without printing it.
- The `yue2` group downloads with the `hf` CLI (`pipx install 'huggingface_hub[cli]'`).
- A 401/403 during a download means the licence was not accepted or the token lacks access:
  report it; do not retry with other credentials.

### Run it

```bash
deploy/install.sh --dry-run --origin https://media.example.com --models recommended   # review first
deploy/install.sh --yes --origin https://media.example.com --models recommended
```

- Downloads are large and resumable: run the installer in the background or a persistent
  terminal, and re-run the same command after an interruption. Verified files are skipped.
- Never use `--force` without the user's explicit approval: it interrupts active jobs.
- With `--yes` (or without a terminal) the installer does not print the first-administrator
  link. Ask the user to run `deploy/install.sh bootstrap` in their own terminal: the single-use
  link creates the admin account and must not pass through chats or logs.
- `kandinsky6` and `scail2` also install shared encoders (Qwen2.5-VL 7B; Wan 2.1 UMT5-XXL and
  VAE) into the shared model directory through `deploy/scripts/download-shared-comfy-models.sh`.
  Never fetch unpinned copies of these or any other weights yourself.

### Verify

- `deploy/install.sh status` shows healthy `comfyui`, `comfyui-gpu1`, `runtime` and `agent`.
- After the user logs in, the MCP `capabilities` tool (or the studio itself) reports which
  models are `ready`; a model missing files reports `false`, which is not an install failure.
- During a job, `nvidia-smi` shows one ComfyUI worker busy per GPU.

### Update, roll back, certificates

- `deploy/install.sh update` (idle check, database backup, `:rollback` images, `git pull
  --ff-only`, re-install). It needs a clean git checkout.
- `deploy/install.sh rollback` returns to the code and images before the last update;
  `--restore-db` also restores the database and loses newer work, so ask first.
- `deploy/install.sh renew-cert` renews the private origin certificate (yearly).

### Responsible use

Voice cloning requires the speaker's permission (`consent=true` only after the user confirms
it). Swap faces or characters only of consenting people or fictional characters. Never help make
deceptive content that impersonates real people.

## Notas del mantenedor (Saturno)

El proyecto está en el servidor Saturno, accesible mediante el alias SSH `saturno`.

Rutas en Saturno confirmadas por el usuario:

- Código (copia sin git): `~/media-lab`; datos en `~/media-lab-data` (estado, secretos, releases)
- UI web: `~/media-lab/apps/web`
- Vistas de creación: `~/media-lab/apps/web/src/studio`
- Motor del agente: `~/media-lab/services/agent/lib`
- Runtime/API: `~/media-lab/services/runtime/src/media_lab`

Usar estas rutas como referencia para el trabajo remoto en este proyecto. Saturno es el host de
referencia: se despliega con `deploy/media-lab.sh` y `deploy/.web.env`, no con
`deploy/install.sh`.

### Trabajo local en la UI

La UI web local está en `C:\Users\Xainner\Documents\Proyectos\rinari-visual-lab\apps\web`.
El usuario ha indicado que el trabajo actual se centrará en la UI, usando esta ruta local.
