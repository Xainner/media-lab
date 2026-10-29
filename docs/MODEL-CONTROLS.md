# Model controls

## Model controls and limits
Read live `capabilities` first. Installed weights and account quotas can differ;
`tools/list` is the exact input contract. Send creation arguments under `body`;
`idempotency_key` is a sibling argument, not inside `body`. Unset/null controls use
the original pipeline defaults. Use only supported options, not arbitrary node inputs.
Sample ranges are validation limits, not a guarantee that every setting fits GPU memory.

### Image and edit
`generate_image` takes `model=qwen` (default, Qwen-Image 2.1) or `model=moss` (MOSS-Image
SFT, a 5B DiT strong at poster/infographic layouts and rendering quoted English or Chinese
copy). MOSS runs at the 1MP ratio presets only, with `quality` draft (16 steps) or quality
(25); `options`, `transparent`, turbo, bf16 and 2K are refused, and it does not edit. Check
`capabilities.image_models.moss.ready`.
`model=flux3` is FLUX 3 Image Klein: fast photorealism. Its official prompt upsampler (a
fine-tuned Qwen3.5 9B) always expands the request into a full caption first, so a short prompt
in any language works; the caption it wrote is saved as the image's compiled prompt.
`quality=draft` is the distilled model (16 steps), `quality=quality` the base model (50 steps,
CFG 3.5). 1MP ratio presets only; `options`, `transparent`, turbo, bf16, 2K, `control` and
`loras` are refused. `edit_image` with `model=flux3` edits or composes 1–4 references (16
steps); the result is about 1 MP in the first reference's shape. Name references as "the first
image", "the second image" (or `<image1>`…). Not with `camera`, `remove_background`,
`resolution`, options or LoRAs. Check `capabilities.image_models.flux3`.
Structure control (Qwen, 1MP): `generate_image` with `control={reference, mode, strength}`
follows an owned image through the Qwen 2.1 Fun ControlNet Union. `mode`: `canny` (edges),
`depth` (Depth Anything 3), `pose` (SDPose body, hands and face) or `map` (the reference
already is a pose skeleton, depth, lineart, scribble, HED or MLSD map, used as given).
`strength` 0.1–1.5; unset uses the per-mode default (canny 0.45, depth 0.5, pose and map
0.8); lower it when the prompt fights the map. The reference is
center-cropped to `aspect_ratio`, so pick the closest ratio. The prompt still describes the
whole image (subject, style, light); the map only fixes the layout. Check
`capabilities.image_control.modes`.
Camera angles: `edit_image` with `camera={azimuth, elevation, distance}` and exactly one
reference re-shoots the same subject and scene from a new viewpoint (QMA LoRA, 30 steps,
CFG 3, base only; no `options` or `transparent`). Azimuths: front view, front-right quarter
view, right side view, back-right quarter view, back view, back-left quarter view, left side
view, front-left quarter view, all relative to the source camera. Elevations: low-angle,
eye-level, elevated, high-angle shot. Distances: close-up, medium shot, wide shot. `prompt`
is optional extra edits; camera-only is cleanest. Quarter views, elevation and distance
changes are the most reliable; unseen sides (a back) are invented. Check
`capabilities.image_camera.ready`.
Image ratios: 1:1, 4:3, 3:4, 3:2, 2:3, 16:9, 9:16, 4:5, 5:4.
`quality=draft` uses 25 steps; `quality=quality` uses 40. `options.steps` overrides
the preset. Image API defaults: quality=quality, model_precision=int8, resolution_tier=1mp.
`model_precision=bf16` requires live availability. `resolution_tier=2k` is for
INT8 image creation only when `two_k_enabled`; BF16 at 2K is unavailable.
Image custom `options.width` and `options.height` must be supplied together, each
32–16384 and a multiple of 32; total area is capped at 1.2 MP, or 4.5 MP in
INT8 with 2K enabled. Consult `resolution_presets` for actual ratio dimensions.
Edit `resolution=0` preserves the first reference's size only within the pixel gate;
otherwise choose a multiple of 32 up to 1024. With `two_k_enabled`, Qwen INT8 edits
accept up to 2048 with at most `two_k_edit.max_references` (4) references, and no camera or
background removal; 2048 gives about 4 MP (a 16:9 canvas comes out near 2720×1536) and takes
roughly 4 min with one reference and 9 min with four at 25 steps. This is the encoder resize
control, not custom output width/height. Edit has no `resolution_tier` or custom canvas options.
`transparent`, precision, seed, quality and `session_id` are top-level body fields.
`model_variant`: `base` (default; quality presets above) or `turbo` (Qwen-Image-2.1-Turbo,
fixed 8-step schedule, CFG 1; `quality` is ignored and `options.steps/scheduler/denoise`
are rejected). Turbo accepts INT8 and, when live, BF16; check
`capabilities.model_variants`. It applies to create and edit; Director uses `keyframe_variant`.

