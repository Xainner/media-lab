from __future__ import annotations

import re


UNET = "qwen_image_2.1_int8_convrot.safetensors"
UNET_BF16 = "qwen_image_2.1_bf16.safetensors"
ENCODER = "qwen3vl_8b_int8_convrot.safetensors"
VAE = "qwen_image_2.1_vae_bf16.safetensors"
UNET_TURBO = "qwen_image_2.1_turbo_int8_convrot.safetensors"
UNET_TURBO_BF16 = "qwen_image_2.1_turbo_bf16.safetensors"
# Qwen-Image-2.1-Turbo ships this 8-step schedule (model_index.json "sample_sigmas");
# other schedules are unevaluated, so Turbo graphs always use it (plus the terminal 0).
TURBO_SIGMAS = (1.0, 0.978453, 0.95418, 0.926626, 0.89508, 0.845148, 0.704534, 0.414568, 0.0)
TURBO_STEPS = len(TURBO_SIGMAS) - 1


# MOSS-Image SFT (OpenMOSS, Apache-2.0): official ComfyUI template — Qwen3.5 9B "moss_image" encoder,
# small FLUX.2 VAE, skip-layer guidance on single block 22 for the first half, er_sde / simple, CFG 2.5.
MOSS_UNET = "moss_image_sft_int8_convrot.safetensors"
MOSS_ENCODER = "qwen3.5_9b_w4a8_gptq.safetensors"
MOSS_VAE = "flux2-vae_small.safetensors"
MOSS_STEPS = {"draft": 16, "quality": 25}
MOSS_NEGATIVE = "nsfw, worst quality, bad anatomy, watermark, jpeg artifact"


def moss_ready(model_root) -> bool:
    return all(p.is_file() for p in (model_root / "diffusion_models" / MOSS_UNET,
                                     model_root / "text_encoders" / MOSS_ENCODER, model_root / "vae" / MOSS_VAE))


def moss_workflow(prompt: str, width: int, height: int, seed: int, steps: int) -> dict:
    if width % 16 or height % 16:
        raise ValueError("MOSS-Image needs width and height in multiples of 16")
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": MOSS_UNET, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": MOSS_ENCODER, "type": "moss_image", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": MOSS_VAE}},
        "slg": {"class_type": "SkipLayerGuidanceDiTSimple", "inputs": {
            "model": ["1", 0], "double_layers": "", "single_layers": "22", "start_percent": 0.0, "end_percent": 0.5}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "neg": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": MOSS_NEGATIVE}},
        "5": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "6": {"class_type": "KSampler", "inputs": {
            "model": ["slg", 0], "positive": ["4", 0], "negative": ["neg", 0], "latent_image": ["5", 0],
            "seed": seed, "steps": steps, "cfg": 2.5, "sampler_name": "er_sde", "scheduler": "simple", "denoise": 1.0}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["3", 0]}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "media_lab/moss_t2i"}},
    }


# FLUX 3 Image Klein (Black Forest Labs, FLUX Kommunity License): the official ComfyUI templates.
# Qwen3-VL 4B "flux3" encoder, FLUX.2 VAE, euler / simple. Draft is the step-distilled DiT (16 steps,
# CFG 1); quality is the base DiT (50 steps, CFG 3.5). BFL says never to run Klein without its
# prompt upsampler, so a fine-tuned Qwen3.5 9B always expands the request first (greedy decoding,
# the templates' settings) and the caption it writes is kept as the compiled prompt.
FLUX3_UNETS = {"draft": "flux3-image-klein-int8-convrot.safetensors",
               "quality": "flux3-image-klein-base-int8-convrot.safetensors"}
FLUX3_STEPS = {"draft": 16, "quality": 50}
FLUX3_CFG = {"draft": 1.0, "quality": 3.5}
FLUX3_ENCODER = "qwen3vl_4b_int8_convrot.safetensors"
FLUX3_UPSAMPLER = "qwen3.5_9b_flux3_prompt_upsampler_w4a8.safetensors"
FLUX3_VAE = "flux2-vae.safetensors"
FLUX3_MAX_REFERENCES = 4
TWO_K_EDIT_REFERENCES = 4
ORDINALS = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth")


