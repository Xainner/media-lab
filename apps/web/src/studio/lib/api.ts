export type ArtifactRef = { uri: string; sha256: string; width?: number; height?: number; has_alpha?: boolean }
export type UploadError = { name: string; message: string }
export type UploadResult = { refs: ArtifactRef[]; errors: UploadError[] }

export type Job = {
  id: string
  job_id?: string
  session_id: string
  operation: 'generate' | 'edit' | 'video' | 'song' | 'production' | 'upscale' | 'swap' | 'face_refine' | 'remove' | 'stems' | 'sound' | 'speech'
  status: string
  activity: string[]
  progress?: { pct: number; step: number; steps: number; node: string }
  queue_position?: number
  gpu?: number | null
  preview_seq?: number
  result?: { media: ArtifactRef[]; data: Record<string, any> }
  error?: string
}

const ACCEPTED_IMAGE_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp'])
const MAX_UPLOAD_BYTES = 20 * 1024 * 1024

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error)
}

function abortError() {
  const error = new Error('La operación fue cancelada.')
  error.name = 'AbortError'
  return error
}

function throwIfAborted(signal?: AbortSignal) {
  if (signal?.aborted) throw abortError()
}

export function isAbortError(error: unknown) {
  return Boolean(error && typeof error === 'object' && 'name' in error && (error as { name?: string }).name === 'AbortError')
}

function sleep(ms: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError())
      return
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort)
      resolve()
    }, ms)
    const onAbort = () => {
      clearTimeout(timer)
      reject(abortError())
    }
    signal?.addEventListener('abort', onAbort, { once: true })
  })
}

function runtimeStatus(error: unknown) {
  const match = errorMessage(error).match(/^Runtime (\d{3}):/)
  return match ? Number(match[1]) : null
}

export async function runtime(method: string, path: string, body?: unknown) {
  return window.visualLab.runtime.request(method, path, body)
}

export async function uploadFiles(files: File[], sessionId: string): Promise<UploadResult> {
  const refs: ArtifactRef[] = []
  const errors: UploadError[] = []
  for (const file of files.slice(0, 16)) {
    if (file.size > MAX_UPLOAD_BYTES) {
      errors.push({ name: file.name, message: 'El archivo supera el límite de 20 MiB.' })
      continue
    }
    if (file.type && !ACCEPTED_IMAGE_TYPES.has(file.type)) {
      errors.push({ name: file.name, message: 'Tipo de imagen no permitido.' })
      continue
    }
    try {
      const result = await window.visualLab.runtime.upload({
        name: file.name,
        type: file.type,
        bytes: new Uint8Array(await file.arrayBuffer()),
        sessionId,
      })
      refs.push(result.data)
    } catch (error) {
      errors.push({ name: file.name, message: errorMessage(error) })
    }
  }
  return { refs, errors }
}

export function formatUploadErrors(errors: UploadError[]) {
  return errors.map(error => `${error.name}: ${error.message}`).join('\n')
}

/** Broadcast job status changes so the shell and the mascot can react (detail: { id, status, operation }). */
export const JOB_EVENT = 'rvl-job'
const TERMINAL = ['completed', 'failed', 'cancelled', 'interrupted', 'blocked_gpu']
function announce(job: Job, previous: string) {
  // A job recovered already finished (first poll) is history, not news.
  if (!previous && TERMINAL.includes(job.status)) return
  if (job.status !== previous && typeof window !== 'undefined')
    window.dispatchEvent(new CustomEvent(JOB_EVENT, { detail: { id: job.id || job.job_id, status: job.status, operation: job.operation } }))
}

export async function waitJob(jobId: string, onUpdate: (job: Job) => void, signal?: AbortSignal): Promise<Job> {
  let transientStarted = 0
  let lastStatus = ''
  for (;;) {
    throwIfAborted(signal)
    let job: Job
    try {
      job = await runtime('GET', `/v1/jobs/${encodeURIComponent(jobId)}`) as Job
      throwIfAborted(signal)
      transientStarted = 0
    } catch (error) {
      if (isAbortError(error) || signal?.aborted) throw error
      const status = runtimeStatus(error)
      if (status && status >= 400 && status < 500 && status !== 408 && status !== 429) throw error
      const now = Date.now()
      if (!transientStarted) transientStarted = now
      if (now - transientStarted >= 60000) throw error
      await sleep(2500, signal)
      continue
    }
    onUpdate(job)
    announce(job, lastStatus)
    lastStatus = job.status
    if (['completed', 'failed', 'cancelled', 'interrupted', 'blocked_gpu'].includes(job.status)) return job
    await sleep(1250, signal)
  }
}

export async function dataUrl(uri: string) {
  return window.visualLab.runtime.artifactData(uri)
}

export function cancelJob(jobId: string) {
  return runtime('DELETE', `/v1/jobs/${encodeURIComponent(jobId)}`)
}

export function clearRecoveryValue(key: string, expected: string) {
  if (localStorage.getItem(key) === expected) localStorage.removeItem(key)
}

export function clearRecoveryJob(key: string, jobId: string) {
  const raw = localStorage.getItem(key)
  if (!raw) return
  try {
    if (JSON.parse(raw)?.jobId === jobId) localStorage.removeItem(key)
  } catch {
    return
  }
}

export type EnhancerMode = 'manual' | 'external' | 'off'
const ENHANCER_KEY = 'media-lab:enhancer-mode'

export function getEnhancerMode(): EnhancerMode {
  try {
    const value = localStorage.getItem(ENHANCER_KEY)
    if (value === 'manual' || value === 'external' || value === 'off') return value
    if (value === 'qwen' || value === 'compare') localStorage.setItem(ENHANCER_KEY, 'manual')
  } catch { }
  return 'manual'
}

export function setEnhancerMode(value: EnhancerMode) {
  try { localStorage.setItem(ENHANCER_KEY, value) } catch { }
}

export type AnimationMode = 'live' | 'simulated' | 'off'
const ANIMATION_KEY = 'media-lab:animation-mode'
export const ANIMATION_EVENT = 'media-lab:animation-mode'

export function getAnimationMode(): AnimationMode {
  try {
    const value = localStorage.getItem(ANIMATION_KEY)
    if (value === 'simulated' || value === 'off') return value
  } catch { }
  return 'live'
}

export function setAnimationMode(value: AnimationMode) {
  try { localStorage.setItem(ANIMATION_KEY, value) } catch { }
  window.dispatchEvent(new Event(ANIMATION_EVENT))
}

export type ImproveMode = 't2i' | 'i2i' | 't2v' | 'i2v' | 'r2v' | 'song'

export async function enhancePrompt(_source: 'external', prompt: string, mode: 't2i' | 'i2i', references: ArtifactRef[] = []): Promise<string> {
  return (await window.visualLab.agent.improve(prompt, mode, references)).prompt
}

export function deleteGalleryImage(ref: ArtifactRef) {
  return runtime('DELETE', `/v1/gallery?uri=${encodeURIComponent(ref.uri)}&sha256=${encodeURIComponent(ref.sha256)}`)
}

export function newSession() {
  return `sess_${crypto.randomUUID().replaceAll('-', '').slice(0, 12)}`
}

export async function saveMessage(session: string, role: 'user' | 'assistant' | 'tool', content: string, media: ArtifactRef[] = []) {
  try { await runtime('POST', `/v1/sessions/${session}/messages`, { role, content, media }) } catch { /* persistence must not break the turn */ }
}