### Background removal
`edit_image(body={references: [one image], remove_background: true})` cuts the subject out onto
a transparent PNG with Qwen-Image 2.1's own instruction (base variant, 40 steps, about 75 s at
1 MP); `prompt` is not used. Fine hair and edges survive. The whole image is redrawn, so tiny
details can shift slightly. Do not use `transparent: true` with a "remove the background"
prompt: that wording erases the subject too. Check `capabilities.image_remove_background.ready`.

### Video upscaling
`upscale_video(body={video, scale, quality, seed})` runs FlashVSR v1.1 on an owned video
(`videos`, `productions` or uploaded `sources`). `scale`: 2 (default) or 4. `quality`:
`fast` (default, FlashVSR tiny) or `quality` (FlashVSR full, slower). Inputs: up to
`capabilities.upscale.max_seconds` seconds and at most
`capabilities.upscale.max_input_pixels[scale]` pixels per frame (x4 is for small sources
such as 480p and below). Estimated GPU time = duration × output megapixels ×
`seconds_per_output_megapixel_second[quality]`; jobs above `max_work_seconds` are rejected,
so long Director productions usually need x2 with quality=fast. The result is a new MP4 (H.264) in `videos` with the original audio
stream kept; the source is never modified. Long jobs process the clip in overlapping chunks.
Check `capabilities.upscale.ready` first; there is no automatic fallback.

### Character swap
`swap_character(body={mode, video, character, target, details, prompt, seed})` replaces one person in an
owned clip (`videos`, `productions` or uploaded `sources`, 2–15 s; best at 5 s or less, one
continuous shot) with the character in an owned image, using MiniMax H3 Ref2VA with the
H3 Character Swap v1.5 LoRA and an 8-step Turbo LoRA. Motion, scene, camera and timing come
from the clip; the original soundtrack is copied verbatim and the result is cut to the
source length. `target` is an English description of who to replace (default: the main
person); `prompt` optionally overrides the whole instruction (cite `<Video 1>` and
`<Picture 1>`). Identity can drift on long clips, cuts and close-ups. Only swap real people
who consented. Check `capabilities.swap.modes.<mode>.ready` first; there is no automatic fallback.
`mode=character` (default) swaps the whole person: face, hair, outfit and art style.
`mode=head` (experimental Head Swap v1.0) replaces only the head and keeps the body and
clothes; `character` is then one clear front view of the new face, the clip is an aligned
guide from frame 0, and `details` is an optional English attribute list of the face (gender,
face shape, skin, eyes, hair, distinctive features) written automatically when empty;
`prompt` is ignored.
`mode=scail` uses SCAIL-2 (Wan 2.1 14B, MIT) instead of H3: SAM 3.1 tracks `target` in the clip
and the person in the image, and the character is redrawn on that body in 81-frame chunks
(6 steps each), so arms, hands and turns follow the source tightly and the light is matched
to the scene; about 11 min for 5 s at 896×512. Its `prompt` describes the finished clip and
must describe the NEW character (look, outfit), never the person being replaced, or SCAIL-2
draws that person again; leave it empty and Qwen3-VL writes it from the image.

### Person removal
`remove_person(body={video, target, clean_frame, seed})` erases one person from an owned
1–10 s clip (best 5 s or less, one continuous shot, little camera motion) and rebuilds what
was behind them. SAM 3.1 tracks the person named by `target` (short English description such
as "man in yellow hoodie"; empty = the most prominent person) and paints them green; MiniMax H3
Ref2VA with the Person Remover V1 LoRA then regenerates the clip in one pass from that green
video and a clean first frame. `clean_frame` (optional owned image of the first frame without
the person, same framing) is otherwise made automatically with Qwen-Image edit. The original
soundtrack is kept, so the removed person's voice stays. H3 regenerates the whole frame, so
small background details can shift; missed shadows or reflections can remain. One person per
job; run it again on the result to remove another. Experimental: check
`capabilities.remove.ready`.

