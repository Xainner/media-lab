let csrf = ''
let user = ''
let accountEpoch = 0
const urls = new Map<string, string>()
const streams = new Set<EventSource>()
export const isWeb = true

export async function request(method: string, route: string, body?: unknown, key?: string) {
  if (!route.startsWith('/v1/') || route.startsWith('//') || /[\r\n\\]/.test(route)) throw new Error('Ruta no permitida')
  const headers: Record<string, string> = {}
  if (!['GET', 'HEAD'].includes(method)) headers['X-CSRF-Token'] = csrf
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (key) headers['Idempotency-Key'] = key
  else if (method === 'POST' && route === '/v1/agent/runs') headers['Idempotency-Key'] = crypto.randomUUID()
  const response = await fetch(route, { method, credentials: 'same-origin', redirect: 'error', headers,
    ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
  if (!response.ok) {
    if (response.status === 401) { clearBrowser(); window.dispatchEvent(new Event('rvl-logged-out')) }
    let detail = 'Operación no disponible'
    try {
      const data = await response.json()
      if (typeof data.detail === 'string') detail = data.detail
      else if (Array.isArray(data.detail)) {
        const labels:Record<string,string>={model:'modelo',api_key:'clave API',username:'nombre de usuario',email:'correo',password:'contraseña',prompt:'descripción',code:'código de verificación'}
        const fields=[...new Set(data.detail.map((item:any)=>labels[String(item.loc?.at(-1))]||'datos del formulario'))]
        detail='Revisa los campos: '+fields.join(', ')+'. Comprueba que estén completos y respeten los límites indicados.'
      }
    } catch {}
    throw new Error(`Runtime ${response.status}: ${detail}`)
  }
  return response
}

export async function api(method: string, route: string, body?: unknown) {
  const response = await request(method, route, body)
  return response.json()
}

export async function session() {
  const current = await api('GET', '/v1/auth/session')
  csrf = current.csrf
  return current
}

export function setSession(current: any) { csrf = current.csrf }

const OLD_PREFIX = 'rinari-visual-lab:'

// 0.14.1 renamed the browser storage prefix: carry preferences and job recovery over once.
export function migrateStorage() {
  for (const key of Object.keys(localStorage)) {
    if (!key.startsWith(OLD_PREFIX)) continue
    const next = 'media-lab:' + key.slice(OLD_PREFIX.length)
    const value = localStorage.getItem(key)
    if (value !== null && localStorage.getItem(next) === null) localStorage.setItem(next, value)
    localStorage.removeItem(key)
  }
}

export function clearBrowser() {
  accountEpoch++
  for (const value of urls.values()) URL.revokeObjectURL(value)
  urls.clear()
  for (const stream of streams) stream.close()
  streams.clear()
  for (const key of Object.keys(localStorage)) if (key.startsWith('media-lab:') || key.startsWith(OLD_PREFIX) || key === 'rvl-owner') localStorage.removeItem(key)
  sessionStorage.clear()
  user = ''; csrf = ''
}

function artifactRoute(uri: string) {
  const match = /^artifact:\/\/([A-Za-z0-9_-]{1,80})\/(images|references|sources|songs|videos|productions)\/([A-Za-z0-9_.-]+)$/.exec(uri)
  if (!match) throw new Error('URI inválida')
  return `/v1/artifacts/${match[1]}/${match[2]}/${encodeURIComponent(match[3])}`
}

async function preview(route: string, hash: string) {
  const epoch = accountEpoch
  const key = user + ':' + hash
  if (urls.has(key)) return urls.get(key)!
  const response = await request('GET', route)
  if (response.status === 204) return ''
  const value = URL.createObjectURL(await response.blob())
  if (epoch !== accountEpoch) { URL.revokeObjectURL(value); throw new Error('La cuenta cambió') }
  urls.set(key, value)
  return value
}

const MEDIA_TYPES = ['audio/flac', 'audio/wav', 'audio/mpeg', 'audio/ogg', 'audio/opus', 'video/mp4', 'video/webm', 'video/x-matroska']
// Browsers report some of these as empty or x- types (.mkv, .opus, audio/x-wav).
const MEDIA_EXTENSIONS = /\.(flac|wav|mp3|ogg|opus|mp4|webm|mkv)$/i

async function uploadFile(file: File | Blob, sessionId: string, media = false) {
  const epoch = accountEpoch
  const data = new FormData()
  data.append('session_id', sessionId)
  data.append('file', file, 'upload')
  const response = await fetch(media ? '/v1/media/uploads' : '/v1/uploads', {
    method: 'POST', credentials: 'same-origin', redirect: 'error', headers: { 'X-CSRF-Token': csrf }, body: data,
  })
  if (!response.ok) {
    if (response.status === 401) { clearBrowser(); window.dispatchEvent(new Event('rvl-logged-out')) }
    throw new Error(`Runtime ${response.status}: No se pudo subir el archivo`)
  }
  if (epoch !== accountEpoch) throw new Error('La cuenta cambió')
  return response.json()
}

export async function download(payload: ExportPayload) {
  const epoch = accountEpoch
  const settings = await exportSettings()
  const format = payload.format || settings.format
  const response = await request('POST', '/v1/artifacts/export', { uri: payload.media.uri, sha256: payload.media.sha256,
    format, quality: payload.quality || (format === 'webp' ? settings.webpQuality : settings.jpegQuality), background: payload.background || settings.jpegBackground })
  const name = `rinari-${payload.operation || 'generate'}-${new Date().toISOString().replace(/[:.]/g, '-')}-seed-${payload.seed ?? 'unknown'}.${format === 'jpeg' ? 'jpg' : format}`
  const blob = await response.blob()
  if (epoch !== accountEpoch) throw new Error('La cuenta cambió')
  triggerDownload(URL.createObjectURL(blob), name, true)
  return { cancelled: false, format }
}

function triggerDownload(url: string, name: string, revoke = false) {
  const temporaryKey = 'download:' + crypto.randomUUID()
  if (revoke) urls.set(temporaryKey, url)
  const link = document.createElement('a')
  link.href = url; link.download = name; link.rel = 'noopener'
  document.body.append(link); link.click(); link.remove()
  if (revoke) setTimeout(() => { URL.revokeObjectURL(url); urls.delete(temporaryKey) }, 60000)
}

async function exportSettings(): Promise<ExportSettings> {
  const settings = await api('GET', '/v1/account/preferences')
  return { directory: '', format: settings.format || 'png', jpegQuality: settings.jpegQuality || 92,
    webpQuality: settings.webpQuality || 90, jpegBackground: settings.jpegBackground || '#ffffff' }
}

export async function prepareBrowser(current: any) {
  if (localStorage.getItem('rvl-owner') !== current.user_id) clearBrowser()
  user = current.user_id; csrf = current.csrf
  localStorage.setItem('rvl-owner', user) // Identity namespace only, never a session credential.
  const prefs = await api('GET', '/v1/account/preferences')
  for (const [field, key] of [['enhancer', 'enhancer-mode'], ['animation', 'animation-mode']]) {
    if (prefs[field]) localStorage.setItem('media-lab:' + key, prefs[field])
  }
  const runs = await api('GET', '/v1/agent/runs').catch(() => [])
  if (runs.length) localStorage.setItem('media-lab:agent-session', runs.at(-1).session)
  const jobs = await api('GET', '/v1/jobs')
  const names: Record<string, string> = { generate: 'create', edit: 'edit', song: 'song', video: 'video', production: 'production' }
  for (const name of Object.values(names)) localStorage.removeItem(`media-lab:${name}-job`)
  for (const job of [...jobs.items].reverse()) if (['running', 'queued'].includes(job.status) && names[job.operation]) {
    localStorage.setItem(`media-lab:${names[job.operation]}-job`, job.id)
  }
}

const unsupported = async () => { throw new Error('Esta acción local no existe en la versión web') }

window.visualLab = {
  platform: 'web',
  ui: { confirm: action => new Promise<boolean>(resolve => window.dispatchEvent(new CustomEvent('rvl-confirm', {detail:{action,resolve}}))) },
  runtime: {
    request: async (method, route, body) => (await request(method, route, body,
      method === 'POST' && /^\/v1\/jobs\//.test(route) ? crypto.randomUUID() : undefined)).json(),
    upload: payload => uploadFile(new Blob([new Uint8Array(payload.bytes)], { type: payload.type }), payload.sessionId),
    artifactData: uri => preview(artifactRoute(uri), uri),
    preview: ref => preview(`/v1/review?${new URLSearchParams({ uri: ref.uri, sha256: ref.sha256 })}`, ref.sha256),
    jobPreview: async jobId => {
      const epoch = accountEpoch
      const response = await request('GET', `/v1/jobs/${encodeURIComponent(jobId)}/preview`)
      if (response.status === 204) return ''
      const key = 'job:' + user + ':' + jobId
      const old = urls.get(key); if (old) URL.revokeObjectURL(old)
      const value = URL.createObjectURL(await response.blob())
      if (epoch !== accountEpoch) { URL.revokeObjectURL(value); throw new Error('La cuenta cambió') }
      urls.set(key, value); return value
    },
    saveUrl: unsupported,
    uploadMedia: (sessionId, file) => file
      // A dropped file skips the picker; the runtime still validates the content.
      ? (MEDIA_TYPES.includes(file.type) || MEDIA_EXTENSIONS.test(file.name) ? uploadFile(file, sessionId, true) : Promise.reject(new Error('Ese tipo de audio o vídeo no se admite.')))
      : new Promise((resolve,reject) => {
      const input = document.createElement('input'); input.type = 'file'; input.accept = MEDIA_TYPES.join(',')
      input.oncancel = () => resolve(null)
      input.onchange = () => { const file = input.files?.[0]; if (!file) return resolve(null); void uploadFile(file, sessionId, true).then(resolve).catch(reject) }
      input.click()
    }),
    mediaUrl: async uri => artifactRoute(uri),
    saveMedia: async uri => { triggerDownload(artifactRoute(uri), 'rinari-' + uri.split('/').at(-1)); return { cancelled: false } },
  },
  provider: {
    get: async () => { const value = await api('GET', '/v1/account/provider'); return { ...value, baseUrl: value.baseUrl,
      runtimeUrl: location.origin, allowInsecure: false, keyPersisted: value.configured, encryptionAvailable: true } },
    save: async config => {
      const endpoints = await api('GET', '/v1/account/endpoints')
      const endpoint = endpoints.items.find((e: any) => e.base_url === config.baseUrl)
      if (!endpoint) throw new Error('Endpoint no aprobado por el administrador')
      await api('PUT', '/v1/account/provider', { endpoint_id: endpoint.id, model: config.model, ...(config.apiKey ? { api_key: config.apiKey } : {}) })
      return window.visualLab.provider.get()
    },
    test: () => api('POST', '/v1/account/provider/test', {}),
  },
  export: {
    getSettings: exportSettings,
    saveSettings: async settings => { const { directory: _directory, ...body } = settings; await api('PUT', '/v1/account/preferences', body); return exportSettings() },
    chooseFolder: unsupported, saveAs: download, quickSave: download, showInFolder: unsupported,
  },
  agent: {
    improve: (prompt, mode, references = [], seconds) => api('POST', '/v1/agent/improve', { prompt, mode, references, ...(seconds === undefined ? {} : { seconds }) }),
    start: payload => api('POST', '/v1/agent/runs', payload),
    get: payload => api('GET', payload.id ? `/v1/agent/runs/${encodeURIComponent(payload.id)}` : `/v1/agent/runs?session=${encodeURIComponent(payload.session || '')}`),
    cancel: (id, jobId) => api('POST', `/v1/agent/runs/${encodeURIComponent(id)}/cancel`, { ...(jobId ? { jobId } : {}) }),
    continue: id => api('POST', `/v1/agent/runs/${encodeURIComponent(id)}/continue`, {}),
    onEvent: callback => { const stream = new EventSource('/v1/agent/events'); streams.add(stream)
      stream.onmessage = e => { for (const run of JSON.parse(e.data)) callback(run) }
      stream.onerror = () => { void api('GET', '/v1/auth/session').then(current => {
        if (!current.authenticated || !current.mfa) { clearBrowser(); window.dispatchEvent(new Event('rvl-logged-out')) }
      }).catch(() => {}) }
      return () => { stream.close(); streams.delete(stream) } },
    review: payload => api('POST', '/v1/agent/review', payload),
    directorPlan: payload => api('POST', '/v1/agent/director', payload),
  },
  graph: { show: unsupported, bounds: unsupported, hide: async () => {} },
}

