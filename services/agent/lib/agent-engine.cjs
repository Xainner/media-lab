/* Runs in the private agent service. No browser networking, model paths, or executable workflows. */
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const str = (maxLength = 20000) => ({ type: 'string', minLength: 1, maxLength });
const en = (...values) => ({ type: 'string', enum: values });
const num = (minimum, maximum) => ({ type: 'number', minimum, maximum });
const integer = (minimum, maximum) => ({ type: 'integer', minimum, maximum });
const obj = (properties, required = []) => ({ type: 'object', properties, required, additionalProperties: false });
const arr = (items, maxItems, minItems = 0) => ({ type: 'array', items, maxItems, minItems });
const modelOptions = require('./model-options.cjs');
const { modelPromptLanguage, englishCapabilities, guides } = require('./agent-language.cjs');
const guideTopics = Object.keys(guides.topics);
const imageOptions = { quality: en('quality', 'draft'), model_precision: en('bf16', 'int8'), model_variant: en('base', 'turbo'), seed: integer(0, Number.MAX_SAFE_INTEGER), transparent: { type: 'boolean' } };
const ratios = en('1:1', '16:9', '9:16', '4:3', '3:4', '3:2', '2:3', '4:5', '5:4');
const videoRatios = en('1:1', '16:9', '9:16');
const imageControl = obj({ reference: str(80), mode: en('canny', 'depth', 'pose', 'map'), strength: num(0.1, 1.5) }, ['reference']);
const cameraMove = obj({ azimuth: en('front view', 'front-right quarter view', 'right side view', 'back-right quarter view', 'back view', 'back-left quarter view', 'left side view', 'front-left quarter view'), elevation: en('low-angle shot', 'eye-level shot', 'elevated shot', 'high-angle shot'), distance: en('close-up', 'medium shot', 'wide shot') });
const loraUses = arr(obj({ id: str(40), strength: num(0.05, 2) }, ['id']), 4);
const scene = obj({ start: num(0, 900), end: num(0, 900), image_prompt: str(), video_prompt: str(), image: str(80), video: str(80), lip_sync: { type: 'boolean' } }, ['start', 'end', 'image_prompt', 'video_prompt']);
const schemas = {
  capabilities: obj({}), health: obj({}),
  prompt_guide: obj({ topic: en(...guideTopics) }, ['topic']),
  prompt_check: obj({ model: en('image', 'edit', 'video', 'music'), prompt: str(), lyrics: str(), mode: en('t2v', 'i2v', 'r2v'), seconds: num(5, 15),
    first_frame: { type: 'boolean' }, last_frame: { type: 'boolean' }, images: integer(0, 16), videos: integer(0, 3), videos_with_audio: integer(0, 3), audios: integer(0, 3) }, ['model']),
  library_search: obj({ q: str(1000), kind: en('images', 'songs', 'videos', 'productions', 'sources', 'references'), offset: integer(0, 100000), limit: integer(1, 100) }),
  characters_list: obj({}),
  artifact_inspect: obj({ alias: str(80) }, ['alias']),
  image_generate: obj({ model: en('qwen', 'moss', 'flux3'), prompt: str(), aspect_ratio: ratios, resolution_tier: en('1mp', '2k'), control: imageControl, loras: loraUses, options: modelOptions.image, ...imageOptions }, ['prompt']),
  image_edit: obj({ model: en('qwen', 'flux3'), prompt: str(), references: arr(str(80), 10, 1), camera: cameraMove, remove_background: { type: 'boolean' }, loras: loraUses, options: modelOptions.edit, resolution: integer(0, 2048), ...imageOptions }, ['references']),
  video_generate: obj({ model: en('h3', 'kandinsky6'), audio_prompt: str(4000), literal_prompt: { type: 'boolean' }, prompt: str(), loras: loraUses, control: obj({ video: str(80), mode: en('pose', 'canny', 'depth'), strength: num(0.1, 2), keep_audio: { type: 'boolean' } }, ['video']), profile: en('base', 'turbo', 'omni', 'flex', 'fused_turbo'), mode: en('t2v', 'i2v', 'r2v'), first_frame: str(80), last_frame: str(80), references: arr(str(80), 9), reference_videos: arr(str(80), 3), reference_audios: arr(str(80), 3), options: modelOptions.video, aspect_ratio: videoRatios, seconds: num(5, 15), steps: integer(4, 40), seed: integer(0, Number.MAX_SAFE_INTEGER) }, ['prompt']),
  music_generate: obj({ model: en('yue2', 'ace_step'), bpm: integer(40, 240), key: str(12), language: str(2), style: str(10000), lyrics: str(), mode: en('direct', 'full', 'melody'), abc: str(100000), source_audio: str(80), options: modelOptions.song, max_duration: num(10, 900), steps: integer(4, 80), seed: integer(0, Number.MAX_SAFE_INTEGER) }, ['style', 'lyrics']),
  audio_analyze: obj({ alias: str(80) }, ['alias']),
  storyboard_prepare: obj({ song: str(80), brief: str(10000), lyrics: str() }, ['song', 'brief']),
  production_generate: obj({ title: str(120), song: str(80), brief: str(10000), lyrics: str(), storyboard: str(80), scenes: arr(scene, 100, 1), aspect_ratio: videoRatios, keyframe_precision: en('bf16', 'int8'), keyframe_variant: en('base', 'turbo'), keyframe_quality: en('quality', 'draft'), video_profile: en('base', 'turbo', 'flex', 'fused_turbo'), video_steps: integer(4, 40), keyframe_options: modelOptions.image, keyframe_resolution: en('legacy', '1mp', '2k'), video_options: modelOptions.video, seed: integer(0, Number.MAX_SAFE_INTEGER) }, ['title', 'song', 'brief']),
  video_upscale: obj({ video: str(80), scale: { type: 'integer', enum: [2, 4] }, quality: en('fast', 'quality'), seed: integer(0, 2 ** 50) }, ['video']),
  video_face_refine: obj({ video: str(80), identity: str(80), strength: en('light', 'medium', 'strong'), seed: integer(0, 2 ** 53) }, ['video']),
  audio_stems: obj({ audio: str(80), stems: en('two', 'four'), format: en('flac', 'mp3') }, ['audio']),
  audio_sound: obj({ prompt: str(4000), kind: en('music', 'instrument', 'sfx', 'one_shot'), seconds: num(0.5, 380), enhance: { type: 'boolean' }, format: en('flac', 'mp3'), seed: integer(0, Number.MAX_SAFE_INTEGER) }, ['prompt']),
  audio_speech: obj({ text: str(5000), voice: en('preset', 'design', 'clone'), speaker: en('serena', 'vivian', 'uncle_fu', 'ryan', 'aiden', 'ono_anna', 'sohee', 'eric', 'dylan'), instruct: str(1000), language: en('auto', 'spanish', 'english', 'portuguese', 'french', 'german', 'italian', 'japanese', 'korean', 'chinese', 'russian'), reference: str(80), reference_text: str(1000), consent: { type: 'boolean' }, format: en('flac', 'mp3'), seed: integer(0, Number.MAX_SAFE_INTEGER) }, ['text']),
  video_remove: obj({ video: str(80), target: str(300), clean_frame: str(80), seed: integer(0, 2 ** 53) }, ['video']),
  video_swap: obj({ mode: en('character', 'head', 'scail'), video: str(80), character: str(80), target: str(300), seed: integer(0, 2 ** 53) }, ['video', 'character']),
  job_status: obj({ job_id: str(80) }, ['job_id']), job_cancel: obj({ job_id: str(80) }, ['job_id']), job_resume: obj({ job_id: str(80) }, ['job_id']),
  artifact_export: obj({ alias: str(80), format: en('png', 'jpeg', 'webp'), quick: { type: 'boolean' }, quality: integer(1, 100), background: str(7) }, ['alias']),
};
const descriptions = {
  capabilities: 'Current models, limits, quality presets, and supported modes.', health: 'Workers, GPU guards and real queue status.',
  prompt_guide: 'Full prompt-writing guide for one medium: image (Qwen, MOSS, FLUX 3 Klein), edit (Qwen, FLUX), video (MiniMax H3, Kandinsky 6), music (YuE2, ACE-Step), sound (Stable Audio 3), speech (Qwen3-TTS) or director. Read it before writing an H3 or edit prompt you have not written in this run.',
  prompt_check: 'Free structural check of a prompt before generating: field order, H3 labels versus the inputs you will send (images/videos/videos_with_audio/audios counts), shot timestamps, <d> tags, speech density, YuE2 sections. For music, prompt is the style. Fix errors before calling a generation tool.',
  characters_list: 'The user’s private characters and LoRA library. Call it whenever the request mentions @handle (e.g. "@ana bailando") or a LoRA/style from their library. Each character has a look description and image aliases for its references (use them as edit references, r2v references or the swap character) and maybe a LoRA. Each LoRA has an id, base (qwen = image_generate/image_edit, h3 = video_generate), trigger words and status; pass ready ones as loras [{id, strength}] (max 4, same base as the tool) and put the trigger words in the prompt.',
  library_search: 'Literal case-insensitive search of metadata, NOT semantic search. q is optional: omit q to list a kind. After no matches, list the kind once rather than guessing synonyms. Returns typed aliases; never use a song alias as an image. Paginate with offset.',
  artifact_inspect: 'Inspect a known alias: reduced image or up to six timestamped video frames, alpha stats, or technical audio metadata. No whole video/audio sent.',
  image_generate: 'Create image. model=moss (MOSS-Image) is best for posters, layouts and quoted in-image text; it takes only prompt, aspect_ratio, quality and seed. model=flux3 (FLUX 3 Klein) is fast photorealism with its own prompt upsampler (a short prompt is fine); it takes only prompt, aspect_ratio, quality (draft = 16-step distilled, quality = 50-step base) and seed. Defaults BF16, 40 steps, 1 MP; resolution_tier=2k renders about 4 MP with model_precision=int8 when 2K is enabled. model_variant=turbo uses Qwen-Image-2.1-Turbo: same prompt, fixed 8-step schedule (no steps/scheduler/denoise), ideal for fast drafts and iterations; base stays the maximum-fidelity default. control = {reference image alias, mode canny|depth|pose|map, strength 0.1–1.5 (unset = per-mode default)} makes a Qwen 1MP image follow the edges, depth or body pose of that image (map: the alias already is a pose/depth/line map); pick the aspect_ratio closest to the reference. Waits for real completion. Do not call again for review corrections without an explicit user request.',
  image_edit: 'Edit/compose ordered image aliases (1–10, the Qwen-Image-2.1 maximum). model=flux3 edits/composes 1–4 aliases with FLUX 3 Klein (16 steps; its upsampler sees the images; about 1 MP in the first image shape); it takes only prompt, references and seed. First is target; prompt is required unless camera or remove_background is set. remove_background=true cuts ONE image alias out onto a transparent PNG (official Qwen instruction, base, 40 steps; prompt unused) — use it for "quitar/remove the background", not transparent=true. Defaults BF16/40 steps, resolution 1024. resolution up to 2048 edits at 2K (about 4 MP) only with model_precision=int8, at most 4 aliases, no camera or remove_background, and when 2K is enabled; it is slow (about 4 min with one image, 9 with four), so use it for final renders. model_variant=turbo edits in 8 fixed steps with the same prompt. camera = {azimuth, elevation, distance} re-shoots ONE image alias from another viewpoint (QMA LoRA; base only, no options or transparency); directions are relative to the source camera, prompt then is optional extra edits.',
  video_face_refine: 'Redraw the main face of a known 1–15 s video alias sharper and truer to identity (H3 face refine); keeps everything else and the audio, creates a NEW video. identity = optional known image alias of the person (a swap result reuses its character automatically). strength light|medium|strong (default medium). Use when the user asks to fix, sharpen or refine faces; for small faces upscale first.',
  audio_sound: 'Stable Audio 3, no vocals: kind=music (instrumental track, 5–380 s), instrument (solo part or loop, 2–380 s), sfx (effects or ambience, 1–120 s), one_shot (single hit or sample, 0.5–10 s); seconds is the exact length. enhance (default true) lets Qwen rewrite the idea with the official category prompt. Use for background music, beds, loops, foley and sound effects; songs with lyrics go to music_generate.',
  audio_speech: 'Speak a text (Qwen3-TTS, 10 languages). voice=preset uses speaker (serena, vivian, sohee, ono_anna female; ryan, aiden, uncle_fu, eric, dylan male) with optional instruct for delivery; voice=design invents a voice from instruct (gender, age, timbre, accent, emotion); voice=clone copies the voice of a known 3–30 s audio/video alias (reference, plus reference_text = its exact words when known). Clone ONLY the user’s own voice or someone who agreed, never to deceive: ask the user to confirm that permission first and pass consent=true only after they do.',
  audio_stems: 'Split a known song/audio alias (1–900 s) with Hybrid Demucs into NEW audio files: stems=two (default) vocals + instrumental, stems=four vocals, drums, bass and other. Takes seconds. Use when the user asks for stems, an acapella, a karaoke/instrumental version, or to remove the voice or the music.',
  video_remove: 'Erase one person from a known 1–10 s video alias (best ≤5 s, steady shot) and rebuild the background (SAM 3.1 + H3 Person Remover). target = short English description of who to remove (default the most prominent person); clean_frame = optional known image alias of the first frame without them (else made with Qwen edit). Keeps the rest and the original audio; creates a NEW video. Use only when the user asks to remove/erase someone.',
  video_swap: 'Replace one person in a known 2–15 s video alias (best ≤5 s, one shot) with the character in a known image alias (H3 Character Swap). Keeps motion, scene and the original audio; creates a NEW video. mode=character (default) swaps the whole person (face, hair, outfit); mode=head swaps only the head and keeps body and clothes (character = a clear face image); mode=scail swaps the whole person with SCAIL-2 (Wan 2.1), which tracks the body motion tightly and re-lights the character into the scene. target = English description of who to replace (default the main person). Use only when the user asks to swap/replace a person or character, and only for consenting real people or fictional characters.',
  video_upscale: 'Upscale a known video alias with FlashVSR v1.1: scale 2 (default) or 4 (small sources only, see capabilities.upscale), quality fast (default) or quality (slower). Keeps the original audio and creates a NEW video; the source is unchanged. Use only when the user asks for upscaling, higher resolution, 2x/4x, 1080p/4K-style enlargement or sharper video.',
  video_generate: 'model=kandinsky6 makes one 5 s Kandinsky 6.0 clip (16:9 or 9:16, 864x480) WITH synchronized audio and lip-synced speech from text (t2v) or a first_frame (i2v): put spoken lines in the prompt as <S>exact words<E> and the voice/sounds in audio_prompt; it takes only prompt, audio_prompt, first_frame, aspect_ratio, literal_prompt and seed. Prefer it when someone must say a short line with matching lips. Otherwise: generate MiniMax-H3 video, 5–15 seconds. profile=base uses 8–40 steps (default 20); profile=turbo adds the LightX2V Turbo LoRAs to the real H3 weights (true Ref2VA for r2v), 4–12 steps (default 8): the fast choice for drafts, iteration and many Director scenes. profile=fused_turbo uses 4–12 (default 4), an experimental community merge, not Maestro SLA. profile=omni is FastH3 Omni, an 8-step distilled Ref2VA checkpoint: r2v only, fast reference-driven clips. profile=flex is Pika H3 Flex, official six-step LoRAs on the real weights for t2v, i2v and r2v: steps stay 6 and options cannot change sampler, scheduler, denoise or shifts; no control. Choose turbo when the user asks for Turbo/fast H3, omni for FastH3/Omni, flex for Flex/Pika/6-step, fused_turbo only for Fused/4-step; never just lower base steps. Check profile availability. i2v requires first_frame (add last_frame for FL2VA); t2v with only last_frame lands on that image (L2VA); the runtime adds the keyframe alignment line. r2v requires image or video references and the six-section Ref2VA prompt. Reference/frame arguments are known aliases. options controls native generation resolution, sampler, schedule, sigma shifts and encoding. r2v supports up to 9 images, 3 reference_videos (2–15 s) and 3 reference_audios (2–15 s), at most 12 files; total reference video ≤ 15 s and total audio (soundtracks of reference videos included) ≤ 15 s. control = {video, mode, strength, keep_audio} makes the new clip follow a known 2–15 s video alias (Fun ControlNet-Union 2.0): mode=pose copies the movement of up to 2 people ("que baile como en este vídeo"), canny keeps the outlines, depth keeps the 3D layout and camera move; it forces r2v, references become optional (use them for who appears), base or turbo only, and the clip sets length and aspect; keep_audio (default true) keeps its soundtrack. Check capabilities.generation_options for limits; do not confuse sampling steps with output resolution or CRF.',
  music_generate: 'Generate a song. model=ace_step (ACE-Step 1.5 XL Turbo) is fast and max_duration is the exact length (10–600 s), with optional bpm, key (e.g. E minor) and language; no covers. model=yue2 (default) is slower, supports covers and ABC. YuE2: use [Instrumental] lyrics for instrumental music. Structured lyrics [Verse]/[Chorus], voice, instruments, genre and mood in style. Cover uses source_audio with full or melody mode. options exposes composition, automatic ABC score, diffusion sampling and FLAC/MP3/Opus encoding. Score controls do not modify supplied ABC or extracted cover scores.',
  audio_analyze: 'Local technical audio analysis; never claim you listened to audio.',
  storyboard_prepare: 'Prepare a contiguous storyboard covering the real duration of a known song. Returns a storyboard alias; does not generate media.',
  production_generate: 'Execute a complete Director production from storyboard alias or explicit scenes. Reuse known image/video aliases, original song retained. A scene with lip_sync=true (>=2 s, new clip only) is rendered in r2v with its keyframe as <Picture 1> and the song excerpt as <Audio 1>; its video_prompt must be Ref2VA (see prompt_guide director). Short clips repeat to cover their scene; excess is trimmed. Explain this when reusing clips. New keyframes default BF16/40 steps/1 MP. keyframe_options and video_options apply to newly generated scenes; final canvas follows video_options.resolution. Seed is incremented per scene.',
  job_status: 'Inspect a job previously authorized in this conversation.', job_cancel: 'Cancel only an authorized job, only when user requests cancellation.', job_resume: 'Explicitly resume a failed/cancelled/interrupted authorized job, only when user asks. Productions reuse partial output; other media restart the requested job.',
  artifact_export: 'Only when user asks to save/export: open native Save As or quick-save folder dialog. Never provide paths. Images PNG/JPEG/WebP, audio/video original media.',
};
const TOOLS = Object.entries(schemas).map(([name, parameters]) => ({ type: 'function', function: { name, description: descriptions[name], parameters } }));