### Face refine
`refine_faces(body={video, identity, strength, seed})` redraws the main face of an owned
1–15 s clip: MediaPipe tracks the face, a smoothed square window around it is re-diffused
with MiniMax H3 from a partial noise level and pasted back with a feathered oval, so the
rest of the frame and the soundtrack stay untouched. `identity` (optional owned image)
holds who the face is; a `swap_character` result reuses its character image automatically.
`strength`: `light` sharpens, `medium` (default) fixes soft or smeared features, `strong`
also repairs identity drift but may alter small expression details. One face per clip; faces
under ~32 px are refused, so upscale small videos first (`upscale_video`) and refine after.
Check `capabilities.face_refine.ready` first.

### Video
`generate_video` with `model=kandinsky6` uses Kandinsky 6.0 Lite Distill instead of H3: one
5 s clip at 864x480 (`aspect_ratio` 16:9 or 9:16) with synchronized 44 kHz audio, from text
(`t2v`) or a `first_frame` (`i2v`). Put each spoken line in the prompt as `<S>exact
words<E>` (lips follow it) and describe the voice and other sounds in `audio_prompt`. The
official beautifier expands both into English captions; `literal_prompt=true` sends them as
written. No references, last frame, control, LoRAs, options, profile or steps. Check
`capabilities.video.models.kandinsky6.ready`. Everything below is H3.
H3 `profile=base`: 8–40 steps, default 20. `profile=turbo`: the LightX2V Turbo LoRAs on the
official weights (FL2VA LoRA for t2v/i2v, Ref2VA LoRA for r2v), 4–12 steps, default 8, about
twice as fast as base at the same canvas. `profile=omni`: FastH3 Omni, an 8-step distilled
Ref2VA checkpoint (FastVideo + Nuva Lab), `mode=r2v` only, 4–12 steps, default 8; not for the
Director. `profile=flex`: Pika H3 Flex, official six-step post-trained LoRAs on the real
weights (FL2VA for t2v/i2v, Ref2VA for r2v); fixed 6 steps and schedule, so `steps` stays 6 and
`options` cannot set sampler, scheduler, denoise or shifts; no video `control`. About 5–6 min per
5 s clip at 1344×768 on an RTX 3090. `profile=fused_turbo`: 4–12 steps,
default 4, experimental and only usable if ready. Do not silently switch profiles
on failure. More steps are not a quality guarantee. Dense attention does not imply
Maestro SLA or identical quality. Ratio: 16:9, 9:16 or 1:1; `seconds`: 5–15.
24 fps is fixed. Native temporal alignment can make actual clip duration differ
slightly from requested seconds; inspect the output before promising exact timing.
`options.resolution`: preview (default), 480p, 720p, native or custom. Read the
exact dimensions for each ratio in `generation_options.video_resolutions` below.
The aligned 720p landscape is 1280×704, not 1280×720. Custom requires width/height
in multiples of 32, with at most 1.1 MP per frame; dimensions are invalid with other presets.
`r2v` accepts `references` (up to 9 images), `reference_videos` (up to 3 videos,
2–15 seconds each) and `reference_audios` (up to 3 audio references, 2–15 seconds each),
at most 12 files and at least one image or video (official H3 limits). Total reference
video is at most 15 s, and total audio at most 15 s: the soundtrack of every reference video
that has one counts and becomes an `<Audio>` label, so upload a silent copy of a video used only
for motion or identity. Video/audio references require r2v mode. Video references are
normalized to 24 fps with bounded dimensions; silent video does not invent audio.
H3 `options.container`: mp4/mkv/webm; `codec`: h264/av1. WebM requires AV1;
MP4 and MKV accept either. `bit_depth`: 8 or 10 (SDR, not HDR). CRF: 0–51 for
H.264 and 0–63 for AV1; lower CRF means less compression and larger files.
CRF unset uses encoder defaults. There is no independent audio codec/bitrate control for H3.
`ref_image_size=match` is default; `max` may improve identity conditioning at higher cost with
`profile=base`. Keep `match` for `turbo` and `omni`: their distillation was trained that way.
Seeds, profile, steps, seconds and ratio are top-level; sampling/shifts/encoding are `options`.