def flux3_ready(model_root, quality: str = "draft") -> bool:
    return all(p.is_file() for p in (model_root / "diffusion_models" / FLUX3_UNETS[quality],
                                     model_root / "text_encoders" / FLUX3_ENCODER,
                                     model_root / "text_encoders" / FLUX3_UPSAMPLER, model_root / "vae" / FLUX3_VAE))


def flux3_request(prompt: str) -> str:
    """Our <image1>… reference names as the ordinals the Klein edit upsampler is trained on."""
    return re.sub(r"<image(\d{1,2})>", lambda m: f"the {ORDINALS[int(m.group(1)) - 1]} image"
                  if 1 <= int(m.group(1)) <= len(ORDINALS) else m.group(0), prompt.strip())


def flux3_upsampler(graph: dict, system: str, request: str, presence: float, images: list | None = None) -> list:
    graph["up_clip"] = {"class_type": "CLIPLoader", "inputs": {"clip_name": FLUX3_UPSAMPLER, "type": "flux3", "device": "default"}}
    inputs = {"clip": ["up_clip", 0], "prompt": request, "max_length": 3584, "sampling_mode": "on",
              "sampling_mode.temperature": 1.0, "sampling_mode.top_k": 1, "sampling_mode.top_p": 0.95,
              "sampling_mode.min_p": 0.0, "sampling_mode.repetition_penalty": 1.0, "sampling_mode.seed": 0,
              "sampling_mode.presence_penalty": presence, "thinking": False, "use_default_template": True,
              "mtp": "off", "system_prompt": system}
    if images:
        graph["up_images"] = {"class_type": "BatchImagesNode",
                              "inputs": {f"images.image{i}": image for i, image in enumerate(images)}}
        inputs["image"] = ["up_images", 0]
    graph["upsample"] = {"class_type": "TextGenerate", "inputs": inputs}
    graph["caption"] = {"class_type": "PreviewAny", "inputs": {"source": ["upsample", 0]}}
    return ["upsample", 0]


def flux3_workflow(prompt: str, width: int, height: int, seed: int, quality: str, aspect_ratio: str) -> dict:
    """Text to image. The request gets the template's optional TARGET CANVAS line so the caption fits the frame."""
    from .upsamplers import FLUX3_T2I_SYSTEM
    if width % 16 or height % 16:
        raise ValueError("FLUX 3 Klein needs width and height in multiples of 16")
    graph = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": FLUX3_UNETS[quality], "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": FLUX3_ENCODER, "type": "flux3", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": FLUX3_VAE}},
    }
    caption = flux3_upsampler(graph, FLUX3_T2I_SYSTEM, f"TARGET CANVAS: {aspect_ratio}\n{prompt.strip()}", 1.5)
    graph.update({
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": caption}},
        "neg": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": ""}},
        "5": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "6": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["4", 0], "negative": ["neg", 0], "latent_image": ["5", 0], "seed": seed,
            "steps": FLUX3_STEPS[quality], "cfg": FLUX3_CFG[quality], "sampler_name": "euler", "scheduler": "simple",
            "denoise": 1.0}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["3", 0]}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "media_lab/flux3_t2i"}},
    })
    return graph


