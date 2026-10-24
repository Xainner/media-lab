import { useEffect, useState } from 'react'
import { LayoutGroup, motion } from 'motion/react'
import { AudioLines, AudioWaveform, Clapperboard, Film, ImagePlus, Maximize2, Mic, RotateCcw, ScanFace, UserRoundPen, UserRoundX, WandSparkles, X, type LucideIcon } from 'lucide-react'
import { api } from '../bridge'
import { useMediaSrc } from './live'
import { ratioOf, type Art, type Modality } from './data'

const KINDS: Record<string, [string, LucideIcon, Modality]> = { generate: ['Imagen', ImagePlus, 'image'], edit: ['Edición', WandSparkles, 'image'], video: ['Vídeo', Film, 'video'],
  song: ['Canción', AudioLines, 'audio'], production: ['Videoclip', Clapperboard, 'video'], upscale: ['Escalado', Maximize2, 'video'],
  swap: ['Cambio de personaje', UserRoundPen, 'video'], face_refine: ['Cara refinada', ScanFace, 'video'], remove: ['Persona quitada', UserRoundX, 'video'],
  stems: ['Pistas separadas', AudioLines, 'audio'], sound: ['Sonido', AudioWaveform, 'audio'], speech: ['Voz', Mic, 'audio'] }
const STATUS: Record<string, string> = { queued: 'En cola', running: 'Creando', completed: 'Listo', failed: 'Error', cancelled: 'Cancelado', interrupted: 'Interrumpido', blocked_gpu: 'GPU ocupada' }
const STRENGTH: Record<string, string> = { light: 'ligero', medium: 'medio', strong: 'fuerte' }
const filters: [string, string][] = [['', 'Todos'], ['active', 'En proceso'], ['completed', 'Listos'], ['failed', 'Con errores']]
const ACTIVE = ['queued', 'running']
const RESUMABLE = ['failed', 'cancelled', 'interrupted', 'blocked_gpu']

function Thumb({ media, kind, onOpen }: { media?: any; kind: Modality; onOpen?: () => void }) {
  const src = useMediaSrc(media && kind !== 'audio' ? media : undefined)
  const Icon = kind === 'audio' ? AudioLines : kind === 'video' ? Film : ImagePlus
  const body = src ? (kind === 'video' ? <video src={src} muted playsInline preload="metadata" /> : <img src={src} alt="" />) : <Icon size={20} />
  return onOpen ? <button type="button" className="ml-job-thumb" aria-label="Ver resultado" onClick={onOpen}>{body}</button> : <span className="ml-job-thumb">{body}</span>
}

function describe(j: any) {
  const r = j.request || {}
  if (j.operation === 'upscale') return `FlashVSR ×${r.scale ?? 2} · ${r.quality === 'quality' ? 'calidad' : 'rápido'}`
  if (j.operation === 'swap') return `${r.mode === 'head' ? 'Cabeza' : r.mode === 'scail' ? 'Personaje · SCAIL-2' : 'Personaje'}${r.target ? ` · ${r.target}` : ''}`
  if (j.operation === 'edit' && r.remove_background) return 'Fondo quitado'
  if (j.operation === 'stems') return r.stems === 'four' ? 'Voz, batería, bajo y otros' : 'Voz e instrumental'
  if (j.operation === 'remove') return r.target ? `Quitar · ${r.target}` : 'Quitar persona'
  if (j.operation === 'face_refine') return `Refinado ${STRENGTH[r.strength] || 'medio'}`
  return r.prompt || r.style || r.text || r.title || ''
}

