"""Official MCP transport, explicit creative API allowlist, account-scoped execution."""
import base64
import inspect
import io
import json
import mimetypes
import re
import threading
import time
from functools import partial
from typing import Annotated, Literal, get_type_hints
from urllib.parse import urlencode, urlsplit

import anyio
from fastapi import HTTPException, UploadFile
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.server.streamable_http_manager import StreamableHTTPASGIApp, StreamableHTTPSessionManager
from mcp.types import ToolAnnotations, ImageContent, TextContent
from pydantic.fields import FieldInfo
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticUndefined
from starlette.responses import FileResponse, JSONResponse, Response

from .accounts import AccessDenied
from .artifacts import MEDIA_TYPES, SAFE_ID
from .mcp_files import MAX_LINKS_PER_CALL, McpFiles
from .mcp_guides import build_guides, english_capabilities
from .contracts import ArtifactRef, ExportRequest, ProductionRequest
from .prompt_check import PromptCheck
from .providers import ProviderBusy
from .security import OWNER, as_owner
from .tenancy import NotOwned, ResourceLimit


class UploadSlot(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=200, description='Local file name or label, echoed back so you can match each link and result to your file.')


class PromptImprovement(BaseModel):
    model_config = ConfigDict(extra='forbid')
    prompt: str = Field(min_length=1, max_length=20000, description='Complete original request. Preserve literal quoted text and every explicit requirement.')
    mode: Literal['t2i', 'i2i', 'moss', 't2v', 'i2v', 'r2v', 'kandinsky', 'song', 'ace_song'] = Field(default='t2i', description='Target: Qwen image (t2i) or edit (i2i), MOSS-Image caption (moss), H3 video (t2v/i2v/r2v), Kandinsky 6 (kandinsky: returns prompt and audio_prompt), YuE2 song (song) or ACE-Step song (ace_song: also bpm, key, time_signature, language); song modes return style and lyrics. FLUX 3 Klein, Stable Audio 3 and Qwen3-TTS need no improver. Proposing a prompt does not execute it.')
    references: list[ArtifactRef] = Field(default_factory=list, max_length=16, description='Owned images in request order: edit references, the H3 or Kandinsky first frame, or H3 r2v reference images.')
    seconds: float | None = Field(default=None, ge=5, le=15, description='H3 only: requested clip duration for timing shots and dialogue.')


class AgentReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    prompt: str = Field(min_length=1, max_length=20000)
    media: ArtifactRef = Field(description='Owned image to review with the active provider, only with verified vision support.')


