import { useEffect, useRef, useState } from 'react'
import { ANIMATION_EVENT, getAnimationMode, type AnimationMode, type Job } from '../lib/api'

export function useAnimationMode(): AnimationMode {
  const [mode, setMode] = useState<AnimationMode>(getAnimationMode)
  useEffect(() => {
    const sync = () => setMode(getAnimationMode())
    window.addEventListener(ANIMATION_EVENT, sync)
    return () => window.removeEventListener(ANIMATION_EVENT, sync)
  }, [])
  return mode
}

export function aspectFromRatio(value?: string | null) {
  const match = String(value || '').match(/^(\d+):(\d+)$/)
  return match ? Number(match[1]) / Number(match[2]) : 1
}

const ACTIVE = ['queued', 'running']

export default function GenerationCanvas({ job, aspect = 1 }: { job: Job | null; aspect?: number }) {
  const mode = useAnimationMode()
  const [frame, setFrame] = useState('')
  const lastSeq = useRef(0)
  const fetching = useRef(false)
  const jobId = job?.id || job?.job_id || ''
  const active = Boolean(job && ACTIVE.includes(job.status))

  const currentJob = useRef(jobId)

  useEffect(() => { currentJob.current = jobId; setFrame(''); lastSeq.current = 0 }, [jobId, active])

  useEffect(() => {
    const seq = job?.preview_seq || 0
    if (mode !== 'live' || !active || !jobId.startsWith('job_') || seq <= lastSeq.current || fetching.current) return
    fetching.current = true
    window.visualLab.runtime.jobPreview(jobId)
      .then(value => { if (currentJob.current === jobId && value) { lastSeq.current = seq; setFrame(value) } })
      .catch(() => {})
      .finally(() => { fetching.current = false })
  }, [mode, active, jobId, job?.preview_seq])

  if (mode === 'off' || !job || !active) return null
  const pct = Math.max(0, Math.min(100, job.progress?.pct ?? 0))
  const queued = job.status === 'queued'
  const blur = Math.round(22 - pct * 0.2)
  const ratio = Math.min(2.4, Math.max(0.42, aspect || 1))
  const label = queued ? `En cola · posición ${job.queue_position ?? 0}` : pct > 0 ? 'Creando imagen' : 'Preparando el lienzo'

  return (
    <div className="gen-canvas" style={{ aspectRatio: String(ratio) }}>
      <div className="gen-aurora"><i /><i /><i /></div>
      {mode === 'live' && frame && <img className="gen-frame" src={frame} alt="" style={{ filter: `blur(${blur}px) saturate(1.15)` }} />}
      <div className="gen-grain" />
      {!queued && <div className="gen-scan" />}
      <div className="gen-caption">
        <span className="gen-label">{label}</span>
        {!queued && <b>{pct}%</b>}
      </div>
    </div>
  )
}

export function RevealImage({ src, alt, animate }: { src: string; alt: string; animate: boolean }) {
  if (!animate) return <img src={src} alt={alt} />
  return (
    <span className="reveal">
      <img className="reveal-base" src={src} alt="" aria-hidden="true" />
      <img className="reveal-sharp" src={src} alt={alt} />
    </span>
  )
}
