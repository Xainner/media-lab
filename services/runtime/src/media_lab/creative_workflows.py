"""Pinned API graphs for native ComfyUI H3 and YuE2 nodes."""
from __future__ import annotations

import re

H3_FL = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
H3_REF = "minimax_h3_ref2va_pruned_int8_convrot.safetensors"
H3_CLIP = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
H3_VIDEO_VAE = "minimax_h3_video_vae_fp16.safetensors"
H3_AUDIO_VAE = "minimax_h3_audio_vae_fp32.safetensors"
H3_FUSED = "minimax_h3_fused_refdelta_r1024_turbo8_mystic07_int8_convrot.safetensors"
H3_FUSED_VIDEO_VAE = "minimax_h3_video_vae_int8_convrot.safetensors"
H3_FUSED_REVISION = "3b51096a1bf67608d98131116558202208fcf195"
H3_FUSED_SHA256 = "4262e4e9963c553fa00016bbe83961407a4fc0a888be95fd836c8d4f2304e48b"
H3_FUSED_VAE_SHA256 = "9bb2d96f218c76babd85e0611b85ca8fb330a90546c01a0005e8a58a59593410"
# LightX2V H3 Turbo LoRAs (768p builds): base checkpoints + LoRA at 1.0, euler / simple, 8 steps, shift 6/3.
H3_TURBO_FL_LORA = "minimax_h3_fl2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors"
H3_TURBO_REF_LORA = "minimax_h3_ref2v_turbo_8step_v1.1_768p_comfyui_bf16.safetensors"
H3_TURBO_SHIFT = (6.0, 3.0)
# FastH3 Omni (FastVideo + Nuva Lab): an 8-step distilled Ref2VA checkpoint; official core template is euler /
# simple, 8 steps, CFG 1, shift 12/3, int8 video VAE (its VSA sparse attention is skipped: Ampere is unverified).
H3_OMNI = "fasth3_omniref_8step_pruned_int8_convrot.safetensors"
# Fun ControlNet-Union 2.0 (10 control blocks) on the Ref2VA transformer; the official Comfy template
# feeds SDPose skeletons with RT-DETR person boxes, and Canny/Depth Anything 3 cover edges and depth.
H3_CONTROL_PATCH = "minimax_h3_fun_controlnet_union_2.0_pruned_int8_convrot.safetensors"
H3_DETECTOR = "rt_detr_v4-x-hgnet_fp16.safetensors"
VIDEO_CONTROL_MODES = ("pose", "canny", "depth")
VIDEO_CONTROL_SECONDS = (2, 15)
YUE2 = "yue2_3b_int8_convrot.safetensors"
SHEETSAGE = "sheetsage2_bf16.safetensors"


def h3_profiles(shared_root, fused_root, lora_root) -> dict:
    common = [(shared_root / "text_encoders" / H3_CLIP), (shared_root / "vae" / H3_AUDIO_VAE)]
    base = common + [shared_root / "diffusion_models" / H3_FL,
                     shared_root / "diffusion_models" / H3_REF, shared_root / "vae" / H3_VIDEO_VAE]
    fused = common + [fused_root / "diffusion_models" / H3_FUSED, fused_root / "vae" / H3_FUSED_VIDEO_VAE]
    turbo = base[:-1] + [fused_root / "vae" / H3_FUSED_VIDEO_VAE,
                         lora_root / "loras" / H3_TURBO_FL_LORA, lora_root / "loras" / H3_TURBO_REF_LORA]
    omni = common + [fused_root / "vae" / H3_FUSED_VIDEO_VAE, lora_root / "diffusion_models" / H3_OMNI]
    return {
        "base": {"label": "H3 Base", "ready": all(p.is_file() for p in base),
                 "steps": {"min": 8, "max": 40, "default": 20}, "attention": "dense"},
        "fused_turbo": {"label": "H3 Fused Turbo · 4 pasos", "ready": all(p.is_file() for p in fused),
                        "steps": {"min": 4, "max": 12, "default": 4}, "attention": "dense",
                        "experimental": True, "checkpoint": H3_FUSED, "revision": H3_FUSED_REVISION,
                        "notice": "Turbo y Mystic fusionados. Atención densa, no SLA; calidad no idéntica a Maestro."},
        "omni": {"label": "FastH3 Omni · 8 pasos", "ready": all(p.is_file() for p in omni),
                 "steps": {"min": 4, "max": 12, "default": 8}, "attention": "dense", "modes": ["r2v"],
                 "checkpoint": H3_OMNI},
        "turbo": {"label": "H3 Turbo · 8 pasos", "ready": all(p.is_file() for p in turbo),
                  "steps": {"min": 4, "max": 12, "default": 8}, "attention": "dense",
                  "loras": [H3_TURBO_FL_LORA, H3_TURBO_REF_LORA]},
    }


def h3_length(seconds: float) -> int:
    """Frame count on H3's 17n+5 grid at 24 fps, clamped to the trained 124–362 range."""
    return min(362, max(124, 17 * round((seconds * 24 - 5) / 17) + 5))


def h3_model_prompt(prompt: str, mode: str, seconds: float, first: bool, last: bool) -> str:
    """Prefix the official keyframe alignment instruction unless the prompt already has one.

    The native encoder labels the supplied frames <Picture 1>/<Picture 2> but never states
    where they sit on the timeline; the official I2VA/FL2VA/L2VA formats require that line.
    """
    text = prompt.strip()
    lowered = text.lower()
    if mode == "r2v" or not (first or last) or "is fully referenced" in lowered or "align with the target video" in lowered:
        return text
    end = f"{h3_length(seconds) / 24:.2f}"
    shots = [int(n) for n in re.findall(r"\[Shot (\d+)\]", text)]
    final = max(shots, default=1)
    if first and last:
        header = ("How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the "
                  f"0.00-second mark of the target video; Picture 2 (from Shot {final}) aligns with the {end}-second mark of the target video.")
    elif first:
        header = "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced."
    else:
        header = ("How the reference pictures align with the target video — <Picture 1> "
                  f"(from [Shot {final}]) aligns with the {end}-second mark of the target video.")
    return header + "\n\n" + text


