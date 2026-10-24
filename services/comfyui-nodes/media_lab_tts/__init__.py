"""Media Lab speech: text to speech with Qwen3-TTS 12Hz 1.7B (Qwen, Apache-2.0).

In-house node over the official qwen-tts package. qwen-tts 0.1.1 is written for transformers
4.57 and the image ships 5.x, so each job runs worker.py in a subprocess with /opt/qwen-tts
(qwen-tts and its pinned transformers, accelerate, huggingface_hub and tokenizers) first on
PYTHONPATH; ComfyUI frees the VRAM it needs first and the subprocess gives it all back on exit.
Three checkpoints in models/tts (deploy/scripts/download-qwen3-tts-models.sh): CustomVoice speaks
with one of nine preset voices, VoiceDesign invents a voice from a description, and Base clones
the voice of a reference clip. Cloning is only for voices used with permission; the runtime asks
for that consent before a clone job is admitted.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

import numpy as np
import soundfile as sf
import torch

import comfy.model_management as mm
import folder_paths

CHECKPOINTS = {"preset": "Qwen3-TTS-12Hz-1.7B-CustomVoice", "design": "Qwen3-TTS-12Hz-1.7B-VoiceDesign",
               "clone": "Qwen3-TTS-12Hz-1.7B-Base"}
SPEAKERS = ["serena", "vivian", "uncle_fu", "ryan", "aiden", "ono_anna", "sohee", "eric", "dylan"]
LANGUAGES = ["auto", "spanish", "english", "portuguese", "french", "german", "italian", "japanese", "korean",
             "chinese", "russian"]
# A 1.7B talker in bf16 plus its speech tokenizer; freed from ComfyUI before the worker starts.
VRAM_BYTES = 6 * 1024 ** 3
QWEN_TTS_PATH = os.environ.get("MEDIA_LAB_QWEN_TTS_PATH", "/opt/qwen-tts")
WORKER = os.path.join(os.path.dirname(__file__), "worker.py")

folder_paths.add_model_folder_path("tts", os.path.join(folder_paths.models_dir, "tts"))


def checkpoint(name):
    path = next((os.path.join(root, name) for root in folder_paths.get_folder_paths("tts")
                 if os.path.isdir(os.path.join(root, name))), None)
    if path is None:
        raise FileNotFoundError(f"Qwen3-TTS checkpoint not installed: tts/{name}")
    return path


def run_worker(job_path):
    """Run one job, killing the worker if the ComfyUI prompt is cancelled."""
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(p for p in (QWEN_TTS_PATH, os.environ.get("PYTHONPATH")) if p)}
    worker = subprocess.Popen([sys.executable, WORKER, job_path], env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True)
    try:
        while worker.poll() is None:
            mm.throw_exception_if_processing_interrupted()
            time.sleep(0.25)
    except BaseException:
        worker.kill()
        worker.wait()
        raise
    out, err = worker.communicate()
    if worker.returncode:
        raise RuntimeError("Qwen3-TTS failed: " + (err.strip().splitlines() or ["no output"])[-1])
    return out


class MediaLabSpeech:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"multiline": True, "default": ""}),
                "voice": (list(CHECKPOINTS), {"default": "preset"}),
                "language": (LANGUAGES, {"default": "auto"}),
                "speaker": (SPEAKERS, {"default": "serena"}),
                "instruct": ("STRING", {"multiline": True, "default": "",
                                        "tooltip": "preset: optional delivery (emotion, pace). design: the voice itself, in words."}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
            },
            "optional": {
                "reference": ("AUDIO", {"tooltip": "clone: 3–30 s of the voice, used only with the speaker's permission."}),
                "reference_text": ("STRING", {"multiline": True, "default": "",
                                              "tooltip": "clone: what the reference says; empty clones the timbre only."}),
            },
        }

    RETURN_TYPES = ("AUDIO",)
    FUNCTION = "speak"
    CATEGORY = "audio/Media Lab"

    def speak(self, text, voice, language, speaker, instruct, seed, reference=None, reference_text=""):
        if not text.strip():
            raise ValueError("Nothing to say")
        if voice == "clone" and reference is None:
            raise ValueError("Voice cloning needs a reference clip")
        if voice == "design" and not instruct.strip():
            raise ValueError("Describe the voice to design")
        model = checkpoint(CHECKPOINTS[voice])
        device = mm.get_torch_device()
        mm.free_memory(VRAM_BYTES, device)
        mm.soft_empty_cache()
        with tempfile.TemporaryDirectory(prefix="media-lab-tts-") as work:
            job = {"model": model, "device": str(device), "voice": voice, "text": text, "speaker": speaker,
                   "language": "Auto" if language == "auto" else language.capitalize(),
                   "instruct": instruct.strip(), "seed": seed, "reference": None,
                   "reference_text": reference_text.strip(), "output": os.path.join(work, "speech.wav")}
            if voice == "clone":
                job["reference"] = os.path.join(work, "reference.wav")
                wave = reference["waveform"][0].float().mean(0).cpu().numpy().astype(np.float32)
                sf.write(job["reference"], wave, int(reference["sample_rate"]), subtype="FLOAT")
            job_path = os.path.join(work, "job.json")
            with open(job_path, "w", encoding="utf-8") as f:
                json.dump(job, f)
            run_worker(job_path)
            data, rate = sf.read(job["output"], dtype="float32", always_2d=True)
        wave = torch.from_numpy(data.mean(axis=1)).reshape(1, 1, -1)
        peak = float(wave.abs().max())
        if peak > 0.99:
            wave = wave * (0.99 / peak)
        return ({"waveform": wave, "sample_rate": int(rate)},)


NODE_CLASS_MAPPINGS = {"MediaLabSpeech": MediaLabSpeech}
NODE_DISPLAY_NAME_MAPPINGS = {"MediaLabSpeech": "Media Lab Speech (Qwen3-TTS)"}
