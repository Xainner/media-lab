"""Media Lab stems: split a song into vocals, drums, bass and other with Hybrid Demucs.

In-house node. It uses torchaudio's HDemucs (the HDEMUCS_HIGH_MUSDB_PLUS bundle: Meta's
weights, MIT) and needs nothing beyond the torch and torchaudio the image already ships.
Weights: models/stems/hdemucs_high_trained.pt (deploy/scripts/download-stems-model.sh).
"""
import os

import torch
import torchaudio
from torchaudio.transforms import Fade

import comfy.model_management as mm
import comfy.utils
import folder_paths

MODEL = "hdemucs_high_trained.pt"
SOURCES = ["drums", "bass", "other", "vocals"]
RATE = 44100
# Chunked like the torchaudio separation guide: 10 s windows overlapping 10% with a linear
# crossfade, so a whole song fits in a few GiB of VRAM.
SEGMENT, OVERLAP = 10.0, 0.1

folder_paths.add_model_folder_path("stems", os.path.join(folder_paths.models_dir, "stems"))
_model = None


def load_model():
    global _model
    if _model is None:
        path = folder_paths.get_full_path_or_raise("stems", MODEL)
        model = torchaudio.models.hdemucs_high(sources=SOURCES)
        model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
        _model = model.eval()
    return _model


def separate(model, mix, device, progress=None):
    """(batch, 2, samples) at 44.1 kHz -> (batch, 4 sources, 2, samples)."""
    batch, channels, length = mix.shape
    chunk = int(RATE * SEGMENT * (1 + OVERLAP))
    overlap = int(RATE * OVERLAP)
    fade = Fade(fade_in_len=0, fade_out_len=overlap, fade_shape="linear")
    final = torch.zeros(batch, len(SOURCES), channels, length)
    start, end = 0, chunk
    while start < length - overlap:
        with torch.inference_mode():
            out = model(mix[:, :, start:end].to(device)).float().cpu()
        final[:, :, :, start:end] += fade(out)
        if start == 0:
            fade.fade_in_len = overlap
            start += chunk - overlap
        else:
            start += chunk
        end += chunk
        if end >= length:
            fade.fade_out_len = 0
        if progress:
            progress.update_absolute(min(start, length), length)
    return final


class MediaLabStems:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"audio": ("AUDIO",)}}

    RETURN_TYPES = ("AUDIO", "AUDIO", "AUDIO", "AUDIO", "AUDIO")
    RETURN_NAMES = ("vocals", "instrumental", "drums", "bass", "other")
    FUNCTION = "split"
    CATEGORY = "audio/Media Lab"

    def split(self, audio):
        wave = audio["waveform"].float()
        if wave.shape[1] == 1:
            wave = wave.repeat(1, 2, 1)
        wave = wave[:, :2]
        if audio["sample_rate"] != RATE:
            wave = torchaudio.functional.resample(wave, audio["sample_rate"], RATE)
        # The model expects a normalised mix; the stems get the original scale back.
        ref = wave.mean(1)
        mean, std = ref.mean(), ref.std().clamp_min(1e-8)
        device = mm.get_torch_device()
        model = load_model().to(device)
        try:
            stems = separate(model, (wave - mean) / std, device, comfy.utils.ProgressBar(wave.shape[-1]))
        finally:
            model.to("cpu")
            mm.soft_empty_cache()
        stems = stems * std + mean
        by_name = dict(zip(SOURCES, stems.unbind(1)))
        by_name["instrumental"] = by_name["drums"] + by_name["bass"] + by_name["other"]
        # One shared gain keeps the stems summing to the song while none of them clips.
        gain = max(1.0, max(float(w.abs().max()) for w in by_name.values()) / 0.99)
        return tuple({"waveform": by_name[name] / gain, "sample_rate": RATE} for name in self.RETURN_NAMES)


NODE_CLASS_MAPPINGS = {"MediaLabStems": MediaLabStems}
NODE_DISPLAY_NAME_MAPPINGS = {"MediaLabStems": "Media Lab Stems (Hybrid Demucs)"}
