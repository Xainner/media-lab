// Media Lab ↔ runtime: job submission, history, polling and artifact URLs for the Media Lab creators.
import { useCallback, useEffect, useRef, useState } from 'react'
import { isAbortError, newSession, runtime, uploadFiles, waitJob, type ArtifactRef, type Job } from '../studio/lib/api'
import { api } from '../bridge'
import { DISTANCES, FOLLOWS, GUIDES, HEIGHTS, LANGUAGES, ORBITS, RESOLUTIONS, ratioOf, SOUND_KINDS, SPEAKERS, SWAP_MODES, VOICES, type Art, type Modality } from './data'

export type LabJob = { id: string; status: string; pct: number; queue?: number; error?: string; prompt: string; ratio: number; kind: Modality; model: string; ref?: ArtifactRef; more?: { ref: ArtifactRef; prompt: string }[] }
export type Caps = { turbo: boolean; h3Turbo: boolean; omni: boolean; fusedTurbo: boolean; bf16: boolean; turboPrecision: 'int8' | 'bf16'; swap: { character: boolean; head: boolean; remove: boolean; scail: boolean }; stems: boolean; faceRefine: boolean; upscale: boolean; ace: boolean; moss: boolean; control: Record<string, boolean>; camera: boolean; cutout: boolean; follow: Record<string, boolean>; loras: boolean
  flux3: boolean; kandinsky6: boolean; sound: Record<string, boolean>; speech: Record<string, boolean> }

/** Job operations each composer view lists after a reload; every request() operation must appear here. */
export const operations: Record<Modality, string[]> = { image: ['generate', 'edit'], video: ['video', 'swap', 'face_refine', 'remove', 'upscale'], audio: ['song', 'stems', 'sound', 'speech'] }
const ACTIVE = ['queued', 'running']

function modelLabel(job: Job & { request?: any }) {
  const r = job.request || {}
  if (job.operation === 'video' && r.model === 'kandinsky6') return 'Kandinsky 6'
  if (job.operation === 'sound') return r.kind === 'sfx' || r.kind === 'one_shot' ? 'Stable Audio 3 SFX' : 'Stable Audio 3'
  if (job.operation === 'speech') return ({ design: 'Qwen3-TTS · voz diseñada', clone: 'Qwen3-TTS · voz clonada' } as Record<string, string>)[r.voice] || 'Qwen3-TTS'
  if (job.operation === 'video') return `${({ turbo: 'H3 Turbo', fused_turbo: 'H3 Fused Turbo', omni: 'FastH3 Omni' } as Record<string, string>)[r.profile] || 'MiniMax H3'}${r.control ? ' · siguiendo un vídeo' : ''}${({ '480p': ' · 480p', '720p': ' · 720p', native: ' · nativa' } as Record<string, string>)[r.options?.resolution] || ''}`
  if (job.operation === 'swap') return ({ head: 'H3 Head Swap', scail: 'SCAIL-2' } as Record<string, string>)[r.mode] || 'H3 Character Swap'
  if (job.operation === 'face_refine') return 'H3 Face Refine'
  if (job.operation === 'remove') return 'H3 Person Remover'
  if (job.operation === 'stems') return 'Hybrid Demucs'
  if (job.operation === 'song') return r.model === 'ace_step' ? 'ACE-Step 1.5' : 'YuE2 3B'
  if (r.model === 'moss') return 'MOSS-Image'
  if (r.model === 'flux3') return job.operation === 'edit' ? 'FLUX 3 Klein · edición' : 'FLUX 3 Klein'
  const name = r.model_variant === 'turbo' ? 'Qwen Image 2.1 Turbo' : 'Qwen Image 2.1'
  if (r.camera) return `${name} · ángulo`
  if (r.remove_background) return `${name} · sin fondo`
  if (r.control) return `${name} · estructura`
  return job.operation === 'edit' ? `${name} · edición` : name
}