def flux3_edit_workflow(prompt: str, uploaded_names: list[str], seed: int) -> dict:
    """Edit or compose from 1–4 references (distilled template: 16 steps, CFG 1, ~1 MP references).

    The output takes the first reference's shape at about 1 MP. Every reference goes to both the
    positive and the zeroed negative, as the reference pipeline does."""
    from .upsamplers import FLUX3_EDIT_SYSTEM
    if not 1 <= len(uploaded_names) <= FLUX3_MAX_REFERENCES:
        raise ValueError(f"FLUX 3 Klein edits 1–{FLUX3_MAX_REFERENCES} references")
    graph = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": FLUX3_UNETS["draft"], "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": FLUX3_ENCODER, "type": "flux3", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": FLUX3_VAE}},
    }
    images = []
    for index, name in enumerate(uploaded_names):
        graph[f"ref{index}"] = {"class_type": "LoadImage", "inputs": {"image": name}}
        images.append([f"ref{index}", 0])
    caption = flux3_upsampler(graph, FLUX3_EDIT_SYSTEM, flux3_request(prompt), 0.0, images)
    graph.update({
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": caption}},
        "neg": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["4", 0]}},
        "refs": {"class_type": "ReferenceMultiLatent", "inputs": {
            "positive": ["4", 0], "negative": ["neg", 0], "vae": ["3", 0], "resolution": "resize",
            "resolution.megapixels": 1.0, **{f"images.image{i}": image for i, image in enumerate(images)}}},
        "6": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["refs", 0], "negative": ["refs", 1], "latent_image": ["refs", 2],
            "seed": seed, "steps": FLUX3_STEPS["draft"], "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple",
            "denoise": 1.0}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["3", 0]}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "media_lab/flux3_edit"}},
    })
    return graph


# Qwen-Image 2.1 Fun ControlNet Union (alibaba-pai, qwen-research): one model patch for Canny, Depth,
# Pose, HED, Lineart, MLSD and Scribble maps, applied by the core ZImageFunControlnet node. The map is
# built from a plain photo with core preprocessors (Canny, Depth Anything 3, SDPose) or used as given.
CONTROL_PATCH = "qwen_image_2.1_fun_controlnet_union_int8_convrot.safetensors"
DEPTH_MODEL = "depth_anything_3_mono_large.safetensors"
POSE_MODEL = "sdpose_wholebody_fp16.safetensors"
CONTROL_MODES = ("canny", "depth", "pose", "map")
# Tuned on Saturno: edges and depth carry the source's silhouette and face (depth 0.8 turned a face into a
# mask), so they need a much lighter hand than pose.
CONTROL_STRENGTH = {"canny": 0.45, "depth": 0.5, "pose": 0.8, "map": 0.8}
CONTROL_FILES = {"canny": (), "map": (), "depth": (("geometry_estimation", DEPTH_MODEL),),
                 "pose": (("checkpoints", POSE_MODEL),)}

# QMA camera angles (gribbliest, Apache-2.0): Qwen 2.1 edit LoRA prompted "<qma> {azimuth} {elevation}
# {distance}", directions relative to the source camera. Card settings: strength 1.0, 30 steps, CFG 3.
CAMERA_LORA = "qwen-image-2.1-qma-camera-angles.safetensors"
CAMERA_STEPS = 30
# Qwen-Image 2.1's background-removal instruction (official Comfy template), verbatim: the RGBA wording
# of compile_prompt combined with "remove the background" erases the subject too.
REMOVE_BACKGROUND_PROMPT = "Remove the background, and output a PNG image"
REMOVE_BACKGROUND_STEPS = 40
CAMERA_CFG = 3.0
CAMERA_AZIMUTHS = ("front view", "front-right quarter view", "right side view", "back-right quarter view",
                   "back view", "back-left quarter view", "left side view", "front-left quarter view")
CAMERA_ELEVATIONS = ("low-angle shot", "eye-level shot", "elevated shot", "high-angle shot")
CAMERA_DISTANCES = ("close-up", "medium shot", "wide shot")


def control_ready(model_root, mode: str) -> bool:
    files = (("model_patches", CONTROL_PATCH),) + CONTROL_FILES[mode]
    return all((model_root / folder / name).is_file() for folder, name in files)


def camera_ready(model_root) -> bool:
    return (model_root / "loras" / CAMERA_LORA).is_file()


def camera_prompt(azimuth: str, elevation: str, distance: str, extra: str = "") -> str:
    prompt = f"<qma> {azimuth} {elevation} {distance}"
    return f"{prompt}. {extra.strip()}" if extra.strip() else prompt