### Video control
`generate_video(body={prompt, mode: "r2v", control: {video, mode, strength, keep_audio}, references?})`
makes a new clip follow an owned 2–15 s video with MiniMax H3 Fun ControlNet-Union 2.0.
`control.mode=pose` copies the movement of up to 2 people (SDPose skeletons, RT-DETR person boxes) and
redraws everything else: "make her dance like this video". `canny` keeps the outlines of the whole
shot; `depth` keeps its 3D layout and camera move (Depth Anything 3). The clip sets the length and the
aspect ratio (nearest of 16:9, 9:16, 1:1); `seconds` and `aspect_ratio` are ignored, `options.resolution`
still applies. `references` are optional and give identity (<Picture 1>…); write the prompt in the Ref2VA
format describing who, where and the look, not the motion. `strength` 1.0 (default) follows the
control fully; lower it when the prompt fights the source. `keep_audio` (default true) lays the
source soundtrack on the result; false keeps H3's own audio. Profiles: `base` (about 8 min for 5 s at
480p) or `turbo` (about 3 min, nearly the same quality). Check `capabilities.video.control.modes`.

### Music
`model` picks the engine. `yue2` (default) is described below. `ace_step` is ACE-Step 1.5 XL
Turbo: `style` (at most 512 characters) and `lyrics` (at most 4096), `max_duration` is the
exact length (10–600 s), and optional `bpm`, `key` (e.g. `E minor`), `time_signature` (`2`,
`3`, `4` default, `6`) and `language` (two-letter code) steer it. Prefer the parameters: a
`95 BPM` / `E minor` tag in `style` is used when they are unset (else 110 BPM, C major) and
removed from the caption; the language is otherwise guessed (Spanish or English) from the lyrics. Its 4B planner writes the audio codes and it renders in
8 steps, so it is the fast choice; `mode`, `abc`, `source_audio` (covers), `steps` and the
YuE2 `options` except `format`/`audio_quality` do not apply. Check
`capabilities.music.models.ace_step.ready`.

YuE2: `mode=direct` generates from style/lyrics without a separate ABC-planning pass.
`mode=full` generates a full ABC score first when no ABC/audio is provided;
`mode=melody` plans melody ABC. A supplied nonempty `abc` is used unchanged.
`source_audio` with full or melody uses SheetSage2 to extract ABC and takes
precedence over supplied ABC. Cover is this combination, not `mode=cover`.
Check `cover_ready`. `source_audio` with direct is invalid.
`options.score` applies only to automatically generated ABC; it does not change a
supplied score or SheetSage2 output. `options.composition` controls music-token
generation; top-level `steps` (4–80, default 32) and `options.cfg/sampler/scheduler/denoise`
control diffusion. `max_duration` (10–900, default 120) is a cap, not exact duration.
`options.format=flac` is lossless and requires audio_quality unset.
MP3 accepts V0/128k/320k, default V0; Opus accepts 64k/96k/128k/192k/320k,
default 128k. `audio_quality` sets file encoding, not model generation quality.
No exposed independent sample rate, channel count, negative prompt or BPM knob.

### Stems
`separate_stems(body={audio, stems, format})` splits an owned song or audio of 1–900 s with
Hybrid Demucs. `stems=two` (default) returns vocals and instrumental (karaoke, covers, a new
voice over the same beat); `stems=four` returns vocals, drums, bass and other. Each stem is a
new song in the library (`format` flac or mp3) whose metadata names its `stem`; together they
add back up to the source. Takes seconds even for a full song. It separates music, not
dialogue from ambience. Check `capabilities.stems.ready`.

### Sound
`generate_sound(body={prompt, kind, seconds, enhance, format})` uses Stable Audio 3 for
everything without singing. `kind=music` (Medium, 5–380 s): an instrumental track;
`instrument` (Medium, 2–380 s): a solo part or loop; `sfx` (Small SFX, 1–120 s): effects
and ambiences; `one_shot` (Small SFX, 0.5–10 s): a single hit or sample. `seconds` is the
exact length. With `enhance=true` (default) Qwen3.5 2B rewrites the idea with the official
category prompt, so any language works; the rewrite is returned in the job data. No vocals
or lyrics: songs go to `generate_music`. Check `capabilities.sound.kinds`.