function toLab(job: Job & { request?: any }, kind: Modality): LabJob {
  const r = job.request || {}
  const ref = job.result?.media?.[0]
  const ratio = kind === 'audio' ? 1 : ref?.width && ref?.height ? ref.width / ref.height : ratioOf(r.aspect_ratio || (kind === 'video' ? '16:9' : '1:1'))
  return { id: job.id || job.job_id!, status: job.status, pct: job.status === 'completed' ? 100 : job.progress?.pct ?? 0, queue: job.queue_position,
    error: job.error, prompt: r.prompt || r.style || r.text || r.target || (r.camera ? Object.values(r.camera).join(', ') : '') || stemLabel[(ref as any)?.stem] || '', ratio, kind, model: modelLabel(job), ref,
    // Stems jobs return one song per stem; the rest follow the first on the canvas.
    more: (job.result?.media || []).slice(1).map((m: any) => ({ ref: m, prompt: stemLabel[m.stem] || '' })) }
}

/** Object URL (images, via /v1/review) or authenticated route (video/audio) for an artifact. */
export function useMediaSrc(ref?: ArtifactRef) {
  const [src, setSrc] = useState('')
  useEffect(() => {
    if (!ref) return
    let live = true
    const image = /\/(images|references)\//.test(ref.uri)
    void (image ? window.visualLab.runtime.preview(ref) : window.visualLab.runtime.mediaUrl(ref.uri)).then(url => { if (live) setSrc(url) }).catch(() => {})
    return () => { live = false }
  }, [ref?.uri, ref?.sha256])
  return src
}

export function useCaps() {
  const [caps, setCaps] = useState<Caps>({ turbo: false, h3Turbo: false, omni: false, fusedTurbo: false, bf16: false, turboPrecision: 'int8', swap: { character: false, head: false, remove: false, scail: false }, stems: false, faceRefine: false, upscale: false, ace: false, moss: false, control: {}, camera: false, cutout: false, follow: {}, loras: false, flux3: false, kandinsky6: false, sound: {}, speech: {} })
  useEffect(() => {
    let live = true
    runtime('GET', '/v1/capabilities').then(c => {
      if (!live) return
      const turbo = c.model_variants?.turbo?.precisions || {}
      setCaps({ turbo: Boolean(turbo.int8 || turbo.bf16), h3Turbo: Boolean(c.video?.profiles?.turbo?.ready), omni: Boolean(c.video?.profiles?.omni?.ready), fusedTurbo: Boolean(c.video?.profiles?.fused_turbo?.ready), bf16: Boolean(c.model_precisions?.bf16), turboPrecision: turbo.int8 ? 'int8' : 'bf16',
        swap: { character: Boolean(c.swap?.modes?.character?.ready), head: Boolean(c.swap?.modes?.head?.ready), remove: Boolean(c.remove?.ready), scail: Boolean(c.swap?.modes?.scail?.ready) }, stems: Boolean(c.stems?.ready), faceRefine: Boolean(c.face_refine?.ready), upscale: Boolean(c.upscale?.ready), ace: Boolean(c.music?.models?.ace_step?.ready), moss: Boolean(c.image_models?.moss?.ready),
        control: c.image_control?.modes || {}, camera: Boolean(c.image_camera?.ready), cutout: Boolean(c.image_remove_background?.ready), follow: c.video?.control?.modes || {}, loras: Boolean(c.loras?.ready),
        flux3: Boolean(c.image_models?.flux3?.ready), kandinsky6: Boolean(c.video?.models?.kandinsky6?.ready),
        sound: Object.fromEntries(Object.entries(c.sound?.kinds || {}).map(([k, v]: [string, any]) => [k, Boolean(v?.ready)])), speech: c.speech?.voices || {} })
    }).catch(() => {})
    return () => { live = false }
  }, [])
  return caps
}

/** The modality's recent jobs (newest first); queued/running ones are followed until they finish. */
export function useLabJobs(kind: Modality) {
  const [jobs, setJobs] = useState<LabJob[]>([])
  const [loaded, setLoaded] = useState(false)
  const followed = useRef(new Map<string, AbortController>())
  const upsert = (job: LabJob) => setJobs(list => list.some(j => j.id === job.id) ? list.map(j => j.id === job.id ? job : j) : [job, ...list])
  const follow = (id: string) => {
    if (followed.current.has(id)) return
    const controller = new AbortController()
    followed.current.set(id, controller)
    waitJob(id, job => upsert(toLab(job, kind)), controller.signal)
      .catch(error => { if (!isAbortError(error)) setJobs(list => list.map(j => j.id === id ? { ...j, status: 'failed', error: String(error.message || error) } : j)) })
      .finally(() => followed.current.delete(id))
  }
  useEffect(() => {
    let live = true
    setJobs([]); setLoaded(false)
    runtime('GET', '/v1/jobs').then(value => {
      if (!live) return
      const mine = (value.items as Job[]).filter(j => operations[kind].includes(j.operation) && (j.status !== 'completed' || j.result?.media?.length))
      setJobs(mine.slice(0, 60).map(j => toLab(j, kind)))
      for (const j of mine) if (ACTIVE.includes(j.status)) follow(j.id)
    }).catch(() => {}).finally(() => { if (live) setLoaded(true) })
    const current = followed.current
    return () => { live = false; for (const c of current.values()) c.abort(); current.clear() }
  }, [kind])
  const add = (accepted: any, request: any, operation: string) => {
    const id = accepted.job_id || accepted.id
    upsert(toLab({ ...accepted, id, operation, status: accepted.status || 'queued', request, activity: [] } as Job, kind))
    follow(id)
  }
  const busy = jobs.filter(j => ACTIVE.includes(j.status))
  return { jobs, loaded, add, busy }
}