def h3_workflow(prompt: str, mode: str, width: int, height: int, seconds: float,
                steps: int, seed: int, first: str | None = None,
                last: str | None = None, references: list[str] | None = None,
                profile: str = "base", options=None, reference_videos=None, reference_audios=None, video_soundtracks=None,
                control: tuple[str, str, float] | None = None) -> dict:
    """control = (uploaded clip already at the output size and length, pose|canny|depth, strength)."""
    from .contracts import h3_steps
    if profile not in {"base", "fused_turbo", "turbo", "omni"}:
        raise ValueError("unsupported H3 profile")
    h3_steps(profile, steps)
    fused = profile == "fused_turbo"
    turbo = profile == "turbo"
    omni = profile == "omni"
    if omni and mode != "r2v":
        raise ValueError("FastH3 Omni solo genera desde referencias (r2v)")
    if mode not in {"t2v", "i2v", "r2v"}:
        raise ValueError("unsupported H3 mode")
    if mode == "i2v" and not first:
        raise ValueError("image to video needs a first frame")
    if control and (mode != "r2v" or profile not in {"base", "turbo"}):
        raise ValueError("El control de vídeo usa H3 Ref2VA (modo r2v) con el perfil base o turbo")
    if mode == "r2v" and not (references or reference_videos or reference_audios or control):
        raise ValueError("reference to video needs references")
    length = h3_length(seconds)
    graph = {
        "video_vae": {"class_type": "VAELoader", "inputs": {"vae_name": H3_FUSED_VIDEO_VAE if fused or turbo or omni else H3_VIDEO_VAE}},
        "audio_vae": {"class_type": "VAELoader", "inputs": {"vae_name": H3_AUDIO_VAE}},
        "unet": {"class_type": "UNETLoader", "inputs": {
            "unet_name": H3_FUSED if fused else H3_OMNI if omni else (H3_REF if mode == "r2v" else H3_FL), "weight_dtype": "default"}},
        "clip": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": H3_CLIP, "type": "minimax", "device": "default"}},
        "noise": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "scheduler": {"class_type": "BasicScheduler", "inputs": {
            "model": ["unet", 0], "scheduler": "beta" if mode == "r2v" and not fused else "simple",
            "steps": steps, "denoise": 1.0}},
        "sampler": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "guider": {"class_type": "BasicGuider", "inputs": {
            "model": ["unet", 0], "conditioning": ["condition", 0]}},
        "sample": {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise": ["noise", 0], "guider": ["guider", 0], "sampler": ["sampler", 0],
            "sigmas": ["scheduler", 0], "latent_image": ["condition", 1]}},
        "decode_video": {"class_type": "VAEDecode", "inputs": {
            "samples": ["sample", 0], "vae": ["video_vae", 0]}},
        "decode_audio": {"class_type": "VAEDecodeAudio", "inputs": {
            "samples": ["sample", 0], "vae": ["audio_vae", 0]}},
        "video": {"class_type": "CreateVideo", "inputs": {
            "images": ["decode_video", 0], "audio": ["decode_audio", 0], "fps": 24}},
        "save": {"class_type": "SaveVideo", "inputs": {
            "video": ["video", 0], "filename_prefix": "media_lab/h3", "format": "mp4", "format.codec": "h264"}},
    }
    if turbo:
        graph["turbo_lora"] = {"class_type": "LoraLoaderModelOnly", "inputs": {
            "model": ["unet", 0], "lora_name": H3_TURBO_REF_LORA if mode == "r2v" else H3_TURBO_FL_LORA, "strength_model": 1.0}}
    if turbo or omni:
        graph["sampler"]["inputs"]["sampler_name"] = "euler"
        graph["scheduler"]["inputs"]["scheduler"] = "simple"
    model = ["turbo_lora", 0] if turbo else ["unet", 0]
    graph["scheduler"]["inputs"]["model"] = graph["guider"]["inputs"]["model"] = model
    if fused or turbo or omni or (options and (options.shift_video is not None or options.shift_audio is not None)):
        # Native dense attention: do not stack a second Turbo/SLA LoRA on the bake.
        video_shift, audio_shift = H3_TURBO_SHIFT if turbo else (12.0, 3.0)
        graph["shift"] = {"class_type": "MiniMaxH3SigmaShift", "inputs": {
            "model": model, "shift_video": options.shift_video if options and options.shift_video is not None else video_shift,
            "shift_audio": options.shift_audio if options and options.shift_audio is not None else audio_shift}}
        graph["scheduler"]["inputs"]["model"] = ["shift", 0]
        graph["guider"]["inputs"]["model"] = ["shift", 0]
    inputs = {"clip": ["clip", 0], "prompt": h3_model_prompt(prompt, mode, seconds, bool(first), bool(last)), "width": width,
              "height": height, "length": length}
    if mode == "r2v":
        inputs.update({"vae": ["video_vae", 0], "audio_vae": ["audio_vae", 0],
                       "ref_image_size": "match"})
        refs = {}
        for index, name in enumerate(references or []):
            node_id = f"ref_{index}"
            graph[node_id] = {"class_type": "LoadImage", "inputs": {"image": name}}
            refs[f"ref_images.ref_image_{index}"] = [node_id, 0]
        for index, name in enumerate(reference_videos or []):
            load, parts = f'ref_video_{index}', f'ref_video_parts_{index}'
            graph[load] = {'class_type': 'LoadVideo', 'inputs': {'file': name}}
            graph[parts] = {'class_type': 'GetVideoComponents', 'inputs': {'video': [load, 0]}}
            refs[f'ref_videos.ref_video_{index}'] = [parts, 0]
            if video_soundtracks and video_soundtracks[index]:
                refs[f'ref_video_audios.ref_video_audio_{index}'] = [parts, 1]
        for index, name in enumerate(reference_audios or []):
            node_id = f'ref_audio_{index}'
            graph[node_id] = {'class_type': 'LoadAudio', 'inputs': {'audio': name}}
            refs[f'ref_audios.ref_audio_{index}'] = [node_id, 0]
        inputs.update(refs)
        if options:
            inputs['ref_image_size'] = options.ref_image_size
        condition_type = "MiniMaxH3ReferenceToVideo"
    else:
        inputs["vae"] = ["video_vae", 0]
        for label, name in (("first_frame", first), ("last_frame", last)):
            if name:
                node_id = f"load_{label}"
                graph[node_id] = {"class_type": "LoadImage", "inputs": {"image": name}}
                inputs[label] = [node_id, 0]
        condition_type = "MiniMaxH3ImageToVideo"
    graph["condition"] = {"class_type": condition_type, "inputs": inputs}
    if control:
        apply_h3_control(graph, *control)
    if options:
        if options.sampler is not None:
            graph['sampler']['inputs']['sampler_name'] = options.sampler
        for key in ('scheduler', 'denoise'):
            if getattr(options, key) is not None:
                graph['scheduler']['inputs'][key] = getattr(options, key)
        if options.bit_depth is not None:
            graph['video']['inputs']['bit_depth'] = options.bit_depth
        graph['save']['inputs'].update({'format': options.container, 'format.codec': options.codec})
        if options.crf is not None:
            graph['save']['inputs'].update({'format.codec.encoding': 're-encode', 'format.codec.encoding.crf': options.crf})
    return graph


def h3_control_ready(model_root, mode: str) -> bool:
    from .workflows import DEPTH_MODEL, POSE_MODEL
    files = [model_root / "model_patches" / H3_CONTROL_PATCH]
    if mode == "pose":
        files += [model_root / "checkpoints" / POSE_MODEL, model_root / "diffusion_models" / H3_DETECTOR]
    elif mode == "depth":
        files.append(model_root / "geometry_estimation" / DEPTH_MODEL)
    return all(path.is_file() for path in files)


def h3_control_frames(graph: dict, clip: str, mode: str) -> list:
    """Turn the source clip into the control video: skeletons, edges or depth, frame by frame."""
    from .workflows import DEPTH_MODEL, POSE_MODEL
    graph["control_clip"] = {"class_type": "LoadVideo", "inputs": {"file": clip}}
    graph["control_parts"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["control_clip", 0]}}
    frames = ["control_parts", 0]
    if mode == "canny":
        graph["control_map"] = {"class_type": "Canny", "inputs": {"image": frames, "low_threshold": 0.1, "high_threshold": 0.32}}
    elif mode == "depth":
        graph.update({
            "control_depth_model": {"class_type": "LoadDA3Model", "inputs": {"model_name": DEPTH_MODEL, "weight_dtype": "default"}},
            "control_depth": {"class_type": "DA3Inference", "inputs": {
                "da3_model": ["control_depth_model", 0], "image": frames, "resolution": 504,
                "resize_method": "upper_bound_resize", "mode": "mono"}},
            "control_map": {"class_type": "DA3Render", "inputs": {
                "da3_geometry": ["control_depth", 0], "output": "depth", "output.normalization": "v2_style",
                "output.apply_sky_clip": False}},
        })
    elif mode == "pose":
        graph.update({
            "control_pose_model": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": POSE_MODEL}},
            "control_detector": {"class_type": "UNETLoader", "inputs": {"unet_name": H3_DETECTOR, "weight_dtype": "default"}},
            "control_people": {"class_type": "RTDETR_detect", "inputs": {
                "model": ["control_detector", 0], "image": frames, "threshold": 0.5, "class_name": "person", "max_detections": 2}},
            "control_keypoints": {"class_type": "SDPoseKeypointExtractor", "inputs": {
                "model": ["control_pose_model", 0], "vae": ["control_pose_model", 2], "image": frames,
                "bboxes": ["control_people", 0], "batch_size": 16}},
            "control_map": {"class_type": "SDPoseDrawKeypoints", "inputs": {
                "keypoints": ["control_keypoints", 0], "draw_body": True, "draw_hands": True, "draw_face": True,
                "draw_feet": True, "stick_width": 4, "face_point_size": 2, "score_threshold": 0.5, "draw_head": True}},
        })
    else:
        raise ValueError("unsupported video control mode")
    return ["control_map", 0]


def apply_h3_control(graph: dict, clip: str, mode: str, strength: float) -> None:
    """Route the sampled model through the Fun ControlNet-Union patch (official template: simple schedule)."""
    graph["control_patch"] = {"class_type": "ModelPatchLoader", "inputs": {"name": H3_CONTROL_PATCH}}
    graph["control"] = {"class_type": "MiniMaxH3FunControlNetApply", "inputs": {
        "model": graph["guider"]["inputs"]["model"], "model_patch": ["control_patch", 0], "vae": ["video_vae", 0],
        "strength": strength, "start_percent": 0.0, "end_percent": 1.0,
        "control_video": h3_control_frames(graph, clip, mode)}}
    graph["guider"]["inputs"]["model"] = graph["scheduler"]["inputs"]["model"] = ["control", 0]
    graph["scheduler"]["inputs"]["scheduler"] = "simple"
    graph["save"]["inputs"]["filename_prefix"] = "media_lab/h3_control"


# SCAIL-2 character replacement (Wan 2.1 14B, official Comfy template): SAM 3.1 colour-codes who is replaced,
# DPO + LightX2V step-distill LoRAs, 6 steps at CFG 1, 81-frame chunks that overlap by 5.
SCAIL_MODEL = "wan2.1_14B_SCAIL_2_int8_convrot.safetensors"
SCAIL_DPO_LORA = "wan2.1_SCAIL_2_DPO_lora_bf16.safetensors"
SCAIL_DISTILL_LORA = "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"
WAN_CLIP = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
WAN_VAE = "wan_2.1_vae.safetensors"
WAN_CLIP_VISION = "clip_vision_h.safetensors"
SCAIL_STEPS = 6
SCAIL_CHUNK, SCAIL_OVERLAP = 81, 5
SCAIL_PIXELS = 896 * 512


