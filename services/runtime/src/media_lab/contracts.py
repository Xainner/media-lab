from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from .model_options import CanvasOptions, ImageOptions, VideoOptions, SongOptions, video_size
from .creative_workflows import SA3_KINDS, TTS_LANGUAGES, TTS_SPEAKERS
from .workflows import CAMERA_AZIMUTHS, CAMERA_DISTANCES, CAMERA_ELEVATIONS, CONTROL_MODES, FLUX3_MAX_REFERENCES, TURBO_STEPS


PRESETS_1MP: dict[str, tuple[int, int]] = {
    "1:1": (1024, 1024),
    "4:3": (1152, 864),
    "3:4": (864, 1152),
    "3:2": (1216, 832),
    "2:3": (832, 1216),
    "16:9": (1344, 768),
    "9:16": (768, 1344),
    "4:5": (896, 1120),
    "5:4": (1120, 896),
}

PRESETS_2K: dict[str, tuple[int, int]] = {
    "1:1": (2048, 2048),
    "4:3": (2400, 1792),
    "3:4": (1792, 2400),
    "3:2": (2528, 1696),
    "2:3": (1696, 2528),
    "16:9": (2752, 1536),
    "9:16": (1536, 2752),
    "4:5": (1792, 2240),
    "5:4": (2240, 1792),
}

PRESET_LABELS: dict[str, tuple[str, str]] = {
    "1:1": ("Cuadrado", "square"),
    "16:9": ("Panorámico", "landscape"),
    "9:16": ("Historia vertical", "portrait"),
    "4:3": ("Horizontal clásico", "landscape"),
    "3:4": ("Retrato clásico", "portrait"),
    "3:2": ("Foto horizontal", "landscape"),
    "2:3": ("Foto vertical", "portrait"),
    "5:4": ("Social horizontal", "landscape"),
    "4:5": ("Social vertical", "portrait"),
}


def resolution_presets() -> list[dict]:
    return [
        {
            "id": ratio,
            "label": PRESET_LABELS[ratio][0],
            "orientation": PRESET_LABELS[ratio][1],
            "width": PRESETS_1MP[ratio][0],
            "height": PRESETS_1MP[ratio][1],
            "tier": "1mp",
        }
        for ratio in PRESET_LABELS
    ]


SESSION_HELP = "Optional conversation id to group results (1–80 letters, digits, _ or -). Default: your direct session."


class ArtifactRef(BaseModel):
    """An owned file: the exact pair returned by create_uploads, a completed job's `outputs` or list_library."""
    uri: str = Field(description="artifact://… identifier inside this studio, exactly as returned. It is not a local file: your own file or artifact tools cannot open it (use inspect_media to view, get_download_links to download). Never a local path or web URL.")
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$", description="SHA-256 returned together with the uri.")


class ExportRequest(ArtifactRef):
    format: Literal["png", "jpeg", "webp"] = "png"
    quality: int = Field(default=90, ge=1, le=100)
    background: str = Field(default="#ffffff", pattern=r"^#[0-9a-fA-F]{6}$")


class ModelRequest(BaseModel):
    def model_dump(self, *args, **kwargs):
        data = super().model_dump(*args, **kwargs)
        # Preserve fingerprints of persisted jobs created before advanced controls.
        for name in ('options', 'keyframe_options', 'video_options', 'reference_videos', 'reference_audios', 'seed',
                     'control', 'camera', 'remove_background', 'loras', 'audio_prompt', 'literal_prompt'):
            if name == 'seed' and not isinstance(self, ProductionRequest):
                continue
            if name in data and (data[name] is None or data[name] == [] or data[name] is False):
                data.pop(name)
        # Base is the pre-Turbo default: omit it so older idempotency fingerprints still match.
        for name in ('model_variant', 'keyframe_variant'):
            if data.get(name) == 'base':
                data.pop(name)
        # Edit and video requests gained `model` later; their default engine stays implicit.
        if isinstance(self, (EditRequest, VideoRequest)) and data.get('model') in ('qwen', 'h3'):
            data.pop('model')
        return data