function validate(schema, value, at = 'arguments') {
  if (schema.type === 'object') {
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`${at}: object required`);
    for (const key of Object.keys(value)) {
      if (!Object.hasOwn(schema.properties, key)) throw new Error(`${at}: unknown field ${key}`);
      validate(schema.properties[key], value[key], `${at}.${key}`);
    }
    for (const key of schema.required || []) if (!Object.hasOwn(value, key)) throw new Error(`${at}.${key}: required`);
  } else if (schema.type === 'array') {
    if (!Array.isArray(value) || value.length < schema.minItems || value.length > schema.maxItems) throw new Error(`${at}: invalid array size`);
    value.forEach((item, i) => validate(schema.items, item, `${at}[${i}]`));
  } else {
    const type = schema.type === 'integer' ? 'number' : schema.type;
    if (typeof value !== type || (type === 'number' && !Number.isFinite(value))) throw new Error(`${at}: ${schema.type} required`);
    if (schema.type === 'integer' && !Number.isSafeInteger(value)) throw new Error(`${at}: safe integer required`);
    if (schema.enum && !schema.enum.includes(value)) throw new Error(`${at}: unsupported value`);
    if (schema.minimum !== undefined && value < schema.minimum || schema.maximum !== undefined && value > schema.maximum) throw new Error(`${at}: outside limits`);
    if (schema.minLength && value.length < schema.minLength || schema.maxLength && value.length > schema.maxLength) throw new Error(`${at}: invalid length`);
  }
}