export type LoraPick = { id: string; strength?: number }
export type Submission = { kind: Modality; prompt: string; lyrics?: string; modelId: string; values: Record<string, string>; count: number; refs: ArtifactRef[]; source?: ArtifactRef | null; loras?: LoraPick[]
  consent?: boolean
  /** ACE-Step tempo, key, meter and sung language, set by the IA pass. */
  music?: { bpm?: number; key?: string; time_signature?: string; language?: string } }

const seconds = (v: string) => { const [m, s] = v.split(':').map(Number); return s === undefined ? parseFloat(v) : m * 60 + s }

/** Kandinsky lips follow lines marked <S>…<E>; quoted dialogue becomes those marks unless the prompt already has them. */
export const speechTags = (prompt: string) => /<S>/.test(prompt) ? prompt : prompt.replace(/[«“"]([^«»“”"]+)[»”"]/g, '<S>$1<E>')

/** Build the runtime request(s) for one composer submission. Images fan out to one job per requested copy. */
export function requests(s: Submission): { path: string; body: any; operation: string }[] {
  const session_id = newSession()
  const loras = s.loras?.length && loraBase(s) ? { loras: s.loras } : {}
  // Structure, angle and cutout are Qwen recipes, whichever model the picker last showed.
  if (s.kind === 'image' && s.modelId === 'flux3-klein' && (s.values.mode || 'Crear') === 'Crear') {
    // Klein's upsampler rewrites every request; references (up to 4) make it an edit.
    const quality = s.values.quality === 'Borrador' ? 'draft' : 'quality'
    const body = s.refs.length
      ? { path: '/v1/jobs/edit', operation: 'edit', body: { model: 'flux3', prompt: s.prompt, references: s.refs.slice(0, 4), session_id } }
      : { path: '/v1/jobs/generate', operation: 'generate', body: { model: 'flux3', prompt: s.prompt, aspect_ratio: s.values.aspect, quality, session_id } }
    return Array.from({ length: s.count }, () => body)
  }
  if (s.kind === 'image') {
    const quality = s.values.quality === 'Borrador' ? 'draft' : 'quality'
    const model_variant = s.modelId === 'qwen-turbo' ? 'turbo' : 'base'
    if (s.values.mode === 'Quitar fondo')
      return [{ path: '/v1/jobs/edit', operation: 'edit', body: { prompt: '', references: s.refs.slice(0, 1), remove_background: true, session_id } }]
    if (s.values.mode === 'Ángulo') {
      // One re-shoot per copy; the QMA recipe fixes steps, CFG and the base model.
      const camera = { azimuth: ORBITS[s.values.orbit], elevation: HEIGHTS[s.values.height], distance: DISTANCES[s.values.distance] }
      return Array.from({ length: s.count }, () => ({ path: '/v1/jobs/edit', operation: 'edit', body: { prompt: s.prompt, references: s.refs.slice(0, 1), camera, resolution: 1024, session_id, ...loras } }))
    }
    if (s.values.mode === 'Estructura') {
      const control = { reference: s.refs[0], mode: GUIDES[s.values.guide] }
      return Array.from({ length: s.count }, () => ({ path: '/v1/jobs/generate', operation: 'generate', body: { prompt: s.prompt, aspect_ratio: s.values.aspect, quality,
        model_variant: s.modelId === 'moss-image' ? 'base' : model_variant, control, session_id, ...loras } }))
    }
    const body = s.refs.length
      ? { path: '/v1/jobs/edit', operation: 'edit', body: { prompt: s.prompt, references: s.refs, quality, model_variant, session_id, ...loras } }
      : s.modelId === 'moss-image' ? { path: '/v1/jobs/generate', operation: 'generate', body: { model: 'moss', prompt: s.prompt, aspect_ratio: s.values.aspect, quality, session_id } }
      : { path: '/v1/jobs/generate', operation: 'generate', body: { prompt: s.prompt, aspect_ratio: s.values.aspect, quality, model_variant, session_id, ...loras } }
    return Array.from({ length: s.count }, () => body)
  }
  if (s.kind === 'audio' && s.modelId === 'stable-audio3')
    return [{ path: '/v1/jobs/sound', operation: 'sound', body: { prompt: s.prompt, kind: SOUND_KINDS[s.values.sound] || 'music', seconds: seconds(s.values.length), session_id } }]
  if (s.kind === 'audio' && s.modelId === 'qwen3-tts') {
    // The second box is the delivery (preset), the voice description (design) or what the reference says (clone).
    const voice = VOICES[s.values.voice] || 'preset', extra = s.lyrics?.trim() || ''
    return [{ path: '/v1/jobs/speech', operation: 'speech', body: { text: s.prompt, voice, language: LANGUAGES[s.values.language] || 'auto', session_id,
      ...(voice === 'preset' ? { speaker: SPEAKERS[s.values.speaker] || 'serena', instruct: extra } : voice === 'design' ? { instruct: extra }
        : { reference: s.source, reference_text: extra, consent: Boolean(s.consent) }) } }]
  }
  if (s.kind === 'audio' && s.values.type === 'Separar pistas')
    return [{ path: '/v1/jobs/stems', operation: 'stems', body: { audio: s.source, stems: s.values.stems === '4 pistas' ? 'four' : 'two', session_id } }]
  if (s.kind === 'video' && s.values.mode === 'Escalar')
    return [{ path: '/v1/jobs/upscale', operation: 'upscale', body: { video: s.source, scale: s.values.scale === '×4' ? 4 : 2, quality: s.values.finish === 'Calidad' ? 'quality' : 'fast', session_id } }]
  if (s.kind === 'video' && SWAP_MODES[s.values.mode] === 'remove') {
    // The prompt says who to erase; an attached image is the clean first frame.
    return [{ path: '/v1/jobs/remove', operation: 'remove', body: { video: s.source, target: s.prompt, clean_frame: s.refs[0] ?? null, session_id } }]
  }
  if (s.kind === 'video' && SWAP_MODES[s.values.mode]) {
    // The prompt is who to replace; the source clip sets size, length and soundtrack.
    const mode = SWAP_MODES[s.values.mode] === 'character' && s.values.engine === 'SCAIL-2' ? 'scail' : SWAP_MODES[s.values.mode]
    return [{ path: '/v1/jobs/swap', operation: 'swap', body: { mode, video: s.source, character: s.refs[0],
      target: s.prompt, session_id } }]
  }
  if (s.kind === 'video' && s.modelId === 'kandinsky6') {
    const i2v = s.values.mode === 'Imagen inicial' && s.refs.length > 0
    return [{ path: '/v1/jobs/video', operation: 'video', body: { model: 'kandinsky6', prompt: speechTags(s.prompt), mode: i2v ? 'i2v' : 't2v', first_frame: i2v ? s.refs[0] : null,
      aspect_ratio: s.values.aspect === '9:16' ? '9:16' : '16:9', seconds: 5, session_id, ...(s.lyrics?.trim() ? { audio_prompt: s.lyrics.trim() } : {}) } }]
  }
  if (s.kind === 'video') {
    const follow = s.values.mode === 'Seguir vídeo'
    const mode = s.values.mode === 'Imagen inicial' ? 'i2v' : s.values.mode === 'Referencias' || follow ? 'r2v' : 't2v'
    // Preview is the runtime default, so it is left out and older requests keep their fingerprint.
    const resolution = RESOLUTIONS[s.values.resolution] || 'preview'
    return [{ path: '/v1/jobs/video', operation: 'video', body: { prompt: s.prompt, mode, first_frame: mode === 'i2v' ? s.refs[0] ?? null : null,
      references: mode === 'r2v' ? s.refs : [], aspect_ratio: s.values.aspect, seconds: seconds(s.values.duration),
      profile: ({ 'h3-turbo': 'turbo', 'h3-fused': 'fused_turbo', 'fasth3-omni': 'omni' } as Record<string, string>)[s.modelId] || 'base', session_id, ...loras,
      ...(resolution !== 'preview' ? { options: { resolution } } : {}),
      ...(follow ? { control: { video: s.source, mode: FOLLOWS[s.values.follow] || 'pose', keep_audio: true } } : {}) } }]
  }
  const cover = s.values.type === 'Cover'
  if (s.modelId === 'ace-step' && !cover) {
    // ACE-Step renders the exact length; YuE2 below treats it as a cap.
    return [{ path: '/v1/jobs/song', operation: 'song', body: { model: 'ace_step', style: s.prompt, lyrics: s.values.type === 'Instrumental' ? '[Instrumental]' : (s.lyrics?.trim() || '[Instrumental]'),
      max_duration: seconds(s.values.duration), session_id, ...s.music } }]
  }
  const lyrics = s.values.type === 'Instrumental' ? '[Instrumental]' : (s.lyrics?.trim() || '[Instrumental]')
  return [{ path: '/v1/jobs/song', operation: 'song', body: { style: s.prompt, lyrics, mode: cover ? 'melody' : 'full', source_audio: cover ? s.source ?? null : null,
    max_duration: seconds(s.values.duration), steps: 32, session_id } }]
}

/** The viewer's AI provider, if one is configured and enabled (Cuenta → Proveedores IA). */
export function useProvider() {
  const [provider, setProvider] = useState<{ ready: boolean; model: string }>({ ready: false, model: '' })
  useEffect(() => {
    let live = true
    api('GET', '/v1/account/providers').then(v => { if (live) setProvider({ ready: Boolean(v.active?.configured), model: v.active?.model || '' }) }).catch(() => {})
    return () => { live = false }
  }, [])
  return provider
}

/** Rewrite the submission's prompt with the viewer's provider, following the target model's guide. Covers have no guide and pass through. */
export async function improve(s: Submission): Promise<Submission> {
  if (s.kind === 'video' && (SWAP_MODES[s.values.mode] || s.values.mode === 'Escalar')) return s
  // These models rewrite or read the text themselves: FLUX's and Stable Audio's official upsamplers, the exact words of a voice.
  if (['stable-audio3', 'qwen3-tts'].includes(s.modelId) || (s.modelId === 'flux3-klein' && (s.values.mode || 'Crear') === 'Crear')) return s
  if (s.kind === 'image' && (s.values.mode === 'Ángulo' || s.values.mode === 'Quitar fondo')) return s
  if (s.modelId === 'kandinsky6') {
    // Kandinsky's beautifier keeps the request's language, but the model learned English captions: the provider translates the scene and keeps the words.
    const brief = [`Scene: ${s.prompt}`, s.lyrics?.trim() ? `Voice and sounds: ${s.lyrics.trim()}` : ''].filter(Boolean).join('\n\n')
    const v = await window.visualLab.agent.improve(brief, 'kandinsky', s.values.mode === 'Imagen inicial' ? s.refs.slice(0, 1) : [])
    return { ...s, prompt: v.prompt?.trim() || s.prompt, lyrics: v.audio_prompt?.trim() || s.lyrics }
  }
  if (s.kind === 'audio') {
    if (s.values.type === 'Cover' || s.values.type === 'Separar pistas') return s
    // With IA on, the first box is the idea of the song; the provider writes the style and, unless supplied, the lyrics.
    const instrumental = s.values.type === 'Instrumental', lyrics = s.lyrics?.trim(), ace = s.modelId === 'ace-step'
    const brief = [`Song idea (a description of the song, not lyrics): ${s.prompt}`,
      instrumental ? 'Instrumental: no vocals.' : lyrics ? `Lyrics supplied by the user (keep verbatim):\n${lyrics}` : 'No lyrics supplied: write original lyrics.',
      `Length: ${s.values.duration || '2:00'}${ace ? ' (exact)' : ' (upper bound)'}.`].join('\n\n')
    const { prompt, lyrics: written, ...music } = await window.visualLab.agent.improve(brief, ace ? 'ace_song' : 'song')
    return { ...s, prompt: prompt || s.prompt, lyrics: instrumental ? s.lyrics : written || s.lyrics, ...(ace ? { music } : {}) }
  }
  // A structure guide only fixes the layout and is a Qwen recipe: the prompt still describes the whole new image.
  const [mode, refs] = s.kind === 'image' ? (s.modelId === 'moss-image' && s.values.mode !== 'Estructura' ? ['moss', []] as const
    : s.refs.length && s.values.mode !== 'Estructura' ? ['i2i', s.refs] as const : ['t2i', []] as const)
    : s.values.mode === 'Imagen inicial' ? ['i2v', s.refs.slice(0, 1)] as const : s.values.mode === 'Referencias' || s.values.mode === 'Seguir vídeo' ? ['r2v', s.refs] as const : ['t2v', []] as const
  // A followed clip sets its own length, unknown here.
  const v = await window.visualLab.agent.improve(s.prompt, mode, [...refs], s.kind === 'video' && s.values.mode !== 'Seguir vídeo' ? seconds(s.values.duration) : undefined)
  return { ...s, prompt: v.prompt?.trim() || s.prompt }
}

export async function submit(s: Submission, add: (accepted: any, request: any, operation: string) => void) {
  for (const r of requests(s)) add(await runtime('POST', r.path, r.body), r.body, r.operation)
}

export async function uploadImages(files: File[]) {
  const result = await uploadFiles(files, newSession())
  if (result.errors.length && !result.refs.length) throw new Error(result.errors.map(e => `${e.name}: ${e.message}`).join('\n'))
  return result.refs
}

/** What a dropped file is for: a reference image, or an audio/video source. */
export const droppedKind = (file: File): 'image' | 'media' | null =>
  /^image\//.test(file.type) || /\.(png|jpe?g|webp)$/i.test(file.name) ? 'image'
    : /^(audio|video)\//.test(file.type) || /\.(flac|wav|mp3|ogg|opus|mp4|webm|mkv|mov)$/i.test(file.name) ? 'media' : null

/** Opens the file picker, or uploads a dropped audio or video file. */
export const uploadAudio = (file?: File) => window.visualLab.runtime.uploadMedia(newSession(), file).then(r => r?.data as ArtifactRef | undefined)
export const download = (ref: ArtifactRef) => window.visualLab.runtime.saveMedia(ref.uri)

export type FaceStrength = 'light' | 'medium' | 'strong'
/** Queue a face refine of an owned video; a swap result keeps its character as the identity on the server. */
export const refineFace = (video: ArtifactRef, strength: FaceStrength) =>
  runtime('POST', '/v1/jobs/face_refine', { video: { uri: video.uri, sha256: video.sha256 }, strength, session_id: newSession() })

const libraryKind: Record<string, Modality> = { images: 'image', references: 'image', videos: 'video', productions: 'video', songs: 'audio', sources: 'audio' }
const operationLabel: Record<string, string> = { generate: 'Qwen Image 2.1', edit: 'Qwen Image 2.1 · edición', video: 'MiniMax H3', song: 'YuE2 3B', production: 'Videoclip', upscale: 'FlashVSR', swap: 'Cambio de personaje', face_refine: 'Cara refinada', remove: 'Persona quitada', stems: 'Hybrid Demucs', sound: 'Stable Audio 3', speech: 'Qwen3-TTS' }
const stemLabel: Record<string, string> = { vocals: 'Voz', instrumental: 'Instrumental', drums: 'Batería', bass: 'Bajo', other: 'Otros instrumentos' }
const kindLabel: Record<string, string> = { references: 'Referencia subida', sources: 'Audio subido', productions: 'Videoclip' }

/** A library row as a canvas tile. */
export function libraryArt(i: any): Art {
  const kind = libraryKind[i.kind] || 'image'
  const ratio = i.width && i.height ? i.width / i.height : kind === 'audio' ? 1 : kind === 'video' ? 16 / 9 : 1
  return { id: i.uri, src: '', ref: { uri: i.uri, sha256: i.sha256, width: i.width, height: i.height }, ratio, kind, created: i.created_at,
    prompt: i.prompt || i.style || i.text || i.title || i.input_prompt || stemLabel[i.stem] || '', model: kindLabel[i.kind] || operationLabel[i.operation] || i.model || 'Media Lab' }
}

export const LIBRARY_CHANGED = 'ml-library-changed'

/** Permanently delete an owned file after the shared confirmation dialog. Resolves false when the viewer backs out. */
export async function removeMedia(ref: ArtifactRef) {
  if (!await window.visualLab.ui.confirm('gallery-remove')) return false
  await runtime('DELETE', `/v1/library?${new URLSearchParams({ uri: ref.uri, sha256: ref.sha256 })}`)
  window.dispatchEvent(new CustomEvent(LIBRARY_CHANGED, { detail: ref.uri }))
  return true
}

/** A page-at-a-time view of the viewer's library, filtered by kind and text. Deletions elsewhere drop out live. */
export function useLibrary(kind: string, query: string, page = 48) {
  const [items, setItems] = useState<Art[]>([])
  const [next, setNext] = useState<number | null>(0)
  const [total, setTotal] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const load = async (offset: number, reset = false) => {
    setBusy(true); setError('')
    try {
      const v = await runtime('GET', `/v1/library?${new URLSearchParams({ limit: String(page), offset: String(offset), q: query, kind })}`)
      const rows = (v.items as any[]).map(libraryArt)
      setItems(list => reset ? rows : [...list, ...rows]); setNext(v.next_offset ?? null); setTotal(v.total ?? rows.length)
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) } finally { setBusy(false) }
  }
  useEffect(() => { void load(0, true) }, [kind, query])
  useEffect(() => {
    const drop = (e: Event) => { const uri = (e as CustomEvent).detail; setItems(list => list.filter(a => a.id !== uri)); setTotal(t => Math.max(0, t - 1)) }
    window.addEventListener(LIBRARY_CHANGED, drop)
    return () => window.removeEventListener(LIBRARY_CHANGED, drop)
  }, [])
  return { items, total, busy, error, more: next !== null ? () => void load(next) : null, reload: () => void load(0, true) }
}