def scail_ready(model_root, shared_root) -> bool:
    from .workflows import ENCODER
    return all(p.is_file() for p in (
        model_root / "text_encoders" / ENCODER, model_root / "diffusion_models" / SCAIL_MODEL, model_root / "loras" / SCAIL_DPO_LORA,
        model_root / "loras" / SCAIL_DISTILL_LORA, model_root / "clip_vision" / WAN_CLIP_VISION,
        model_root / "checkpoints" / SAM_MODEL, shared_root / "text_encoders" / WAN_CLIP, shared_root / "vae" / WAN_VAE))


def scail_size(width: int, height: int) -> tuple[int, int]:
    """The source aspect ratio at SCAIL-2's 896x512 training budget, on a 32-px grid."""
    scale = (SCAIL_PIXELS / (width * height)) ** 0.5
    return max(256, round(width * scale / 32) * 32), max(256, round(height * scale / 32) * 32)


def scail_frames(frames: int) -> tuple[int, int]:
    """(chunks, frames they cover): each chunk after the first adds 76 new frames."""
    step = SCAIL_CHUNK - SCAIL_OVERLAP
    chunks = max(1, -(-(frames - SCAIL_OVERLAP) // step))
    return chunks, chunks * step + SCAIL_OVERLAP


# SCAIL-2's prompt describes the finished clip, so it must describe the new character: naming the person
# being replaced ("the man in the yellow hoodie") makes it draw that person again. Qwen3-VL writes the
# description from the reference image when no prompt is given.
SCAIL_DESCRIBE = ("Describe the person in this image for a video generation prompt, in one English sentence that starts "
                  "with 'A': apparent gender and age, skin tone, hairstyle and hair colour, and every visible piece of "
                  "clothing with its colour and footwear. Only the person, no background, no mood words.")
SCAIL_PROMPT_TAIL = (" The person moves exactly as in the original video, in the same place and with the same camera. "
                     "Realistic, natural light that matches the scene, sharp details, smooth motion.")


def scail_workflow(video: str, character: str, prompt: str, target: str, width: int, height: int,
                   frames: int, seed: int, encoder: str | None = None) -> dict:
    """video is already at width x height, 24 fps and scail_frames(frames)[1] frames long.
    An empty prompt is written from the character image by Qwen3-VL (encoder)."""
    from .workflows import ENCODER
    chunks, _ = scail_frames(frames)
    step = SCAIL_CHUNK - SCAIL_OVERLAP
    graph = {
        "unet": {"class_type": "UNETLoader", "inputs": {"unet_name": SCAIL_MODEL, "weight_dtype": "default"}},
        "dpo": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["unet", 0], "lora_name": SCAIL_DPO_LORA, "strength_model": 1.0}},
        "distill": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["dpo", 0], "lora_name": SCAIL_DISTILL_LORA, "strength_model": 0.8}},
        "shift": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["distill", 0], "shift": 5.0}},
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": WAN_CLIP, "type": "wan", "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": WAN_VAE}},
        "vision": {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": WAN_CLIP_VISION}},
        "positive": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": prompt.strip()}},
        "negative": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": ""}},
        "character": {"class_type": "LoadImage", "inputs": {"image": character}},
        "seen": {"class_type": "CLIPVisionEncode", "inputs": {"clip_vision": ["vision", 0], "image": ["character", 0], "crop": "none"}},
        "source": {"class_type": "LoadVideo", "inputs": {"file": video}},
        "parts": {"class_type": "GetVideoComponents", "inputs": {"video": ["source", 0]}},
        "sam": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": SAM_MODEL}},
        "who": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["sam", 1], "text": target.strip() or "person"}},
        "human": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["sam", 1], "text": "human"}},
        "character_track": {"class_type": "SAM3_VideoTrack", "inputs": {
            "images": ["character", 0], "model": ["sam", 0], "conditioning": ["human", 0],
            "detection_threshold": 0.5, "max_objects": 1, "detect_interval": 1}},
        "sigmas": {"class_type": "BasicScheduler", "inputs": {"model": ["distill", 0], "scheduler": "simple", "steps": SCAIL_STEPS, "denoise": 1.0}},
        "sampler": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
    }
    if not prompt.strip():
        graph.update({
            "describer": {"class_type": "CLIPLoader", "inputs": {"clip_name": encoder or ENCODER, "type": "qwen_image", "device": "default"}},
            "description": {"class_type": "TextGenerate", "inputs": {
                "clip": ["describer", 0], "image": ["character", 0], "prompt": SCAIL_DESCRIBE, "max_length": 160,
                "sampling_mode": "off", "thinking": False, "use_default_template": True}},
            "prompt": {"class_type": "StringConcatenate", "inputs": {
                "string_a": ["description", 0], "string_b": SCAIL_PROMPT_TAIL, "delimiter": ""}},
        })
        graph["positive"]["inputs"]["text"] = ["prompt", 0]
    result = last = None
    for i in range(chunks):
        n = f"_{i}"
        graph.update({
            "pose" + n: {"class_type": "ImageFromBatch", "inputs": {"image": ["parts", 0], "batch_index": step * i, "length": SCAIL_CHUNK}},
            "track" + n: {"class_type": "SAM3_VideoTrack", "inputs": {
                "images": ["pose" + n, 0], "model": ["sam", 0], "conditioning": ["who", 0],
                "detection_threshold": 0.5, "max_objects": 1, "detect_interval": 1}},
            "masks" + n: {"class_type": "SCAIL2ColoredMask", "inputs": {
                "driving_track_data": ["track" + n, 0], "ref_track_data": ["character_track", 0],
                "object_indices": "", "sort_by": "left_to_right", "replacement_mode": True}},
            "scail" + n: {"class_type": "WanSCAILToVideo", "inputs": {
                "positive": ["positive", 0], "negative": ["negative", 0], "vae": ["vae", 0],
                "width": width, "height": height, "length": SCAIL_CHUNK, "batch_size": 1,
                "pose_strength": 1.0, "pose_start": 0.0, "pose_end": 1.0, "video_frame_offset": 0,
                "previous_frame_count": SCAIL_OVERLAP, "replacement_mode": True,
                "pose_video": ["pose" + n, 0], "pose_video_mask": ["masks" + n, 0],
                "reference_image": ["character", 0], "reference_image_mask": ["masks" + n, 1],
                "clip_vision_output": ["seen", 0]}},
            "sample" + n: {"class_type": "SamplerCustom", "inputs": {
                "model": ["shift", 0], "add_noise": True, "noise_seed": seed, "cfg": 1.0,
                "positive": ["scail" + n, 0], "negative": ["scail" + n, 1], "sampler": ["sampler", 0],
                "sigmas": ["sigmas", 0], "latent_image": ["scail" + n, 2]}},
            "decode" + n: {"class_type": "VAEDecode", "inputs": {"samples": ["sample" + n, 1], "vae": ["vae", 0]}},
        })
        if not i:
            result = last = ["decode" + n, 0]
            continue
        # Later chunks anchor on the previous chunk's tail, drop the 5 shared frames and match its colours.
        graph["scail" + n]["inputs"]["previous_frames"] = last
        graph.update({
            "fresh" + n: {"class_type": "ImageFromBatch", "inputs": {"image": ["decode" + n, 0], "batch_index": SCAIL_OVERLAP, "length": 4096}},
            "anchor" + n: {"class_type": "ImageFromBatch", "inputs": {"image": last, "batch_index": -1, "length": 1}},
            "graded" + n: {"class_type": "ColorTransfer", "inputs": {
                "image_target": ["fresh" + n, 0], "image_ref": ["anchor" + n, 0], "method": "reinhard_lab",
                "source_stats": "per_frame", "strength": 1.0}},
            "joined" + n: {"class_type": "ImageBatch", "inputs": {"image1": result, "image2": ["graded" + n, 0]}},
        })
        last, result = ["graded" + n, 0], ["joined" + n, 0]
    graph.update({
        "video": {"class_type": "CreateVideo", "inputs": {"images": result, "fps": 24}},
        "save": {"class_type": "SaveVideo", "inputs": {"video": ["video", 0], "filename_prefix": "media_lab/scail2",
                                                       "format": "mp4", "format.codec": "h264"}},
    })
    return graph