const TERMINAL = new Set(['completed', 'failed', 'cancelled', 'interrupted', 'blocked_gpu']);
const ACTIVE = new Set(['running', 'recovering']);
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
function safeData(value) {
  if (value === undefined) return null;
  return JSON.parse(JSON.stringify(value, (key, val) => {
    if (/^(apiKey|encryptedKey|authorization|headers|base64|preview|dataUri)$/i.test(key)) return undefined;
    if (typeof val === 'string') return val.replace(/data:[^\s"']*;base64,[A-Za-z0-9+/=]+/g, '[binary omitted]')
      .replace(/"(?:apiKey|encryptedKey|authorization|headers|base64)"\s*:\s*(?:"(?:[^"\\]|\\.)*"|\{[^}]*\})/gi, '"redacted":"[omitted]"');
    return val;
  }));
}

class AgentEngine {
  constructor({ directory, runtime, chat, provider, inspect, director, exporter, emit = () => {}, redact = s => s, pollMs = 1250, web = false }) {
    Object.assign(this, { directory, runtime, chat, provider, inspect, director, exporter, emit, redact, pollMs });
    this.tools = web ? TOOLS.map(t => t.function.name === 'artifact_export' ? { ...t, function: { ...t.function,
      description: 'Only on explicit export/download request: prepare a browser download action. The user must click it. Never claim a local file was saved and never accept local paths.' } } : t) : TOOLS;
    this.runs = new Map(); this.executing = new Set(); this.previewCache = new Map(); this.capCache = null;
    this.startingSessions = new Set();
    fs.mkdirSync(directory, { recursive: true });
    this.loadErrors = [];
    for (const name of fs.readdirSync(directory).filter(n => /^run_[a-f0-9]{24}\.json$/.test(n))) {
      try {
        const run = JSON.parse(fs.readFileSync(path.join(directory, name), 'utf8'));
        if (run.id !== name.slice(0, -5) || !Array.isArray(run.transcript) || !Array.isArray(run.turns) || !run.artifacts || !run.jobs) throw new Error('invalid run record');
        if (ACTIVE.has(run.status)) run.status = 'recovering';
        this.runs.set(run.id, run);
      } catch { this.loadErrors.push(name); /* Preserve corrupt source; direct modes must still start. */ }
    }
  }
  save(run) {
    run.updatedAt = Date.now();
    const target = path.join(this.directory, `${run.id}.json`), temporary = `${target}.tmp`;
    fs.writeFileSync(temporary, this.redact(JSON.stringify(safeData(run))), { mode: 0o600 });
    fs.renameSync(temporary, target);
    this.emit(this.view(run));
  }
  view(run) { return JSON.parse(this.redact(JSON.stringify(safeData({ ...run, transcript: undefined })))); }
  get(id, session) {
    if (id) { const run = this.runs.get(id); if (!run) throw new Error('Ejecución desconocida.'); return this.view(run); }
    return [...this.runs.values()].filter(r => !session || r.session === session).sort((a, b) => a.createdAt - b.createdAt).map(r => this.view(r));
  }
  register(run, ref, hint = '') {
    if (!ref || !/^artifact:\/\/[A-Za-z0-9_-]+\/(images|references|sources|songs|videos|productions)\/[A-Za-z0-9_.-]+$/.test(ref.uri) || !/^[a-f0-9]{64}$/i.test(ref.sha256)) throw new Error('Referencia URI/SHA-256 inválida.');
    const known = Object.entries(run.artifacts).find(([, r]) => r.uri === ref.uri && r.sha256 === ref.sha256);
    if (known) return known[0];
    const alias = `artifact${Object.keys(run.artifacts).length + 1}`;
    run.artifacts[alias] = { uri: ref.uri, sha256: ref.sha256, kind: ref.kind,
      content_type: ref.content_type, width: ref.width, height: ref.height,
      has_alpha: ref.has_alpha, label: hint || ref.title || String(ref.input_prompt || ref.prompt || ref.style || alias).slice(0, 120) };
    return alias;
  }
  ref(run, alias, kind) {
    const ref = run.artifacts[alias];
    if (!ref) throw new Error(`Alias desconocido: ${alias}. Consulta la biblioteca, no inventes referencias.`);
    if (kind === 'image' && !/\/(images|references)\//.test(ref.uri)) throw new Error('Se requiere una imagen.');
    if (kind === 'audio' && !/\.(wav|flac|mp3|opus|ogg)$/i.test(ref.uri)) throw new Error('Se requiere audio.');
    if (kind === 'video' && !/\.(mp4|mkv|webm)$/i.test(ref.uri)) throw new Error('Se requiere vídeo.');
    return { uri: ref.uri, sha256: ref.sha256 };
  }
  owned(run, id) {
    if (!Object.values(run.jobs).some(j => j.id === id)) throw new Error('Trabajo no autorizado en esta conversación.');
    return id;
  }
  async capabilities() {
    if (!this.capCache || Date.now() - this.capCache.at > 30000) this.capCache = { at: Date.now(), data: await this.runtime('GET', '/v1/capabilities') };
    return this.capCache.data;
  }
  async start(payload) {
    const requestHash = crypto.createHash('sha256').update(JSON.stringify({ prompt: payload?.prompt, session: payload?.session,
      references: payload?.references || [] })).digest('hex');
    if (payload?.idempotencyKey) {
      if (!/^[\x21-\x7e]{1,128}$/.test(payload.idempotencyKey)) throw new Error('Idempotency-Key inválida');
      const previous = [...this.runs.values()].find(r => r.idempotencyKey === payload.idempotencyKey);
      if (previous) { if (previous.requestHash !== requestHash) throw new Error('Idempotency-Key conflict'); return this.view(previous); }
    }
    if (!this.provider()?.tools) throw new Error('El proveedor debe admitir herramientas; Crear/Editar directos siguen disponibles.');
    const request = String(payload?.prompt || '').trim();
    if (!request || request.length > 20000 || !/^[A-Za-z0-9_-]{1,80}$/.test(payload?.session || '')) throw new Error('Solicitud o sesión inválida.');
    if (this.startingSessions.has(payload.session) || [...this.runs.values()].some(r => r.session === payload.session && ACTIVE.has(r.status))) throw new Error('Ya hay una ejecución en esta sesión.');
    this.startingSessions.add(payload.session);
    try {
    const refs = payload.references || [];
    if (!Array.isArray(refs) || refs.length > 16) throw new Error('Máximo dieciséis referencias.');
    const previous = [...this.runs.values()].filter(r => r.session === payload.session).sort((a, b) => a.createdAt - b.createdAt);
    const run = { id: `run_${crypto.randomBytes(12).toString('hex')}`, session: payload.session, request, status: 'running', createdAt: Date.now(),
      artifacts: {}, jobs: {}, storyboards: {}, turns: [], transcript: [], pending: null, responses: 0, calls: 0, cancelled: false, final: '', notices: [], mirrored: [] };
    if (payload.idempotencyKey) Object.assign(run, { idempotencyKey: payload.idempotencyKey, requestHash });
    for (const old of previous) {
      for (const ref of Object.values(old.artifacts)) this.register(run, ref);
      Object.assign(run.jobs, old.jobs);
    }
    for (let i = 0; i < refs.length; i++) this.register(run, refs[i], `Referencia ${i + 1}`);
    run.references = refs.map((r, i) => ({ alias: this.register(run, r), number: i + 1, role: i === 0 ? 'edit target' : 'visual reference' }));
    // Incoming artifacts must be real; metadata is kept, previews remain memory-only.
    for (const ref of refs) {
      const inspection = await this.inspect(ref);
      if (inspection.preview && this.provider()?.vision) this.previewCache.set(`${run.id}:${ref.sha256}`, {
        runId: run.id, alias: this.register(run, ref), kind: inspection.kind,
        dataUri: `data:${inspection.preview.mime};base64,${inspection.preview.base64}`, inspection: safeData(inspection),
      });
    }
    run.transcript = previous.slice(-6).flatMap(r => [{ role: 'user', content: r.request }, { role: 'assistant', content: r.final || `Estado: ${r.status}` }]);
    if (!previous.length) {
      try {
        const legacy = await this.runtime('GET', `/v1/sessions/${run.session}`);
        run.transcript = (legacy.messages || []).filter(m => ['user', 'assistant'].includes(m.role)).slice(-12)
          .map(m => ({ role: m.role, content: String(m.content).slice(0, 10000) }));
        for (const message of legacy.messages || []) for (const r of message.media || []) this.register(run, r, 'Sesión anterior');
      } catch { /* A brand-new session has no legacy history. */ }
    }
    run.transcript.push({ role: 'user', content: request });
    this.runs.set(run.id, run); this.save(run); this.drive(run);
    return this.view(run);
    } finally { this.startingSessions.delete(payload.session); }
  }
  async mirror(run, token, role, content, media = []) {
    if (run.mirrored.includes(token)) return;
    try {
      await this.runtime('POST', `/v1/sessions/${run.session}/messages`, { role, content: this.redact(content).slice(0, 100000), media: media.map(r => ({ uri: r.uri, sha256: r.sha256 })) });
      run.mirrored.push(token); this.save(run);
    } catch { /* Local structured record remains authoritative while Saturno is offline. */ }
  }
  async recover() {
    for (const run of this.runs.values()) if (run.status === 'recovering') this.drive(run);
  }
  async continue(id) {
    const run = this.runs.get(id);
    if (!run || !['paused', 'budget', 'failed'].includes(run.status)) throw new Error('No hay una ejecución pendiente para continuar.');
    run.cancelled = false; run.status = 'running'; run.responses = 0; run.calls = 0; run.error = '';
    this.save(run); this.drive(run); return this.view(run);
  }
  async cancel(id, jobId) {
    const run = this.runs.get(id);
    if (!run) throw new Error('Ejecución desconocida.');
    if (jobId) {
      this.owned(run, jobId);
      await this.runtime('DELETE', `/v1/jobs/${jobId}`);
      run.jobs[jobId].cancellationRequested = true; this.save(run);
      return this.view(run);
    }
    run.cancelled = true; this.save(run);
    await this.reconcileCancellation(run);
    for (const j of Object.values(run.jobs).filter(j => j.runId === run.id && !TERMINAL.has(j.status))) await this.runtime('DELETE', `/v1/jobs/${j.id}`);
    if (!this.executing.has(id)) { run.status = 'cancelled'; this.save(run); }
    return this.view(run);
  }
  async reconcileCancellation(run) {
    for (const turn of run.turns.filter(t => t.intent && !t.jobId)) {
      const scope = turn.intent.endpoint.endsWith('/resume') ? `resume:${turn.intent.endpoint.split('/').at(-2)}` : turn.intent.endpoint.split('/').pop();
      try {
        const receipt = await this.runtime('GET', `/v1/jobs/by-idempotency?${new URLSearchParams({ scope, key: turn.intent.key })}`);
        turn.jobId = receipt.job_id;
        run.jobs[receipt.job_id] = { id: receipt.job_id, status: receipt.status, runId: run.id };
        this.save(run);
      } catch (error) { if (!/Runtime 404:/.test(error.message)) throw error; }
    }
    for (const job of Object.values(run.jobs).filter(j => j.runId === run.id && !TERMINAL.has(j.status))) await this.runtime('DELETE', `/v1/jobs/${job.id}`);
  }
  async drive(run) {
    if (this.executing.has(run.id)) return;
    this.executing.add(run.id);
    try {
      if (run.cancelled) await this.reconcileCancellation(run);
      await this.mirror(run, 'request', 'user', run.request);
      while (!run.cancelled) {
        if (run.pending) {
          const pending = run.pending;
          for (; pending.index < pending.calls.length; pending.index++) {
            if (run.cancelled) break;
            const call = pending.calls[pending.index];
            if (run.calls >= 32 && !run.turns.some(t => t.id === call.id)) { run.status = 'budget'; this.save(run); return; }
            let turn = run.turns.find(t => t.id === call.id);
            if (!turn) { turn = { id: call.id, tool: call.function.name, arguments: call.function.arguments, status: 'pending' }; run.turns.push(turn); run.calls++; this.save(run); }
            let output = turn.result;
            if (turn.status !== 'done') {
              try {
                if (!Object.hasOwn(schemas, turn.tool)) throw new Error('Herramienta desconocida.');
                const args = JSON.parse(turn.arguments); validate(schemas[turn.tool], args);
                output = await this.execute(run, turn, args);
              } catch (error) {
                if (error.pause) throw error;
                output = { error: this.redact(String(error.message)), no_automatic_retry: true };
              }
              turn.result = safeData(output); turn.status = 'done'; this.save(run);
            }
            await this.mirror(run, turn.id, 'tool', `${turn.tool}: ${JSON.stringify(turn.result)}`, turn.result?.media || []);
            run.transcript.push({ role: 'tool', tool_call_id: call.id, content: JSON.stringify(turn.result) });
            pending.index++; this.save(run); pending.index--;
          }
          if (run.cancelled) break;
          run.pending = null; this.save(run);
        }
        if (run.responses >= 16 || run.calls >= 32) { run.status = 'budget'; this.save(run); return; }
        const caps = await this.capabilities();
        const health = await this.runtime('GET', '/v1/health');
        const system = this.instructions(run, caps, health);
        const outbound = [{ role: 'system', content: system }, ...run.transcript];
        // The provider sees all numbered attached images; individual inspection also remains available.
        const previews = this.provider()?.vision && !run.visionDisabled ? [...this.previewCache.values()].filter(p => p.runId === run.id) : [];
        if (previews.length) outbound.push({ role: 'user', content: previews.flatMap(p => [{ type: 'text', text: `Inspected ${p.alias} (${p.kind})` }, { type: 'image_url', image_url: { url: p.dataUri } }]) });
        let message;
        for (let attempt = 0; attempt < 2; attempt++) {
          try { message = await this.chat(outbound, this.tools, 6000); break; }
          catch (error) {
            if (attempt || !/timeout|fetch failed|ECONN|400|422|500|502|503|504|429/i.test(error.message)) throw error;
            if (previews.length) {
              run.visionDisabled = true;
              run.notices.push('La solicitud visual al proveedor falló; se continúa sólo con herramientas y metadatos, sin afirmar revisión visual.');
              outbound[0].content += '\nVISUAL INPUT FAILED: you cannot see images in this run. Report visual review unavailable; use actual tool metadata only.';
              for (const item of outbound) if (Array.isArray(item.content)) item.content = item.content.filter(part => part.type !== 'image_url');
              this.save(run);
            }
            const cooldown = Number(String(error.message).match(/Try again in (\d+) seconds/i)?.[1] || 0);
            await sleep(Math.min(15000, cooldown ? (cooldown + 1) * 1000 : 1000));
          }
        }
        if (run.cancelled) break;
        if (!message || typeof message !== 'object' || (message.content != null && typeof message.content !== 'string')) throw new Error('Respuesta inválida del proveedor.');
        run.responses++;
        const calls = message.tool_calls || [];
        if (!Array.isArray(calls) || calls.length > 32 || calls.some(c => typeof c.id !== 'string' || !c.id || c.id.length > 128 || !c.function || typeof c.function.name !== 'string' || typeof c.function.arguments !== 'string') || new Set(calls.map(c => c.id)).size !== calls.length || calls.some(c => run.turns.some(t => t.id === c.id))) throw new Error('Llamadas de herramientas inválidas o duplicadas.');
        if (!calls.length) {
          run.final = String(message.content || 'Sin respuesta textual.'); run.status = 'completed'; this.save(run);
          const media = Object.values(run.jobs).filter(j => j.runId === run.id && j.status === 'completed').flatMap(j => j.media || []);
          await this.mirror(run, 'final', 'assistant', run.final, media); return;
        }
        run.transcript.push({ role: 'assistant', content: message.content || null, tool_calls: safeData(calls) });
        run.pending = { calls: safeData(calls), index: 0 }; this.save(run);
      }
      run.status = 'cancelled'; this.save(run);
    } catch (error) {
      run.status = error.budget ? 'budget' : error.pause ? 'paused' : 'failed'; run.error = this.redact(String(error.message)); this.save(run);
    } finally { this.executing.delete(run.id); }
  }
  instructions(run, caps, health) {
    return [
      'You operate Media Lab. Sending the user request authorizes the requested tools and optimized model prompts. Preserve every explicit requirement, literal quoted text, identities and composition. Ask before material ambiguity.',
      'Create only what was requested. Review may suggest corrections but NEVER generate replacement or iterative variations based on failures, OOM, review or your own dissatisfaction. Do not retry failed GPU jobs. Cancel/resume/export only on explicit user request.',
      'Never claim media exists before completed tool results. Use artifact aliases from the registry, not paths, URLs, hashes or invented workflows. Process dependencies: use tool results before referring to new artifacts.',
      'Default Qwen image profile BF16, quality=quality (40 steps), resolution_tier=1mp. Respect explicit user adjustments. If BF16 unavailable clearly report INT8 fallback. Two independent 24 GiB GPUs, not pooled memory.',
      'Use options (images/video/music) or keyframe_options/video_options (Director) for user requested advanced controls. Query capabilities.generation_options for actual ranges and settings. Native node limits are not promises of VRAM availability. H3 has no CFG/negative prompt control in this pipeline. H3 video defaults to base/20 steps. For requests for Fused, Turbo or 4-step H3, use profile=fused_turbo/4 steps only if available; flex (Pika H3 Flex, fixed 6 steps) when the user asks for it. Director uses video_profile/video_steps for new clips; reused clips are unchanged. Fused uses native dense attention, not Maestro SLA: do not promise identical quality or add Turbo LoRAs.',
      modelPromptLanguage,
      guides.agentBrief,
      'Before writing an H3 prompt (especially r2v), an edit with several references, or a YuE2 cover, call prompt_guide for that medium, then prompt_check with the inputs you will send. Use alpha statistics when reviewing transparency.',
      'Audio analysis is technical, you have NOT listened. Vision sees reduced images or timestamped video contact sheets, not entire videos. Without vision tools still operate; state visual review unavailable.',
      'A storyboard must cover actual song duration, scenes >0 and <=15 seconds. A last scene shorter than 5s is allowed (runtime generates 5 then trims). Reuse visuals when user asks. Plan then execute requested production, do not stop merely after planning.',
      `Current capabilities: ${JSON.stringify(englishCapabilities(caps))}`, `Workers and queue: ${JSON.stringify(this.healthSummary(health))}`,
      `Known artifacts: ${JSON.stringify(run.artifacts)}`, `Authorized jobs: ${JSON.stringify(Object.values(run.jobs).map(j => ({ id: j.id, status: j.status })))}`,
      `Attached references in exact user order (first is editing target, regardless of alias number): ${JSON.stringify(run.references || [])}`,
      `Storyboards: ${JSON.stringify(Object.keys(run.storyboards))}`, `Visual review: ${Boolean(this.provider()?.vision && !run.visionDisabled)}`,
    ].join('\n');
  }
  async execute(run, turn, args) {
    const ref = (alias, kind) => this.ref(run, alias, kind);
    const caps = await this.capabilities();
    const precision = requested => {
      if (requested === 'bf16' && !caps.model_precisions?.bf16) throw new Error('BF16 solicitado pero no disponible.');
      if (!requested && !caps.model_precisions?.bf16 && !run.notices.includes('BF16 no disponible: se utiliza INT8.')) run.notices.push('BF16 no disponible: se utiliza INT8.');
      return requested || (caps.model_precisions?.bf16 ? 'bf16' : 'int8');
    };
    const turboFixed = options => {
      if (!options) return options;
      const kept = { ...options };
      const dropped = ['steps', 'scheduler', 'denoise'].filter(key => key in kept);
      dropped.forEach(key => delete kept[key]);
      if (dropped.length && !run.notices.includes('Turbo usa su calendario fijo de 8 pasos.')) run.notices.push('Turbo usa su calendario fijo de 8 pasos.');
      return kept;
    };
    const variantPrecision = (variant, requested) => {
      if (variant !== 'turbo') return precision(requested);
      const ready = caps.model_variants?.turbo?.precisions || {};
      if (!ready.int8 && !ready.bf16) throw new Error('Qwen-Image 2.1 Turbo no disponible; no se sustituye automáticamente.');
      if (requested && !ready[requested]) throw new Error(`Turbo ${requested.toUpperCase()} no disponible.`);
      return requested || (ready.bf16 ? 'bf16' : 'int8');
    };
    if (turn.tool === 'capabilities') return englishCapabilities(caps);
    if (turn.tool === 'prompt_guide') return { topic: args.topic, guide: guides.topics[args.topic] };
    if (turn.tool === 'prompt_check') return this.runtime('POST', '/v1/prompts/check', args);
    if (turn.tool === 'health') return this.healthSummary(await this.runtime('GET', '/v1/health'));
    if (turn.tool === 'library_search') {
      const data = await this.runtime('GET', `/v1/library?${new URLSearchParams({ ...args, limit: args.limit || 30 })}`);
      return { ...data, items: data.items.map(item => ({ alias: this.register(run, item), uri: item.uri, sha256: item.sha256,
        kind: item.kind, created_at: item.created_at, width: item.width, height: item.height,
        has_alpha: item.has_alpha, title: item.title, prompt: String(item.input_prompt || item.prompt || item.style || '').slice(0, 600) })) };
    }
    if (turn.tool === 'characters_list') {
      const [people, library] = await Promise.all([this.runtime('GET', '/v1/characters'), this.runtime('GET', '/v1/loras')]);
      return {
        characters: (people.items || []).map(c => ({ handle: `@${c.handle}`, name: c.name, description: c.description,
          references: c.references.map((r, i) => this.register(run, { ...r, kind: 'images' }, `@${c.handle} ${i + 1}`)), lora: c.lora })),
        loras: library.ready ? (library.items || []).map(l => ({ id: l.id, name: l.name, base: l.base, trigger: l.trigger, strength: l.strength, status: l.status })) : [],
      };
    }
    if (turn.tool === 'artifact_inspect') {
      const artifact = ref(args.alias);
      const key = `${run.id}:${artifact.sha256}`;
      let inspection = this.previewCache.get(key)?.inspection;
      if (!inspection) {
        inspection = await this.inspect(artifact);
        if (inspection.preview && this.provider()?.vision) this.previewCache.set(key, { runId: run.id, alias: args.alias, kind: inspection.kind,
          dataUri: `data:${inspection.preview.mime};base64,${inspection.preview.base64}`, inspection: safeData(inspection) });
      }
      return safeData(inspection);
    }
    if (turn.tool === 'audio_analyze') {
      const r = ref(args.alias, 'audio'); return this.runtime('GET', `/v1/media/analyze?uri=${encodeURIComponent(r.uri)}&sha256=${r.sha256}`);
    }
    if (turn.tool === 'storyboard_prepare') {
      const r = ref(args.song, 'audio');
      const analysis = await this.runtime('GET', `/v1/media/analyze?uri=${encodeURIComponent(r.uri)}&sha256=${r.sha256}`);
      if (run.responses >= 16) { const error = new Error('Límite de respuestas: continúa explícitamente.'); error.pause = true; error.budget = true; throw error; }
      const plan = await this.director({ brief: args.brief, lyrics: args.lyrics || '', analysis });
      run.responses++; this.save(run);
      this.checkScenes(plan.scenes, analysis.duration);
      const alias = `storyboard${Object.keys(run.storyboards).length + 1}`;
      run.storyboards[alias] = plan.scenes; return { alias, scenes: plan.scenes, duration: analysis.duration };
    }
    if (turn.tool === 'artifact_export') {
      // Native dialog is also the explicit confirmation. The model cannot pick any local path.
      if (!/(guardar|descargar|export|save|download)/i.test(run.request)) throw new Error('Guardar requiere una solicitud explícita del usuario.');
      const r = ref(args.alias); const inspection = await this.inspect(r);
      const result = await this.exporter({ ...r, has_alpha: inspection.alpha?.has_alpha }, {
        ...args, operation: inspection.metadata?.operation === 'edit' ? 'edit' : 'generate', seed: inspection.metadata?.seed,
      });
      run.exported = result; this.save(run);
      return result.prepared ? { prepared: true, saved: false, action: 'User must click the browser download action; no local file has been saved.' }
        : { cancelled: result.cancelled, saved: !result.cancelled }; // Local path never sent to provider.
    }
    if (turn.tool === 'job_status' || turn.tool === 'job_cancel') {
      this.owned(run, args.job_id);
      if (turn.tool === 'job_cancel' && !/(cancel|det[eé]n|stop|parar)/i.test(run.request)) throw new Error('Cancelar requiere una solicitud explícita.');
      return this.runtime(turn.tool === 'job_status' ? 'GET' : 'DELETE', `/v1/jobs/${args.job_id}`);
    }
    let endpoint, body = { ...args, session_id: run.session };
    if (args.loras?.length && !caps.loras?.ready) throw new Error('La biblioteca de LoRAs no está disponible.');
    const videoProfile = (profile = 'base', steps) => {
      const entry = caps.video?.profiles?.[profile];
      if ((entry && !entry.ready) || (!entry && profile !== 'base')) throw new Error(`H3 ${profile} no disponible; no se sustituye automáticamente.`);
      const limits = entry?.steps || { min: 8, max: 40, default: 20 };
      const actual = steps ?? limits.default;
      if (actual < limits.min || actual > limits.max) throw new Error(`H3 ${profile} requiere ${limits.min}–${limits.max} pasos.`);
      return actual;
    };
    if (turn.tool === 'image_generate') {
      endpoint = '/v1/jobs/generate'; body = { aspect_ratio: '1:1', quality: 'quality', resolution_tier: '1mp', ...body, model_precision: variantPrecision(args.model_variant, args.model_precision) };
      if (body.model === 'moss' || body.model === 'flux3') {
        if (!caps.image_models?.[body.model]?.ready) throw new Error(`${body.model === 'moss' ? 'MOSS-Image' : 'FLUX 3 Klein'} no disponible; no se sustituye automáticamente.`);
        if (args.control || args.loras?.length) throw new Error('El control de estructura y los LoRAs son solo para Qwen-Image.');
        body = { model: body.model, prompt: body.prompt, aspect_ratio: body.aspect_ratio, quality: body.quality, seed: body.seed, session_id: body.session_id, model_precision: 'int8' };
      }
      if (args.control) {
        const mode = args.control.mode || 'canny';
        if (!caps.image_control?.modes?.[mode]) throw new Error(`Control ${mode} no disponible.`);
        body.control = { ...args.control, mode, reference: ref(args.control.reference, 'image') };
      }
      if (body.model_variant === 'turbo') body.options = turboFixed(body.options);
      if (body.resolution_tier === '2k' && (!caps.two_k_enabled || body.model_precision === 'bf16')) throw new Error('Este perfil 2K no está habilitado.');
    } else if (turn.tool === 'image_edit') {
      endpoint = '/v1/jobs/edit'; body = { quality: 'quality', resolution: 1024, ...body, model_precision: variantPrecision(args.model_variant, args.model_precision), references: args.references.map(a => ref(a, 'image')) };
      if (body.resolution > 1024 && (!caps.two_k_enabled || body.model_precision !== 'int8' || body.references.length > 4 || args.camera || args.remove_background))
        throw new Error('La edición 2K necesita 2K habilitado, INT8, hasta 4 imágenes y sin ángulo ni quitar fondo.');
      if (args.model === 'flux3') {
        if (!caps.image_models?.flux3?.ready) throw new Error('FLUX 3 Klein no disponible; no se sustituye automáticamente.');
        if (body.references.length > (caps.image_models.flux3.max_references || 4)) throw new Error('FLUX 3 Klein edita con hasta 4 imágenes.');
        if (args.camera || args.remove_background || args.loras?.length) throw new Error('FLUX 3 Klein no hace ángulo, quitar fondo ni LoRAs.');
        if (!args.prompt?.trim()) throw new Error('Describe la edición.');
        body = { model: 'flux3', prompt: args.prompt, references: body.references, seed: args.seed, session_id: run.session };
      } else if (body.model_variant === 'turbo') body.options = turboFixed(body.options);
      if (body.resolution % 32) throw new Error('Resolución debe ser múltiplo de 32.');
      if (args.remove_background) {
        if (!caps.image_remove_background?.ready) throw new Error('Quitar fondo no disponible.');
        if (body.references.length !== 1) throw new Error('Quitar el fondo usa una sola imagen.');
        body.model_variant = 'base'; body.prompt = ''; delete body.options; delete body.transparent; delete body.camera;
      } else if (args.camera) {
        if (!caps.image_camera?.ready) throw new Error('Cambio de ángulo no disponible.');
        if (body.references.length !== 1) throw new Error('El cambio de ángulo usa una sola imagen.');
        body.model_variant = 'base'; delete body.options; delete body.transparent;
      } else if (!args.prompt?.trim()) throw new Error('Describe la edición.');
    } else if (turn.tool === 'video_generate' && args.model === 'kandinsky6') {
      if (!caps.video?.models?.kandinsky6?.ready) throw new Error('Kandinsky 6 no disponible; no se sustituye automáticamente.');
      endpoint = '/v1/jobs/video';
      body = { model: 'kandinsky6', prompt: args.prompt, mode: args.first_frame ? 'i2v' : 't2v', aspect_ratio: args.aspect_ratio === '9:16' ? '9:16' : '16:9',
        seconds: 5, seed: args.seed, session_id: run.session, ...(args.audio_prompt ? { audio_prompt: args.audio_prompt } : {}),
        ...(args.literal_prompt ? { literal_prompt: true } : {}), ...(args.first_frame ? { first_frame: ref(args.first_frame, 'image') } : {}) };
    } else if (turn.tool === 'video_generate') {
      if (!caps.video?.ready) throw new Error('H3 no disponible.');
      delete body.model; delete body.audio_prompt; delete body.literal_prompt;
      endpoint = '/v1/jobs/video'; body.mode ||= 't2v';
      body.profile ||= 'base'; body.steps = videoProfile(body.profile, body.steps);
      for (const name of ['first_frame', 'last_frame']) if (args[name]) body[name] = ref(args[name], 'image');
      if (args.references) body.references = args.references.map(a => ref(a, 'image'));
      if (args.reference_videos) body.reference_videos = args.reference_videos.map(a => ref(a, 'video'));
      if (args.reference_audios) body.reference_audios = args.reference_audios.map(a => ref(a, 'audio'));
      if (args.control) {
        if (!caps.video?.control?.modes?.[args.control.mode || 'pose']) throw new Error('Control de vídeo no disponible para ese modo.');
        if (!['base', 'turbo'].includes(body.profile)) throw new Error('El control de vídeo usa el perfil base o turbo.');
        body.mode = 'r2v'; body.control = { ...args.control, video: ref(args.control.video, 'video') };
      }
    } else if (turn.tool === 'music_generate') {
      if (args.model === 'ace_step') { if (!caps.music?.models?.ace_step?.ready) throw new Error('ACE-Step no disponible; no se sustituye automáticamente.'); if (args.source_audio) throw new Error('ACE-Step no hace covers; usa YuE2.'); }
      else if (!caps.music?.ready) throw new Error('YuE2 no disponible.');
      endpoint = '/v1/jobs/song'; if (args.source_audio) { if (!caps.music.cover_ready) throw new Error('Cover no disponible.'); body.source_audio = ref(args.source_audio, 'audio'); body.mode ||= 'full'; if (body.mode === 'direct') throw new Error('Cover requiere full o melody.'); }
    } else if (turn.tool === 'production_generate') {
      endpoint = '/v1/jobs/production'; body.song = ref(args.song, 'audio');
      body.scenes = args.scenes || run.storyboards[args.storyboard];
      if (!body.scenes) throw new Error('Storyboard desconocido o ausente.');
      const analysis = await this.runtime('GET', `/v1/media/analyze?uri=${encodeURIComponent(body.song.uri)}&sha256=${body.song.sha256}`);
      this.checkScenes(body.scenes, analysis.duration);
      body.scenes = body.scenes.map(s => ({ ...s, ...(s.image ? { image: ref(s.image, 'image') } : {}), ...(s.video ? { video: ref(s.video, 'video') } : {}) }));
      body.video_profile ||= 'base';
      if (body.scenes.some(s => !s.video)) body.video_steps = videoProfile(body.video_profile, body.video_steps);
      delete body.storyboard; body.keyframe_precision = variantPrecision(args.keyframe_variant, args.keyframe_precision);
      if (body.keyframe_variant === 'turbo') body.keyframe_options = turboFixed(body.keyframe_options); body.keyframe_quality ||= 'quality'; body.keyframe_resolution ||= '1mp';
    } else if (turn.tool === 'video_face_refine') {
      if (!caps.face_refine?.ready) throw new Error('Refinado de caras no disponible; no se sustituye automáticamente.');
      endpoint = '/v1/jobs/face_refine'; body = { ...body, video: ref(args.video, 'video'), identity: args.identity ? ref(args.identity, 'image') : null };
    } else if (turn.tool === 'audio_stems') {
      if (!caps.stems?.ready) throw new Error('Separar pistas no disponible.');
      endpoint = '/v1/jobs/stems'; body = { ...body, audio: ref(args.audio, 'audio') };
    } else if (turn.tool === 'audio_sound') {
      const kind = args.kind || 'music';
      if (!caps.sound?.kinds?.[kind]?.ready) throw new Error('Stable Audio 3 no disponible; no se sustituye automáticamente.');
      endpoint = '/v1/jobs/sound'; body = { seconds: { one_shot: 2, sfx: 8 }[kind] || 30, ...body, kind };
    } else if (turn.tool === 'audio_speech') {
      const voice = args.voice || 'preset';
      if (!caps.speech?.voices?.[voice]) throw new Error('Qwen3-TTS no disponible; no se sustituye automáticamente.');
      if (voice === 'clone' && !args.consent) throw new Error('Clonar una voz requiere que el usuario confirme el permiso del dueño de la voz.');
      endpoint = '/v1/jobs/speech'; body = { ...body, voice, ...(args.reference ? { reference: ref(args.reference) } : {}) };
    } else if (turn.tool === 'video_remove') {
      if (!caps.remove?.ready) throw new Error('Quitar personas no disponible; no se sustituye automáticamente.');
      endpoint = '/v1/jobs/remove'; body = { ...body, video: ref(args.video, 'video'), clean_frame: args.clean_frame ? ref(args.clean_frame, 'image') : null };
    } else if (turn.tool === 'video_swap') {
      if (!caps.swap?.modes?.[args.mode || 'character']?.ready) throw new Error('Cambio de personaje no disponible; no se sustituye automáticamente.');
      endpoint = '/v1/jobs/swap'; body = { ...body, video: ref(args.video, 'video'), character: ref(args.character, 'image') };
    } else if (turn.tool === 'video_upscale') {
      if (!caps.upscale?.ready) throw new Error('FlashVSR no disponible; no se sustituye automáticamente.');
      endpoint = '/v1/jobs/upscale'; body = { scale: 2, quality: 'fast', ...body, video: ref(args.video, 'video') };
    } else if (turn.tool === 'job_resume') {
      this.owned(run, args.job_id);
      if (!/(reanuda|continu|resume|retry|reintent)/i.test(run.request)) throw new Error('Reanudar requiere una solicitud explícita.');
      endpoint = `/v1/jobs/${args.job_id}/resume`; body = undefined;
    } else throw new Error('Herramienta no ejecutable.');
    if (Object.values(run.jobs).some(j => j.runId === run.id && ['failed', 'interrupted', 'blocked_gpu'].includes(j.status)) && turn.tool !== 'job_resume' && !turn.jobId) throw new Error('Un trabajo falló o se interrumpió: no se genera una sustitución automáticamente. Envía una nueva solicitud explícita.');
    const previousEffects = Object.values(run.jobs).filter(j => j.runId === run.id && j.operation === endpoint.split('/').pop());
    const quantities = { dos: 2, two: 2, tres: 3, three: 3, cuatro: 4, four: 4, cinco: 5, five: 5 };
    const countMatch = run.request.match(/\b([1-9][0-9]?|dos|two|tres|three|cuatro|four|cinco|five)\s+(?:im[aá]genes|images|variantes|variants|variaciones|variations|versiones|versions|v[ií]deos|videos|canciones|songs|piezas|clips)\b/i);
    const quota = countMatch ? Math.min(32, quantities[countMatch[1].toLowerCase()] || Number(countMatch[1])) : 1;
    if (!turn.intent && previousEffects.length >= quota && turn.tool !== 'job_resume') throw new Error('Ya se ejecutó la cantidad solicitada: nuevas iteraciones requieren una solicitud explícita.');
    // Persist intent before sending; replay uses the exact same idempotency key.
    if (!turn.intent) { turn.intent = { endpoint, body, key: `${run.id}-${crypto.createHash('sha256').update(turn.id).digest('hex').slice(0, 32)}` }; this.save(run); }
    let job = turn.jobId && run.jobs[turn.jobId];
    if (!job) {
      try {
        const receipt = await this.runtime('POST', turn.intent.endpoint, turn.intent.body, turn.intent.key);
        turn.jobId = receipt.job_id;
        job = run.jobs[receipt.job_id] = { id: receipt.job_id, status: receipt.status, runId: run.id, operation: endpoint.split('/').pop(), prompt: body?.prompt || body?.style || body?.brief, settings: safeData(body) };
        this.save(run);
      } catch (error) { error.pause = !/Runtime (400|404|409|422):/.test(error.message); throw error; }
    }
    for (;;) {
      if (run.cancelled) { await this.runtime('DELETE', `/v1/jobs/${job.id}`); return { cancelled: true, job_id: job.id }; }
      let update;
      try { update = await this.runtime('GET', `/v1/jobs/${job.id}`); }
      catch (error) { error.pause = true; throw error; }
      Object.assign(job, { status: update.status, gpu: update.gpu, progress: update.progress, queue_position: update.queue_position }); this.save(run);
      if (TERMINAL.has(update.status)) {
        const media = update.result?.media || [];
        job.media = media; job.error = update.error; job.data = safeData(update.result?.data);
        const aliases = media.map(r => ({ alias: this.register(run, r), ...r })); this.save(run);
        const inspections = [];
        if (update.status === 'completed' && this.provider()?.vision) {
          for (const r of aliases.filter(r => /\/(images|videos|productions)\//.test(r.uri))) {
            try {
              const inspection = await this.inspect(r);
              inspections.push({ alias: r.alias, kind: inspection.kind, alpha: inspection.alpha, timestamps: inspection.timestamps, probe: inspection.probe });
              if (inspection.preview) this.previewCache.set(`${run.id}:${r.sha256}`, { runId: run.id, alias: r.alias, kind: inspection.kind,
                dataUri: `data:${inspection.preview.mime};base64,${inspection.preview.base64}`, inspection: safeData(inspection) });
            } catch { run.notices.push(`No se pudo preparar la revisión visual de ${r.alias}; el resultado se conserva.`); }
          }
        }
        return { job_id: job.id, status: update.status, error: update.error, media: aliases, data: safeData(update.result?.data), inspections, no_automatic_retry: update.status !== 'completed' };
      }
      await sleep(this.pollMs);
    }
  }
  checkScenes(scenes, duration) {
    if (!Array.isArray(scenes) || !scenes.length || scenes.length > 100) throw new Error('Storyboard inválido.');
    let end = 0;
    for (const s of scenes) {
      if (!Number.isFinite(s.start) || !Number.isFinite(s.end) || Math.abs(s.start - end) > .1 || s.end <= s.start || s.end - s.start > 15 || !String(s.video_prompt || '').trim() || !String(s.image_prompt || '').trim()) throw new Error('Escenas no contiguas o fuera de límites.');
      end = s.end;
    }
    if (Math.abs(end - duration) > .1) throw new Error('Storyboard debe cubrir la canción completa.');
  }
  healthSummary(health) {
    return { status: health.status, runtime: health.runtime, queue: health.queue,
      workers: (health.workers || []).map(w => ({ gpu: w.gpu, online: w.health?.ok, busy: w.busy,
        pending: w.pending, active_job: w.active_job, operation: w.operation,
        guard_available: w.gpu_guard?.available, reason: w.gpu_guard?.reason })) };
  }
}
module.exports = { AgentEngine, TOOLS, schemas, validate, safeData };
