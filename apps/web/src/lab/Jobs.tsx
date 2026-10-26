import { useEffect, useState } from 'react'
import { LayoutGroup, motion } from 'motion/react'
import { AudioLines, AudioWaveform, Clapperboard, Film, ImagePlus, Maximize2, Mic, RotateCcw, ScanFace, UserRoundPen, UserRoundX, WandSparkles, X, type LucideIcon } from 'lucide-react'
import { api } from '../bridge'
import { useMediaSrc } from './live'
import { ratioOf, type Art, type Modality } from './data'
import { formatDateTime, t, type MessageKey } from '../i18n'

const KINDS: Record<string, [MessageKey, LucideIcon, Modality]> = { generate: ['creations.kind.generate', ImagePlus, 'image'], edit: ['creations.kind.edit', WandSparkles, 'image'], video: ['creations.kind.video', Film, 'video'],
  song: ['creations.kind.song', AudioLines, 'audio'], production: ['creations.kind.production', Clapperboard, 'video'], upscale: ['creations.kind.upscale', Maximize2, 'video'],
  swap: ['creations.kind.swap', UserRoundPen, 'video'], face_refine: ['creations.kind.faceRefine', ScanFace, 'video'], remove: ['creations.kind.remove', UserRoundX, 'video'],
  stems: ['creations.kind.stems', AudioLines, 'audio'], sound: ['creations.kind.sound', AudioWaveform, 'audio'], speech: ['creations.kind.speech', Mic, 'audio'] }
const STATUS: Record<string, MessageKey> = { queued: 'creations.status.queued', running: 'creations.status.running', completed: 'creations.status.completed', failed: 'creations.status.failed',
  cancelled: 'creations.status.cancelled', interrupted: 'creations.status.interrupted', blocked_gpu: 'creations.status.blockedGpu' }
const STRENGTH: Record<string, MessageKey> = { light: 'creations.jobs.strengthLight', medium: 'creations.jobs.strengthMedium', strong: 'creations.jobs.strengthStrong' }
const filters: [string, MessageKey][] = [['', 'creations.jobs.filterAll'], ['active', 'creations.jobs.filterActive'], ['completed', 'creations.jobs.filterCompleted'], ['failed', 'creations.jobs.filterFailed']]
const ACTIVE = ['queued', 'running']
const RESUMABLE = ['failed', 'cancelled', 'interrupted', 'blocked_gpu']

function Thumb({ media, kind, onOpen }: { media?: any; kind: Modality; onOpen?: () => void }) {
  const src = useMediaSrc(media && kind !== 'audio' ? media : undefined)
  const Icon = kind === 'audio' ? AudioLines : kind === 'video' ? Film : ImagePlus
  const body = src ? (kind === 'video' ? <video src={src} muted playsInline preload="metadata" /> : <img src={src} alt="" />) : <Icon size={20} />
  return onOpen ? <button type="button" className="ml-job-thumb" aria-label={t('creations.jobs.viewResult')} onClick={onOpen}>{body}</button> : <span className="ml-job-thumb">{body}</span>
}

function describe(j: any) {
  const r = j.request || {}
  if (j.operation === 'upscale') return `FlashVSR ×${r.scale ?? 2} · ${t(r.quality === 'quality' ? 'creations.jobs.upscaleQuality' : 'creations.jobs.upscaleFast')}`
  if (j.operation === 'swap') return `${r.mode === 'head' ? t('creations.jobs.swapHead') : r.mode === 'scail' ? `${t('creations.jobs.swapCharacter')} · SCAIL-2` : t('creations.jobs.swapCharacter')}${r.target ? ` · ${r.target}` : ''}`
  if (j.operation === 'edit' && r.remove_background) return t('creations.jobs.backgroundRemoved')
  if (j.operation === 'stems') return t(r.stems === 'four' ? 'creations.jobs.stemsFour' : 'creations.jobs.stemsTwo')
  if (j.operation === 'remove') return r.target ? t('creations.jobs.removeTarget', { target: r.target }) : t('creations.jobs.removePerson')
  if (j.operation === 'face_refine') return t('creations.jobs.refined', { strength: t(STRENGTH[r.strength] || 'creations.jobs.strengthMedium') })
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
      <div><small className="ml-kicker">{t('creations.jobs.kicker')}</small><h1>{t('creations.jobs.title')}</h1></div>
      <span className="ml-count">{running ? <><i className="ml-live" />{t('creations.jobs.running', { count: running })}</> : t('creations.jobs.total', { count: jobs.length })}</span>
    </header>
    <div className="ml-toolbar"><LayoutGroup><div className="ml-pills" role="group" aria-label={t('creations.jobs.filterLabel')}>{filters.map(([value, label]) => <button key={value} type="button" aria-pressed={filter === value} className={filter === value ? 'is-on' : ''} onClick={() => setFilter(value)}>
      {filter === value && <motion.span layoutId="ml-pill" className="ml-tab-pill" transition={{ type: 'spring', stiffness: 420, damping: 34 }} />}<span>{t(label)}</span></button>)}</div></LayoutGroup></div>
    {error && <p className="ml-error" role="alert">{error}</p>}
    {!shown.length ? <div className="ml-blank"><h2>{t(jobs.length ? 'creations.jobs.emptyFiltered' : 'creations.jobs.empty')}</h2><p>{t('creations.jobs.emptyHint')}</p></div>
      : <ol className="ml-jobs">{shown.map((j, index) => {
        const [labelKey, Icon, kind] = KINDS[j.operation] || ['creations.kind.fallback' as MessageKey, ImagePlus, 'image' as Modality]
        const label = t(labelKey)
        const media = j.result?.media || []
        const pct = j.status === 'completed' ? 100 : j.progress?.pct ?? 0
        const prompt = describe(j)
        const open = media[0] ? () => onOpen({ id: media[0].uri, src: '', ref: media[0], kind, prompt, model: label, created: j.created_at,
          ratio: media[0].width && media[0].height ? media[0].width / media[0].height : kind === 'audio' ? 1 : ratioOf(j.request?.aspect_ratio || (kind === 'video' ? '16:9' : '1:1')) }) : undefined
        return <motion.li key={j.id} className={`ml-job is-${j.status}`} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(index, 12) * .03 }}>
          <Thumb media={media[0]} kind={kind} onOpen={open} />
          <div className="ml-job-body">
            <div className="ml-job-head"><Icon size={14} /><b>{label}</b><time>{formatDateTime(j.created_at)}</time>
              <em data-state={j.status}>{STATUS[j.status] ? t(STATUS[j.status]) : j.status}{j.status === 'queued' && j.queue_position ? ` · ${j.queue_position}` : ''}</em></div>
            {prompt && <p>{prompt}</p>}
            {j.error && <p className="ml-job-error">{j.error}</p>}
            {ACTIVE.includes(j.status) && <div className="ml-job-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)} aria-label={t('creations.jobs.progress', { label })}><i style={{ transform: `scaleX(${pct / 100})` }} /></div>}
          </div>
          <div className="ml-job-actions">
            {media.length > 1 && <span className="ml-job-more">+{media.length - 1}</span>}
            {ACTIVE.includes(j.status) && <button type="button" className="ml-btn" disabled={busy === j.id} onClick={() => void act(j, false)}><X size={14} />{t('creations.jobs.cancel')}</button>}
            {RESUMABLE.includes(j.status) && <button type="button" className="ml-btn" disabled={busy === j.id} onClick={() => void act(j, true)}><RotateCcw size={14} />{t('creations.jobs.resume')}</button>}
          </div>
        </motion.li>
      })}</ol>}
  </div>
}
