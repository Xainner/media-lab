"""Speak one job with the official qwen-tts package, outside ComfyUI's Python environment.

qwen-tts 0.1.1 needs transformers 4.57 and ComfyUI ships 5.x, so the node runs this file in a
subprocess whose PYTHONPATH puts /opt/qwen-tts (qwen-tts, transformers 4.57.3 and their pinned
helpers) before the image's packages; torch, librosa and soundfile come from the image.

Usage: python worker.py job.json -> writes job["output"] (WAV) and prints its sample rate.
"""
import json
import sys

import numpy as np
import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel


def main(path):
    job = json.load(open(path, encoding="utf-8"))
    torch.manual_seed(job["seed"] % 2 ** 63)
    tts = Qwen3TTSModel.from_pretrained(job["model"], dtype=torch.bfloat16, device_map=job["device"])
    voice, language = job["voice"], job["language"]
    with torch.inference_mode():
        if voice == "preset":
            wavs, rate = tts.generate_custom_voice(text=job["text"], speaker=job["speaker"], language=language,
                                                   instruct=job["instruct"] or None)
        elif voice == "design":
            wavs, rate = tts.generate_voice_design(text=job["text"], instruct=job["instruct"], language=language)
        else:
            reference, reference_rate = sf.read(job["reference"], dtype="float32", always_2d=True)
            said = job["reference_text"]
            wavs, rate = tts.generate_voice_clone(text=job["text"], language=language,
                                                  ref_audio=(reference.mean(axis=1), reference_rate),
                                                  ref_text=said or None, x_vector_only_mode=not said)
    sf.write(job["output"], np.asarray(wavs[0], dtype=np.float32), int(rate), subtype="FLOAT")
    print(int(rate))


if __name__ == "__main__":
    main(sys.argv[1])
