"""Canonical English prompt-writing guides for every model this studio runs.

One source for the MCP server, the Rinari agent, the prompt improver and the Director
planner; the Node agent receives a generated copy (deploy/scripts/sync-mcp-guides.py).

Sources, checked 2026-10-07:
- Qwen-Image-2.1 official prompt rewriters (Qwen/Qwen-Image-2.1-PE-T2I and -PE-I2I
  system prompts) and model card.
- MiniMax H3 official prompt-writing skill (MiniMax-AI/MiniMax-H3 skills/h3-prompt-writing,
  base-en and ref-en references) and model card.
- MiniMax H3 Prompt Architect v4.0 (owner's guide), with Maestro-only routes removed.
- YuE2-3B model card, example songs and native prompting protocol (yue2-native-v1).
- The native ComfyUI H3/YuE2 nodes and tokenizers pinned in deploy/Dockerfile.comfyui.
"""
from .creative_workflows import h3_length


def _h3_duration_table() -> str:
    rows = ['| Requested `seconds` | Frames (24 fps) | Effective duration | Alignment mark `S.SS` |',
            '| --- | --- | --- | --- |']
    for seconds in range(5, 16):
        frames = h3_length(seconds)
        rows.append(f'| {seconds} | {frames} | {frames / 24:.3f} s | {frames / 24:.2f} |')
    return '\n'.join(rows)


LANGUAGE = """## Language policy (all models)
- Write every model-facing descriptive prompt in English: image/edit prompt, H3 prompt,
  YuE2 style, Director brief and scene prompts.
- Keep literal content in its own language and script, character for character: text that
  must appear in an image or video, spoken dialogue, sung lyrics, names, ABC notation.
- Reply to the user in their language. Keep their original request separately; never replace
  it with the translated model prompt.
- Faithful first: keep every explicit requirement (cast, counts, colours, positions, text,
  actions, ending, audio behaviour). Invent only what the user left open.
"""

QWEN_IMAGE = """## Qwen-Image-2.1 · text to image (`generate_image`)

Qwen-Image-2.1 renders best from one long, concrete English paragraph that describes the
finished picture as an observer would see it. This mirrors Qwen's official T2I prompt rewriter.

### Fixed versus open
List what the user fixed: every string of visible text (copy it exactly, in its own script),
named objects, counts, colours, positions and the aspect ratio. Everything else is open and
yours to decide: a three-word brief still becomes a full description. Instructions about the
job ("sharp text", "4K", "no noise") are not picture content: honour them silently, never echo them.

### Structure
1. **Opening sentence (~20 words):** medium, style, subject, background/palette, usually the
   orientation. `The image is a vertical watercolour illustration of …`. The medium noun
   (photograph, poster, illustration, portrait, infographic, logo …) is never omitted.
2. **Walk the frame.** For layouts and busy scenes walk regions: background and surface first,
   then the top band, then left → centre → right, then the bottom band. For a single subject
   walk the subject: background falloff, pose and placement, head and face, body and each
   garment, held objects, edges. Use 8–14 positional phrases ("In the upper-left corner, …",
   "Across the lower third, …") reaching corners, edges and centre.
3. **Text.** Skip if nothing is meant to be read; never invent signage. Otherwise, in reading
   order: where it sits, how it looks (weight, colour, case, relative size) and what it says in
   straight double quotes: `a bold black headline across the top reads "OPEN LATE"`. Describe
   a line break as a second line. Unreadable marks are "blurred" or "too small to read".
   Chart axes, legends and table cells are text too.
4. **Lighting sentence:** source, direction, quality, shadows and highlights.
5. **One closing sentence** on composition, balance, palette, style and mood.

### Style rules
- Present tense, third person, declarative. No "create", "make sure", "you".
- No quality boosters ("masterpiece", "8K", "highly detailed", "award-winning").
- Colours with modifiers (deep navy, pale cream, warm terracotta); hex only if supplied.
- Materials and texture (brushed metal, matte ceramic, coarse linen, visible brush strokes).
- Enumerate, never summarise; small counts as words ("three lanterns").
- People: build, posture, gaze, expression, hair, skin tone, each garment with colour and
  material; age as a life stage or decade, never a number of years.
- Objects by class, not brand, unless the user named the brand.
- Physical coherence: shadows away from the light, consistent scale and reflections.
- Typical length 150–500 words. Longer is fine for dense layouts; never pad with repetition.

### Studio specifics
- Aspect ratio, 1 MP/2K tier, precision and steps are request fields. Never write a ratio,
  resolution or pixel count into the prompt.
- Transparency: set `transparent=true`. The runtime adds the official RGBA wording
  ("This is an RGBA format image with transparency … transparent background"). Describe an
  isolated subject with clean edges; do not describe a checkerboard or a backdrop.
- `options.negative_prompt` exists but is rarely needed; prefer stating the wanted result.

### Turbo (`model_variant="turbo"`)
Qwen-Image-2.1-Turbo is an accelerated checkpoint of the same 7B model for creation and
editing. It always runs its own fixed 8-step schedule (CFG 1), so `quality`,
`options.steps`, `options.scheduler` and `options.denoise` do not apply (the three options
are rejected). Write exactly the same prompts as for the base model. Use it for fast
iterations, drafts and most everyday images; keep `model_variant="base"` (40 steps) when the
user asks for maximum fidelity or when a Turbo result misses fine detail. INT8 is the
default; BF16 needs live availability in `capabilities.model_variants.turbo.precisions`.

### Example
```text
The image is a vertical anime-style portrait illustration of a young adult singer with violet hair, set against a deep plum gradient background. The singer stands slightly left of centre, framed from the waist up, turning her shoulders toward the right edge while her violet eyes look straight at the viewer. Her shoulder-length hair falls in soft layers, with a few loose strands lifting near her left cheek. Over her ears she wears glossy white headphones shaped like feline ears, their inner cups glowing a soft lilac. She wears a cropped charcoal bomber jacket with satin sheen over a pale cream turtleneck, and a thin silver chain rests at her collarbone. In the lower-right corner, a small handwritten caption in warm white script reads "Good night". Across the upper third, faint star-like specks of light drift over the darker gradient. The lighting is a soft key light from the upper left that leaves gentle cel-shaded shadows under her chin and along the right side of her jacket, with a thin rim of lilac backlight outlining her hair. The overall composition is calm and balanced, with a cool plum-and-violet palette, clean linework and a quiet nocturnal mood.
```
"""