/** Every job of the viewer, newest first, refreshed every five seconds. */
export default function Jobs({ onOpen }: { onOpen: (a: Art) => void }) {
  const [jobs, setJobs] = useState<any[]>([])
  const [filter, setFilter] = useState('')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const load = () => api('GET', '/v1/jobs').then(v => setJobs(v.items || [])).catch(e => setError(String(e)))
  useEffect(() => { void load(); const t = setInterval(() => { if (!document.hidden) void load() }, 5000); return () => clearInterval(t) }, [])
  const act = async (j: any, resume: boolean) => {
    setBusy(j.id); setError('')
    try { if (resume) await window.visualLab.runtime.request('POST', `/v1/jobs/${j.id}/resume`, {}); else await api('DELETE', `/v1/jobs/${j.id}`); await load() }
    catch (e) { setError(String(e)) } finally { setBusy('') }
  }
  const shown = jobs.filter(j => !filter || (filter === 'active' ? ACTIVE.includes(j.status) : filter === 'failed' ? RESUMABLE.includes(j.status) : j.status === filter))
  const running = jobs.filter(j => ACTIVE.includes(j.status)).length
  return <div className="ml-page">
    <header className="ml-page-head">
      <div><small className="ml-kicker">Tu espacio</small><h1>Mis trabajos</h1></div>
      <span className="ml-count">{running ? <><i className="ml-live" />{running} en curso</> : `${jobs.length} trabajos`}</span>
    </header>
    <div className="ml-toolbar"><LayoutGroup><div className="ml-pills" role="group" aria-label="Estado">{filters.map(([value, label]) => <button key={value} type="button" aria-pressed={filter === value} className={filter === value ? 'is-on' : ''} onClick={() => setFilter(value)}>
      {filter === value && <motion.span layoutId="ml-pill" className="ml-tab-pill" transition={{ type: 'spring', stiffness: 420, damping: 34 }} />}<span>{label}</span></button>)}</div></LayoutGroup></div>
    {error && <p className="ml-error" role="alert">{error}</p>}
    {!shown.length ? <div className="ml-blank"><h2>{jobs.length ? 'Nada con este filtro' : 'Todavía no hay trabajos'}</h2><p>Lo que generes aparece aquí con su progreso.</p></div>
      : <ol className="ml-jobs">{shown.map((j, index) => {
        const [label, Icon, kind] = KINDS[j.operation] || ['Creación', ImagePlus, 'image' as Modality]
        const media = j.result?.media || []
        const pct = j.status === 'completed' ? 100 : j.progress?.pct ?? 0
        const prompt = describe(j)
        const open = media[0] ? () => onOpen({ id: media[0].uri, src: '', ref: media[0], kind, prompt, model: label, created: j.created_at,
          ratio: media[0].width && media[0].height ? media[0].width / media[0].height : kind === 'audio' ? 1 : ratioOf(j.request?.aspect_ratio || (kind === 'video' ? '16:9' : '1:1')) }) : undefined
        return <motion.li key={j.id} className={`ml-job is-${j.status}`} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(index, 12) * .03 }}>
          <Thumb media={media[0]} kind={kind} onOpen={open} />
          <div className="ml-job-body">
            <div className="ml-job-head"><Icon size={14} /><b>{label}</b><time>{new Date(j.created_at * 1000).toLocaleString('es', { dateStyle: 'medium', timeStyle: 'short' })}</time>
              <em data-state={j.status}>{STATUS[j.status] || j.status}{j.status === 'queued' && j.queue_position ? ` · ${j.queue_position}` : ''}</em></div>
            {prompt && <p>{prompt}</p>}
            {j.error && <p className="ml-job-error">{j.error}</p>}
            {ACTIVE.includes(j.status) && <div className="ml-job-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)} aria-label={`Progreso de ${label}`}><i style={{ transform: `scaleX(${pct / 100})` }} /></div>}
          </div>
          <div className="ml-job-actions">
            {media.length > 1 && <span className="ml-job-more">+{media.length - 1}</span>}
            {ACTIVE.includes(j.status) && <button type="button" className="ml-btn" disabled={busy === j.id} onClick={() => void act(j, false)}><X size={14} />Cancelar</button>}
            {RESUMABLE.includes(j.status) && <button type="button" className="ml-btn" disabled={busy === j.id} onClick={() => void act(j, true)}><RotateCcw size={14} />Reanudar</button>}
          </div>
        </motion.li>
      })}</ol>}
  </div>
}