def yue2_workflow(style: str, lyrics: str, mode: str, abc: str, duration: float,
                  steps: int, seed: int, source_audio: str | None = None, options=None) -> dict:
    if mode not in {"direct", "full", "melody"}:
        raise ValueError("unsupported YuE2 mode")
    if source_audio and mode == "direct":
        raise ValueError("cover needs melody or full planning")
    graph = {
        "model": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": YUE2}},
        "music": {"class_type": "YuE2GenerateMusic", "inputs": {
            "clip": ["model", 1], "style": style, "lyrics": lyrics, "abc": abc,
            "seed": seed, "mode": "full" if mode == "direct" else mode,
            "max_duration": duration, "temperature": 1.0, "top_p": 0.95,
            "top_k": 100, "repetition_penalty": 1.2}},
        "negative": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["music", 0]}},
        "latent": {"class_type": "EmptyYuE2LatentAudio", "inputs": {
            "seconds": ["music", 1], "batch_size": 1}},
        "sample": {"class_type": "KSampler", "inputs": {
            "model": ["model", 0], "positive": ["music", 0], "negative": ["negative", 0],
            "latent_image": ["latent", 0], "seed": seed, "steps": steps,
            "cfg": 1.0, "sampler_name": "dpm_2", "scheduler": "sgm_uniform", "denoise": 1.0}},
        "decode": {"class_type": "VAEDecodeAudio", "inputs": {
            "samples": ["sample", 0], "vae": ["model", 2]}},
        "save": {"class_type": "SaveAudioAdvanced", "inputs": {
            "audio": ["decode", 0], "filename_prefix": "media_lab/yue2", "format": "flac"}},
    }
    if source_audio:
        graph["sheet_model"] = {"class_type": "AudioEncoderLoader", "inputs": {
            "audio_encoder_name": SHEETSAGE}}
        graph["source"] = {"class_type": "LoadAudio", "inputs": {"audio": source_audio}}
        graph["abc"] = {"class_type": "SheetSage2AudioToABC", "inputs": {
            "audio_encoder": ["sheet_model", 0], "audio": ["source", 0], "mode": mode}}
        graph["music"]["inputs"]["abc"] = ["abc", 0]
    elif mode != "direct" and not abc:
        graph["abc"] = {"class_type": "YuE2GenerateABC", "inputs": {
            "clip": ["model", 1], "style": style, "lyrics": lyrics, "seed": seed,
            "mode": mode, "max_abc_tokens": 8192, "temperature": 0.7,
            "top_p": 0.9, "top_k": 30, "repetition_penalty": 1.005,
            "penalty_window": 100}}
        graph["music"]["inputs"]["abc"] = ["abc", 0]
    if "abc" in graph:
        graph["save_abc"] = {"class_type": "SaveText", "inputs": {
            "text": ["abc", 0], "filename_prefix": "media_lab/yue2_score", "format": "txt"}}
    if options:
        if options.composition:
            graph['music']['inputs'].update(options.composition.values())
        if options.score and 'abc' in graph and graph['abc']['class_type'] == 'YuE2GenerateABC':
            graph['abc']['inputs'].update(options.score.values())
        for key in ('cfg', 'scheduler', 'denoise'):
            if getattr(options, key) is not None:
                graph['sample']['inputs'][key] = getattr(options, key)
        if options.sampler is not None:
            graph['sample']['inputs']['sampler_name'] = options.sampler
        graph['save']['inputs']['format'] = options.format
        if options.format != 'flac':
            graph['save']['inputs']['format.quality'] = options.audio_quality or ('V0' if options.format == 'mp3' else '128k')
    return graph


# H3 Character Swap (akatz-ai, MiniMax H3 Community License): the source clip is <Video 1>, the
# character is <Picture 1>. Tested recipe from the model card: Ref2VA int8 base + swap V1.5 at 1.0
# + FL2V Turbo 8-step 768p at 1.0, 8 steps, CFG 1, er_sde / normal, shift 12 / 3.
SWAP_LORA = "h3_character_swap_v1.5.safetensors"
SWAP_LORA_SHA256 = "8f2c3c3eba161df8d0c6099598b4730f641f5ce01e04cd16d2427cff8a35218f"
SWAP_TURBO = "minimax_h3_fl2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors"
SWAP_TURBO_SHA256 = "08cfe946033af7d27719b964b6e0a0e50c32138daabbd6ce4137e23df6bf9980"
SWAP_STEPS = 8
SWAP_PIXELS = 864 * 480  # 480p: at 1376x768 one 8-step swap took 29 min on a 3090 (218 s/step)


def swap_ready(model_root, h3_root) -> bool:
    return all(p.is_file() for p in (model_root / "loras" / SWAP_LORA, model_root / "loras" / SWAP_TURBO,
                                     h3_root / "diffusion_models" / H3_REF, h3_root / "text_encoders" / H3_CLIP))


def swap_size(width: int, height: int) -> tuple[int, int]:
    """Keep the source aspect ratio at the 768p pixel budget, on H3's 32-px grid."""
    scale = (SWAP_PIXELS / (width * height)) ** 0.5
    return max(256, round(width * scale / 32) * 32), max(256, round(height * scale / 32) * 32)


def swap_prompt(target: str = "") -> str:
    who = target.strip() or "the main person"
    return (f"Replace {who} in <Video 1> with the character in <Picture 1>. Keep the reference character's face, "
            "hair, clothing and art style from <Picture 1>. Follow the source performance's pose, gaze, expression, "
            "lip movement and timing. Preserve the scene, the camera, the lighting and the other people.")


def swap_workflow(prompt: str, width: int, height: int, seconds: float, seed: int,
                  video: str, character: str, soundtrack: bool) -> dict:
    graph = h3_workflow(prompt, "r2v", width, height, seconds, SWAP_STEPS, seed,
                        references=[character], reference_videos=[video], video_soundtracks=[soundtrack])
    graph["turbo"] = {"class_type": "LoraLoaderModelOnly", "inputs": {
        "model": ["unet", 0], "lora_name": SWAP_TURBO, "strength_model": 1.0}}
    graph["swap"] = {"class_type": "LoraLoaderModelOnly", "inputs": {
        "model": ["turbo", 0], "lora_name": SWAP_LORA, "strength_model": 1.0}}
    graph["shift"] = {"class_type": "MiniMaxH3SigmaShift", "inputs": {
        "model": ["swap", 0], "shift_video": 12.0, "shift_audio": 3.0}}
    graph["scheduler"]["inputs"].update({"model": ["shift", 0], "scheduler": "normal", "steps": SWAP_STEPS})
    graph["guider"]["inputs"]["model"] = ["shift", 0]
    graph["sampler"]["inputs"]["sampler_name"] = "er_sde"
    graph["save"]["inputs"]["filename_prefix"] = "media_lab/swap"
    return graph



# Head Swap v1.0 (Alissonerdx, experimental; not covered by that repo's BFS Character Swap license).
# Recipe from its workflow: Ref2VA int8 base, shift 12 / 3, Taomate 3-step LoRA + head swap LoRA at
# 1.0, euler / beta 8 steps, CFG 1. The face is the native <Picture 1> reference; the complete
# source clip is an aligned guide at frame 0 (never the video-reference channel).
HEAD_LORA = "minimax_h3_head_swap_v1.0_r32.safetensors"
HEAD_LORA_SHA256 = "ea97bd1a8178460661055784d63b4cb560732196fd15d5d7f33bfd214b65ab00"
HEAD_TURBO = "minimax_h3_taomate_3step_lora_avg_rank_19_bf16.safetensors"
HEAD_TURBO_SHA256 = "de9663d974a884b477556748239c6f28239f7ca1825be270f98f023ff5dab6a7"
HEAD_STEPS = 8
HEAD_FACE_SIZE = 256  # the workflow pads the face to this square before the reference encoder
HEAD_DETAILS_QUESTION = (
    'Describe this face in a short comma-separated attribute list, in exactly this style: "Male, oval face shape, '
    'average-sized head with strong jawline, light brown skin, dark eyes, black tousled hair, silver hoop earring." '
    "Cover, in order: gender, head/face shape and proportions (e.g. oval/round/square/heart-shaped, narrow/wide, jaw "
    "structure, whether the head reads as small/average/large relative to the shoulders), skin tone, eye color, hair "
    "color and style, and any distinctive features (facial hair, jewelry, makeup, glasses, etc.). Only output the "
    "description, nothing else.")