QWEN_EDIT = """## Qwen-Image-2.1 · image editing (`edit_image`)

Write a precise, decisive editing instruction anchored on what the input images actually
show. This mirrors Qwen's official I2I prompt rewriter.

### Governing principle
Edit exactly the attributes the user named, push each change to an unmistakable degree, and
hold everything else at input fidelity. Avoid both failure modes: leakage (touching what was
not named) and under-editing (a result that looks unedited).

### How to write it
- **Lead with the operation**, written for someone holding only the input image(s):
  "Replace the background with …", "Change the jacket to …", "Place the person from
  <image1> into the café of <image2> …".
- **Say what stays without repainting it.** Prefer one blanket preservation clause
  ("keep the person's face, hairstyle, pose, clothing and the rest of the scene unchanged").
  Describing kept content in detail makes the model regenerate it and drift.
  Describe appearance concretely only for what you change.
- **Identity is the hardest invariant.** Faces, recognisable accessories, product design and
  markings, counts, and the rendering medium (photo, anime, 3D, painting) survive unless
  targeted. When identity comes from a reference image, point at that image instead of
  describing the face in words.
- **Only what was asked.** Do not clean up unmentioned defects. When removing or moving
  something, describe the newly revealed area so the result stays physically coherent.
  Name canvas extension explicitly as outpainting.
- **Resolve ambiguity, then commit.** Turn vague words ("nicer", "more pro") into observable
  properties. No hedging, no unresolved alternatives.
- **Affirmative phrasing:** "keep the background identical" rather than "do not change".
- **One continuous paragraph**, no line breaks, written in full.

### Image references
- **One input image:** refer to it naturally ("the image", "the woman in the image").
  Do not use `<image1>` tags.
- **Two or more:** always use `<image1>`, `<image2>` … in the order of the `references` list,
  never "the first image" or "picture A". State each image's role: which one is the canvas
  whose composition survives and what is taken from each other image. Describe every image
  individually. For a group scene with no canvas, every image is an identity source.
- In this studio the first reference is the canvas whose size `resolution=0` preserves.
  Order references accordingly.
- Up to 10 reference images, Qwen-Image-2.1's documented maximum (the studio enforces it).

### Text in the edited image
Every legible string is literal: quote it exactly in straight double quotes. Its language:
(1) the exact text or target language the user gave; otherwise (2) the dominant language of
text already in the image; otherwise (3) the user's language. Quoted text is monolingual
unless a bilingual pair was requested. Match the existing typography unless asked otherwise.

### Studio specifics
- Never put an aspect ratio, resolution or "2K/4K" in the prompt. Canvas size is the
  `resolution` field (0 = keep the first reference's size within the pixel cap).
- `transparent=true` requests RGBA output (subject extraction, transparent layers).
- `model_variant="turbo"` edits with the same prompt in 8 fixed steps; see the Turbo notes
  in the image guide.

### Examples
Single image:
```text
Replace the overcast sky with a warm sunset of deep orange near the horizon fading to violet overhead, and let the warmer light fall on the rooftops and wet street so their highlights turn amber. Keep the buildings, street, parked cars and the person with the umbrella exactly as they are, in the same positions and framing.
```
Two images:
```text
Place the woman from <image1> into the night market scene of <image2>, standing at the noodle stall in the centre foreground and facing the camera with a relaxed smile. <image2> is the canvas: keep its stalls, lanterns, crowd and framing unchanged. Take only the woman's identity, hairstyle and red coat from <image1>, and light her with the same warm lantern glow and soft haze as the surrounding scene so she casts a matching shadow on the pavement.
```
"""