class LoraUse(BaseModel):
    """A ready LoRA from the owner's library (list_loras), applied right after the diffusion model."""
    id: str = Field(pattern=r"^lora_[0-9a-f]{16}$", description="Library id from list_loras (or a character's lora).")
    strength: float | None = Field(default=None, ge=0.05, le=2.0, description="Unset = the strength saved in the library (usually 1.0).")


def check_loras(value: list[LoraUse]) -> list[LoraUse]:
    if len({use.id for use in value}) != len(value):
        raise ValueError("Cada LoRA solo puede usarse una vez")
    return value


LORAS_HELP = ("Up to 4 ready LoRAs from the owner's library, in order; each must match this model (base qwen for images, h3 for video). "
              "Put the LoRA's trigger words in the prompt.")
ModelVariant = Literal["base", "turbo"]
TURBO_FIXED = ('steps', 'scheduler', 'denoise')


def check_turbo_options(variant: str, options) -> None:
    if variant == "turbo" and options is not None:
        fixed = [name for name in TURBO_FIXED if getattr(options, name) is not None]
        if fixed:
            raise ValueError("Turbo usa su calendario fijo de 8 pasos; quita: " + ", ".join(fixed))


VARIANT_HELP = "base: Qwen-Image-2.1, maximum fidelity. turbo: fixed 8 steps, much faster (options.steps/scheduler/denoise not allowed). Check capabilities.model_variants."


class ImageControl(BaseModel):
    """Structure guide for a new Qwen image (Fun ControlNet Union)."""
    reference: ArtifactRef = Field(description="Owned image whose structure the new image follows; cropped to the chosen aspect ratio.")
    mode: Literal[CONTROL_MODES] = Field(default="canny", description="canny: edges of a photo. depth: Depth Anything 3 depth of a photo. pose: SDPose body, hands and face of the people in a photo. map: the reference already is a control map (pose skeleton, depth, lineart, scribble, HED or MLSD) and is used as given.")
    strength: float | None = Field(default=None, ge=0.1, le=1.5, description="How strictly the image follows the map; unset = per-mode default (canny 0.45, depth 0.5, pose and map 0.8). Lower it when the prompt fights the map.")


class GenerateRequest(ModelRequest):
    options: CanvasOptions | None = Field(default=None, description="Advanced sampling and custom canvas; leave unset for studio defaults (prompt_guide topic controls).")
    prompt: str = Field(min_length=1, max_length=20_000, description="English Qwen-Image observer paragraph written with prompt_guide topic image. Quote visible text exactly; no quality boosters or pixel sizes.")
    aspect_ratio: str = Field(default="1:1", description="Frame ratio.", json_schema_extra={"enum": list(PRESETS_1MP)})
    quality: Literal["draft", "quality"] = Field(default="quality", description="draft = 25 steps, quality = 40. Ignored by turbo.")
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1, description="Fixed seed to reproduce or compare; unset = random.")
    transparent: bool = Field(default=False, description="RGBA output with a transparent background; the runtime adds the alpha wording to the prompt.")
    resolution_tier: Literal["1mp", "2k"] = Field(default="1mp", description="2k only with INT8 when capabilities.two_k_enabled.")
    model_precision: Literal["int8", "bf16"] = "int8"
    model_variant: ModelVariant = Field(default="base", description=VARIANT_HELP)
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,80}$", description=SESSION_HELP)
    model: Literal["qwen", "moss", "flux3"] = Field(default="qwen", description="qwen: Qwen-Image 2.1 (variants, precisions, options, transparency). moss: MOSS-Image SFT, strong layout and in-image text (English or Chinese copy); 1MP presets only, draft 16 / quality 25 steps. flux3: FLUX 3 Image Klein, fast photorealism; its own prompt upsampler expands the request first (any language, short is fine); 1MP presets only, draft = distilled 16 steps, quality = base 50 steps.")
    control: ImageControl | None = Field(default=None, description="Qwen only, 1MP: follow the edges, depth or pose of an owned image (Fun ControlNet Union). Check capabilities.image_control.")
    loras: list[LoraUse] = Field(default_factory=list, max_length=4, description="Qwen only. " + LORAS_HELP)

    @model_validator(mode="after")
    def turbo_schedule(self):
        check_turbo_options(self.model_variant, self.options)
        if self.model != "qwen" and (self.options or self.transparent or self.model_variant != "base"
                                     or self.model_precision != "int8" or self.resolution_tier != "1mp"):
            name = {"moss": "MOSS-Image", "flux3": "FLUX 3 Klein"}[self.model]
            raise ValueError(f"{name} solo admite los formatos 1MP, sin opciones avanzadas ni transparencia")
        if self.control is not None and (self.model != "qwen" or self.resolution_tier != "1mp"):
            raise ValueError("El control de estructura solo funciona con Qwen-Image en 1MP")
        if self.loras and self.model != "qwen":
            raise ValueError("Los LoRAs de imagen funcionan con Qwen-Image 2.1")
        check_loras(self.loras)
        return self

    @field_validator("aspect_ratio")
    @classmethod
    def supported_ratio(cls, value: str) -> str:
        if value not in PRESETS_1MP:
            raise ValueError("unsupported aspect ratio")
        return value