class AudioSection(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    energy: str = Field(default='', max_length=80)


class AudioAnalysis(BaseModel):
    duration: float = Field(ge=5, le=900, description='Actual duration from analyze_audio, in seconds.')
    bpm_estimate: float | None = None
    sections: list[AudioSection] = Field(default_factory=list, max_length=100)


class StoryboardPlan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    brief: str = Field(min_length=1, max_length=10000, description='Visual direction: identity, wardrobe, location, lighting and style. Write descriptive direction in English.')
    lyrics: str = Field(default='', max_length=20000)
    analysis: AudioAnalysis = Field(description='Technical song metadata. The agent has not listened to the audio.')


class Scene(BaseModel):
    model_config = ConfigDict(extra='forbid')
    start: float = Field(ge=0, description='Start time in seconds, contiguous with the previous scene.')
    end: float = Field(gt=0, description='End time in seconds; maximum scene duration is 15 seconds.')
    image_prompt: str = Field(min_length=1, max_length=20000, description='Complete English keyframe prompt: identity, wardrobe, composition, style and lighting. Preserve literal text.')
    video_prompt: str = Field(min_length=1, max_length=20000, description='Complete English H3 prompt: Base I2VA body from the keyframe, or Ref2VA when lip_sync is true. See prompt_guide director.')
    image: ArtifactRef | None = Field(default=None, description='Owned PNG to reuse as a keyframe.')
    video: ArtifactRef | None = Field(default=None, description='Owned MP4, MKV or WebM clip to reuse; loop or trim to cover the scene.')
    lip_sync: bool = Field(default=False, description='Experimental: render this new clip in H3 r2v with its keyframe as <Picture 1> and the exact song excerpt as <Audio 1> so a visible singer lip-syncs. Needs at least 2 s and a six-section Ref2VA video_prompt.')

    @model_validator(mode='after')
    def valid_duration(self):
        if not 0 < self.end - self.start <= 15:
            raise ValueError('Each scene must last more than 0 and at most 15 seconds')
        return self


class StoryboardProduction(ProductionRequest):
    scenes: list[Scene] = Field(min_length=1, max_length=100, description='Complete ordered contiguous storyboard; starts at 0 and covers the entire song.')


BODY_SCHEMAS = {'improve_prompt': PromptImprovement, 'review_with_agent': AgentReview,
                'plan_storyboard': StoryboardPlan, 'create_production': StoryboardProduction,
                'check_prompt': PromptCheck}

# Every operation reuses the existing ownership checks, quotas and generation workflows.
OPERATIONS = [
    ('capabilities', 'GET', '/v1/capabilities', 'read', 'Live available models, formats, profiles and advanced controls; consult before creating.'),
    ('studio_status', 'GET', '/v1/health', 'read', 'Current studio and multimedia worker status.'),
    ('account_profile', 'GET', '/v1/account/profile', 'read', 'Resource profile and quotas of the token owner.'),
    ('account_preferences', 'GET', '/v1/account/preferences', 'read', 'Owner export defaults (format, JPEG/WebP quality, JPEG background) and prompt-enhancer preference.'),
    ('check_prompt', 'POST', '/v1/prompts/check', 'read', 'Structural pre-flight check of a Qwen image/edit, H3 or YuE2 prompt against the model format and the inputs you will send; returns errors, warnings and, for H3, the exact text the model receives. No generation.'),
    ('list_jobs', 'GET', '/v1/jobs', 'read', 'Recent owned jobs including active work.'),
    ('get_job', 'GET', '/v1/jobs/{job_id}', 'read', 'Status, progress and resulting artifacts of an owned job.'),
    ('get_job_preview', 'GET', '/v1/jobs/{jid}/preview', 'read', 'Visual preview of an owned image job while generating, when available.'),
    ('find_job', 'GET', '/v1/jobs/by-idempotency', 'read', 'Find a job receipt by scope and idempotency key before retrying admission.'),
    ('cancel_job', 'DELETE', '/v1/jobs/{job_id}', 'create', 'Cancel an owned active job.'),
    ('resume_job', 'POST', '/v1/jobs/{job_id}/resume', 'create', 'Resume a stopped owned job ONLY with explicit user authorization.'),
    ('generate_image', 'POST', '/v1/jobs/generate', 'create', 'Generate an image using an English descriptive prompt (model_variant base, or turbo for the 8-step Qwen Turbo; model=moss for MOSS-Image layouts and in-image text; model=flux3 for fast FLUX 3 Klein photorealism with its own prompt upsampler; control follows the edges, depth or pose of an owned image; resolution_tier=2k renders about 4 MP with Qwen INT8 when capabilities.two_k_enabled); returns an asynchronous job receipt.'),
    ('edit_image', 'POST', '/v1/jobs/edit', 'create', 'Edit 1–10 owned image references with English instructions preserving unchanged features (model_variant base or turbo); camera re-shoots one image from another angle; model=flux3 edits or composes 1–4 references with FLUX 3 Klein; resolution up to 2048 edits at 2K (about 4 MP) with Qwen INT8 and at most 4 references when capabilities.two_k_enabled.'),
    ('generate_video', 'POST', '/v1/jobs/video', 'create', 'Generate H3 video (Base, Turbo, Fused Turbo, Omni) from text, keyframes or image/video/audio references, or model=kandinsky6 for a 5 s Kandinsky 6.0 clip with synchronized audio and lip-synced speech (<S>words<E>).'),
    ('generate_music', 'POST', '/v1/jobs/song', 'create', 'Generate a song: model=yue2 (YuE2 3B; ABC scores and covers from owned audio) or model=ace_step (ACE-Step 1.5 XL Turbo; a full song of exact length in about a minute).'),
    ('upscale_video', 'POST', '/v1/jobs/upscale', 'create', 'Upscale an owned video 2x or 4x with FlashVSR v1.1, keeping its original audio; creates a new video and never modifies the source.'),
    ('refine_faces', 'POST', '/v1/jobs/face_refine', 'create', 'Redraw the main face of an owned 1–15 s video sharper and truer to identity with MiniMax H3 (light/medium/strong), keeping everything else and the audio; creates a new video.'),
    ('remove_person', 'POST', '/v1/jobs/remove', 'create', 'Erase one person from an owned 1–10 s video (best ≤5 s, steady shot) and rebuild the background with MiniMax H3 Person Remover, keeping the rest of the scene and the audio; creates a new video.'),
    ('separate_stems', 'POST', '/v1/jobs/stems', 'create', 'Split an owned song or audio (1–900 s) into vocals + instrumental (stems=two) or vocals, drums, bass and other (stems=four) with Hybrid Demucs; creates new audio files and never modifies the source.'),
    ('generate_sound', 'POST', '/v1/jobs/sound', 'create', 'Generate instrumental music, a solo instrument part, sound effects/ambience or a one-shot sample of exact length with Stable Audio 3 (Medium or Small SFX); no vocals or lyrics.'),
    ('generate_speech', 'POST', '/v1/jobs/speech', 'create', 'Speak a text with Qwen3-TTS: a preset studio voice (with optional delivery), a voice designed from a description, or a clone of an owned reference clip ONLY with the voice owner’s permission (consent=true).'),
    ('swap_character', 'POST', '/v1/jobs/swap', 'create', 'Replace a person in an owned 2–15 s video with the character from an owned image (mode=character, H3 Character Swap) or only their head (mode=head, experimental Head Swap), or with SCAIL-2 (mode=scail, tight body motion), keeping motion, scene, camera and the original audio; creates a new video.'),
    ('create_production', 'POST', '/v1/jobs/production', 'create', 'Create a music video from an owned song and complete storyboard with English scene prompts.'),
    ('list_library', 'GET', '/v1/library', 'read', 'Search and paginate owned images, audio, videos and references.'),
    ('list_characters', 'GET', '/v1/characters', 'read', 'Owned private characters (@handle, look description, reference images, optional LoRA) to reuse the same person or mascot across images and videos.'),
    ('list_loras', 'GET', '/v1/loras', 'read', 'Owned LoRA library: id, base (qwen for images, h3 for video), trigger words, strength and status; pass ready ones in loras of generate_image, edit_image or generate_video.'),
    ('list_gallery', 'GET', '/v1/gallery', 'read', 'Owned images with original prompts and reusable references.'),
    ('inspect_media', 'GET', '/v1/media/inspect', 'read', 'Inspect owned image/audio/video by URI and hash; reduced visual previews or technical metadata.'),
    ('analyze_audio', 'GET', '/v1/media/analyze', 'read', 'Actual audio duration, estimated BPM and energy sections for scene timing; not a listening review.'),
    ('review_image', 'GET', '/v1/review', 'read', 'Local image preview and alpha statistics; not an external AI critique.'),
    ('list_sessions', 'GET', '/v1/sessions', 'read', 'Owned creative conversations.'),
    ('get_session', 'GET', '/v1/sessions/{session_id}', 'read', 'Messages and references in an owned conversation.'),
    ('add_message', 'POST', '/v1/sessions/{session_id}/messages', 'create', 'Store a message and owned references in a conversation; preserve original user requests.'),
    ('provider_status', 'GET', '/v1/account/provider', 'read', 'Active provider and verified capabilities, without secrets.'),
    ('list_providers', 'GET', '/v1/account/providers', 'read', 'Owned saved provider configurations and active selection, without secrets.'),
    ('discover_models', 'GET', '/v1/account/providers/{eid}/models', 'read', 'Discover models from an approved endpoint whose account key is already saved in the web UI.'),
    ('start_agent', 'POST', '/v1/agent/runs', 'agent', 'Ask the studio agent to execute an authorized multimedia task; asynchronous agent-run receipt.'),
    ('list_agent_runs', 'GET', '/v1/agent/runs', 'read', 'Agent runs belonging to the token owner.'),
    ('get_agent_run', 'GET', '/v1/agent/runs/{rid}', 'read', 'Steps, status and media results of an owned agent run.'),
    ('cancel_agent', 'POST', '/v1/agent/runs/{rid}/cancel', 'agent', 'Cancel an owned agent run.'),
    ('continue_agent', 'POST', '/v1/agent/runs/{rid}/continue', 'agent', 'Continue an owned stopped agent run with explicit user authorization.'),
    ('improve_prompt', 'POST', '/v1/agent/improve', 'agent', 'Propose a model-ready English prompt (Qwen image/edit, MOSS caption, H3 or Kandinsky video, or YuE2/ACE-Step style plus lyrics) with the active provider using the studio guides, preserving intent and literal text; no generation.'),
    ('review_with_agent', 'POST', '/v1/agent/review', 'agent', 'Review an owned image with the external provider; verified vision required.'),
    ('plan_storyboard', 'POST', '/v1/agent/director', 'agent', 'Plan scenes with English model prompts from brief, literal lyrics and technical audio analysis; does not generate.'),
    ('delete_media', 'DELETE', '/v1/library', 'delete', 'Permanently delete an owned media file; obtain user confirmation first.'),
]


TERMINAL = {'completed', 'failed', 'cancelled', 'interrupted', 'blocked_gpu'}
# POST only because the body is large; these change nothing.
READ_ONLY_POSTS = {'check_prompt'}
# Clients treat tools without hints as possibly destructive and ask for approval.
READS = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
WAIT_WITHOUT_PROGRESS = 50
WAIT_WITH_PROGRESS = 600


def progress_token(ctx):
    params = ctx.request_context.params or {}
    meta = params.get('_meta') if isinstance(params, dict) else None
    return (meta or {}).get('progressToken') if isinstance(meta, dict) else None


def progress_of(job):
    progress = job.get('progress') if isinstance(job.get('progress'), dict) else {}
    pct = progress.get('pct')
    pct = 100 if job.get('status') == 'completed' else (round(float(pct), 1) if isinstance(pct, (int, float)) else None)
    return pct, progress.get('node') or (job.get('activity') or [None])[-1]


def running_summary(job, waited):
    """Compact view while a job runs: agents need state and progress, not the full request again."""
    pct, stage = progress_of(job)
    return {'job_id': job.get('id'), 'operation': job.get('operation'), 'status': job.get('status'),
            'progress_pct': pct, 'stage': stage, 'queue_position': job.get('queue_position'), 'gpu': job.get('gpu'),
            'waited_seconds': round(waited, 1), 'still_running': True,
            'next': 'Call wait_for_job again with the same job_id.'}
PRIVATE_PATH = re.compile(r'(?<![\w:/])/(?:data|home|tmp|app|opt|usr|srv|var|root|models|workspace)(?:/[\w.@+-]+)+')


def reason(detail):
    """The studio's own validation message, without server paths, short enough for a tool error."""
    text = detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False, default=str)
    return PRIVATE_PATH.sub('<path>', text).strip()[:400]


