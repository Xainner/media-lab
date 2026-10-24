# Third-party notice

Media Lab's own code is licensed under the GNU Affero General Public License v3.0 (see
`LICENSE`). Media Lab is an independent project, not affiliated with any model publisher.

## Model weights

No model weights are part of this repository. The download scripts fetch them from their
publishers, and each keeps its own licence; the README's Licenses section lists them. In
particular, Qwen-Image 2.1 and Qwen-Image 2.1 Turbo (Comfy-Org repackages) are under the Qwen
Research License:

> Qwen is licensed under the Qwen RESEARCH LICENSE AGREEMENT, Copyright (c)
> 2026 Hangzhou Tongyi Laboratory Technology Co., Ltd. All Rights Reserved.

The model is restricted to non-commercial research/evaluation unless a separate commercial
license is obtained from its owner: https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE
(full text in `docs/QWEN-RESEARCH-LICENSE.txt`).

MiniMax H3 weights remain subject to the MiniMax model license:
https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE. The H3 Fused Turbo merge is an
experimental community merge for research use (`docs/H3-FUSED-0.7.1.md`). YuE2-3B weights
remain subject to their model terms: https://huggingface.co/m-a-p/YuE2-3B.

Generated work is intended for personal, non-commercial use under the applicable model terms.

## Third-party code

ComfyUI and its custom-node packs are fetched from their upstream repositories at pinned commits
into the ComfyUI image and are subject to their own licenses.

Video upscaling uses the FlashVSR v1.1 weights (Apache-2.0,
https://huggingface.co/JunhaoZhuang/FlashVSR-v1.1, from https://github.com/OpenImagingLab/FlashVSR)
through the ComfyUI node lihaoyun6/ComfyUI-FlashVSR_Ultra_Fast (GPL-3.0), cloned at a pinned
commit into the ComfyUI image. The idea of chunked FlashVSR upscaling comes from Maestro
(Blizaine/Maestro); no Maestro or WanGP code is used, since their non-commercial evaluation
license forbids hosted or API integrations.

Qwen3-TTS runs through the qwen-tts package (Apache-2.0) and Kandinsky 6 through the official
Kandinsky Lab ComfyUI extension (MIT), both pinned in `deploy/Dockerfile.comfyui`.

The web UI includes vendored Animate UI components (`apps/web/src/components/animate-ui`) under
their own license, MIT + Commons Clause, which forbids selling them; they are not covered by the
AGPL grant. It also uses shadcn/ui (MIT), and the web fonts are distributed locally under their
SIL Open Font Licenses (Bricolage Grotesque, Instrument Sans and JetBrains Mono). The upstream
license texts are included in `apps/web/public/licenses` and copied into the web build.