H3 = """## MiniMax H3 · audio-video generation (`generate_video`)

H3 generates one 24 fps clip with synchronized 32 kHz stereo sound from a structured English
prompt. The native ComfyUI encoder feeds the prompt as raw text (no chat template); the field
names, labels and tags below are what H3 was trained on, so reproduce them exactly.

### 1. Route the request (this studio)
| Request | Studio call | Official mode | Prompt format |
| --- | --- | --- | --- |
| Text only | `mode=t2v` | T2VA | Base (3 fields) |
| Animate an opening image | `mode=i2v`, `first_frame` | I2VA | Base + first-frame line |
| Connect two images | `mode=i2v`, `first_frame` + `last_frame` | FL2VA | Base + alignment line |
| Land on a final image only | `mode=t2v`, `last_frame` only | L2VA | Base + last-frame line |
| Identity, style, motion, voice, music, video edit or continuation references | `mode=r2v` with `references` / `reference_videos` / `reference_audios` | Ref2VA (Omni) | Ref2VA (6 fields) |

- An uploaded portrait is not automatically a first frame: use `first_frame` only when the
  picture must literally open the clip; otherwise it is an r2v identity reference.
- Give r2v at least one image or video reference: identity needs a visual source, and
  audio-only reference generation is not an officially documented setup.
- Choose the profile (section 1b); the prompt format is identical for both. Never switch it silently.
- Not available in this studio (Maestro-only features of older guides): 30-second extended
  pass, multi-window "Exact H3 prompts", H3 Voice Audio, Animate/Viggle, Outpaint, masked
  control-video editing, PDD/TaoMate/VDN/Singularity presets, audio refinement and
  Regenerate-2K. Do not promise them; for longer pieces use the Director (scenes of 5–15 s).

### 1b. Profiles: H3 Base, H3 Turbo or H3 Fused Turbo
`profile=turbo` loads the official checkpoints with the LightX2V MiniMax-H3 Turbo LoRA (FL2VA
8-step v1.0 768p for t2v/i2v, Ref2VA 8-step v1.1 768p for r2v) at strength 1.0, euler / simple,
shifts video 6 / audio 3, the int8 video VAE; 4–12 steps, default 8. It keeps the true Ref2VA
weights, so references hold identity like Base. Observed here (RTX 3090, 5 s at 480p): Turbo
about 140–150 s for t2v, i2v and r2v versus about 285 s for Base at 20 steps; Turbo at 720p
took about 375 s. It is the default fast choice; Fused stays the experimental 4-step merge.
`profile=omni` is FastH3 Omni (FastVideo + Nuva Lab), an 8-step distilled Ref2VA checkpoint:
r2v only (same six-section Ref2VA prompt), euler / simple, shifts 12 / 3, int8 video VAE,
4–12 steps, default 8. Use it for fast reference-driven clips; it is not a Director profile.

| | `profile=base` (default) | `profile=fused_turbo` (experimental) |
| --- | --- | --- |
| Weights | Official pruned FL2VA checkpoint for t2v/i2v and the dedicated Ref2VA checkpoint for r2v | One community merge (MATLOWAI): FL2VA with a rank-1024 approximation of the Ref2VA delta, the lightx2v Turbo LoRA and Mystic v2 (motion smoothing, 0.7) baked in |
| Steps | 8–40, default 20 | 4–12, default 4 (where the merge is tuned) |
| Sampling | res_multistep; beta schedule for r2v, simple otherwise; checkpoint sigma shifts | res_multistep / simple, shifts video 12 / audio 3, no CFG |
| Best for | Final renders, maximum reference/identity fidelity (true Ref2VA weights), stylised looks | Drafts, fast iteration, many Director scenes, smooth motion |
| Caveats | Slower: 20 default steps versus 4, so roughly several times the sampling time | Dense attention here (no SLA): soundtrack softer/duller; Mystic can nudge flat 2D styles toward smoother shading; r2v uses the approximated delta |
- Fused steps: 4 is the recommended setting. 8 or 12 only sharpen the drawing slightly, take
  longer and do not change the soundtrack or the take; they never turn Fused into Base.
- Base steps: 20 is the studio default; fewer steps (8–16) are drafts, more (30–40) can help
  dense detail but are not a quality guarantee.
- Observed in this studio (RTX 3090, 5 s clip at the conservative canvas): Fused at 4 steps took
  about 52–58 s for t2v, i2v and r2v. Treat timings as observations, not promises.
- Never stack another Turbo/acceleration LoRA on Fused and never "make Base turbo" by lowering
  its steps to 4 (Base rejects fewer than 8). If the user asks for "H3 4 steps", "Turbo" or
  "Fused", use `profile=fused_turbo` when capabilities report it ready (for plain "Turbo" or "fast"
  H3, prefer `profile=turbo`); otherwise say it is
  unavailable instead of substituting.

### 2. Duration
Output length snaps to the model's 17n+5 frame grid; the clip can differ slightly from the
requested seconds. Plan timestamps against the effective duration:

{duration_table}

### 3. Keyframe alignment line (I2VA / FL2VA / L2VA)
The runtime adds the official alignment line automatically when frames are supplied and the
prompt has none, using the effective duration above. If you write it yourself, it must be the
first line, followed by one blank line, verbatim:
- I2VA: `For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.`
- FL2VA: `How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot N) aligns with the S.SS-second mark of the target video.`
- L2VA: `How the reference pictures align with the target video — <Picture 1> (from [Shot N]) aligns with the S.SS-second mark of the target video.`
`N` is the final shot number and `S.SS` the alignment mark from the table.

### 4. Base format (T2VA, I2VA, FL2VA, L2VA)
```text
integrated_multimodal_description: [Shot 1] STYLE, INITIAL COMPOSITION, SUBJECTS, SETTING, ACTION, CAMERA, SPEECH AND DIEGETIC SOUND. [Shot 2] At 00:04.500, the camera cuts to ...

overall_soundscape: AMBIENCE, PHYSICAL SOUNDS, NON-VERBAL HUMAN SOUNDS (1–4 sentences), OR N/A FOR COMPLETE SILENCE.

non_diegetic_music: AUDIENCE-ONLY MUSIC (1–3 sentences: instruments, tempo, rhythm, dynamics) OR N/A.
```
- I2VA: begin from the first frame's style, subjects and composition, then develop forward:
  first-frame anchor → action onset → development → result. No invented opening shot.
- FL2VA: describe the physical path between the frames, not two static descriptions. Prefer one
  continuous shot; reach the last frame's pose, spacing and composition by the end.
- L2VA: infer a plausible earlier state, then converge on the final image in the last shot.
- Leave roughly 0.5–1.5 s of settling before a required last frame when the action allows.

### 5. Ref2VA format (r2v)
Six sections, exactly once, in this order. No extra top-level sections (no `negative_prompt:`,
`camera:` or `reference_manifest:`).
```text
subject_definitions:
<Subject 1> is the adult presenter from <Picture 1>, preserving facial identity, hair and body proportions; the picture supplies appearance rather than its pose or background.
<Audio 1> is the voice-timbre reference for <Subject 1> (S1), guiding vocal identity without copying the sample's words or recording environment.

summary:
[reference generation + audio reference] One short paragraph on the target video and the main reference relationships, without repeating dialogue.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - preserve the defined identity.
<Audio 1>: reference - guide the subject's voice without copying the original signal.

detailed_description:
The target video is in realistic photographic style.
[Shot 1] Composition, setting, initial state, action, camera. <Subject 1> (S1) says in the voice referenced from <Audio 1>, <d>[Spanish] Texto exacto del usuario.</d> Reaction and concrete ending state.

overall_soundscape:
Target-scene ambience and physical sounds without repeating speech.

non_diegetic_music:
N/A
```
- **Reference labels in this studio** (the encoder numbers them automatically, 1-based per type):
  `<Picture i>` = the i-th entry of `references`; `<Video k>` = the k-th entry of
  `reference_videos`; `<Audio j>` counts first the soundtrack of every reference video that
  contains an audio stream (in video order), then each `reference_audios` entry. A silent
  video creates no Audio label. Never cite a label that has no real input.
- `<Subject N>`: reusable visible content (person, animal, product, environment, costume,
  style, motion, pose). Define once; one subject may combine sources ("whose face comes from
  <Picture 1> and whose walking motion comes from <Video 1>"). Cite a Picture/Video inside a
  Subject definition when it only supplies appearance; give it its own line only when it is a
  frame anchor, storyboard reference, source video or whole-video structure.
- **summary task types** (combine with ` + `): `reference generation`, `keyframe completion`,
  `video editing`, `video continuation`, `audio reuse` (signal copied), `audio reference`
  (timbre/style guided, not copied). A video used only for motion or camera guidance is
  reference generation, not editing. Source edits start with `The target video is an edited version of <Video 1>.`
- **retention_analysis values.** Visual: `fully_preserved`, `partially_preserved`,
  `attribute_transfer`, `weak_reference`. Audio: `fully_copy`, `partially_copy`, `reference`,
  `weak_reference`. No speaker IDs here. These state intent; they do not guarantee pixel- or
  sample-exact results.
- **Limits:** up to 9 images, 3 videos (2–15 s each) and 3 audio clips (1–15 s each); keep total
  reference video and audio around 15 s each (official H3 limits). Voice conditioning favours
  about two active voice references per clip; do not promise three independently cloned voices.
- Identity and roles are separate: a portrait used for identity does not supply its pose,
  background, outfit or opening composition unless you say so. If clothes will change, keep
  them out of the immutable identity definition.

### 6. Shots, timing and camera
- `[Shot 1]` has no timestamp. Later shots: `[Shot 2] At 00:03.500, the camera cuts to …`
  with strictly increasing times inside the effective duration. Cut only for new information;
  use camera motion for small changes. Do not place a cut at the very end.
- Planning heuristic: 5–6 s → one strong shot or two simple phases; 7–10 s → 1–3 shots;
  11–15 s → 2–4 shots. Continuous-shot requests stay continuous.
- Start `[Shot 1]` with style and composition: `Live-action, cinematic, a medium-wide shot frames …`
  (or 2D-animated, 3D CG, claymation, watercolor, vintage film; derive it from the keyframe or
  references when present).
- Camera = motion type + optional amplitude + speed, written as natural action:
  Push In/Pull Out (camera moves), Zoom In/Out (focal length), Pan, Truck, Tilt, Pedestal,
  Arc Shot, Tracking Shot, Static Shot, Shake Slightly/Strongly, POV, Roll; `with small/large
  amplitude`, `at slow/fast speed`. Example: `The camera pushes in with small amplitude at slow
  speed toward the letter.` Never stack contradictions (static and orbiting).
- A locked camera holds position, focal length and framing; motion comes from the subject,
  light, particles or environment.

### 7. Speech, singing and voice
- Spoken words and sung lyrics go inside `<d>[Language] exact words</d>` — language tag and the
  user's literal words only, preserved verbatim with their punctuation and accents. Speaker,
  voice description, delivery, accent and action stay outside the tag:
  `The young woman with a quiet, breathy voice (S1) says: <d>[English] I get off at the next station.</d>`
- Speaker IDs `(S1)`, `(S2)` follow the order of first vocalisation in this clip, stay stable
  across shots, and silent characters get none. Simultaneous voices: `(S1,S2)`.
- First mention of a speaker: enough identity for a stable voice (age, gender, on/off screen,
  pitch, timbre, pace, accent). For a requested regional accent, describe it outside `<d>`
  ("natural Costa Rican Spanish pronunciation") without rewriting the words.
- Voiceover: `says in an off-screen voiceover:` then the `<d>` block, then state that the
  on-screen character's lips remain closed.
- A line that crosses a cut uses `<scenetrans>` at both connecting points and says the audio
  continues uninterrupted. A line truncated by the end of the clip uses `<cutoff>`; never use it
  to hide a script that does not fit.
- Only the active speaker's lips move; others listen or react visibly.
- Density: about 2.8 words per second (3 at most) for all speakers together, after pauses and
  action. If exact dialogue will not fit, keep the words and say so; do not speed it up or cut it.
- Stable dialogue languages: Arabic, Chinese, English, French, German, Italian, Japanese,
  Korean, Portuguese, Russian and Spanish.

### 8. Audio fields
- `overall_soundscape`: ambience, physical action sounds, non-verbal human sounds. Never repeat
  dialogue, lyrics or music here. `N/A` only for complete silence. If the clip has speech or
  music but no ambience, write an explicit absence statement ("No ambience or foley is added.").
- `non_diegetic_music`: music only the audience hears (instrumentation, tempo, rhythm,
  dynamics; no mood explanations). `N/A` when none. Radio, phones and visible instruments are
  diegetic and belong in the shot description.
- "No music" ≠ "no dialogue" ≠ "complete silence". Complete silence: both audio fields `N/A`,
  no `<d>`, no foley elsewhere.
- Audio references: distinguish voice timbre (`reference`), exact copied track (`fully_copy`
  only when the whole signal is the whole final track; otherwise `partially_copy`), and music
  style (`reference`). For a delayed or partial cue, state both the target interval and the
  source interval. Text timing is guidance, not a sample-accurate editor.
- If the supplied track must be the only audio, add no ambience, foley, breathing or music.

### 9. Visual fidelity
- Visible text: straight double quotes, exact language and spelling, outside `<d>` unless also
  spoken: `A red neon sign reading "营业中" glows above the doorway.` Generated lettering is not
  guaranteed across frames; for mandatory legal/brand text recommend compositing.
- Identity lock: facial geometry, eyes, hair, facial hair, age presentation, body proportions
  and signature features; keep enough face area when fidelity matters. Roles (singer, villain)
  never change gender presentation, age or hairstyle.
- Style lock: name concrete rendering traits (line weight, cel shading, palette, material);
  reinforce at transformations and big environment changes. No "8K, masterpiece" lists.
- Keep one instance of each principal unless clones/reflections are requested; state
  left/centre/right placement and keep screen direction through cuts.
- Physical continuity: plausible support, contact and momentum; props stay in the right hand;
  hair and cloth move with localized secondary motion.
- Products and UI: preserve real geometry, branding and count; no invented claims, metrics,
  certifications or fake screens.
- Seamless loops: closed movement cycle, stable camera, matching light; with FL2VA use the same
  image as first and last frame. Inspect the join before calling it seamless.

### 10. Pre-flight checklist
1. Correct mode and format: 3 Base fields or 6 Ref2VA fields, in order, each once.
2. Every label maps to a real input under the numbering above; no phantom Subject/Audio.
3. Retention values from the allowed lists; no speaker IDs in retention.
4. Shots numbered from 1, timestamps increasing inside the effective duration, the action and
   any required last frame fit.
5. Every requested line appears once, in order, inside `<d>` next to its true speaker;
   speaker IDs and Audio bindings agree; speech density fits.
6. Audio layers match the request (no unrequested music, narration or foley).
7. No static/moving camera contradiction; identity, outfit and prop state consistent.
8. Literal text preserved; no invented logos, digits or claims.
9. No placeholders, settings, citations or notes inside the prompt.
10. Report an untested prompt as untested; inspect the actual output before claiming results.

### Example · T2VA (official case)
```text
integrated_multimodal_description: [Shot 1] Live-action, cinematic, a medium-wide shot frames a baker opening the shutters of a small street bakery before sunrise. The camera pushes in with small amplitude at slow speed as the middle-aged baker with a calm, slightly raspy voice (S1) places a fresh loaf on the wooden counter and says: <d>[English] First batch of the morning.</d> [Shot 2] At 00:05.000, the camera cuts to a close-up of steam rising from the sliced bread while the baker's final words carry over from the previous shot.

overall_soundscape: Wooden shutters scrape open over a quiet street as trays clink softly inside the bakery. The doorbell rings once, followed by light footsteps and the crisp sound of bread being sliced.

non_diegetic_music: A soft acoustic-guitar pattern at a moderate tempo, joined by sparse upright-bass notes and a gentle fade at the end.
```

### Example · I2VA (alignment line added by the runtime)
```text
integrated_multimodal_description: [Shot 1] Live-action, cinematic, the young woman shown in <Picture 1> remains beside the rain-covered train window, preserving her appearance, clothing, seat position and the carriage layout. The camera trucks right with small amplitude at slow speed as she lifts her gaze from the folded letter toward the passing city lights. Her reflection moves across the glass while the quiet, breathy young woman (S1) says: <d>[English] I get off at the next station.</d> She folds the letter along its existing crease.

overall_soundscape: The train wheels produce a steady metallic rhythm beneath a low ventilation hum. Rain ticks against the window while paper rustles softly in her hands.

non_diegetic_music: Sustained cello notes at a slow tempo with widely spaced piano tones, gradually decreasing in volume.
```
""".replace('{duration_table}', _h3_duration_table())