/** The viewer's latest images, videos, videoclips and songs, newest first, as canvas tiles. */
export function useCreations(limit = 24) {
  const [items, setItems] = useState<Art[]>([])
  useEffect(() => {
    let live = true
    runtime('GET', `/v1/library?limit=${limit * 3}`).then(value => {
      if (!live) return
      setItems((value.items as any[]).filter(i => ['images', 'videos', 'productions', 'songs'].includes(i.kind)).slice(0, limit).map(libraryArt))
    }).catch(() => {})
    return () => { live = false }
  }, [limit])
  return items
}

export type LoraBase = 'qwen' | 'h3'
export type Character = { id: string; handle: string; name: string; description: string; references: ArtifactRef[]
  lora: { id: string; name: string; base: LoraBase | null; trigger: string; strength: number; status: string } | null }
export type Lora = { id: string; name: string; base: LoraBase | null; source_url: string; page?: string | null; trigger: string; strength: number
  status: 'downloading' | 'ready' | 'error'; error?: string | null; bytes?: number | null; total?: number | null }
export const LORA_BASES: Record<LoraBase, string> = { qwen: 'Imagen · Qwen-Image 2.1', h3: 'Vídeo · MiniMax H3' }

/** The base a submission's LoRAs must match, or null when that job takes none. */
export function loraBase(s: Pick<Submission, 'kind' | 'modelId' | 'values'>): LoraBase | null {
  if (s.kind === 'image') return s.modelId === 'moss-image' || s.modelId === 'flux3-klein' || s.values.mode === 'Quitar fondo' ? null : 'qwen'
  if (s.kind === 'video') return SWAP_MODES[s.values.mode] || s.modelId === 'kandinsky6' ? null : 'h3'
  return null
}