class CameraMove(BaseModel):
    """New viewpoint for the same subject and scene (QMA camera-angles LoRA)."""
    azimuth: Literal[CAMERA_AZIMUTHS] = Field(default="front-right quarter view", description="Where the camera orbits to, relative to the source camera (not the subject).")
    elevation: Literal[CAMERA_ELEVATIONS] = Field(default="eye-level shot", description="Camera height.")
    distance: Literal[CAMERA_DISTANCES] = Field(default="medium shot", description="Framing distance.")


class EditRequest(ModelRequest):
    options: ImageOptions | None = Field(default=None, description="Advanced sampling; leave unset for studio defaults.")
    prompt: str = Field(default="", max_length=20_000, description="English edit instruction (prompt_guide topic edit): lead with the operation, change only what is asked. With several references name them <image1>, <image2>… in list order. Optional with camera: extra edits after the camera move (camera-only gives the cleanest result).")
    references: list[ArtifactRef] = Field(min_length=1, max_length=10, description="1–10 owned images in order; the first is the canvas being edited.")
    camera: CameraMove | None = Field(default=None, description="Re-shoot the single reference from another angle (QMA LoRA, base variant, 30 steps, CFG 3; no options or transparency). Check capabilities.image_camera.")
    quality: Literal["draft", "quality"] = Field(default="quality", description="draft = 25 steps, quality = 40. Ignored by turbo.")
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1, description="Fixed seed to reproduce; unset = random.")
    transparent: bool = Field(default=False, description="Keep or produce a transparent background.")
    remove_background: bool = Field(default=False, description="Cut the single reference out onto a transparent background with Qwen-Image 2.1's own instruction (base variant, 40 steps). The prompt is not used; no camera or options.")
    resolution: int = Field(default=0, ge=0, le=2048, description="0 keeps the first reference size within about 1 MP; otherwise a multiple of 32 up to 1024.")
    loras: list[LoraUse] = Field(default_factory=list, max_length=4, description="Not with remove_background. " + LORAS_HELP)
    model_precision: Literal["int8", "bf16"] = "int8"
    model_variant: ModelVariant = Field(default="base", description=VARIANT_HELP)
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,80}$", description=SESSION_HELP)
    model: Literal["qwen", "flux3"] = Field(default="qwen", description=f"qwen: Qwen-Image 2.1 edit. flux3: FLUX 3 Image Klein (distilled, 16 steps): 1–{FLUX3_MAX_REFERENCES} references, output about 1 MP in the first reference's shape; its upsampler sees the images and expands the request (name references 'the first image'…, or <image1>…); no camera, background removal, options, transparency, turbo, bf16, resolution or LoRAs.")

    @model_validator(mode="after")
    def turbo_schedule(self):
        check_turbo_options(self.model_variant, self.options)
        if self.model == "flux3" and (len(self.references) > FLUX3_MAX_REFERENCES or self.camera is not None
                                      or self.remove_background or self.options or self.transparent or self.loras
                                      or self.model_variant != "base" or self.model_precision != "int8" or self.resolution):
            raise ValueError(f"FLUX 3 Klein edita con 1 a {FLUX3_MAX_REFERENCES} imágenes, sin ángulo, quitar fondo, opciones, transparencia, LoRAs ni resolución")
        if self.camera is None and not self.remove_background and not self.prompt.strip():
            raise ValueError("Describe la edición")
        if self.remove_background and (len(self.references) != 1 or self.camera is not None
                                       or self.model_variant != "base" or self.options):
            raise ValueError("Quitar el fondo usa una sola imagen y el modelo base, sin ángulo ni opciones avanzadas")
        if self.camera is not None and (len(self.references) != 1 or self.model_variant != "base"
                                        or self.options or self.transparent):
            raise ValueError("El cambio de ángulo usa una sola imagen, el modelo base, sin transparencia ni opciones avanzadas")
        if self.remove_background and self.loras:
            raise ValueError("Quitar el fondo no usa LoRAs")
        check_loras(self.loras)
        return self

    @field_validator("resolution")
    @classmethod
    def multiple_of_32(cls, value: int) -> int:
        if value and value % 32:
            raise ValueError("resolution must be zero or a multiple of 32")
        return value


