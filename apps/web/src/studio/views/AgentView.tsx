import AdvancedOptions from '../components/AdvancedOptions'
const agentStates: Record<string,string> = {running:'Creando',recovering:'Recuperando',completed:'Completado',paused:'En pausa',failed:'Error',cancelled:'Cancelado',budget:'Límite alcanzado'}
const toolNames: Record<string,string> = {generate_image:'Crear imagen',edit_image:'Editar imagen',generate_video:'Crear vídeo',generate_song:'Crear música',produce_music_video:'Producir videoclip'}
import MediaPreview from '../components/MediaPreview'
import { useEffect, useRef, useState } from 'react'
import { Sparkles } from 'lucide-react'
import ExportActions from '../components/ExportActions'
import JobProgress from '../components/JobProgress'
import { SemanticData } from '../components/SemanticData'
import { CreativeResult } from './CreativeJob'
import { Action } from '../components/Kit'
import { formatUploadErrors, newSession, runtime, uploadFiles, type ArtifactRef, type Job } from '../lib/api'

function ImageResult({ media, job }: { media: ArtifactRef; job: any }) {
  const [preview, setPreview] = useState('')
  useEffect(() => {
    let live = true
    void window.visualLab.runtime.preview(media).then(value => { if (live) setPreview(value) }).catch(() => {})
    return () => { live = false }
  }, [media.uri, media.sha256])
  return <div>{preview && <img src={preview} alt="Resultado generado" style={{ maxWidth: '100%' }} />}
    <ExportActions media={media} operation={job.operation === 'edit' ? 'edit' : 'generate'} seed={job.data?.seed ?? job.settings?.seed} />
  </div>
}