### Speech
`generate_speech(body={text, voice, ...})` speaks with Qwen3-TTS 1.7B (10 languages,
`language=auto` by default). `voice=preset`: one of nine studio voices (`speaker`: serena,
vivian, sohee, ono_anna are female; ryan, aiden, uncle_fu, eric, dylan male), with an optional
`instruct` for delivery ("whispering, nervous"). `voice=design`: a new voice described in
`instruct` (gender, age, timbre, accent, emotion). `voice=clone`: the voice of an owned 3–30 s
`reference` clip (audio or video), better with `reference_text` (its exact words). Clone ONLY
the user's own voice or that of someone who agreed, never to deceive or impersonate, and only
with `consent=true` after the user confirms that permission. Check `capabilities.speech`.

### Characters and LoRAs
`list_characters` returns the owner's private characters: `handle` (written `@handle` by the
user), `name`, `description` (look, in English), 1–4 `references` (owned images, the first is the
main one) and an optional `lora`. When the user names `@handle`, put the character's
references into the job and refer to them by position: `<image1>`… in `edit_image`,
`<Picture 1>`… in `generate_video` mode r2v, or the `character` image of `swap_character`;
add the description to the prompt when it helps. Characters are created in the web page.
`list_loras` returns the owner's LoRA library: `id`, `base` (`qwen` = Qwen-Image 2.1 for
`generate_image`/`edit_image`, `h3` = MiniMax H3 for `generate_video`), `trigger` words,
saved `strength` and `status` (only `ready` ones work). Pass up to 4 as
`loras: [{"id": "lora_…", "strength": 0.8}]` (strength 0.05–2, unset = saved value) and put the
trigger words in the prompt. A LoRA of the wrong base is rejected; MOSS-Image and background
removal take none. LoRAs are added in the web page from a Hugging Face or Civitai link.

### Director
`create_production` requires title, owned song, brief and 1–100 scenes. Analyze
the actual song first. Scenes start at zero, have contiguous positive start/end times,
each at most 15 seconds, and cover the whole song. Both prompts are required even
when reusing media. Any scene may be shorter than 5 seconds: its clip is generated at 5 then trimmed.
Optional scene `image` is owned PNG; scene `video` is owned MP4/MKV/WebM.
If video is present, reuse it; otherwise use the image or generate a keyframe, then i2v.
Reused short clips loop and longer ones trim to cover their scene; original files are preserved.
`keyframe_precision` int8/bf16, `keyframe_quality` draft/quality and
`keyframe_resolution` legacy/1mp/2k control new keyframes; `keyframe_variant` base/turbo
selects Qwen-Image-2.1 or its 8-step Turbo for them. `keyframe_options` has
the image options including paired custom canvas dimensions. `video_profile`,
`video_steps` and `video_options` control new clips; no fake per-scene settings.
Optional production seed is 0–9007199254740991; new scenes use seed+scene index
(wrapped in the safe range) for both keyframes and video. Other API seeds accept
0–9223372036854775807, but JavaScript clients should stay within the safe integer range.
Final production packaging is documented under Formats; container/codec/CRF options
for scene clips do not alter the final MP4 preview or original-audio MKV master.


### Exact advanced-option reference


#### `image` options

| Field | Default when unset | Allowed values / limits | Meaning |
| --- | --- | --- | --- |
| `sampler` | "euler" | `euler`, `euler_cfg_pp`, `euler_ancestral`, `euler_ancestral_cfg_pp`, `heun`, `heunpp2`, `exp_heun_2_x0`, `exp_heun_2_x0_sde`, `dpm_2`, `dpm_2_ancestral`, `lms`, `dpm_fast`, `dpm_adaptive`, `dpmpp_2s_ancestral`, `dpmpp_2s_ancestral_cfg_pp`, `dpmpp_sde`, `dpmpp_sde_gpu`, `dpmpp_2m`, `dpmpp_2m_cfg_pp`, `dpmpp_2m_sde`, `dpmpp_2m_sde_gpu`, `dpmpp_2m_sde_heun`, `dpmpp_2m_sde_heun_gpu`, `dpmpp_3m_sde`, `dpmpp_3m_sde_gpu`, `ddpm`, `lcm`, `ipndm`, `ipndm_v`, `deis`, `cfgpp_ud10_ab`, `res_multistep`, `res_multistep_cfg_pp`, `res_multistep_ancestral`, `res_multistep_ancestral_cfg_pp`, `gradient_estimation`, `gradient_estimation_cfg_pp`, `er_sde`, `seeds_2`, `seeds_3`, `sa_solver`, `sa_solver_pece`, `ddim`, `uni_pc`, `uni_pc_bh2` | Sampler |
| `scheduler` | "simple" | `simple`, `sgm_uniform`, `karras`, `exponential`, `ddim_uniform`, `beta`, `normal`, `linear_quadratic`, `kl_optimal` | Noise schedule |
| `denoise` | 1 | 0–1 | Denoising strength |
| `cfg` | 1 | 0–100 | CFG guidance |
| `steps` | Preset / automatic | 1–200 | Custom steps. Unset: use the quality preset steps. |
| `negative_prompt` | "" | Text, up to 20000 characters | Negative prompt |
| `width` | Preset / automatic | 32–16384; multiple of 32; paired dimensions and pixel cap | Custom width |
| `height` | Preset / automatic | 32–16384; multiple of 32; paired dimensions and pixel cap | Custom height |