class SessionMessage(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: str = Field(max_length=100_000)
    media: list[ArtifactRef] = Field(default_factory=list, max_length=100)


H3Profile = Literal["base", "fused_turbo", "turbo", "omni"]


def h3_steps(profile: str, steps: int | None) -> int:
    low, high, default = {"fused_turbo": (4, 12, 4), "turbo": (4, 12, 8), "omni": (4, 12, 8)}.get(profile, (8, 40, 20))
    value = default if steps is None else steps
    if not low <= value <= high:
        raise ValueError(f"H3 {profile} requires {low}-{high} steps")
    return value


class VideoControl(BaseModel):
    """Motion or structure source for a new H3 clip (Fun ControlNet-Union 2.0 on Ref2VA)."""
    video: ArtifactRef = Field(description="Owned clip of 2–15 s that the new clip follows; it also sets the length and the aspect ratio (nearest of 16:9, 9:16, 1:1).")
    mode: Literal["pose", "canny", "depth"] = Field(default="pose", description="pose: copy the movement of up to 2 people (SDPose skeletons) and redraw everything else. canny: keep the outlines of the whole shot. depth: keep the 3D layout and camera move (Depth Anything 3).")
    strength: float = Field(default=1.0, ge=0.1, le=2.0, description="1.0 follows the control fully (official recipe); lower it when the prompt fights the source.")
    keep_audio: bool = Field(default=True, description="Put the source clip's soundtrack on the result (the motion matches it); false keeps the audio H3 generates.")


class VideoRequest(ModelRequest):
    options: VideoOptions | None = Field(default=None, description="Resolution, encoding and advanced sampling; unset = preview resolution and studio defaults.")
    reference_videos: list[ArtifactRef] = Field(default_factory=list, max_length=3, description="r2v only: owned videos of 2–15 s, labelled <Video 1>… in order.")
    reference_audios: list[ArtifactRef] = Field(default_factory=list, max_length=3, description="r2v only: owned audio of 2–15 s (all audio, including reference-video soundtracks, at most 15 s in total), labelled <Audio j> after the soundtracks of reference videos.")
    prompt: str = Field(min_length=1, max_length=20000, description="English H3 prompt in the exact sectioned format for the mode (prompt_guide topic video). Run check_prompt with the same inputs first.")
    mode: Literal["t2v", "i2v", "r2v"] = Field(default="t2v", description="t2v: text only (a last_frame alone gives L2VA). i2v: needs first_frame, optional last_frame. r2v: references, reference_videos and/or reference_audios.")
    first_frame: ArtifactRef | None = Field(default=None, description="i2v: owned image that opens the clip.")
    last_frame: ArtifactRef | None = Field(default=None, description="Optional owned image the clip ends on.")
    references: list[ArtifactRef] = Field(default_factory=list, max_length=9, description="r2v only: up to 9 owned images, labelled <Picture 1>… in order.")
    aspect_ratio: Literal["16:9", "9:16", "1:1"] = "16:9"
    seconds: float = Field(default=5, ge=5, le=15, description="Clip length, 5–15 s at 24 fps.")
    control: VideoControl | None = Field(default=None, description="Follow the motion, outlines or depth of an owned clip (mode r2v; references are optional and give identity). The clip sets length and aspect ratio; profile base or turbo. Check capabilities.video.control.")
    profile: H3Profile = Field(default="base", description="base: best fidelity, 8–40 steps (default 20). fused_turbo: experimental fast drafts, 4–12 steps. turbo: LightX2V Turbo LoRAs on the real H3 weights (true Ref2VA for r2v), 4–12 steps (default 8). omni: FastH3 Omni, an 8-step distilled Ref2VA checkpoint, r2v only, 4–12 steps (default 8). Check capabilities.video.profiles.")
    steps: int | None = Field(default=None, ge=4, le=40, description="Unset = profile default.")
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1, description="Fixed seed to reproduce; unset = random.")
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,80}$", description=SESSION_HELP)
    loras: list[LoraUse] = Field(default_factory=list, max_length=4, description=LORAS_HELP)
    model: Literal["h3", "kandinsky6"] = Field(default="h3", description="h3: MiniMax H3 (everything above). kandinsky6: Kandinsky 6.0 Lite Distill, a 5 s clip at 864x480 (16:9 or 9:16) with synchronized 44 kHz audio and lip-synced speech, from text (t2v) or a first_frame (i2v); write spoken lines in the prompt as <S>exact words<E> and the voice/sounds in audio_prompt. No references, last_frame, control, LoRAs, options, profile or steps. Check capabilities.video.models.kandinsky6.")
    audio_prompt: str | None = Field(default=None, max_length=4000, description="kandinsky6 only: the voice (gender, age, tone, accent) and the other sounds, ambience or music of the clip.")
    literal_prompt: bool = Field(default=False, description="kandinsky6 only: send prompt and audio_prompt unchanged instead of letting the official beautifier (Qwen3.5 9B) expand them into full captions (it keeps the language you wrote in, so write English).")

    @model_validator(mode="after")
    def profile_steps(self):
        check_loras(self.loras)
        if self.model == "kandinsky6":
            if (self.mode not in ("t2v", "i2v") or self.last_frame or self.references or self.reference_videos
                    or self.reference_audios or self.control or self.loras or self.options or self.profile != "base"
                    or self.steps is not None):
                raise ValueError("Kandinsky 6 genera desde texto o una imagen inicial, sin referencias, imagen final, control, LoRAs, opciones, perfil ni pasos")
            if self.aspect_ratio not in ("16:9", "9:16") or self.seconds != 5:
                raise ValueError("Kandinsky 6 hace clips de 5 s en 16:9 o 9:16")
            if self.mode == "i2v" and not self.first_frame:
                raise ValueError("El modo i2v necesita first_frame")
            return self
        if self.audio_prompt or self.literal_prompt:
            raise ValueError("audio_prompt y literal_prompt son solo para Kandinsky 6")
        self.steps = h3_steps(self.profile, self.steps)
        if self.profile == "omni" and self.mode != "r2v":
            raise ValueError("FastH3 Omni solo genera desde referencias (modo r2v)")
        video_size(self.aspect_ratio, self.options)
        if self.control and (self.mode != "r2v" or self.profile not in ("base", "turbo")):
            raise ValueError("El control de vídeo usa el modo r2v con el perfil base o turbo")
        if self.mode != 'r2v' and (self.reference_videos or self.reference_audios):
            raise ValueError('Las referencias de audio y vídeo requieren modo r2v')
        return self

    @field_validator("references")
    @classmethod
    def references_for_mode(cls, value: list[ArtifactRef]) -> list[ArtifactRef]:
        return value