YUE2 = """## YuE2-3B · song generation (`generate_music`)

YuE2 turns an English style tag list and structured lyrics into a full song with vocals and
accompaniment (48 kHz stereo), optionally planning an ABC score first. The model receives
exactly `[Tags]` (your `style`) and `[Lyrics]` (your `lyrics`).

### Style (`style`)
A comma-separated list of English tags, typically 5–12, covering:
genre/subgenre, mood and energy, key instruments, vocal (gender, timbre, delivery),
tempo feel, era or production character. Exclusions as plain tags are fine ("no guitar").
Official examples:
- `City Pop, upbeat, danceable, groovy bass, electric guitar, synth, energetic, joyful, neon city night`
- `Jazz-funk, warm lead vocal, Rhodes piano, electric bass, tight drums`
- `Jazz, expressive lead vocal, piano, tenor saxophone, upright bass, brushed drums, no guitar, spacious modern harmony`
There is no BPM, key or duration parameter: express tempo as a feel ("relaxed mid-tempo",
"fast driving beat") and treat it as guidance, not a guarantee.

### Lyrics (`lyrics`)
- One section tag per line in square brackets, a blank line between sections:
  `[Intro]`, `[Verse]`, `[Pre-Chorus]`, `[Chorus]`, `[Interlude]`, `[Bridge]`, `[Outro]`.
- A section tag with no lines below it is an instrumental passage (official example songs use
  empty `[Intro]` and `[Interlude]`).
- One sung phrase per line. Write repeated choruses out in full where they are sung again;
  never "x2" or "(repeat)".
- Keep the user's lyrics verbatim in their language. The model card lists Mandarin and
  English; other languages (including Spanish) work to a lesser, untested degree — say so
  when the user cares about pronunciation.
- Song length follows the lyric structure; more sections make a longer song.
- Fully instrumental piece: add `instrumental, no vocals` to the style and use only section
  tags as lyrics (for example `[Intro]`, `[Interlude]`, `[Outro]`). The studio also accepts
  `[Instrumental]` as the whole lyrics. Instrumental behaviour is not documented officially;
  check the result.

### Modes and scores
| `mode` | Native behaviour | Use for |
| --- | --- | --- |
| `full` | Plans a chord-annotated ABC score, then renders (official default) | Best structure and harmony for new songs |
| `melody` | Plans a melody-only ABC score, then renders | Covers (official recommendation) |
| `direct` | No score ("off"); renders straight from tags and lyrics | Quicker drafts |
- A supplied nonempty `abc` is used unchanged (agentic editing: keep the original, edit a copy
  — reharmonise, add a solo, adapt lyrics — then regenerate with the same seed).
- **Cover:** `source_audio` with `mode=melody` (recommended) or `full`; SheetSage2 extracts the
  score and takes precedence over `abc`. Supply the original song's real lyrics organised into
  sections that match the recording, and a style describing the new arrangement. Never invent
  or recall lyrics you were not given; ask the user. `source_audio` with `direct` is invalid.
- Prompt, lyrics, score and music share one 24,576-token context: very long lyrics or scores
  leave less room and can shorten the song. `max_duration` (10–900 s) is a cap, not a target.
- Defaults: composition temperature 1.0, top_p 0.95, top_k 100, repetition penalty 1.2;
  ABC planning temperature 0.7, top_p 0.9, top_k 30, repetition penalty 1.005, window 100;
  32 diffusion steps.

### Example
```json
{"style": "Dreamy synth-pop, warm analog pads, crisp electronic drums, gentle female vocal, relaxed mid-tempo, nocturnal, luminous",
 "lyrics": "[Intro]\\n\\n[Verse]\\nLa ciudad se apaga lento\\nY yo sigo aquí despierta\\n\\n[Chorus]\\nBuenas noches, luna llena\\nQuédate un rato más\\n\\n[Outro]",
 "mode": "full"}
```
"""