#### `edit` options

| Field | Default when unset | Allowed values / limits | Meaning |
| --- | --- | --- | --- |
| `sampler` | "euler" | `euler`, `euler_cfg_pp`, `euler_ancestral`, `euler_ancestral_cfg_pp`, `heun`, `heunpp2`, `exp_heun_2_x0`, `exp_heun_2_x0_sde`, `dpm_2`, `dpm_2_ancestral`, `lms`, `dpm_fast`, `dpm_adaptive`, `dpmpp_2s_ancestral`, `dpmpp_2s_ancestral_cfg_pp`, `dpmpp_sde`, `dpmpp_sde_gpu`, `dpmpp_2m`, `dpmpp_2m_cfg_pp`, `dpmpp_2m_sde`, `dpmpp_2m_sde_gpu`, `dpmpp_2m_sde_heun`, `dpmpp_2m_sde_heun_gpu`, `dpmpp_3m_sde`, `dpmpp_3m_sde_gpu`, `ddpm`, `lcm`, `ipndm`, `ipndm_v`, `deis`, `cfgpp_ud10_ab`, `res_multistep`, `res_multistep_cfg_pp`, `res_multistep_ancestral`, `res_multistep_ancestral_cfg_pp`, `gradient_estimation`, `gradient_estimation_cfg_pp`, `er_sde`, `seeds_2`, `seeds_3`, `sa_solver`, `sa_solver_pece`, `ddim`, `uni_pc`, `uni_pc_bh2` | Sampler |
| `scheduler` | "simple" | `simple`, `sgm_uniform`, `karras`, `exponential`, `ddim_uniform`, `beta`, `normal`, `linear_quadratic`, `kl_optimal` | Noise schedule |
| `denoise` | 1 | 0–1 | Denoising strength |
| `cfg` | 1 | 0–100 | CFG guidance |
| `steps` | Preset / automatic | 1–200 | Custom steps. Unset: use the quality preset steps. |
| `negative_prompt` | "" | Text, up to 20000 characters | Negative prompt |

#### `video` options

| Field | Default when unset | Allowed values / limits | Meaning |
| --- | --- | --- | --- |
| `sampler` | "res_multistep" | `euler`, `euler_cfg_pp`, `euler_ancestral`, `euler_ancestral_cfg_pp`, `heun`, `heunpp2`, `exp_heun_2_x0`, `exp_heun_2_x0_sde`, `dpm_2`, `dpm_2_ancestral`, `lms`, `dpm_fast`, `dpm_adaptive`, `dpmpp_2s_ancestral`, `dpmpp_2s_ancestral_cfg_pp`, `dpmpp_sde`, `dpmpp_sde_gpu`, `dpmpp_2m`, `dpmpp_2m_cfg_pp`, `dpmpp_2m_sde`, `dpmpp_2m_sde_gpu`, `dpmpp_2m_sde_heun`, `dpmpp_2m_sde_heun_gpu`, `dpmpp_3m_sde`, `dpmpp_3m_sde_gpu`, `ddpm`, `lcm`, `ipndm`, `ipndm_v`, `deis`, `cfgpp_ud10_ab`, `res_multistep`, `res_multistep_cfg_pp`, `res_multistep_ancestral`, `res_multistep_ancestral_cfg_pp`, `gradient_estimation`, `gradient_estimation_cfg_pp`, `er_sde`, `seeds_2`, `seeds_3`, `sa_solver`, `sa_solver_pece`, `ddim`, `uni_pc`, `uni_pc_bh2` | Sampler |
| `scheduler` | simple; beta for Base r2v | `simple`, `sgm_uniform`, `karras`, `exponential`, `ddim_uniform`, `beta`, `normal`, `linear_quadratic`, `kl_optimal` | Noise schedule |
| `denoise` | 1 | 0–1 | Denoising strength |
| `shift_video` | Base: checkpoint defaults; turbo: 6; fused_turbo and omni: 12 | 0.01–100 | Video sigma shift |
| `shift_audio` | Base: checkpoint defaults; turbo: 3; fused_turbo and omni: 3 | 0.01–100 | Audio sigma shift |
| `ref_image_size` | "match" | `match`, `max` | Reference image sizing. max: stronger identity conditioning, more memory and processing time. |
| `container` | "mp4" | `mp4`, `mkv`, `webm` | Container |
| `codec` | "h264" | `h264`, `av1` | Codec |
| `bit_depth` | 8 | `8`, `10` | Color bit depth · SDR output. 8-bit or 10-bit encoding. The model generates SDR; this does not turn the result into HDR. |
| `crf` | Preset / automatic | 0–63 | Compression quality · CRF. Lower CRF retains more detail and increases file size. H.264: 0–51; AV1: 0–63. Unset: automatic. |