class SongRequest(ModelRequest):
    options: SongOptions | None = Field(default=None, description="Composition, score, diffusion and output format controls; unset = studio defaults.")
    style: str = Field(min_length=1, max_length=10000, description="Comma-separated English tags: genre, mood, instruments, vocal, tempo feel (prompt_guide topic music).")
    lyrics: str = Field(min_length=1, max_length=20000, description="Verbatim lyrics with [Verse]/[Chorus]/… section tags, one phrase per line; instrumental: section tags only.")
    mode: Literal["direct", "full", "melody"] = Field(default="direct", description="full: new song with a planned score. melody: covers with source_audio. direct: quick draft without score planning.")
    abc: str = Field(default="", max_length=100000, description="Optional ABC score used unchanged.")
    source_audio: ArtifactRef | None = Field(default=None, description="Owned audio for a cover (with mode full or melody); not allowed with direct.")
    max_duration: float = Field(default=120, ge=10, le=900, description="YuE2: upper bound in seconds, not an exact length. ACE-Step: the exact length (10–600 s).")
    steps: int = Field(default=32, ge=4, le=80)
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1)
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,80}$", description=SESSION_HELP)
    model: Literal["yue2", "ace_step"] = Field(default="yue2", description="yue2: YuE2 3B, covers and scores, slower. ace_step: ACE-Step 1.5 XL Turbo, a full song in about a minute; no covers or ABC.")
    bpm: int | None = Field(default=None, ge=40, le=240, description="ace_step only: tempo. Default: a 'NN BPM' tag in style, else 110.")
    key: str | None = Field(default=None, max_length=12, description="ace_step only: key such as 'E minor'. Default: a key named in style, else C major.")
    language: str | None = Field(default=None, pattern=r"^[a-z]{2}$", description="ace_step only: sung language code (es, en, pt, …). Default: guessed from the lyrics.")
    time_signature: Literal["2", "3", "4", "6"] | None = Field(default=None, description="ace_step only: beats per bar, 2 (2/4), 3 (3/4, waltz), 4 (4/4, default) or 6 (6/8).")

    @model_validator(mode="after")
    def ace_scope(self):
        if self.model == "ace_step":
            if self.source_audio or self.abc:
                raise ValueError("ACE-Step no hace covers ni usa partituras ABC; usa YuE2")
            if self.max_duration > 600:
                raise ValueError("ACE-Step genera hasta 10 minutos")
            # ACE-Step's documented input limits.
            if len(self.style) > 512 or len(self.lyrics) > 4096:
                raise ValueError("ACE-Step admite hasta 512 caracteres de estilo y 4096 de letra")
        return self