def outputs(value, found=None):
    """Every owned file reference inside a job result, in order, without duplicates."""
    found = [] if found is None else found
    if isinstance(value, dict):
        if isinstance(value.get('uri'), str) and value['uri'].startswith('artifact://') and isinstance(value.get('sha256'), str):
            item = {'uri': value['uri'], 'sha256': value['sha256'], 'kind': value['uri'].split('/')[3]}
            if not any(o['uri'] == item['uri'] for o in found):
                found.append(item)
        for nested in value.values():
            outputs(nested, found)
    elif isinstance(value, list):
        for nested in value:
            outputs(nested, found)
    return found


def with_outputs(job):
    if isinstance(job, dict) and job.get('status') == 'completed':
        return {**job, 'outputs': outputs(job.get('result'))}
    return job


GUIDES = build_guides(OPERATIONS)
GUIDE = GUIDES['all']


def build_mcp(app, access):
    server = MCPServer('Media Lab', version='0.14.0-mcp-en.1', instructions=GUIDES['overview'],
                       description='Private image, video, music, Director and agent studio.')

    def authorize(ctx, required):
        request = ctx.request_context.request
        if request is None:
            raise ToolError('An authenticated MCP connection is required')
        try:
            identity = access.authenticate(request.headers.get('authorization', '')[7:], touch=False)
        except AccessDenied:
            raise ToolError('Token revoked, expired or account disabled') from None
        if required not in identity['scopes']:
            raise ToolError('Your token does not allow this operation: ' + required)
        return identity

    async def execute(ctx, required, endpoint, kwargs):
        identity = authorize(ctx, required)
        with as_owner(identity['owner_id']):
            try:
                if inspect.iscoroutinefunction(endpoint):
                    return await endpoint(**kwargs)
                return await anyio.to_thread.run_sync(partial(endpoint, **kwargs))
            except (NotOwned, FileNotFoundError):
                raise ToolError('The resource does not exist or does not belong to your account') from None
            except ResourceLimit:
                raise ToolError('Your account job or storage quota has been reached') from None
            except ProviderBusy:
                raise ToolError('The provider is busy with an active agent run') from None
            except HTTPException as exc:
                # Agents can only fix a request if they see why the studio rejected it.
                detail = reason(exc.detail)
                if exc.status_code == 429:
                    raise ToolError(f'The studio queue is full right now ({detail}). Wait a few minutes and submit again with the same idempotency_key.') from None
                if exc.status_code == 404:
                    raise ToolError('The resource does not exist or does not belong to your account') from None
                if exc.status_code == 409:
                    raise ToolError(f'Conflict: {detail}. Check the job with find_job/get_job; do not reuse an idempotency_key with different parameters.') from None
                if exc.status_code == 503:
                    raise ToolError(f'This feature is unavailable on the server: {detail}. Read capabilities or configure your provider in the web UI.') from None
                raise ToolError(f'Rejected by the studio: {detail}. Fix that and submit again; see capabilities and prompt_guide.') from None
            except ValueError as exc:
                raise ToolError(f'Rejected by the studio: {reason(str(exc)) or "invalid parameters"}. Fix that and submit again; see capabilities and prompt_guide.') from None
            except Exception:
                raise ToolError('The operation could not complete. Check job status before retrying.') from None

    routes = {(method, r.path): r.endpoint for r in app.routes if hasattr(r, 'methods') for method in r.methods}
    transfers = McpFiles(access.accounts, access.origin, app.state.artifacts, lambda: routes)

    def register(name, method, path, required, description):
        endpoint = routes.get((method, path))
        if endpoint is None:
            return
        hints = get_type_hints(endpoint)
        params = []
        for param in inspect.signature(endpoint).parameters.values():
            annotation = hints.get(param.name, param.annotation)
            if param.name == 'body' and name in BODY_SCHEMAS:
                annotation = BODY_SCHEMAS[name]
            default = param.default
            if isinstance(default, FieldInfo):
                if param.name == 'idempotency_key':
                    default = Field(default=None, description='1–128 ASCII characters, one per creative intent. Resubmitting the same key and body returns the same job instead of a duplicate; use find_job to recover a lost receipt.')
                annotation = Annotated[annotation, default]
                default = default.default
            if default is PydanticUndefined:
                default = inspect.Parameter.empty
            params.append(param.replace(annotation=annotation, default=default))
        # Force keyword-only to avoid required-after-optional issues and hide Context from the schema.
        params = [p.replace(kind=inspect.Parameter.KEYWORD_ONLY) for p in params]
        params.append(inspect.Parameter('ctx', inspect.Parameter.KEYWORD_ONLY, annotation=Context))

        async def operation(**kwargs):
            ctx = kwargs.pop('ctx')
            if name in BODY_SCHEMAS:
                data = kwargs['body'].model_dump()
                kwargs['body'] = data if hints['body'] is dict else hints['body'].model_validate(data)
            key = kwargs.get('idempotency_key')
            if key is not None and (not key.strip() or len(key) > 128 or not key.isascii()):
                raise ToolError('idempotency_key must contain 1–128 ASCII characters')
            # Query constraints normally run in FastAPI; enforce these when invoking directly.
            if 'limit' in kwargs and not 1 <= kwargs['limit'] <= 500:
                raise ToolError('limit must be between 1 and 500')
            if 'offset' in kwargs and kwargs['offset'] < 0:
                raise ToolError('offset cannot be negative')
            result = await execute(ctx, required, endpoint, kwargs)
            if name == 'capabilities':
                result = english_capabilities(result)
            if name == 'get_job':
                result = with_outputs(result)
            if name == 'inspect_media' and result.get('preview'):
                data = dict(result)
                preview = data.pop('preview')
                return [TextContent(text=json.dumps(data, ensure_ascii=False)),
                        ImageContent(data=preview['base64'], mimeType=preview['mime'])]
            if isinstance(result, Response):
                if result.status_code == 204:
                    return {'status': 'pending', 'message': 'No preview is available yet'}
                if result.media_type not in {'image/png', 'image/jpeg', 'image/webp'}:
                    raise ToolError('Preview type is unavailable')
                return [TextContent(text=json.dumps({'alpha': json.loads(result.headers.get('x-alpha-stats', '{}'))})),
                        ImageContent(data=base64.b64encode(result.body).decode('ascii'), mimeType=result.media_type)]
            return result

        operation.__name__, operation.__doc__ = name, description
        operation.__signature__ = inspect.Signature(params)
        operation.__annotations__ = {p.name: p.annotation for p in params}
        read_only = method == 'GET' or name in READ_ONLY_POSTS
        server.tool(name=name, description=description + ' Required scope: ' + required + '.', meta={'requiredScope': required}, annotations=ToolAnnotations(
            readOnlyHint=read_only, destructiveHint=required == 'delete',
            idempotentHint=read_only, openWorldHint=required == 'agent'))(operation)

    for operation in OPERATIONS:
        register(*operation)

    # structured_output=False: the guide is plain Markdown text. A generated {"result": str} output
    # schema made some clients validate the Markdown itself and reject every call.
    @server.tool(structured_output=False, annotations=READS, description='English studio guides. Topics: image (Qwen, MOSS and FLUX 3 Klein creation), edit (Qwen and FLUX editing), video (MiniMax H3 and Kandinsky 6), music (YuE2 and ACE-Step), sound (Stable Audio 3), speech (Qwen3-TTS), director (music videos), prompts (all model guides), formats, controls, workflows, overview, all. Read the medium topic before writing a model prompt.')
    def prompt_guide(ctx: Context, topic: Literal['all', 'overview', 'prompts', 'formats', 'controls', 'workflows',
                                                  'image', 'edit', 'video', 'music', 'sound', 'speech',
                                                  'director'] = 'all') -> str:
        authorize(ctx, 'read')
        return GUIDES[topic]

    def guide_resource(uri, topic, description):
        def read() -> str:
            return GUIDES[topic]
        read.__name__ = uri.rsplit('/', 1)[-1].replace('-', '_') + '_guide'
        server.resource(uri, mime_type='text/markdown', description=description)(read)

    guide_resource('media-lab://guides/all', 'all', 'Complete English guide for all creative tools, model prompts, formats and workflows.')
    guide_resource('media-lab://guides/formats', 'formats', 'English upload, reference, encoding, export and private-download format guide.')
    guide_resource('media-lab://guides/controls', 'controls', 'English complete model controls, defaults, constraints and resolution tables.')
    guide_resource('media-lab://guides/image', 'image', 'Image creation prompt guides: Qwen-Image 2.1, MOSS-Image and FLUX 3 Klein.')
    guide_resource('media-lab://guides/edit', 'edit', 'Image editing prompt guides: Qwen-Image 2.1 and FLUX 3 Klein.')
    guide_resource('media-lab://guides/video', 'video', 'Video prompt guides: MiniMax H3 (modes, formats, labels, dialogue, audio) and Kandinsky 6.')
    guide_resource('media-lab://guides/music', 'music', 'Song guides: YuE2 (style, lyrics, modes, covers) and ACE-Step 1.5.')
    guide_resource('media-lab://guides/sound', 'sound', 'Stable Audio 3 instrumental, loop and sound-effect prompt guide.')
    guide_resource('media-lab://guides/speech', 'speech', 'Qwen3-TTS text, preset voices, voice design and consented cloning guide.')
    guide_resource('media-lab://guides/director', 'director', 'Director music-video planning guide with the Qwen and H3 guides it relies on.')

    def brief(ctx, goal, extra=''):
        authorize(ctx, 'read')
        if len(goal) > 20000 or len(extra) > 2000:
            raise ToolError('Description is too long')
        return goal

    @server.prompt(description='English instruction template for an authorized multimedia creative task.')
    def creative_brief(goal: str, medium: str = 'image', ctx: Context = None) -> str:
        brief(ctx, goal, medium)
        topic = {'image': 'image', 'edit': 'edit', 'video': 'video', 'music': 'music', 'song': 'music',
                 'sound': 'sound', 'sfx': 'sound', 'speech': 'speech', 'voice': 'speech',
                 'director': 'director', 'production': 'director'}.get(medium.strip().lower(), 'prompts')
        return (f'{GUIDES["overview"]}\n{GUIDES[topic]}\nOriginal user goal ({medium}): {goal}\nRead live capabilities and plan the authorized work. '
                'Write model-facing descriptive prompts in English, preserving literal lyrics, dialogue and visible text. Preserve the original user request. '
                'Run check_prompt before submitting. Obtain explicit authorization for deletion or resumption.')

    @server.prompt(description='Write a Qwen-Image-2.1 prompt (text-to-image, or editing when references are supplied) for a request.')
    def image_prompt(goal: str, references: str = '0', ctx: Context = None) -> str:
        brief(ctx, goal, references)
        editing = references.strip() not in {'', '0'}
        return (f'{GUIDES["edit" if editing else "image"]}\nReference images supplied: {references}.\nUser request (keep it as the source of truth): {goal}\n'
                'Return only the final English prompt, then call check_prompt before generate_image/edit_image.')

    @server.prompt(description='Write a MiniMax H3 prompt for a request, choosing T2VA/I2VA/FL2VA/L2VA or Ref2VA from the supplied inputs.')
    def video_prompt(goal: str, inputs: str = 'text only', seconds: str = '5', ctx: Context = None) -> str:
        brief(ctx, goal, inputs + seconds)
        return (f'{GUIDES["video"]}\nInputs available: {inputs}. Requested seconds: {seconds}.\nUser request (keep it as the source of truth): {goal}\n'
                'State the chosen mode and inputs briefly, then give the complete prompt. Call check_prompt with the same inputs before generate_video.')

    @server.prompt(description='Write YuE2 style tags and structured lyrics for a song request.')
    def music_prompt(goal: str, ctx: Context = None) -> str:
        brief(ctx, goal)
        return (f'{GUIDES["music"]}\nUser request (keep it as the source of truth): {goal}\n'
                'Return the style tags and the structured lyrics separately. Never invent lyrics for an existing song; ask for them.')

    @server.prompt(description='Plan a Director music video (storyboard of Qwen keyframe and H3 clip prompts) for an owned song.')
    def music_video(goal: str, ctx: Context = None) -> str:
        brief(ctx, goal)
        return (f'{GUIDES["director"]}\nUser request (keep it as the source of truth): {goal}\n'
                'Analyze the song with analyze_audio first, then plan contiguous scenes covering its real duration.')

    async def upload(ctx, data_base64, content_type, session_id, path):
        authorize(ctx, 'create')
        try:
            if len(data_base64) > 28 * 1024 * 1024:
                raise ValueError()
            data = base64.b64decode(data_base64, validate=True)
            if not data or len(data) > 20 * 1024 * 1024:
                raise ValueError()
        except ValueError:
            raise ToolError('Invalid base64 file or decoded file exceeds 20 MiB') from None
        endpoint = routes.get(('POST', path))
        if endpoint is None:
            raise ToolError('Uploads are unavailable on this server')
        file = UploadFile(io.BytesIO(data), filename='reference', headers={'content-type': content_type})
        try:
            return await execute(ctx, 'create', endpoint, {'file': file, 'session_id': session_id})
        finally:
            await file.close()

    @server.tool(annotations=WRITES, description='Small-file fallback: upload a PNG/JPEG/WebP image inline as base64 (practical only for files of a few hundred KB). Prefer create_uploads + HTTP PUT for real files. Returns a normalized owned PNG ArtifactRef.')
    async def upload_reference(data_base64: str, content_type: str, ctx: Context, session_id: str = 'direct') -> dict:
        if content_type not in {'image/png', 'image/jpeg', 'image/webp'}:
            raise ToolError('Use PNG, JPEG or WebP')
        return await upload(ctx, data_base64, content_type, session_id, '/v1/uploads')

    @server.tool(annotations=WRITES, description='Small-file fallback: upload WAV/FLAC/MP3/Ogg/Opus audio (1–900 seconds) inline as base64. Prefer create_uploads + HTTP PUT for real files.')
    async def upload_audio(data_base64: str, content_type: str, ctx: Context, session_id: str = 'direct') -> dict:
        if content_type not in {mime for mime in MEDIA_TYPES if mime.startswith('audio/') }:
            raise ToolError('Use a supported WAV/FLAC/MP3/Ogg/Opus audio MIME type')
        return await upload(ctx, data_base64, content_type, session_id, '/v1/media/uploads')

    @server.tool(annotations=WRITES, description='Small-file fallback: upload MP4/MKV/WebM video inline as base64. Prefer create_uploads + HTTP PUT for real files. Returns an owned video ArtifactRef.')
    async def upload_video(data_base64: str, content_type: str, ctx: Context, session_id: str = 'direct') -> dict:
        if content_type not in {mime for mime in MEDIA_TYPES if mime.startswith('video/')}:
            raise ToolError('Use a supported MP4/MKV/WebM video MIME type')
        return await upload(ctx, data_base64, content_type, session_id, '/v1/media/uploads')

    @server.tool(annotations=READS, description='Size, MIME and download URLs for one owned artifact: temporary_url works without headers (curl -o); download_url needs the Bearer token. Use get_download_links for several files.')
    async def get_media(reference: ArtifactRef, ctx: Context) -> dict:
        identity = authorize(ctx, 'read')
        def result():
            path = app.state.artifacts.resolve(reference.uri, reference.sha256)
            link = transfers.create_downloads(identity, [(reference.model_dump(), path)])
            return {'reference': reference.model_dump(), 'bytes': path.stat().st_size,
                    'content_type': mimetypes.guess_type(path.name)[0] or 'application/octet-stream',
                    'temporary_url': link['links'][0]['url'], 'expires_at': link['expires_at'],
                    'download_url': access.origin + '/mcp/media?' + urlencode(reference.model_dump()),
                    'authentication': 'temporary_url: none (expires). download_url: Authorization: Bearer <your MCP token>'}
        return await execute(ctx, 'read', result, {})

    @server.tool(annotations=WRITES, description=f'Send local files to the studio: returns one temporary upload link per file (1–{MAX_LINKS_PER_CALL}). '
                 'Upload each with HTTP PUT of the raw bytes, no Authorization header: curl -sS -T ./photo.png "<url>". '
                 'The JSON reply contains the owned reference {uri, sha256} to pass to any creation tool. '
                 'Images, audio and video in common formats are detected and normalized. Links expire after 2 hours.')
    async def create_uploads(files: Annotated[list[UploadSlot], Field(min_length=1, max_length=MAX_LINKS_PER_CALL)],
                             ctx: Context, session_id: str = 'direct') -> dict:
        identity = authorize(ctx, 'create')
        if session_id != 'direct' and not SAFE_ID.fullmatch(session_id):
            raise ToolError('session_id must contain 1–80 ASCII letters, digits, underscores or hyphens')
        names = [slot.name for slot in files]
        def result():
            created = transfers.create_uploads(identity, names, session_id)
            return {**created, 'method': 'PUT',
                    'how': 'For each file: curl -sS -T <local file> "<url>" (raw bytes, no Authorization header). '
                           'POST multipart with one file field also works: curl -sS -F "file=@<local file>" "<url>". '
                           'The reply JSON has reference {uri, sha256}. A failed upload can be retried on the same url; '
                           'a successful one consumes it. get_uploads(ids) reports results if a reply was lost.'}
        return await execute(ctx, 'create', result, {})

    def output_links(identity, items):
        """Temporary download links for a finished job's files; best effort, never fails the wait."""
        pairs = []
        for item in items:
            try:
                pairs.append(({'uri': item['uri'], 'sha256': item['sha256']}, app.state.artifacts.resolve(item['uri'], item['sha256'])))
            except (ValueError, NotOwned, FileNotFoundError):
                continue
        try:
            created = transfers.create_downloads(identity, pairs) if pairs else {'links': []}
        except ResourceLimit:
            return {}
        return {link['reference']['uri']: {'url': link['url'], 'bytes': link['bytes'], 'expires_at': created['expires_at']}
                for link in created['links']}

    @server.tool(annotations=READS, description='Wait for an owned job to finish and return it like get_job. '
                 'When completed, `outputs` lists every resulting file {uri, sha256, kind, bytes, url}: url is a 1-hour download link '
                 '(curl -sS -o <file> "<url>", no headers). artifact:// URIs are server identifiers, not local files. '
                 f'max_seconds: up to {WAIT_WITHOUT_PROGRESS} s, or up to {WAIT_WITH_PROGRESS} s when the call carries a progressToken '
                 '(the server then sends notifications/progress with status and percent every few seconds). '
                 'While running it returns a compact {status, progress_pct, stage, queue_position}: call it again. '
                 'Use this instead of sleeping or polling in a script.')
    async def wait_for_job(job_id: str, ctx: Context, max_seconds: Annotated[int, Field(ge=1, le=WAIT_WITH_PROGRESS)] = 30) -> dict:
        identity = authorize(ctx, 'read')
        endpoint = routes.get(('GET', '/v1/jobs/{job_id}'))
        if endpoint is None or len(job_id) > 80:
            raise ToolError('The resource does not exist or does not belong to your account')
        reporting = progress_token(ctx) is not None
        # Without progress notifications nothing resets the client's request timeout.
        limit = max_seconds if reporting else min(max_seconds, WAIT_WITHOUT_PROGRESS)
        started = time.monotonic()
        deadline, last_report = started + limit, 0.0
        while True:
            job = await execute(ctx, 'read', endpoint, {'job_id': job_id})
            now = time.monotonic()
            if job.get('status') in TERMINAL:
                job = with_outputs(job)
                if job.get('outputs'):
                    links = await execute(ctx, 'read', partial(output_links, identity, job['outputs']), {})
                    job['outputs'] = [{**o, **links.get(o['uri'], {})} for o in job['outputs']]
                job['progress_pct'], job['stage'] = progress_of(job)
                if reporting:
                    await ctx.report_progress(100, 100, f"{job['status']}")
                return job
            if now >= deadline:
                return running_summary(job, now - started)
            if reporting and now - last_report >= 5:
                pct, stage = progress_of(job)
                position = job.get('queue_position')
                await ctx.report_progress(pct or 0, 100, ' · '.join(str(part) for part in (
                    job.get('status'), f'{pct:g}%' if pct is not None else None, stage,
                    f'queue position {position}' if position else None) if part))
                last_report = now
            await anyio.sleep(min(3, max(0.2, deadline - time.monotonic())))

    @server.tool(annotations=READS, description='Status and resulting owned references of upload links created with create_uploads.')
    async def get_uploads(ids: Annotated[list[str], Field(min_length=1, max_length=MAX_LINKS_PER_CALL)], ctx: Context) -> dict:
        identity = authorize(ctx, 'read')
        if any(len(value) > 64 for value in ids):
            raise ToolError('Unknown upload id')
        return await execute(ctx, 'read', lambda: transfers.upload_status(identity, ids), {})

    @server.tool(annotations=READS, description=f'Temporary download links (1 hour, no headers needed) for 1–{MAX_LINKS_PER_CALL} owned references: '
                 'curl -sS -o <file> "<url>". Use it for job results, library items and uploads.')
    async def get_download_links(references: Annotated[list[ArtifactRef], Field(min_length=1, max_length=MAX_LINKS_PER_CALL)], ctx: Context) -> dict:
        identity = authorize(ctx, 'read')
        def result():
            paths = [(ref.model_dump(), app.state.artifacts.resolve(ref.uri, ref.sha256)) for ref in references]
            return {**transfers.create_downloads(identity, paths),
                    'how': 'curl -sS -o <file> "<url>" (GET, no Authorization header; Range supported). Request new links after expiry.'}
        return await execute(ctx, 'read', result, {})

    @server.tool(annotations=READS, description='Export an owned image as PNG/JPEG/WebP; returns base64 bytes and MIME. JPEG flattens alpha; WebP retains it.')
    async def export_image(request: ExportRequest, ctx: Context) -> dict:
        def result():
            data, mime = app.state.artifacts.export_image(request.uri, request.sha256, request.format, request.quality, request.background)
            return {'content_type': mime, 'data_base64': base64.b64encode(data).decode('ascii')}
        return await execute(ctx, 'read', result, {})

    security = TransportSecuritySettings(allowed_hosts=[urlsplit(access.origin).netloc], allowed_origins=[access.origin])
    transport = server.streamable_http_app(streamable_http_path='/mcp', json_response=True,
        stateless_http=True, max_request_body_size=MAX_MCP_BODY, transport_security=security)
    # In JSON-response mode the SDK drops notifications, so a tools/call carrying a progressToken
    # is answered as an SSE stream (progress events, then the result). Everything else stays JSON.
    streaming = StreamableHTTPSessionManager(app=server._lowlevel_server, json_response=False, stateless=True,
                                             security_settings=security, max_request_body_size=MAX_MCP_BODY)
    app.state.mcp_streaming = streaming
    return server, McpBoundary(transport, access, app.state.artifacts, transfers, StreamableHTTPASGIApp(streaming))