def control_map(graph: dict, upload: str, mode: str, width: int, height: int) -> list:
    """Add nodes that turn the uploaded image into a control map at the output size."""
    graph.update({
        "c1": {"class_type": "LoadImage", "inputs": {"image": upload}},
        "c2": {"class_type": "ImageScale", "inputs": {
            "image": ["c1", 0], "upscale_method": "lanczos", "width": width, "height": height, "crop": "center"}},
    })
    if mode == "canny":
        graph["c3"] = {"class_type": "Canny", "inputs": {"image": ["c2", 0], "low_threshold": 0.1, "high_threshold": 0.32}}
    elif mode == "depth":
        graph.update({
            "c4": {"class_type": "LoadDA3Model", "inputs": {"model_name": DEPTH_MODEL, "weight_dtype": "default"}},
            "c5": {"class_type": "DA3Inference", "inputs": {
                "da3_model": ["c4", 0], "image": ["c2", 0], "resolution": 504,
                "resize_method": "upper_bound_resize", "mode": "mono"}},
            "c3": {"class_type": "DA3Render", "inputs": {
                "da3_geometry": ["c5", 0], "output": "depth", "output.normalization": "v2_style",
                "output.apply_sky_clip": False}},
        })
    elif mode == "pose":
        graph.update({
            "c4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": POSE_MODEL}},
            "c5": {"class_type": "SDPoseKeypointExtractor", "inputs": {
                "model": ["c4", 0], "vae": ["c4", 2], "image": ["c2", 0], "batch_size": 1}},
            "c3": {"class_type": "SDPoseDrawKeypoints", "inputs": {
                "keypoints": ["c5", 0], "draw_body": True, "draw_hands": True, "draw_face": True,
                "draw_feet": False, "stick_width": 4, "face_point_size": 2, "score_threshold": 0.5,
                "draw_head": True}},
        })
    else:
        return ["c2", 0]
    return ["c3", 0]


def apply_control(graph: dict, upload: str, mode: str, strength: float, width: int, height: int) -> None:
    """Route the t2i model (node 1) through the Fun ControlNet Union patch."""
    graph.update({
        "cp": {"class_type": "ModelPatchLoader", "inputs": {"name": CONTROL_PATCH}},
        "cn": {"class_type": "ZImageFunControlnet", "inputs": {
            "model": ["1", 0], "model_patch": ["cp", 0], "vae": ["3", 0], "strength": strength,
            "image": control_map(graph, upload, mode, width, height),
            "start_percent": 0.0, "end_percent": 1.0}},
    })
    sampler = graph["23"] if graph["6"]["class_type"] == "SamplerCustomAdvanced" else graph["6"]
    sampler["inputs"]["model"] = ["cn", 0]
    graph["8"]["inputs"]["filename_prefix"] = "media_lab/qwen21_control"


def apply_camera(graph: dict) -> None:
    """Load the QMA LoRA under the edit cache (node 2) with the card's sampler settings."""
    graph["lora"] = {"class_type": "LoraLoaderModelOnly", "inputs": {
        "model": ["1", 0], "lora_name": CAMERA_LORA, "strength_model": 1.0}}
    graph["2"]["inputs"]["model"] = ["lora", 0]
    graph["6"]["inputs"].update({"cfg": CAMERA_CFG, "sampler_name": "euler", "scheduler": "simple"})
    graph["8"]["inputs"]["filename_prefix"] = "media_lab/qwen21_camera"


def chain_loras(graph: dict, unet: str, loras: list[tuple[str, float]]) -> None:
    """Load library LoRAs right after the diffusion model; everything that read the model reads the chain."""
    if not loras:
        return
    source = [unet, 0]
    readers = [(node, key) for node, spec in graph.items() for key, value in spec["inputs"].items() if value == source]
    for index, (name, strength) in enumerate(loras):
        graph[f"user_lora_{index}"] = {"class_type": "LoraLoaderModelOnly", "inputs": {
            "model": source, "lora_name": name, "strength_model": strength}}
        source = [f"user_lora_{index}", 0]
    for node, key in readers:
        graph[node]["inputs"][key] = source


def diffusion_model(variant: str = "base", precision: str = "int8") -> str:
    if variant == "turbo":
        return UNET_TURBO_BF16 if precision == "bf16" else UNET_TURBO
    return UNET_BF16 if precision == "bf16" else UNET