class ProductionRequest(ModelRequest):
    keyframe_options: CanvasOptions | None = None
    video_options: VideoOptions | None = None
    seed: int | None = Field(default=None, ge=0, le=2**53 - 1)
    title: str = Field(min_length=1, max_length=120)
    song: ArtifactRef = Field(description="Owned song (5–900 s) that drives timing and becomes the soundtrack.")
    brief: str = Field(min_length=1, max_length=10000, description="English visual direction: identity, wardrobe, locations, lighting, style.")
    lyrics: str = Field(default="", max_length=20000)
    scenes: list[dict] = Field(min_length=1, max_length=100)
    aspect_ratio: Literal["16:9", "9:16", "1:1"] = "16:9"
    keyframe_precision: Literal["int8", "bf16"] = "int8"
    keyframe_variant: ModelVariant = "base"
    keyframe_quality: Literal["draft", "quality"] = "draft"
    keyframe_resolution: Literal["legacy", "1mp", "2k"] = "legacy"
    video_profile: H3Profile = "base"
    video_steps: int | None = Field(default=None, ge=4, le=40)
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,80}$", description=SESSION_HELP)

    @model_validator(mode="after")
    def profile_steps(self):
        self.video_steps = h3_steps(self.video_profile, self.video_steps)
        if self.video_profile == "omni":
            raise ValueError("FastH3 Omni solo genera desde referencias; el Director usa Base o Turbo")
        video_size(self.aspect_ratio, self.video_options)
        check_turbo_options(self.keyframe_variant, self.keyframe_options)
        return self


UPSCALE_SCALES = (2, 4)
# Limits measured on a 24 GiB RTX 3090 (see docs/RELEASE-0.9.0.md). Chunking bounds memory,
# so length is limited by estimated GPU time: ~15 s (fast) or ~40 s (quality) per second of
# video and output megapixel, capped at 45 minutes per job.
UPSCALE_MAX_INPUT_PIXELS = {2: 1_100_000, 4: 420_000}
UPSCALE_MAX_SECONDS = 600
UPSCALE_RATE = {"fast": 15, "quality": 40}
UPSCALE_MAX_WORK_SECONDS = 2700