HEAD_PROMPT_HEAD = """head_swap:

subject_definitions:

<Subject 1> is the reference head identity from <Picture 1>, including the complete head, facial identity, facial structure, head shape, hairstyle, hairline, skin appearance, proportions, and all distinctive visual features.

Facial details of <Subject 1>:
"""
HEAD_PROMPT_TAIL = """

<Subject 2> is {who} in <Video 1>, whose body, neck, clothing, pose, physical proportions below the head, actions, motion, timing, and interaction with the environment must remain unchanged.

<Video 1> is the source video for the target video edit, providing the original body performance, motion, camera movement, framing, timing, lighting, environment, scene composition, and temporal structure.

summary:

[video editing + reference generation]

The target video is an edited version of <Video 1>. Replace only the entire head of <Subject 2> with the reference head identity defined by <Subject 1> from <Picture 1>. Preserve the source video's body, clothing, performance, motion, camera behavior, environment, lighting, timing, and composition.

retention_analysis:

<Subject 1> (appears throughout the target video): attribute_transfer - the complete head identity from <Picture 1>, including facial identity, facial structure, hairstyle, head shape, proportions, skin appearance, and distinctive features, is transferred consistently onto the body of <Subject 2>.

<Subject 2> (appears throughout the target video): partially_preserved - the original body, neck position, clothing, pose, motion, gestures, actions, and physical performance are preserved, while only the original head is replaced.

<Video 1> (entire target timeline): partially_preserved - the original video timing, body motion, camera movement, framing, lighting, background, environment, scene composition, and temporal structure are preserved; only the subject's head appearance is modified.

detailed_description:

Preserve <Video 1> as the complete temporal and compositional foundation of the target video. <Subject 2> retains the exact original body, clothing, pose, body proportions, movement, gestures, actions, speed, timing, and interaction with the environment.

Replace only the entire original head of <Subject 2> with <Subject 1>, the reference head identity from <Picture 1>. Preserve the complete recognizable identity of <Subject 1>, including facial structure, skull and head shape, hairstyle, hairline, skin appearance, facial proportions, eyes, eyebrows, nose, mouth, jawline, ears, and distinctive identifying features.

The transferred head follows the original head motion and performance of <Subject 2> throughout <Video 1>, including head rotation, tilt, pitch, yaw, natural translation, facial orientation, gaze direction, and perspective changes. Maintain anatomically correct head scale and a seamless connection between the transferred head and the original neck.

Preserve the lighting conditions of <Video 1> on the transferred head. The head naturally responds to changes in illumination, shadows, highlights, color temperature, exposure, depth of field, motion blur, occlusion, camera angle, and perspective while continuously maintaining the identity established by <Picture 1>.

Maintain strong temporal consistency across every frame. The identity, facial geometry, hairstyle, head size, skin appearance, and distinguishing features of <Subject 1> remain stable during motion and viewpoint changes. Prevent identity drift, facial morphing, hairstyle changes, head-size fluctuations, geometry instability, texture crawling, temporal flickering, frame-to-frame inconsistency, or sudden changes in facial appearance.

Do not alter the body, clothing, hands, pose, gestures, action, background, objects, environment, camera trajectory, framing, lens behavior, scene timing, or composition inherited from <Video 1>. The final result should appear as though <Subject 1>'s head naturally belonged to <Subject 2>'s body during the original recorded performance.

overall_soundscape:

Preserve the original audiovisual timing and visible action structure of <Video 1>. No visual modifications are made outside the head replacement.

non_diegetic_music:
N/A"""


def head_swap_ready(model_root, h3_root) -> bool:
    return all(p.is_file() for p in (model_root / "loras" / HEAD_LORA, model_root / "loras" / HEAD_TURBO,
                                     h3_root / "diffusion_models" / H3_REF, h3_root / "text_encoders" / H3_CLIP))


def head_swap_workflow(width: int, height: int, seconds: float, seed: int, video: str, face: str,
                       soundtrack: bool, target: str = "", details: str = "") -> dict:
    """`details` describes the new face; when empty the H3 Qwen3-VL encoder writes it from the image."""
    graph = h3_workflow("", "r2v", width, height, seconds, HEAD_STEPS, seed, references=[face])
    graph["shift"] = {"class_type": "MiniMaxH3SigmaShift", "inputs": {
        "model": ["unet", 0], "shift_video": 12.0, "shift_audio": 3.0}}
    graph["turbo"] = {"class_type": "LoraLoaderModelOnly", "inputs": {
        "model": ["shift", 0], "lora_name": HEAD_TURBO, "strength_model": 1.0}}
    graph["head"] = {"class_type": "LoraLoaderModelOnly", "inputs": {
        "model": ["turbo", 0], "lora_name": HEAD_LORA, "strength_model": 1.0}}
    graph["scheduler"]["inputs"].update({"model": ["head", 0], "scheduler": "beta", "steps": HEAD_STEPS})
    graph["sampler"]["inputs"]["sampler_name"] = "euler"
    tail = HEAD_PROMPT_TAIL.format(who=target.strip() or "the original person")
    if details.strip():
        graph["condition"]["inputs"]["prompt"] = HEAD_PROMPT_HEAD + details.strip() + tail
    else:
        graph["details"] = {"class_type": "TextGenerate", "inputs": {
            "clip": ["clip", 0], "image": ["ref_0", 0], "prompt": HEAD_DETAILS_QUESTION, "max_length": 512,
            "sampling_mode": "off", "thinking": False, "use_default_template": True}}
        graph["prompt_head"] = {"class_type": "StringConcatenate", "inputs": {
            "string_a": HEAD_PROMPT_HEAD, "string_b": ["details", 0], "delimiter": ""}}
        graph["prompt"] = {"class_type": "StringConcatenate", "inputs": {
            "string_a": ["prompt_head", 0], "string_b": tail, "delimiter": ""}}
        graph["condition"]["inputs"]["prompt"] = ["prompt", 0]
    graph["source"] = {"class_type": "LoadVideo", "inputs": {"file": video}}
    graph["source_parts"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["source", 0]}}
    guide = {"positive": ["condition", 0], "latent": ["condition", 1], "frame_idx": 0,
             "vae": ["video_vae", 0], "image": ["source_parts", 0]}
    if soundtrack:
        guide.update({"audio_vae": ["audio_vae", 0], "audio": ["source_parts", 1]})
    graph["guide"] = {"class_type": "MiniMaxH3AddGuide", "inputs": guide}
    graph["guider"]["inputs"].update({"model": ["head", 0], "conditioning": ["guide", 0]})
    graph["save"]["inputs"]["filename_prefix"] = "media_lab/head_swap"
    return graph


# Person removal (Akatz H3 Person Remover V1 LoRA): SAM 3.1 tracks the person and paints them green, then
# Ref2VA + LoRA regenerates the clip from that green video (<Video 1>) and a clean first frame (<Picture 1>,
# also guided at frame 0). Author settings: LoRA 1.0, er_sde / simple, 12 steps, CFG 1, shift 12/3, mask grown
# 5 px. One pass over the whole clip (the LoRA trained on 5–124 frames) instead of Relay's 22-frame windows,
# whose history anchors need a patched guide engine. The original soundtrack is kept.
REMOVER_LORA = "H3-Person-Remover-V1.safetensors"
SAM_MODEL = "sam3.1_multiplex_fp16.safetensors"
REMOVER_STEPS = 12
REMOVER_PROMPT = ("Remove the green-masked person and reconstruct the background. Preserve the rest of the video, "
                  "including its camera motion and frame timing.")
REMOVER_GREEN = 0x00FF00
CLEAN_FRAME_PROMPT = ("Remove the bright green silhouette completely and fill that area with the background that would "
                      "naturally be behind it, continuing the surrounding walls, floor, furniture and lighting. Keep "
                      "everything else exactly the same: framing, colors and every other object.")


def remover_ready(model_root, h3_root) -> bool:
    return all(p.is_file() for p in (model_root / "loras" / REMOVER_LORA, model_root / "checkpoints" / SAM_MODEL,
                                     h3_root / "diffusion_models" / H3_REF, h3_root / "text_encoders" / H3_CLIP))


def remover_mask_workflow(video: str, target: str) -> dict:
    """Green-out the tracked person; the saved clip keeps the source soundtrack."""
    return {
        "source": {"class_type": "LoadVideo", "inputs": {"file": video}},
        "parts": {"class_type": "GetVideoComponents", "inputs": {"video": ["source", 0]}},
        "size": {"class_type": "GetImageSize", "inputs": {"image": ["parts", 0]}},
        "sam": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": SAM_MODEL}},
        "subject": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["sam", 1], "text": target.strip() or "person"}},
        "first": {"class_type": "ImageFromBatch", "inputs": {"image": ["parts", 0], "batch_index": 0, "length": 1}},
        "detect": {"class_type": "SAM3_Detect", "inputs": {
            "model": ["sam", 0], "image": ["first", 0], "conditioning": ["subject", 0], "threshold": 0.4,
            "refine_iterations": 2, "individual_masks": False}},
        "track": {"class_type": "SAM3_VideoTrack", "inputs": {
            "model": ["sam", 0], "images": ["parts", 0], "initial_mask": ["detect", 0], "conditioning": ["subject", 0],
            "detection_threshold": 0.5, "max_objects": 1, "detect_interval": 12}},
        "mask": {"class_type": "SAM3_TrackToMask", "inputs": {"track_data": ["track", 0], "object_indices": ""}},
        "binary": {"class_type": "ThresholdMask", "inputs": {"mask": ["mask", 0], "value": 0.5}},
        "grow": {"class_type": "GrowMask", "inputs": {"mask": ["binary", 0], "expand": 5, "tapered_corners": False}},
        "green": {"class_type": "EmptyImage", "inputs": {
            "width": ["size", 0], "height": ["size", 1], "batch_size": 1, "color": REMOVER_GREEN}},
        "masked": {"class_type": "ImageCompositeMasked", "inputs": {
            "destination": ["parts", 0], "source": ["green", 0], "mask": ["grow", 0], "x": 0, "y": 0,
            "resize_source": False}},
        "video": {"class_type": "CreateVideo", "inputs": {"images": ["masked", 0], "audio": ["parts", 1], "fps": 24}},
        "save": {"class_type": "SaveVideo", "inputs": {
            "video": ["video", 0], "filename_prefix": "media_lab/remover_mask", "format": "mp4", "format.codec": "h264",
            "format.codec.encoding": "re-encode", "format.codec.encoding.crf": 12}},
    }