const MENTION = /@([A-Za-z0-9_]{2,24})(?![A-Za-z0-9_])/g

/** Characters named with @handle in a prompt, in order of first mention. */
export function mentioned(prompt: string, characters: Character[]) {
  const found: Character[] = []
  for (const m of prompt.matchAll(MENTION)) {
    const c = characters.find(x => x.handle === m[1].toLowerCase())
    if (c && !found.includes(c)) found.push(c)
  }
  return found
}

/** Expand @handles: their images join the references (named the way the model reads them) and their LoRAs join the job. */
export function withCharacters(s: Submission, characters: Character[]): Submission {
  const people = mentioned(s.prompt, characters)
  const base = loraBase(s)
  const loras = base ? [...s.loras || []] : []
  for (const c of people) if (c.lora?.status === 'ready' && c.lora.base === base && !loras.some(l => l.id === c.lora!.id)) loras.push({ id: c.lora.id })
  if (!people.length) return { ...s, loras: loras.slice(0, 4) }
  const swap = s.kind === 'video' && !!SWAP_MODES[s.values.mode]
  // Qwen edits read <imageN>; H3 Ref2VA reads <Picture N>. A swap takes the character as its image.
  // Kandinsky takes no references: a character is described in words (its first photo can be the opening frame).
  const k6 = s.kind === 'video' && s.modelId === 'kandinsky6'
  const takesRefs = s.kind === 'image' ? (s.values.mode || 'Crear') === 'Crear' && s.modelId !== 'moss-image' : s.kind === 'video' && !swap && !k6
  const values = s.kind === 'video' && !swap && !k6 && ['Texto', 'Imagen inicial'].includes(s.values.mode) ? { ...s.values, mode: 'Referencias' } : s.values
  let refs = [...s.refs], prompt = s.prompt
  for (const c of people) {
    const token = new RegExp(`@${c.handle}(?![A-Za-z0-9_])`, 'gi')
    if (swap) {
      if (!refs.length && c.references[0]) refs = [c.references[0]]
      prompt = prompt.replace(token, '').replace(/\s{2,}/g, ' ').trim()
    } else if (takesRefs && c.references.length) {
      refs = [...refs, ...c.references.filter(r => !refs.some(x => x.sha256 === r.sha256))]
      const n = refs.findIndex(x => x.sha256 === c.references[0].sha256) + 1
      const label = s.kind === 'video' ? `<Picture ${n}>` : `<image${n}>`
      prompt = prompt.replace(token, c.description ? `${label} (${c.description})` : label)
    } else prompt = prompt.replace(token, c.description || c.name)
  }
  return { ...s, prompt, values, refs: refs.slice(0, s.kind === 'video' ? 9 : s.modelId === 'flux3-klein' ? 4 : 10), loras: loras.slice(0, 4) }
}