DIRECTOR = """## Director · music videos (`plan_storyboard`, `create_production`)

The Director cuts a song into scenes; for each scene it renders a Qwen-Image-2.1 keyframe and
animates it with H3 in I2VA mode, then lays the ORIGINAL song under the finished cut.

- Analyse the real song first (`analyze_audio`): use its duration and energy sections for cut
  points. You have not listened to it; never claim to have heard it or to know its lyrics.
- Scenes start at 0, are contiguous, last more than 0 and at most 15 s, and cover the whole song.
  Each scene's clip is generated with `seconds = max(5, scene length)` and trimmed; plan the
  action for the effective duration (see the H3 duration table). A final scene under 5 s is allowed.
- `image_prompt`: a complete Qwen-Image observational paragraph for the keyframe (see the Qwen
  text-to-image guide). Repeat identity, wardrobe, setting and style in every scene; each scene
  is generated independently and sees no other prompt.
- `video_prompt`: an H3 Base prompt (three fields) that starts from that keyframe. The runtime
  adds the I2VA first-frame line. Describe motion, camera and continuity from the keyframe.
- The clip's generated sound is discarded: the song is the soundtrack. In ordinary scenes write
  `non_diegetic_music: N/A`, keep `overall_soundscape` short and do not script `<d>` dialogue; a
  visible performer can be described singing, but mouth motion is not synchronised to the vocal.
- **Lip-sync scenes (`lip_sync: true`, experimental):** for a scene where a visible performer
  must sing the real vocal, set `lip_sync: true` (scene of at least 2 s, not a reused clip). The
  runtime then renders that clip in r2v mode: the keyframe is `<Picture 1>` (identity/look, not a
  hard first frame) and the exact song excerpt for the scene is `<Audio 1>`. The `video_prompt`
  must be a six-section Ref2VA prompt, for example:
  ```text
  subject_definitions:
  <Subject 1> is the singer shown in <Picture 1>, preserving facial identity, hair, outfit and body proportions; the picture supplies appearance rather than its exact pose.
  <Audio 1> is the song excerpt for this scene, containing the lead vocal and the full accompaniment.

  summary:
  [reference generation + audio reuse] <Subject 1> performs the excerpt <Audio 1> on the moonlit stage, lip-syncing its lead vocal.

  retention_analysis:
  <Subject 1> (appears in [Shot 1]): fully_preserved - identity and outfit are kept.
  <Audio 1>: fully_copy - the excerpt is the complete soundtrack of the clip; the singer's mouth follows its vocal.

  detailed_description:
  The target video is in 2D-animated style matching <Picture 1>.
  [Shot 1] A medium close-up frames <Subject 1> at the microphone, face clearly visible. <Subject 1> (S1) sings in sync with the lead vocal of <Audio 1>, lips, jaw and breathing following each phrase, while the camera pushes in with small amplitude at slow speed.

  overall_soundscape:
  No ambience or foley is added beyond <Audio 1>.

  non_diegetic_music:
  The accompaniment of <Audio 1> continues as the score.
  ```
  Keep the face large and frontal enough to read the mouth. Put lyric words inside `<d>` only if
  the user supplied them and you know they fall in this scene. The final cut still uses the
  original song; synchronisation quality is not guaranteed and must be checked.
- Continuity: keep a private ledger of identity, outfit, props, location, light and screen
  direction; the next scene begins where the previous one ended unless the music motivates a
  change of place or time.
- Reuse supplied images or clips when asked (`image` keyframe PNG or `video` clip per scene).
  Short clips loop and long clips trim to cover their scene.
"""