def upscale_estimate(duration: float, width: int, height: int, scale: int, quality: str) -> int:
    return round(duration * width * height * scale * scale / 1_000_000 * UPSCALE_RATE[quality])


class UpscaleRequest(ModelRequest):
    video: ArtifactRef = Field(description="Owned video (generated, Director production or uploaded source) up to capabilities.upscale.max_seconds.")
    scale: Literal[2, 4] = Field(default=2, description="2x, or 4x for small sources (see capabilities.upscale.max_input_pixels).")
    quality: Literal["fast", "quality"] = Field(default="fast", description="fast: FlashVSR tiny. quality: FlashVSR full, about 2.7x slower.")
    seed: int | None = Field(default=None, ge=0, le=2**50)
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,80}$", description=SESSION_HELP)


class SwapRequest(ModelRequest):
    mode: Literal["character", "head", "scail"] = Field(default="character", description="character = replace the whole person (face, hair and outfit) with H3 Character Swap; head = replace only the head and keep the body and clothes (experimental Head Swap); scail = replace the whole person with SCAIL-2 (Wan 2.1 14B), which keeps the body motion tightly and re-lights the character into the scene.")
    video: ArtifactRef = Field(description="Owned source clip of 2–15 s (best ≤5 s, one continuous shot). Its motion, scene, camera and soundtrack are kept.")
    character: ArtifactRef = Field(description="Owned image of the replacement character (face, hair and outfit clearly visible); for mode=head, one clear front view of the new face.")
    target: str = Field(default="", max_length=300, description="English description of who to replace, e.g. 'the woman in the red jacket'. Empty = the main person.")
    details: str = Field(default="", max_length=600, description="mode=head only: short English attribute list of the new face (gender, face shape, skin, eyes, hair, distinctive features). Empty = written automatically from the image.")
    prompt: str | None = Field(default=None, max_length=20000, description="mode=character: optional full English Ref2VA prompt overriding the default swap instruction; cite <Video 1> and <Picture 1>. mode=scail: optional English description of the finished clip that describes the NEW character (look, outfit, scene), never the person being replaced; default: written from the character image by Qwen3-VL.")
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1)
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,80}$", description=SESSION_HELP)


class RemoveRequest(ModelRequest):
    video: ArtifactRef = Field(description="Owned source clip of 1–10 s (best ≤5 s, one continuous shot, steady camera). Everything but the removed person, and the soundtrack, is kept.")
    target: str = Field(default="", max_length=300, description="Short English description of the person to remove for the segmenter, e.g. 'man in yellow hoodie'. Empty = the most prominent person.")
    clean_frame: ArtifactRef | None = Field(default=None, description="Optional owned image of the clip's first frame without the person (same framing). Default: made automatically with Qwen-Image edit.")
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1)
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,80}$", description=SESSION_HELP)


class StemsRequest(ModelRequest):
    audio: ArtifactRef = Field(description="Owned song or audio of 1–900 s: an upload, a generated song or a production soundtrack.")
    stems: Literal["two", "four"] = Field(default="two", description="two = vocals + instrumental (karaoke, covers, remixes); four = vocals, drums, bass and other.")
    format: Literal["flac", "mp3"] = Field(default="flac")
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,80}$", description=SESSION_HELP)


class SoundRequest(ModelRequest):
    prompt: str = Field(min_length=1, max_length=4000, description="The sound or instrumental piece: genre, instruments, mood, tempo for music; source, material, space and movement for effects. Any language when enhance is on (Qwen rewrites it in English); English otherwise.")
    kind: Literal["music", "instrument", "sfx", "one_shot"] = Field(default="music", description="music: a full instrumental track (Stable Audio 3 Medium, 5–380 s). instrument: a solo instrument part or loop (Medium, 2–380 s). sfx: sound effects and ambiences (Small SFX, 1–120 s). one_shot: a single hit or sample (Small SFX, 0.5–10 s). No vocals or lyrics: use generate_music for songs.")
    seconds: float = Field(default=30, ge=0.5, le=380, description="Exact length in seconds, within the kind's range.")
    enhance: bool = Field(default=True, description="Let Qwen3.5 2B rewrite the idea with the official category-aware prompt (recommended; the rewrite is returned). false sends the prompt unchanged.")
    format: Literal["flac", "mp3"] = Field(default="flac")
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1)
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,80}$", description=SESSION_HELP)

    @model_validator(mode="after")
    def kind_length(self):
        low, high = SA3_KINDS[self.kind][2]
        if not low <= self.seconds <= high:
            raise ValueError(f"Para {self.kind} la duración va de {low:g} a {high:g} s")
        return self