MAX_MCP_BODY = 32 * 1024 * 1024


async def buffered(receive, limit):
    """Read the whole request body (bounded) and return it with a receive that replays it."""
    chunks, size, more = [], 0, True
    while more:
        message = await receive()
        if message['type'] != 'http.request':
            return None, receive
        chunk = message.get('body', b'')
        size += len(chunk)
        if size > limit:
            return None, None
        chunks.append(chunk)
        more = message.get('more_body', False)
    body, sent = b''.join(chunks), False

    async def replay():
        nonlocal sent
        if not sent:
            sent = True
            return {'type': 'http.request', 'body': body, 'more_body': False}
        return await receive()
    return body, replay


def wants_progress(body):
    try:
        message = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return False
    params = message.get('params') if isinstance(message, dict) else None
    meta = params.get('_meta') if isinstance(params, dict) else None
    return message.get('method') == 'tools/call' and isinstance(meta, dict) and meta.get('progressToken') is not None


class McpBoundary:
    """Bearer accepted only on MCP, never granting browser, service or administrative access."""
    def __init__(self, app, access, artifacts, files, streaming=None):
        self.app, self.access, self.artifacts, self.files, self.streaming = app, access, artifacts, files, streaming
        self.buckets, self.lock = {}, threading.Lock()

    def rate(self, key, maximum):
        now = time.monotonic()
        with self.lock:
            if len(self.buckets) > 4096:
                self.buckets = {k: v for k, v in self.buckets.items() if v[0] > now - 60}
                if len(self.buckets) > 4096:
                    return False
            start, count = self.buckets.get(key, (now, 0))
            if start <= now - 60:
                start, count = now, 0
            self.buckets[key] = (start, count + 1)
            return count < maximum

    async def __call__(self, scope, receive, send):
        from starlette.requests import Request
        request = Request(scope)
        async def reply(status, message):
            return await JSONResponse({'detail': message}, status, headers={'Cache-Control': 'no-store', 'WWW-Authenticate': 'Bearer' } if status == 401 else {'Cache-Control': 'no-store'})(scope, receive, send)
        if request.headers.get('origin') not in {None, self.access.origin}:
            return await reply(403, 'Origin is not allowed')
        if not self.rate('ip:' + (request.client.host if request.client else ''), 300):
            return await reply(429, 'Too many MCP requests; wait one minute')
        grant = None
        if scope['path'].startswith('/mcp/files/'):
            # Transfer links carry their own short-lived, single-file authorization.
            grant = await anyio.to_thread.run_sync(self.files.grant, scope['path'][len('/mcp/files/'):])
            if grant is None:
                return await reply(404, 'Transfer link is invalid or expired; request a new one')
            identity = {'id': grant['token_id'], 'owner_id': grant['owner_id']}
        else:
            header = request.headers.get('authorization', '')
            try:
                if not header.startswith('Bearer '):
                    raise AccessDenied()
                identity = self.access.authenticate(header[7:])
            except AccessDenied:
                return await reply(401, 'Invalid, revoked or expired MCP token')
        if not self.rate('token:' + identity['id'], 180):
            return await reply(429, 'Too many MCP requests; wait one minute')
        accounts, uid = self.access.accounts, identity['owner_id']
        with accounts.request_lock:
            with accounts.db() as db:
                enabled = db.execute('SELECT 1 FROM users WHERE id=? AND enabled=1', (uid,)).fetchone()
            if enabled:
                accounts.inflight_requests[uid] = accounts.inflight_requests.get(uid, 0) + 1
        if not enabled:
            return await reply(401, 'Account disabled')
        token = OWNER.set(uid)
        async def secure_send(message):
            if message['type'] == 'http.response.start':
                message['headers'] = [(k, v) for k, v in message.get('headers', []) if k.lower() != b'cache-control'] + [(b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff')]
            await send(message)
        try:
            if grant is not None:
                return await self.files.serve(grant, scope, receive, secure_send)
            if scope['path'] == '/mcp/media':
                if request.method not in {'GET', 'HEAD'}:
                    return await reply(405, 'Use GET or HEAD to download')
                if 'read' not in identity['scopes']:
                    return await reply(403, 'Your token does not allow reading')
                try:
                    reference = ArtifactRef.model_validate(dict(request.query_params))
                    path = await anyio.to_thread.run_sync(partial(self.artifacts.resolve, reference.uri, reference.sha256))
                    response = FileResponse(path, filename=path.name)
                except (ValueError, NotOwned, FileNotFoundError):
                    return await reply(404, 'Resource unavailable')
                return await response(scope, receive, secure_send)
            if scope['path'] != '/mcp':
                return await reply(404, 'MCP route unavailable')
            if self.streaming and request.method == 'POST' and 'text/event-stream' in request.headers.get('accept', ''):
                body, receive = await buffered(receive, MAX_MCP_BODY)
                if receive is None:
                    return await reply(413, 'MCP request too large')
                if body is not None and wants_progress(body):
                    return await self.streaming(scope, receive, secure_send)
            return await self.app(scope, receive, secure_send)
        finally:
            OWNER.reset(token)
            with accounts.request_lock:
                count = accounts.inflight_requests[uid] - 1
                if count:
                    accounts.inflight_requests[uid] = count
                else:
                    accounts.inflight_requests.pop(uid, None)