def t2i_workflow(prompt: str, width: int, height: int, seed: int, steps: int,
                 encoder: str = ENCODER, unet: str = UNET, options=None, turbo: bool = False) -> dict:
    graph = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": encoder, "type": "qwen_image", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "4": {"class_type": "TextEncodeQwenImage21", "inputs": {
            "clip": ["2", 0], "prompt": prompt, "negative_prompt": "",
            "vae": ["3", 0], "resolution": 1024,
        }},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "6": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["4", 0], "negative": ["4", 1],
            "latent_image": ["5", 0], "seed": seed, "steps": steps, "cfg": 1.0,
            "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0,
        }},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["3", 0]}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "media_lab/qwen21_t2i"}},
    }
    if turbo:
        turbo_sampler(graph, ["1", 0], "4", ["5", 0], seed)
    apply_image_options(graph, "4", options)
    return graph


def edit_workflow(prompt: str, uploaded_names: list[str], seed: int, steps: int,
                  resolution: int = 0, encoder: str = ENCODER, unet: str = UNET, options=None,
                  turbo: bool = False) -> dict:
    if not 1 <= len(uploaded_names) <= 16:
        raise ValueError("edit requires between 1 and 16 references")
    graph: dict[str, dict] = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet, "weight_dtype": "default"}},
        "2": {"class_type": "QwenImage21Cache", "inputs": {"model": ["1", 0], "device": "auto", "dtype": "default"}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": encoder, "type": "qwen_image", "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
    }
    text_inputs: dict = {
        "clip": ["3", 0], "prompt": prompt, "negative_prompt": "",
        "vae": ["4", 0], "resolution": resolution,
    }
    for index, name in enumerate(uploaded_names, start=1):
        node_id = str(10 + index)
        graph[node_id] = {"class_type": "LoadImage", "inputs": {"image": name}}
        text_inputs[f"images.image_{index}"] = [node_id, 0]
    graph.update({
        "5": {"class_type": "TextEncodeQwenImage21", "inputs": text_inputs},
        "6": {"class_type": "KSampler", "inputs": {
            "model": ["2", 0], "positive": ["5", 0], "negative": ["5", 1],
            "latent_image": ["5", 2], "seed": seed, "steps": steps, "cfg": 1.0,
            "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0,
        }},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["4", 0]}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "media_lab/qwen21_edit"}},
    })
    if turbo:
        turbo_sampler(graph, ["2", 0], "5", ["5", 2], seed)
    apply_image_options(graph, "5", options)
    return graph


def turbo_sampler(graph: dict, model: list, text_node: str, latent: list, seed: int) -> None:
    """Replace the KSampler (node 6) with the Turbo checkpoint's fixed-sigma sampler."""
    graph.update({
        "20": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "21": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "22": {"class_type": "ManualSigmas", "inputs": {"sigmas": ", ".join(str(s) for s in TURBO_SIGMAS)}},
        "23": {"class_type": "CFGGuider", "inputs": {
            "model": model, "positive": [text_node, 0], "negative": [text_node, 1], "cfg": 1.0}},
        "6": {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise": ["20", 0], "guider": ["23", 0], "sampler": ["21", 0],
            "sigmas": ["22", 0], "latent_image": latent}},
    })


def apply_image_options(graph, text_node, options):
    if not options:
        return
    values = options.values()
    if graph['6']['class_type'] == 'SamplerCustomAdvanced':
        # Turbo: steps, scheduler and denoise belong to the fixed schedule (rejected upstream).
        if 'sampler' in values:
            graph['21']['inputs']['sampler_name'] = values['sampler']
        if 'cfg' in values:
            graph['23']['inputs']['cfg'] = values['cfg']
        if 'negative_prompt' in values:
            graph[text_node]['inputs']['negative_prompt'] = values['negative_prompt']
        return
    for key in ('steps', 'cfg', 'scheduler', 'denoise'):
        if key in values:
            graph['6']['inputs'][key] = values[key]
    if 'sampler' in values:
        graph['6']['inputs']['sampler_name'] = values['sampler']
    if 'negative_prompt' in values:
        graph[text_node]['inputs']['negative_prompt'] = values['negative_prompt']
