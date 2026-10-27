"""Typed controls for the installed native Qwen 2.1, H3 and YuE2 graphs.

Node capabilities were checked on both Saturno workers. Host memory limits are
deliberately separate from the much larger raw Comfy node input ranges.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SAMPLERS = (
    "euler", "euler_cfg_pp", "euler_ancestral", "euler_ancestral_cfg_pp", "heun", "heunpp2",
    "exp_heun_2_x0", "exp_heun_2_x0_sde", "dpm_2", "dpm_2_ancestral", "lms", "dpm_fast", "dpm_adaptive",
    "dpmpp_2s_ancestral", "dpmpp_2s_ancestral_cfg_pp", "dpmpp_sde", "dpmpp_sde_gpu",
    "dpmpp_2m", "dpmpp_2m_cfg_pp", "dpmpp_2m_sde", "dpmpp_2m_sde_gpu",
    "dpmpp_2m_sde_heun", "dpmpp_2m_sde_heun_gpu", "dpmpp_3m_sde", "dpmpp_3m_sde_gpu",
    "ddpm", "lcm", "ipndm", "ipndm_v", "deis", "cfgpp_ud10_ab", "res_multistep",
    "res_multistep_cfg_pp", "res_multistep_ancestral", "res_multistep_ancestral_cfg_pp",
    "gradient_estimation", "gradient_estimation_cfg_pp", "er_sde", "seeds_2", "seeds_3",
    "sa_solver", "sa_solver_pece", "ddim", "uni_pc", "uni_pc_bh2",
)
SCHEDULERS = ("simple", "sgm_uniform", "karras", "exponential", "ddim_uniform", "beta", "normal", "linear_quadratic", "kl_optimal")


class Options(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    def values(self):
        return self.model_dump(exclude_none=True)


class SamplingOptions(Options):
    sampler: str | None = None
    scheduler: str | None = None
    denoise: float | None = Field(default=None, ge=0, le=1)

    @field_validator("sampler", "scheduler")
    @classmethod
    def installed_choice(cls, value, info):
        if value is not None and value not in (SAMPLERS if info.field_name == "sampler" else SCHEDULERS):
            raise ValueError("Opción de muestreo no instalada")
        return value


class ImageOptions(SamplingOptions):
    steps: int | None = Field(default=None, ge=1, le=200)
    cfg: float | None = Field(default=None, ge=0, le=100)
    negative_prompt: str | None = Field(default=None, max_length=20000)


class CanvasOptions(ImageOptions):
    width: int | None = Field(default=None, ge=32, le=16384, multiple_of=32)
    height: int | None = Field(default=None, ge=32, le=16384, multiple_of=32)

    @model_validator(mode="after")
    def paired_dimensions(self):
        if (self.width is None) != (self.height is None):
            raise ValueError("Indica ancho y alto juntos")
        return self


class VideoOptions(SamplingOptions):
    resolution: Literal["preview", "480p", "720p", "native", "custom"] = "preview"
    width: int | None = Field(default=None, ge=32, le=16384, multiple_of=32)
    height: int | None = Field(default=None, ge=32, le=16384, multiple_of=32)
    shift_video: float | None = Field(default=None, ge=0.01, le=100)
    shift_audio: float | None = Field(default=None, ge=0.01, le=100)
    ref_image_size: Literal["match", "max"] = "match"
    container: Literal["mp4", "mkv", "webm"] = "mp4"
    codec: Literal["h264", "av1"] = "h264"
    bit_depth: Literal[8, 10] | None = None
    crf: int | None = Field(default=None, ge=0, le=63)

    @model_validator(mode="after")
    def combinations(self):
        if self.resolution == "custom" and (self.width is None or self.height is None):
            raise ValueError("La resolución personalizada requiere ancho y alto")
        if self.resolution != "custom" and (self.width is not None or self.height is not None):
            raise ValueError("Elige resolución personalizada para indicar dimensiones")
        if self.container == "webm" and self.codec != "av1":
            raise ValueError("WebM requiere AV1")
        if self.crf is not None and self.codec == "h264" and self.crf > 51:
            raise ValueError("CRF H.264 debe estar entre 0 y 51")
        return self


class CompositionOptions(Options):
    temperature: float | None = Field(default=None, ge=0, le=5)
    top_p: float | None = Field(default=None, ge=0.01, le=1)
    top_k: int | None = Field(default=None, ge=1, le=32768)
    repetition_penalty: float | None = Field(default=None, ge=0.01, le=10)
    cfg_scale: float | None = Field(default=None, ge=0, le=100)


class ScoreOptions(CompositionOptions):
    cfg_scale: None = None
    max_abc_tokens: int | None = Field(default=None, ge=1, le=20000)
    penalty_window: int | None = Field(default=None, ge=1, le=20000)


class SongOptions(SamplingOptions):
    cfg: float | None = Field(default=None, ge=0, le=100)
    composition: CompositionOptions | None = None
    score: ScoreOptions | None = None
    format: Literal["flac", "mp3", "opus"] = "flac"
    audio_quality: Literal["V0", "64k", "96k", "128k", "192k", "320k"] | None = None

    @model_validator(mode="after")
    def encoding_quality(self):
        choices = {"flac": {None}, "mp3": {None, "V0", "128k", "320k"},
                   "opus": {None, "64k", "96k", "128k", "192k", "320k"}}
        if self.audio_quality not in choices[self.format]:
            raise ValueError("Calidad de audio incompatible con el formato")
        return self


VIDEO_PRESETS = {
    "preview": {"16:9": (640, 352), "9:16": (352, 640), "1:1": (480, 480)},
    "480p": {"16:9": (864, 480), "9:16": (480, 864), "1:1": (640, 640)},
    "720p": {"16:9": (1280, 704), "9:16": (704, 1280), "1:1": (960, 960)},
    "native": {"16:9": (1344, 768), "9:16": (768, 1344), "1:1": (1024, 1024)},
}


def video_size(ratio, options=None):
    settings = options or VideoOptions()
    size = ((settings.width, settings.height) if settings.resolution == "custom"
            else VIDEO_PRESETS[settings.resolution][ratio])
    if size[0] * size[1] > 1_100_000:
        raise ValueError("H3: este servidor admite hasta 1,1 MP por fotograma")
    return size


def image_canvas(body, enable_2k, fallback):
    options = body.options
    size = (options.width, options.height) if options and options.width is not None else fallback
    limit = 4_500_000 if enable_2k and body.model_precision == "int8" else 1_200_000
    if size[0] * size[1] > limit:
        raise ValueError("El tamaño supera el límite de generación del servidor para esta precisión")
    return size


def option_catalog():
    """UI and agents consume the same validated fields; no arbitrary graph inputs."""
    def field(path, label, group, default=None, **extra):
        return dict(path=path, label=label, group=group, default=default, **extra)
    def sampling(sampler, scheduler, cfg=True, steps=False):
        out = [field("sampler", "Muestreador", "Muestreo", sampler, choices=list(SAMPLERS)),
               field("scheduler", "Curva de ruido", "Muestreo", scheduler, choices=list(SCHEDULERS)),
               field("denoise", "Intensidad de denoising", "Muestreo", 1, min=0, max=1, step=0.01)]
        if cfg:
            out.append(field("cfg", "Guía CFG", "Muestreo", 1, min=0, max=100, step=0.1))
        if steps:
            out.append(field("steps", "Pasos personalizados", "Muestreo", None, min=1, max=200, step=1,
                             help="Vacío: usa los pasos del preset de calidad."))
        return out
    image = sampling("euler", "simple", steps=True) + [
        field("negative_prompt", "Prompt negativo", "Condicionamiento", "", type="text"),
    ]
    canvas = [field("width", "Ancho personalizado", "Tamaño", None, min=32, max=16384, step=32),
              field("height", "Alto personalizado", "Tamaño", None, min=32, max=16384, step=32)]
    video = sampling("res_multistep", "simple", cfg=False) + [
        field("shift_video", "Desplazamiento de sigmas · vídeo", "Condicionamiento", 12, min=.01, max=100, step=.1),
        field("shift_audio", "Desplazamiento de sigmas · audio", "Condicionamiento", 3, min=.01, max=100, step=.1),
        field("ref_image_size", "Tamaño de las referencias", "Condicionamiento", "match", choices=["match", "max"],
              help="max: mayor fidelidad de identidad, más memoria y tiempo."),
        field("container", "Contenedor", "Archivo de salida", "mp4", choices=["mp4", "mkv", "webm"]),
        field("codec", "Códec", "Archivo de salida", "h264", choices=["h264", "av1"]),
        field("bit_depth", "Profundidad de color · salida SDR", "Archivo de salida", 8, choices=[8, 10],
              help="8 o 10 bits de codificación. El modelo genera SDR; esto no convierte el resultado en HDR."),
        field("crf", "Calidad de compresión · CRF", "Archivo de salida", None, min=0, max=63, step=1,
              help="Menor CRF conserva más detalle y ocupa más. H.264: 0–51; AV1: 0–63. Vacío: automático."),
    ]
    song = sampling("dpm_2", "sgm_uniform")
    for path, group, defaults in [("composition", "Composición", (1, .95, 100, 1.2)), ("score", "Generación de partitura ABC", (.7, .9, 30, 1.005))]:
        for key, label, default, low, high, step in [
            ("temperature", "Temperatura", defaults[0], 0, 5, .01),
            ("top_p", "Top P", defaults[1], .01, 1, .01),
            ("top_k", "Top K", defaults[2], 1, 32768, 1),
            ("repetition_penalty", "Penalización de repetición", defaults[3], .01, 10, .001),
        ]:
            song.append(field(f"{path}.{key}", label, group, default, min=low, max=high, step=step))
    song += [field("composition.cfg_scale", "Guía de composición", "Composición", 1, min=0, max=100, step=.01),
             field("score.max_abc_tokens", "Máximo de tokens ABC", "Generación de partitura ABC", 8192, min=1, max=20000, step=1),
             field("score.penalty_window", "Ventana de repetición", "Generación de partitura ABC", 100, min=1, max=20000, step=1),
             field("format", "Formato de audio", "Archivo de salida", "flac", choices=["flac", "mp3", "opus"]),
             field("audio_quality", "Calidad de compresión", "Archivo de salida", None, choices=["V0", "64k", "96k", "128k", "192k", "320k"])]
    return {"image": image + canvas, "edit": image, "video": video, "song": song,
            "video_resolutions": VIDEO_PRESETS,
            "limits": {"video_pixels": 1_100_000, "image_pixels": 1_200_000, "image_2k_pixels": 4_500_000},
            "notes": {"video": "24 fps con audio sincronizado; 5–15 s dentro del rango entrenado. Dimensiones múltiplos de 32. 720p usa 704 píxeles por alineación. Resoluciones altas requieren más VRAM.",
                      "sampling": "Los valores originales son los predeterminados del estudio. Otros muestreadores son experimentales: más pasos no garantizan más calidad.",
                      "image": "Hasta 1,2 MP; hasta 4,5 MP en INT8 si el servidor habilita 2K. La edición llega a 2K solo con Qwen INT8 y hasta 4 referencias.",
                      "score": "Estos ajustes se aplican al generar ABC; no alteran una partitura escrita o extraída de audio."}}