#### `song` options

| Field | Default when unset | Allowed values / limits | Meaning |
| --- | --- | --- | --- |
| `sampler` | "dpm_2" | `euler`, `euler_cfg_pp`, `euler_ancestral`, `euler_ancestral_cfg_pp`, `heun`, `heunpp2`, `exp_heun_2_x0`, `exp_heun_2_x0_sde`, `dpm_2`, `dpm_2_ancestral`, `lms`, `dpm_fast`, `dpm_adaptive`, `dpmpp_2s_ancestral`, `dpmpp_2s_ancestral_cfg_pp`, `dpmpp_sde`, `dpmpp_sde_gpu`, `dpmpp_2m`, `dpmpp_2m_cfg_pp`, `dpmpp_2m_sde`, `dpmpp_2m_sde_gpu`, `dpmpp_2m_sde_heun`, `dpmpp_2m_sde_heun_gpu`, `dpmpp_3m_sde`, `dpmpp_3m_sde_gpu`, `ddpm`, `lcm`, `ipndm`, `ipndm_v`, `deis`, `cfgpp_ud10_ab`, `res_multistep`, `res_multistep_cfg_pp`, `res_multistep_ancestral`, `res_multistep_ancestral_cfg_pp`, `gradient_estimation`, `gradient_estimation_cfg_pp`, `er_sde`, `seeds_2`, `seeds_3`, `sa_solver`, `sa_solver_pece`, `ddim`, `uni_pc`, `uni_pc_bh2` | Sampler |
| `scheduler` | "sgm_uniform" | `simple`, `sgm_uniform`, `karras`, `exponential`, `ddim_uniform`, `beta`, `normal`, `linear_quadratic`, `kl_optimal` | Noise schedule |
| `denoise` | 1 | 0–1 | Denoising strength |
| `cfg` | 1 | 0–100 | CFG guidance |
| `composition.temperature` | 1 | 0–5 | Temperature |
| `composition.top_p` | 0.95 | 0.01–1 | Top P |
| `composition.top_k` | 100 | 1–32768 | Top K |
| `composition.repetition_penalty` | 1.2 | 0.01–10 | Repetition penalty |
| `score.temperature` | 0.7 | 0–5 | Temperature |
| `score.top_p` | 0.9 | 0.01–1 | Top P |
| `score.top_k` | 30 | 1–32768 | Top K |
| `score.repetition_penalty` | 1.005 | 0.01–10 | Repetition penalty |
| `composition.cfg_scale` | 1 | 0–100 | Composition guidance |
| `score.max_abc_tokens` | 8192 | 1–20000 | Maximum ABC tokens |
| `score.penalty_window` | 100 | 1–20000 | Repetition window |
| `format` | "flac" | `flac`, `mp3`, `opus` | Audio format |
| `audio_quality` | Preset / automatic | `V0`, `64k`, `96k`, `128k`, `192k`, `320k` | Compression quality |

#### Video preset dimensions
| Preset | 16:9 | 9:16 | 1:1 |
| --- | --- | --- | --- |
| preview | 640×352 | 352×640 | 480×480 |
| 480p | 864×480 | 480×864 | 640×640 |
| 720p | 1280×704 | 704×1280 | 960×960 |
| native | 1344×768 | 768×1344 | 1024×1024 |