def remover_workflow(width: int, height: int, frames: int, seed: int, green: str, clean: str, soundtrack: bool) -> dict:
    """`green` is the masked clip on H3's 17n+5 grid; `clean` its first frame with the person removed."""
    graph = h3_workflow(REMOVER_PROMPT, "r2v", width, height, frames / 24, REMOVER_STEPS, seed, references=[clean])
    graph["condition"]["inputs"]["length"] = frames
    graph["green_video"] = {"class_type": "LoadVideo", "inputs": {"file": green}}
    graph["green_parts"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["green_video", 0]}}
    graph["condition"]["inputs"]["ref_videos.ref_video_0"] = ["green_parts", 0]
    graph["shift"] = {"class_type": "MiniMaxH3SigmaShift", "inputs": {
        "model": ["unet", 0], "shift_video": 12.0, "shift_audio": 3.0}}
    graph["remover"] = {"class_type": "LoraLoaderModelOnly", "inputs": {
        "model": ["shift", 0], "lora_name": REMOVER_LORA, "strength_model": 1.0}}
    graph["scheduler"]["inputs"].update({"model": ["remover", 0], "scheduler": "simple"})
    graph["sampler"]["inputs"]["sampler_name"] = "er_sde"
    graph["guide"] = {"class_type": "MiniMaxH3AddGuide", "inputs": {
        "positive": ["condition", 0], "latent": ["condition", 1], "frame_idx": 0, "vae": ["video_vae", 0],
        "image": ["ref_0", 0]}}
    graph["guider"]["inputs"].update({"model": ["remover", 0], "conditioning": ["guide", 0]})
    if soundtrack:
        # The source soundtrack (the removed person's voice included); silent clips keep H3's own ambience.
        graph["video"]["inputs"]["audio"] = ["green_parts", 1]
    graph["save"]["inputs"]["filename_prefix"] = "media_lab/person_removal"
    return graph


# Face refine: re-diffuse a square face window (see face_refine.py) with Ref2VA + Taomate from a
# partial noise level, <Picture 1> holding identity. No AddGuide: tested, anchoring the (blurry)
# window pinned the result to its blur; the noised window latent alone keeps pose and expression.
# Strengths follow the Taomate schedule tail; at 0.8 expressions start to drift.
FACE_STRENGTHS = {"light": "0.4737, 0.2368, 0.0000", "medium": "0.6316, 0.3158, 0.0000",
                  "strong": "0.8000, 0.5500, 0.3000, 0.0000"}
FACE_PROMPT = ("A close-up of the face from <Picture 1>, matching <Video 1> exactly: the same person, head motion, "
               "expression, mouth and eye movement, framing, lighting and colors. Sharp natural detail: clear eyes and "
               "irises, defined eyelids and brows, natural skin texture, clean teeth and lips, individual hair strands. "
               "No identity change, no new objects.")


def face_refine_ready(model_root, h3_root) -> bool:
    return all(p.is_file() for p in (model_root / "detection" / "mediapipe_face_fp32.safetensors",
                                     model_root / "loras" / HEAD_TURBO, h3_root / "diffusion_models" / H3_REF,
                                     h3_root / "text_encoders" / H3_CLIP))


def face_detect_workflow(video: str) -> dict:
    return {
        "load": {"class_type": "LoadVideo", "inputs": {"file": video}},
        "parts": {"class_type": "GetVideoComponents", "inputs": {"video": ["load", 0]}},
        "model": {"class_type": "LoadMediaPipeFaceLandmarker", "inputs": {"model_name": "mediapipe_face_fp32.safetensors"}},
        "faces": {"class_type": "MediaPipeFaceLandmarker", "inputs": {
            "face_detection_model": ["model", 0], "image": ["parts", 0], "detector_variant": "both", "num_faces": 1,
            "min_confidence": 0.4, "missing_frame_fallback": "interpolate"}},
        "boxes": {"class_type": "PreviewAny", "inputs": {"source": ["faces", 1]}},
    }


def face_refine_workflow(window: str, identity: str, size: int, frames: int, seed: int, strength: str = "medium") -> dict:
    """`window` is the face crop clip (size×size, 24 fps, `frames` on H3's 17n+5 grid)."""
    graph = h3_workflow(FACE_PROMPT, "r2v", size, size, frames / 24, HEAD_STEPS, seed, references=[identity])
    graph["condition"]["inputs"]["length"] = frames
    graph["shift"] = {"class_type": "MiniMaxH3SigmaShift", "inputs": {
        "model": ["unet", 0], "shift_video": 12.0, "shift_audio": 3.0}}
    graph["turbo"] = {"class_type": "LoraLoaderModelOnly", "inputs": {
        "model": ["shift", 0], "lora_name": HEAD_TURBO, "strength_model": 1.0}}
    graph["source"] = {"class_type": "LoadVideo", "inputs": {"file": window}}
    graph["source_parts"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["source", 0]}}
    graph["encode"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["source_parts", 0], "vae": ["video_vae", 0]}}
    graph["av_parts"] = {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["condition", 1]}}
    graph["start"] = {"class_type": "LTXVConcatAVLatent", "inputs": {
        "video_latent": ["encode", 0], "audio_latent": ["av_parts", 1]}}
    graph["guider"]["inputs"]["model"] = ["turbo", 0]
    del graph["scheduler"]
    graph["sigmas"] = {"class_type": "ManualSigmas", "inputs": {"sigmas": FACE_STRENGTHS[strength]}}
    graph["sampler"]["inputs"]["sampler_name"] = "euler"
    graph["sample"]["inputs"].update({"sigmas": ["sigmas", 0], "latent_image": ["start", 0]})
    # Silent face window: the runtime pastes it back under the original soundtrack.
    del graph["decode_audio"]
    del graph["video"]["inputs"]["audio"]
    graph["save"]["inputs"]["filename_prefix"] = "media_lab/face_refine"
    return graph


# ACE-Step 1.5 XL Turbo (Apache-2.0): the official ComfyUI template — DualCLIP 0.6B + 4B "ace",
# the 4B planner writes audio codes, AuraFlow shift 3, euler / simple, 8 steps, CFG 1 with a zeroed
# negative. Song length is set exactly (YuE2 treats it as an upper bound).
ACE_DIT = "acestep_v1.5_xl_turbo_bf16.safetensors"
ACE_CLIPS = ("qwen_0.6b_ace15.safetensors", "qwen_4b_ace15.safetensors")
ACE_VAE = "ace_1.5_vae.safetensors"
ACE_STEPS = 8
ACE_SECONDS = (10, 600)
ACE_KEYS = [f"{note} {scale}" for scale in ("major", "minor") for note in
            ("C", "C#", "Db", "D", "D#", "Eb", "E", "F", "F#", "Gb", "G", "G#", "Ab", "A", "A#", "Bb", "B")]
SPANISH = re.compile(r"[ñ¿¡áéíóú]|\b(que|el|la|los|las|por|para|con|una|mi|tu|corazón|quiero|eres|amor|noche)\b", re.I)


def ace_ready(model_root) -> bool:
    return all(p.is_file() for p in (model_root / "diffusion_models" / ACE_DIT, model_root / "vae" / ACE_VAE,
                                     *(model_root / "text_encoders" / name for name in ACE_CLIPS)))