export default function AgentView({ active }: { active: boolean }) {
  const sessionKey = 'media-lab:agent-session'
  const session = useRef(localStorage.getItem(sessionKey) || newSession())
  const [provider, setProvider] = useState<ProviderConfig | null>(null)
  const [runs, setRuns] = useState<any[]>([])
  const [legacy, setLegacy] = useState<any[]>([])
  const [input, setInput] = useState('')
  const [refs, setRefs] = useState<ArtifactRef[]>([])
  const [error, setError] = useState('')
  const [sending, setSending] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [library, setLibrary] = useState<any[]>([])
  const [search, setSearch] = useState('')
  const [showLibrary, setShowLibrary] = useState(false)
  const busy = sending || runs.some(r => ['running', 'recovering'].includes(r.status))
  const ready = provider?.configured && provider.capabilities?.chat && provider.capabilities?.tools

  useEffect(() => {
    localStorage.setItem(sessionKey, session.current)
    return window.visualLab.agent.onEvent(run => {
      if (run.session !== session.current) return
      setRuns(current => current.some(r => r.id === run.id && r.updatedAt > run.updatedAt) ? current : [...current.filter(r => r.id !== run.id), run].sort((a, b) => a.createdAt - b.createdAt))
    })
  }, [])
  useEffect(() => {
    if (!active) return
    let live = true
    void window.visualLab.provider.get().then(value => { if (live) setProvider(value) }).catch(e => setError(String(e)))
    void window.visualLab.agent.get({ session: session.current }).then(value => { if (live) setRuns(value) }).catch(e => setError(String(e)))
    void runtime('GET', `/v1/sessions/${session.current}`).then(value => { if (live) setLegacy(value.messages || []) }).catch(() => {})
    return () => { live = false }
  }, [active])

  useEffect(() => {
    const changed = () => { void window.visualLab.provider.get().then(setProvider).catch(e => setError(String(e))) }
    window.addEventListener('rvl-provider-changed', changed)
    return () => window.removeEventListener('rvl-provider-changed', changed)
  }, [])

  async function send() {
    if (!input.trim() || busy || uploading || !ready) return
    setSending(true); setError('')
    try {
      const run = await window.visualLab.agent.start({ prompt: input, session: session.current, references: refs.map(({ uri, sha256 }) => ({ uri, sha256 })) })
      setRuns(current => current.some(r => r.id === run.id && r.updatedAt > run.updatedAt) ? current : [...current.filter(r => r.id !== run.id), run].sort((a, b) => a.createdAt - b.createdAt))
      setInput(''); setRefs([])
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setSending(false) }
  }
  async function upload(files: File[]) {
    if (uploading) return
    setUploading(true); setError('')
    try {
      const result = await uploadFiles(files.slice(0, 10 - refs.length), session.current)
      setRefs(current => [...current, ...result.refs].slice(0, 16))
      if (result.errors.length) setError(formatUploadErrors(result.errors))
    } finally { setUploading(false) }
  }
  async function audio() {
    if (refs.length >= 16) return
    setUploading(true)
    try { const value = await window.visualLab.runtime.uploadMedia(session.current); if (value) setRefs(current => [...current, value.data].slice(0, 16)) }
    catch (e) { setError(String(e)) }
    finally { setUploading(false) }
  }
  async function searchLibrary() {
    try { const value = await runtime('GET', `/v1/library?limit=100&q=${encodeURIComponent(search)}`); setLibrary(value.items || []); setShowLibrary(true) }
    catch (e) { setError(String(e)) }
  }
  async function clear() {
    if (busy || !await window.visualLab.ui.confirm('agent-clear')) return
    session.current = newSession(); localStorage.setItem(sessionKey, session.current)
    setRuns([]); setLegacy([]); setRefs([]); setInput(''); setError('')
  }
  async function action(kind: 'cancel' | 'continue', id: string, jobId?: string) {
    try { if (kind === 'cancel') await window.visualLab.agent.cancel(id, jobId); else await window.visualLab.agent.continue(id) } catch (e) { setError(String(e)) }
  }
  return <div className="agent">
    <section className="agent-feed glass">
      <div className="agent-feed-head"><div><p className="eyebrow">Agente externo · estudio completo</p><h2>Describe lo que quieres crear</h2></div><button className="ghost" disabled={busy} onClick={() => void clear()}>NUEVA SESIÓN</button></div>
      {!ready && <div className="proposal"><p>Configura y prueba un proveedor con Chat Completions y herramientas en Proveedores IA. Los modos directos siguen disponibles.</p><button onClick={() => {
        setSending(true); void window.visualLab.provider.test().then(() => window.visualLab.provider.get()).then(setProvider).catch(e => setError(String(e))).finally(() => setSending(false))
      }} disabled={sending}>PROBAR PROVEEDOR</button></div>}
      {ready && !provider?.capabilities?.vision && <p className="hint">Herramientas disponibles. Revisión visual desactivada: el proveedor no admite visión.</p>}
      <div className="messages">
        {!legacy.length && !runs.length && <div className="agent-hello"><div><b>Encadena el Lab con un mensaje</b><p>Pide una imagen, una edición con tus referencias, un vídeo con sonido, una canción o un videoclip completo. El agente elige las herramientas, escribe los prompts y te enseña cada paso.</p></div></div>}
        {legacy.filter(m => m.role !== 'tool' && (!runs.length || m.created_at < runs[0].createdAt / 1000)).map((m, i) => <div className={`message ${m.role}`} key={`legacy-${i}`}>{m.role === 'assistant' && <Avatar/>}<div className="bubble"><p>{m.content}</p>
          {(m.media || []).map((media: ArtifactRef) => /\/(images|references)\//.test(media.uri)
            ? <ImageResult key={media.uri} media={media} job={{}} /> : <CreativeResult key={media.uri} media={media} />)}
        </div></div>)}
        {runs.map(run => <div className="run" key={run.id}>
          <div className="message user"><div className="bubble"><p style={{ whiteSpace: 'pre-wrap' }}>{run.request}</p></div></div>
          <div className="message assistant"><Avatar live={['running', 'recovering'].includes(run.status)}/><div className="bubble">
            <div className="run-meta"><span className={`status-badge status-${run.status}`}>{agentStates[run.status]||run.status}</span><small>{run.turns.length} pasos creativos</small></div>
            {(run.notices || []).map((notice: string) => <p className="hint" key={notice}>{notice}</p>)}
            {run.turns.length > 0 && <ol className="agent-steps">{run.turns.map((turn: any, index: number) => <li key={turn.id} className={turn.status === 'done' ? 'is-done' : 'is-live'}><details className="agent-step"><summary>Paso {index + 1} · {toolNames[turn.tool]||turn.tool.replaceAll('_',' ')} · {turn.status === 'done' ? 'Completado' : 'En proceso'}</summary><label>INSTRUCCIONES Y PROMPT UTILIZADO</label><SemanticData value={turn.arguments}/>{turn.result && <><label>RESULTADO</label><SemanticData value={turn.result}/></>}</details></li>)}</ol>}
            {Object.values(run.jobs).filter((j: any) => j.runId === run.id).map((j: any) => <div className="run-job" key={j.id}>
              <JobProgress job={{ ...j, session_id: run.session, activity: [], result: { media: j.media || [], data: {} } } as Job} onCancel={() => void action('cancel', run.id, j.id)} />
              {(j.media || []).map((media: ArtifactRef) => /\/(images|references)\//.test(media.uri) ? <ImageResult key={media.uri} media={media} job={j} /> : <CreativeResult key={media.uri} media={media} />)}
              {j.error && <p className="error">{j.error}</p>}
            </div>)}
            {run.final && <div className="run-final"><SemanticData value={run.final}/></div>}{run.error && <p className="error">{run.error}</p>}
            {run.exported?.path && <p>Guardado: {run.exported.path} <button onClick={() => void window.visualLab.export.showInFolder(run.exported.path)}>MOSTRAR EN CARPETA</button></p>}
            {run.exported?.prepared && <div><p>Exportación preparada. Pulsa Descargar para solicitarla al navegador; aún no se ha guardado en tu equipo.</p>
              {/\/(images|references)\//.test(run.exported.download.media.uri)
                ? <ExportActions media={run.exported.download.media} /> : <CreativeResult media={run.exported.download.media} />}
            </div>}
            <div className="button-row">
              {['running', 'recovering'].includes(run.status) && <button className="danger" onClick={() => void action('cancel', run.id)}>CANCELAR EJECUCIÓN</button>}
              {['paused', 'failed', 'budget'].includes(run.status) && <button disabled={busy || !ready} onClick={() => void action('continue', run.id)}>CONTINUAR SOLICITUD AUTORIZADA</button>}
            </div>
          </div></div>
        </div>)}
      </div>
      <div className="composer">
        <label htmlFor="agent-request" className="field-label">SOLICITUD</label>
        <textarea id="agent-request" rows={4} value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); void send() } }} placeholder="Crea una imagen, edita referencias, genera vídeo o música, o produce un videoclip…" />
        {refs.length > 0 && <div className="refs">{refs.map((ref, index) => <div className={`ref ${index === 0 ? 'is-target' : ''}`} key={`${ref.uri}-${index}`}><MediaPreview media={ref} label={`Referencia ${index+1}`}/><span className="ref-tag">{index === 0 ? 'Objetivo' : `Ref ${index + 1}`}</span>
          <div className="ref-tools"><button aria-label={`Mover referencia ${index + 1} antes`} disabled={!index} onClick={() => setRefs(current => { const copy = [...current]; [copy[index - 1], copy[index]] = [copy[index], copy[index - 1]]; return copy })}>↑</button>
          <button aria-label={`Mover referencia ${index + 1} después`} disabled={index === refs.length - 1} onClick={() => setRefs(current => { const copy = [...current]; [copy[index + 1], copy[index]] = [copy[index], copy[index + 1]]; return copy })}>↓</button>
          <button className="danger" aria-label={`Quitar referencia ${index + 1}`} onClick={() => setRefs(current => current.filter((_, i) => i !== index))}>×</button></div>
        </div>)}</div>}
        <div className="composer-bar">
          <label className="btn ghost composer-attach" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();if(!uploading)void upload(Array.from(e.dataTransfer.files))}}>{uploading ? 'Subiendo…' : '+ Imágenes'}<input hidden type="file" multiple accept="image/png,image/jpeg,image/webp" disabled={uploading || refs.length >= 16} onChange={e => { void upload(Array.from(e.target.files || [])); e.target.value = '' }} /></label>
          <button className="ghost" disabled={uploading || refs.length >= 16} onClick={() => void audio()}>ADJUNTAR AUDIO</button>
          <span className="composer-hint">Ctrl + Enter para enviar</span>
          <Action disabled={!ready || busy || uploading || !input.trim()} onClick={() => void send()}>{busy ? 'EJECUTANDO…' : 'ENVIAR Y EJECUTAR'}</Action>
        </div>
        {error && <p className="error">{error}</p>}
      </div>
    </section>
    <aside className="agent-side">
      <div className="glass agent-panel">
        <h3>Desde tu biblioteca</h3>
        <div className="search-row"><input aria-label="Buscar biblioteca" value={search} onChange={e => setSearch(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') void searchLibrary() }} placeholder="Buscar imágenes, canciones, vídeos…" /><button onClick={() => void searchLibrary()}>BIBLIOTECA</button></div>
        {showLibrary && <div className="agent-library">{library.map(item => <button className="agent-library-card" key={item.uri} disabled={refs.length >= 16} onClick={() => { setRefs(current => [...current, item].slice(0, 16)); setShowLibrary(false) }}><MediaPreview media={item}/><span>{(item as any).title || (item as any).prompt || 'Referencia multimedia'}</span></button>)}</div>}
        <p className="hint">Al enviar, autorizas al agente a ejecutar tu idea con tus herramientas multimedia.</p>
        <AdvancedOptions title="Qué se comparte y cómo trabaja el agente"><p className="hint">Enviar autoriza ejecutar tu solicitud y adaptar los prompts. El proveedor recibe texto y previews reducidas; audio sólo como análisis técnico. No hay correcciones automáticas. Perfil predeterminado: BF16 · 40 pasos · ~1 MP.</p></AdvancedOptions>
      </div>
    </aside>
  </div>
}

function Avatar({ live = false }: { live?: boolean }) {
  return <span className={`agent-avatar ${live ? 'is-live' : ''}`} aria-hidden="true"><Sparkles size={15} /></span>
}