class SpeechRequest(ModelRequest):
    text: str = Field(min_length=1, max_length=5000, description="Exactly what is said, with normal punctuation. Up to about 5 minutes of speech.")
    voice: Literal["preset", "design", "clone"] = Field(default="preset", description="preset: one of the nine studio voices (speaker), with an optional delivery instruction. design: a new voice described in instruct. clone: the voice of an owned reference clip; ONLY with the permission of the person whose voice it is (consent=true).")
    speaker: Literal[TTS_SPEAKERS] = Field(default="serena", description="preset only. serena, vivian, sohee, ono_anna: female; ryan, aiden, uncle_fu, eric, dylan: male. Every voice speaks every language.")
    instruct: str = Field(default="", max_length=1000, description="preset: optional delivery, e.g. 'whispering, nervous, fast'. design: required voice description (gender, age, timbre, accent, emotion, pace). Natural language, any language.")
    language: Literal[TTS_LANGUAGES] = Field(default="auto", description="Spoken language; auto detects it from the text.")
    reference: ArtifactRef | None = Field(default=None, description="clone only: owned audio or video of 3–30 s with one clear voice and little noise.")
    reference_text: str = Field(default="", max_length=1000, description="clone only: the exact words said in the reference; improves likeness. Empty clones only the timbre.")
    consent: bool = Field(default=False, description="clone only: true confirms the person whose voice it is (the user or someone who agreed) allowed this use. Never clone a voice without permission or to deceive.")
    format: Literal["flac", "mp3"] = Field(default="flac")
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1)
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,80}$", description=SESSION_HELP)

    @model_validator(mode="after")
    def voice_inputs(self):
        if self.voice == "clone":
            if self.reference is None:
                raise ValueError("Clonar una voz necesita un clip de referencia")
            if not self.consent:
                raise ValueError("Solo se clona una voz con permiso de su dueño: confirma el consentimiento")
        elif self.reference is not None or self.reference_text or self.consent:
            raise ValueError("La referencia y el consentimiento son solo para clonar")
        if self.voice == "design" and not self.instruct.strip():
            raise ValueError("Describe la voz que quieres diseñar")
        return self


class FaceRefineRequest(ModelRequest):
    video: ArtifactRef = Field(description="Owned clip of 1–15 s with one main face (best ≥ 50 px tall; upscale small videos first). Everything outside the face, and the audio, is kept.")
    identity: ArtifactRef | None = Field(default=None, description="Optional owned image of the person, used to hold identity. Default: the character image of a swap result, else a frame of the clip.")
    strength: Literal["light", "medium", "strong"] = Field(default="medium", description="How much H3 may redraw the face: light only sharpens, strong fixes drift and artifacts but may change expression detail.")
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1)
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,80}$", description=SESSION_HELP)


def steps_for(variant: str, quality: str, options=None) -> int:
    if variant == "turbo":
        return TURBO_STEPS
    return options.steps if options is not None and options.steps is not None else steps_for_quality(quality)


def generation_size(body: GenerateRequest, enable_2k: bool) -> tuple[int, int]:
    if body.resolution_tier == "2k":
        if not enable_2k:
            raise ValueError("2K is not enabled on this host")
        return PRESETS_2K[body.aspect_ratio]
    return PRESETS_1MP[body.aspect_ratio]


def steps_for_quality(quality: str) -> int:
    return 40 if quality == "quality" else 25


def compile_prompt(prompt: str, transparent: bool) -> str:
    prompt = prompt.strip()
    if not transparent:
        return prompt
    # Qwen-Image-2.1's documented transparency wording, verbatim.
    return (
        "This is an RGBA image with transparency. "
        f"{prompt.rstrip('.')}. The image has alpha channel and the background is transparent."
    )