def ace_language(lyrics: str) -> str:
    """The lyric language the 4B planner should sing in; our users write mostly Spanish or English."""
    words = re.sub(r"\[[^\]]*\]", " ", lyrics)
    if not words.strip():
        return "en"
    return "es" if len(SPANISH.findall(words)) >= max(2, len(words.split()) // 25) else "en"


def ace_tempo(style: str) -> tuple[int, str]:
    """BPM and key named in the style tags (e.g. "95 BPM, E minor"), else a neutral 110 BPM in C major."""
    bpm = re.search(r"\b(\d{2,3})\s*bpm\b", style, re.I)
    key = re.search(r"\b([A-G][#b]?)\s*(major|minor|mayor|menor)\b", style, re.I)
    note = key and key.group(1)[0].upper() + key.group(1)[1:]
    scale = key and {"mayor": "major", "menor": "minor"}.get(key.group(2).lower(), key.group(2).lower())
    named = f"{note} {scale}" if key else ""
    return (min(240, max(40, int(bpm.group(1)))) if bpm else 110), (named if named in ACE_KEYS else "C major")


def ace_step_workflow(style: str, lyrics: str, seconds: float, seed: int, bpm: int, key: str, language: str,
                      fmt: str = "flac", quality: str | None = None) -> dict:
    graph = {
        "unet": {"class_type": "UNETLoader", "inputs": {"unet_name": ACE_DIT, "weight_dtype": "default"}},
        "clip": {"class_type": "DualCLIPLoader", "inputs": {
            "clip_name1": ACE_CLIPS[0], "clip_name2": ACE_CLIPS[1], "type": "ace", "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": ACE_VAE}},
        "shift": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["unet", 0], "shift": 3.0}},
        "music": {"class_type": "TextEncodeAceStepAudio1.5", "inputs": {
            "clip": ["clip", 0], "tags": style, "lyrics": lyrics, "seed": seed, "bpm": bpm, "duration": seconds,
            "timesignature": "4", "language": language, "keyscale": key, "generate_audio_codes": True,
            "cfg_scale": 2.0, "temperature": 0.85, "top_p": 0.9, "top_k": 0, "min_p": 0.0}},
        "negative": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["music", 0]}},
        "latent": {"class_type": "EmptyAceStep1.5LatentAudio", "inputs": {"seconds": seconds, "batch_size": 1}},
        "sample": {"class_type": "KSampler", "inputs": {
            "model": ["shift", 0], "positive": ["music", 0], "negative": ["negative", 0], "latent_image": ["latent", 0],
            "seed": seed, "steps": ACE_STEPS, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
        "decode": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["sample", 0], "vae": ["vae", 0]}},
        "save": {"class_type": "SaveAudioAdvanced", "inputs": {
            "audio": ["decode", 0], "filename_prefix": "media_lab/ace_step", "format": fmt}},
    }
    if fmt != "flac":
        graph["save"]["inputs"]["format.quality"] = quality or ("V0" if fmt == "mp3" else "128k")
    return graph


# Hybrid Demucs (torchaudio's HDEMUCS_HIGH_MUSDB_PLUS weights) through the in-house MediaLabStems node.
STEMS_MODEL = "hdemucs_high_trained.pt"
STEM_OUTPUTS = ("vocals", "instrumental", "drums", "bass", "other")
STEMS = {"two": ("vocals", "instrumental"), "four": ("vocals", "drums", "bass", "other")}


def stems_ready(model_root) -> bool:
    return (model_root / "stems" / STEMS_MODEL).is_file()


def stems_workflow(audio: str, mode: str, fmt: str = "flac") -> dict:
    """Split one song; there is a save node per requested stem, named save_<stem>."""
    graph = {"load": {"class_type": "LoadAudio", "inputs": {"audio": audio}},
             "split": {"class_type": "MediaLabStems", "inputs": {"audio": ["load", 0]}}}
    for name in STEMS[mode]:
        graph[f"save_{name}"] = {"class_type": "SaveAudioAdvanced", "inputs": {
            "audio": ["split", STEM_OUTPUTS.index(name)], "filename_prefix": f"media_lab/stems_{name}", "format": fmt}}
        if fmt == "mp3":
            graph[f"save_{name}"]["inputs"]["format.quality"] = "V0"
    return graph


# Qwen3-TTS 12Hz 1.7B (Qwen, Apache-2.0) through the in-house MediaLabSpeech node: CustomVoice
# (nine preset voices, optional delivery instruction), VoiceDesign (a voice described in words) and
# Base (clones a reference clip: only voices used with their owner's permission).
TTS_CHECKPOINTS = {"preset": "Qwen3-TTS-12Hz-1.7B-CustomVoice", "design": "Qwen3-TTS-12Hz-1.7B-VoiceDesign",
                   "clone": "Qwen3-TTS-12Hz-1.7B-Base"}
TTS_SPEAKERS = ("serena", "vivian", "uncle_fu", "ryan", "aiden", "ono_anna", "sohee", "eric", "dylan")
TTS_LANGUAGES = ("auto", "spanish", "english", "portuguese", "french", "german", "italian", "japanese", "korean",
                 "chinese", "russian")
TTS_REFERENCE_SECONDS = (3, 30)


def tts_ready(model_root, voice: str = "preset") -> bool:
    folder = model_root / "tts" / TTS_CHECKPOINTS[voice]
    return all((folder / name).is_file() for name in ("model.safetensors", "config.json", "speech_tokenizer/model.safetensors"))


def speech_workflow(text: str, voice: str, language: str, speaker: str, instruct: str, seed: int,
                    reference: str | None = None, reference_text: str = "", fmt: str = "flac") -> dict:
    graph = {"speak": {"class_type": "MediaLabSpeech", "inputs": {
        "text": text, "voice": voice, "language": language, "speaker": speaker, "instruct": instruct,
        "seed": seed, "reference_text": reference_text}}}
    if voice == "clone":
        graph["reference"] = {"class_type": "LoadAudio", "inputs": {"audio": reference}}
        graph["speak"]["inputs"]["reference"] = ["reference", 0]
    graph["save"] = {"class_type": "SaveAudioAdvanced", "inputs": {
        "audio": ["speak", 0], "filename_prefix": f"media_lab/speech_{voice}", "format": fmt}}
    if fmt == "mp3":
        graph["save"]["inputs"]["format.quality"] = "V0"
    return graph


# Stable Audio 3 (Stability AI Community License): the official ComfyUI template. Medium makes
# instrumental music (up to 6:20) and Small SFX makes sound effects; both are the post-trained
# checkpoints (8 steps, CFG 1, lcm / simple) with the T5Gemma "stable_audio" encoder. The template
# first lets Qwen3.5 2B rewrite the idea with a category-aware system prompt; that rewrite is kept.
SA3_CHECKPOINTS = {"medium": "stable_audio_3_medium.safetensors", "small_sfx": "stable_audio_3_small_sfx.safetensors"}
SA3_ENCODER = "t5gemma_b_b_ul2.safetensors"
SA3_REWRITER = "qwen3.5_2b_bf16.safetensors"
SA3_STEPS = 8
# kind -> (checkpoint, template category, seconds range)
SA3_KINDS = {"music": ("medium", "Music", (5, 380)), "instrument": ("medium", "Instrument", (2, 380)),
             "sfx": ("small_sfx", "SFX", (1, 120)), "one_shot": ("small_sfx", "One-shot", (0.5, 10))}


def sa3_ready(model_root, kind: str = "music") -> bool:
    return all(p.is_file() for p in (model_root / "checkpoints" / SA3_CHECKPOINTS[SA3_KINDS[kind][0]],
                                     model_root / "text_encoders" / SA3_ENCODER, model_root / "text_encoders" / SA3_REWRITER))


def sa3_workflow(prompt: str, kind: str, seconds: float, seed: int, enhance: bool = True, fmt: str = "flac") -> dict:
    from .upsamplers import SA3_SYSTEM, SA3_TEMPLATE
    checkpoint, category, _ = SA3_KINDS[kind]
    graph = {
        "ckpt": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": SA3_CHECKPOINTS[checkpoint]}},
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": SA3_ENCODER, "type": "stable_audio", "device": "default"}},
    }
    text: str | list = prompt.strip()
    if enhance:
        graph["rw_clip"] = {"class_type": "CLIPLoader", "inputs": {"clip_name": SA3_REWRITER, "type": "stable_diffusion", "device": "default"}}
        graph["rewrite"] = {"class_type": "TextGenerate", "inputs": {
            "clip": ["rw_clip", 0], "max_length": 256, "thinking": False, "use_default_template": True,
            "prompt": SA3_TEMPLATE.format(system=SA3_SYSTEM[category], idea=prompt.strip(), seconds=f"{seconds:g}"),
            "sampling_mode": "on", "sampling_mode.temperature": 0.7, "sampling_mode.top_k": 64, "sampling_mode.top_p": 0.95,
            "sampling_mode.min_p": 0.05, "sampling_mode.repetition_penalty": 1.05, "sampling_mode.seed": seed % 2**64,
            "sampling_mode.presence_penalty": 0.0}}
        graph["caption"] = {"class_type": "PreviewAny", "inputs": {"source": ["rewrite", 0]}}
        text = ["rewrite", 0]
    graph.update({
        "positive": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": text}},
        "negative": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": ""}},
        "latent": {"class_type": "EmptyLatentAudio", "inputs": {"seconds": seconds, "batch_size": 1}},
        "sample": {"class_type": "KSampler", "inputs": {
            "model": ["ckpt", 0], "positive": ["positive", 0], "negative": ["negative", 0], "latent_image": ["latent", 0],
            "seed": seed, "steps": SA3_STEPS, "cfg": 1.0, "sampler_name": "lcm", "scheduler": "simple", "denoise": 1.0}},
        "decode": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["sample", 0], "vae": ["ckpt", 2]}},
        "save": {"class_type": "SaveAudioAdvanced", "inputs": {
            "audio": ["decode", 0], "filename_prefix": f"media_lab/stable_audio_3_{kind}", "format": fmt}},
    })
    if fmt == "mp3":
        graph["save"]["inputs"]["format.quality"] = "V0"
    return graph