AGENT_BRIEF = """Model prompt essentials (read prompt_guide for the full guide before complex prompts):
- Qwen text-to-image: one English observer paragraph (150–500 words): opening sentence naming medium, style, subject and background; walk the frame with positional phrases; quote visible text exactly in straight double quotes; one lighting sentence; one closing composition sentence. No quality boosters, no ratio or pixel counts in the prompt. transparent=true handles RGBA wording.
- Qwen editing: lead with the operation; change only what was asked, strongly; one blanket clause for what stays, without re-describing it. One image: no tags. Several images: <image1>, <image2>… in reference order, with each image's role (the first is the canvas). Literal text quoted exactly.
- H3: t2v=T2VA, i2v+first_frame=I2VA, i2v+first+last=FL2VA, t2v+last only=L2VA (runtime adds the alignment line), r2v=Ref2VA. Base prompt = integrated_multimodal_description / overall_soundscape / non_diegetic_music. Ref2VA = subject_definitions / summary / retention_analysis / detailed_description / overall_soundscape / non_diegetic_music. [Shot 1] has no timestamp; later shots "[Shot 2] At 00:04.500, the camera cuts to…". Dialogue/lyrics only inside <d>[Language] exact words</d>, speaker (S1) outside. Labels: <Picture i>=references[i], <Video k>=reference_videos[k], <Audio j>=soundtracks of reference videos that have audio, then reference_audios. N/A only for true absence. ~2.8 words/s of speech. No 30 s clips, Voice Audio, Animate, Outpaint or masked edits here.
- YuE2: style = comma-separated English tags (genre, mood, instruments, vocal, tempo feel); lyrics with [Intro]/[Verse]/[Pre-Chorus]/[Chorus]/[Bridge]/[Outro] tags, one phrase per line, repeated choruses written out, lyrics verbatim. mode=full for new songs, melody for covers with source_audio, direct for quick drafts. Never invent lyrics of an existing song.
- H3 profiles: base (default, 8–40 steps, best fidelity, true Ref2VA weights), turbo (LightX2V Turbo LoRAs on the official weights, 8 steps, about 2x faster, true Ref2VA), omni (FastH3 Omni, 8-step distilled Ref2VA, r2v only) or fused_turbo (experimental merge, 4 steps recommended, 4–12; fast drafts; softer audio). Same prompt format; never substitute one for the other silently.
- Qwen Turbo: model_variant="turbo" (create, edit, Director keyframes via keyframe_variant) uses the same prompts with a fixed 8-step schedule; no steps/scheduler/denoise options. Base (40 steps) remains the maximum-fidelity choice.
- Video upscaling: upscale_video runs FlashVSR v1.1 on an owned video (x2 default, x4 for small sources), keeps the original audio and creates a new video; no prompt is involved.
- Director: image_prompt is a Qwen observer paragraph repeating identity every scene; video_prompt is an H3 Base I2VA body from that keyframe; the song replaces clip audio, so non_diegetic_music is N/A. For a visible singer that must lip-sync, set lip_sync: true and write a Ref2VA video_prompt with <Picture 1> = keyframe and <Audio 1> = the song excerpt (fully_copy)."""

TOPICS = {
    'image': LANGUAGE + '\n' + QWEN_IMAGE,
    'edit': LANGUAGE + '\n' + QWEN_EDIT,
    'video': LANGUAGE + '\n' + H3,
    'music': LANGUAGE + '\n' + YUE2,
    'director': LANGUAGE + '\n' + DIRECTOR + '\n' + QWEN_IMAGE + '\n' + H3,
}

MODEL_GUIDE = '\n'.join([LANGUAGE, QWEN_IMAGE, QWEN_EDIT, H3, YUE2, DIRECTOR])