const CHARACTERS_CHANGED = 'ml-characters-changed'
const changed = <T,>(value: T) => { window.dispatchEvent(new Event(CHARACTERS_CHANGED)); return value }
export const plain = (e: unknown) => (e instanceof Error ? e.message : String(e)).replace(/^Runtime \d+: /, '')

/** The viewer's characters and LoRA library, kept fresh across pages and while LoRAs download. */
export function useCharacters() {
  const [characters, setCharacters] = useState<Character[]>([])
  const [loras, setLoras] = useState<Lora[]>([])
  const [ready, setReady] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const reload = useCallback(async () => {
    try {
      const [c, l] = await Promise.all([runtime('GET', '/v1/characters'), runtime('GET', '/v1/loras')])
      setCharacters(c.items || []); setLoras(l.items || []); setReady(Boolean(l.ready))
    } catch { /* Keep what is shown. */ } finally { setLoaded(true) }
  }, [])
  useEffect(() => {
    void reload()
    const again = () => void reload()
    window.addEventListener(CHARACTERS_CHANGED, again)
    return () => window.removeEventListener(CHARACTERS_CHANGED, again)
  }, [reload])
  const downloading = loras.some(l => l.status === 'downloading')
  useEffect(() => {
    if (!downloading) return
    const timer = setInterval(() => void runtime('GET', '/v1/loras').then(l => setLoras(l.items || [])).catch(() => {}), 2500)
    return () => clearInterval(timer)
  }, [downloading])
  return { characters, loras, ready, loaded, reload }
}

export type CharacterDraft = { handle: string; name: string; description: string; references: ArtifactRef[]; lora_id: string | null }
export const saveCharacter = (draft: CharacterDraft, id?: string) =>
  runtime(id ? 'PUT' : 'POST', id ? `/v1/characters/${id}` : '/v1/characters', { ...draft, references: draft.references.map(r => ({ uri: r.uri, sha256: r.sha256 })) }).then(changed)
export const deleteCharacter = (id: string) => runtime('DELETE', `/v1/characters/${id}`).then(changed)
export const addLora = (url: string) => runtime('POST', '/v1/loras', { url }).then(changed)
export const editLora = (id: string, values: { name?: string; trigger?: string; strength?: number }) => runtime('PATCH', `/v1/loras/${id}`, values).then(changed)
export const deleteLora = (id: string) => runtime('DELETE', `/v1/loras/${id}`).then(changed)