# Kandinsky 6.0 Lite Distill (Kandinsky Lab, MIT) through the pinned kandinsky6 extension: 5 s of
# video with synchronized 44 kHz audio (speech with lip-sync, ambience, music) from text or a first
# frame, 864x480 at 24 fps, PiFlow 10 steps CFG 1 (the extension's distilled defaults; MagCache is
# only for non-distilled Pro). Spoken lines go in the video caption as <S>…<E>; voices and sounds
# in the audio caption. The official beautifier expands both with Qwen3.5 9B (the MOSS-Image copy).
K6_DIT = "Kandinsky-6.0-Lite-distill-5s-Diffusers/transformer/diffusion_pytorch_model.safetensors"
K6_CLIPS = ("qwen_2.5_vl_7b_fp8_scaled.safetensors", "clip_l.safetensors")
K6_VAE = "hunyuan_video_vae_bf16.safetensors"
K6_AUDIO_VAE = ("v1-44.pth", "bigvgan_vocoder")
K6_AUDIO_SCALING = 0.417
K6_BEAUTIFIER = "qwen3.5_9b_w4a8_gptq.safetensors"
K6_STEPS = 10
K6_FRAMES = 121
K6_SIZES = {"16:9": (864, 480), "9:16": (480, 864)}
K6_NEGATIVE = "Static, 2D cartoon, cartoon, 2d animation, paintings, images, worst quality, low quality, ugly, deformed, walking backwards"


def kandinsky6_ready(model_root, h3_model_root=None) -> bool:
    encoder_roots = [model_root / "text_encoders"] + ([h3_model_root / "text_encoders"] if h3_model_root else [])
    return (all(p.is_file() for p in (model_root / "diffusion_models" / K6_DIT, model_root / "vae" / K6_VAE,
                                      model_root / "text_encoders" / K6_CLIPS[1], model_root / "text_encoders" / K6_BEAUTIFIER,
                                      model_root / "audio_vae" / K6_AUDIO_VAE[0],
                                      model_root / "audio_vae" / K6_AUDIO_VAE[1] / "bigvgan_generator.pt"))
            and any((root / K6_CLIPS[0]).is_file() for root in encoder_roots))


def kandinsky6_workflow(prompt: str, audio_prompt: str, aspect_ratio: str, seed: int,
                        first_frame: str | None = None, enhance: bool = True) -> dict:
    width, height = K6_SIZES[aspect_ratio]
    graph = {
        "unet": {"class_type": "UNETLoader", "inputs": {"unet_name": K6_DIT, "weight_dtype": "default"}},
        "clip": {"class_type": "DualCLIPLoader", "inputs": {
            "clip_name1": K6_CLIPS[0], "clip_name2": K6_CLIPS[1], "type": "kandinsky5", "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": K6_VAE}},
        "audio_vae": {"class_type": "Kandinsky6AudioVAELoader", "inputs": {
            "tod_vae": K6_AUDIO_VAE[0], "bigvgan_dir": K6_AUDIO_VAE[1], "mode": "44k", "scaling_factor": K6_AUDIO_SCALING}},
        "beautifier": {"class_type": "CLIPLoader", "inputs": {"clip_name": K6_BEAUTIFIER, "type": "qwen_image", "device": "default"}},
        "beautify": {"class_type": "Kandinsky6BeautifyPrompt", "inputs": {
            "clip": ["beautifier", 0], "video_caption": prompt.strip(), "audio_caption": audio_prompt.strip(),
            "enabled": enhance, "seed": seed % 2**64, "max_tokens": 1500, "temperature": 0.3, "repetition_penalty": 1.1}},
        "caption": {"class_type": "PreviewAny", "inputs": {"source": ["beautify", 2]}},
        "positive": {"class_type": "Kandinsky6TextEncode", "inputs": {
            "clip": ["clip", 0], "video_caption": ["beautify", 0], "audio_caption": ["beautify", 1]}},
        "negative": {"class_type": "Kandinsky6TextEncode", "inputs": {
            "clip": ["clip", 0], "video_caption": K6_NEGATIVE, "audio_caption": ""}},
        "latent": {"class_type": "Kandinsky6EmptyLatent", "inputs": {
            "width": width, "height": height, "length": K6_FRAMES, "fps": 24.0, "batch_size": 1}},
    }
    positive, negative, latent = ["positive", 0], ["negative", 0], ["latent", 0]
    if first_frame:
        graph.update({
            "first": {"class_type": "LoadImage", "inputs": {"image": first_frame}},
            "fit": {"class_type": "ImageScale", "inputs": {
                "image": ["first", 0], "upscale_method": "bilinear", "width": width, "height": height, "crop": "center"}},
            "first_latent": {"class_type": "VAEEncode", "inputs": {"pixels": ["fit", 0], "vae": ["vae", 0]}},
            "i2va": {"class_type": "Kandinsky6ImageToVideoAudio", "inputs": {
                "positive": positive, "negative": negative, "empty_latent": latent, "reference_latent": ["first_latent", 0]}},
        })
        graph["beautify"]["inputs"]["image"] = ["first", 0]
        positive, negative, latent = ["i2va", 0], ["i2va", 1], ["i2va", 2]
    graph["sample"] = {"class_type": "Kandinsky6Sampler", "inputs": {
        "model": ["unet", 0], "positive": positive, "negative": negative, "latent_image": latent, "seed": seed,
        "steps": K6_STEPS, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}}
    joint = ["sample", 0]
    if first_frame:
        graph["drop_ref"] = {"class_type": "Kandinsky6RemoveReferenceLatent", "inputs": {"joint_latent": joint}}
        joint = ["drop_ref", 0]
    graph.update({
        "decode": {"class_type": "VAEDecode", "inputs": {"samples": joint, "vae": ["vae", 0]}},
        "audio": {"class_type": "Kandinsky6AudioVAEDecode", "inputs": {"audio_vae": ["audio_vae", 0], "joint_latent": joint}},
        "video": {"class_type": "CreateVideo", "inputs": {"images": ["decode", 0], "audio": ["audio", 0], "fps": 24.0}},
        "save": {"class_type": "SaveVideo", "inputs": {
            "video": ["video", 0], "filename_prefix": "media_lab/kandinsky6", "format": "mp4", "codec": "h264"}},
    })
    return graph


FLASHVSR_MODEL = "FlashVSR-v1.1"
FLASHVSR_FILES = ("diffusion_pytorch_model_streaming_dmd.safetensors", "LQ_proj_in.ckpt",
                  "TCDecoder.ckpt", "Wan2.1_VAE.pth")
FLASHVSR_MODES = {"fast": "tiny", "quality": "full"}


def flashvsr_ready(model_root) -> bool:
    return all((model_root / FLASHVSR_MODEL / name).is_file() for name in FLASHVSR_FILES)


def flashvsr_tile(scale: int, width: int, height: int) -> int:
    """Measured on a 3090 with chunked input: 512-px tiles are 30% faster at x2 (15-16 GiB VRAM);
    at x4 256-px tiles stay near 17 GiB. Both keep tile*scale % 128 == 0, which the node needs to
    avoid center-cropping (misaligning) a tile."""
    return 512 if scale == 2 else 256


def flashvsr_workflow(video: str, scale: int, quality: str, seed: int, tile: int) -> dict:
    """One silent, 128/scale-aligned chunk through FlashVSR v1.1; the runtime stitches chunks,
    crops the alignment padding and restores the original audio."""
    return {
        "load": {"class_type": "LoadVideo", "inputs": {"file": video}},
        "parts": {"class_type": "GetVideoComponents", "inputs": {"video": ["load", 0]}},
        "pipe": {"class_type": "FlashVSRInitPipe", "inputs": {
            "model": FLASHVSR_MODEL, "mode": FLASHVSR_MODES[quality], "alt_vae": "none",
            "force_offload": True, "precision": "bf16", "device": "auto",
            "attention_mode": "sparse_sage_attention"}},
        "upscale": {"class_type": "FlashVSRNodeAdv", "inputs": {
            "pipe": ["pipe", 0], "frames": ["parts", 0], "scale": scale, "color_fix": True,
            "tiled_vae": True, "tiled_dit": True, "tile_size": tile, "tile_overlap": 24,
            "unload_dit": False, "sparse_ratio": 2.0, "kv_ratio": 3.0, "local_range": 11, "seed": seed}},
        "video": {"class_type": "CreateVideo", "inputs": {"images": ["upscale", 0], "fps": ["parts", 2]}},
        # Near-lossless intermediate; the runtime does the single delivery encode.
        "save": {"class_type": "SaveVideo", "inputs": {
            "video": ["video", 0], "filename_prefix": "media_lab/flashvsr", "format": "mp4",
            "format.codec": "h264", "format.codec.encoding": "re-encode", "format.codec.encoding.crf": 10}},
    }
