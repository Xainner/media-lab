import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AnimatePresence, motion } from 'motion/react'
import { AudioLines, Check, Clapperboard, Download, Loader2, Mic2, RotateCcw, Sparkles, Upload, X } from 'lucide-react'
import { newSession, runtime, type ArtifactRef } from '../studio/lib/api'
import { useCreativeJob } from '../studio/views/CreativeJob'
import { lipSyncTemplate } from '../studio/lib/h3'
import { useCaps, useLibrary, useMediaSrc, useProvider } from './live'
import type { Art } from './data'
import { t } from '../i18n'

type Scene = { start: number; end: number; image_prompt: string; video_prompt: string; lip_sync?: boolean }
const JOB_KEY = 'media-lab:production-job'
const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`

function Choice({ label, options, value, onChange }: { label: string; options: [string, string, boolean?][]; value: string; onChange: (v: string) => void }) {
  return <div className="ml-seg" role="group" aria-label={label}><small>{label}</small>{options.map(([v, text, off]) =>
    <button key={v} type="button" disabled={off} aria-pressed={value === v} className={value === v ? 'is-on' : ''} onClick={() => onChange(v)}>{text}</button>)}</div>
}

function SongCard({ item, on, onPick }: { item: Art; on: boolean; onPick: () => void }) {
  return <button type="button" className={`ml-song ${on ? 'is-on' : ''}`} onClick={onPick} aria-pressed={on}>
    <span className="ml-song-icon">{on ? <Check size={16} /> : <AudioLines size={16} />}</span>
    <span><b>{item.prompt || t('lab.director.untitledSong')}</b><small>{item.model}</small></span>
  </button>
}

function Player({ song }: { song: ArtifactRef }) {
  const src = useMediaSrc(song)
  return src ? <audio className="ml-player" src={src} controls /> : null
}

function Result({ job }: { job: any }) {
  const video = useMediaSrc(job.result?.media?.[0])
  const master = job.result?.media?.[1]
  return <div className="ml-director-result">
    {video && <video src={video} controls playsInline />}
    {master && <button type="button" className="ml-btn is-accent" onClick={() => void window.visualLab.runtime.saveMedia(master.uri)}><Download size={15} />{t('lab.director.exportMaster')}</button>}
  </div>
}

/** Music video director: pick a song, describe the concept, let the provider storyboard it, then produce. */
export default function Director({ incoming }: { incoming: ArtifactRef | null }) {
  const caps = useCaps()
  const provider = useProvider()
  const songs = useLibrary('songs', '', 24)
  const uploads = useLibrary('sources', '', 24)
  const [song, setSong] = useState<ArtifactRef | null>(null)
  const [analysis, setAnalysis] = useState<any>(null)
  const [title, setTitle] = useState('')
  const [brief, setBrief] = useState('')
  const [lyrics, setLyrics] = useState('')
  const [scenes, setScenes] = useState<Scene[]>([])
  const [ratio, setRatio] = useState('16:9')
  const [clips, setClips] = useState('base')
  const [frames, setFrames] = useState('base')
  const [quality, setQuality] = useState('quality')
  const [planning, setPlanning] = useState(false)
  const [error, setError] = useState('')
  const state = useCreativeJob(JOB_KEY)
  const job: any = state.job
  const producing = ['queued', 'running'].includes(job?.status || '')
  const pick = async (ref: ArtifactRef) => {
    setSong(ref); setAnalysis(null); setScenes([]); setError('')
    try { setAnalysis(await runtime('GET', `/v1/media/analyze?uri=${encodeURIComponent(ref.uri)}&sha256=${ref.sha256}`)) } catch (e) { setError(String(e)) }
  }
  useEffect(() => { if (incoming) void pick(incoming) }, [incoming?.uri])
  const upload = async () => {
    try {
      const r = await window.visualLab.runtime.uploadMedia(newSession())
      if (!r) return
      if (!/\.(wav|flac|mp3|opus|ogg)$/i.test(r.data.uri)) throw new Error(t('lab.director.pickAudio'))
      await pick(r.data)
    } catch (e) { setError(String(e)) }
  }
  const plan = async () => {
    setPlanning(true); setError('')
    try { setScenes((await window.visualLab.agent.directorPlan({ brief, lyrics, analysis })).scenes) } catch (e) { setError(String(e)) } finally { setPlanning(false) }
  }
  const edit = (i: number, patch: Partial<Scene>) => setScenes(list => list.map((s, k) => k === i ? { ...s, ...patch } : s))
  const sync = (i: number, on: boolean) => setScenes(list => list.map((s, k) => k !== i ? s : { ...s, lip_sync: on,
    video_prompt: on && !s.video_prompt.includes('subject_definitions:') ? lipSyncTemplate(s.video_prompt) : s.video_prompt }))
  const produce = () => {
    const turbo = frames === 'turbo'
    void state.submit('/v1/jobs/production', { title: title.trim(), song, brief, lyrics, scenes, aspect_ratio: ratio, session_id: newSession(),
      keyframe_variant: frames, keyframe_quality: turbo ? 'quality' : quality, keyframe_resolution: '1mp',
      keyframe_precision: turbo ? caps.turboPrecision : caps.bf16 ? 'bf16' : 'int8', video_profile: clips })
  }
  const resume = () => { const id = job?.id || job?.job_id; if (id) void state.submit(`/v1/jobs/${id}/resume`, undefined) }
  const duration = Number(analysis?.duration) || 0
  const pct = (time: number) => duration ? `${Math.max(0, Math.min(100, time / duration * 100))}%` : '0%'
  const sections: any[] = Array.isArray(analysis?.sections) ? analysis.sections : []
  const all = [...songs.items, ...uploads.items]
  return <div className="ml-page ml-director">
    <header className="ml-page-head">
      <div><small className="ml-kicker">{t('lab.director.kicker')}</small><h1>{t('lab.tabs.director')}</h1></div>
      <Link to="/advanced/director" className="ml-more">{t('lab.director.advanced')}</Link>
    </header>

    <section className="ml-step">
      <header><b>01</b><h2>{t('lab.director.songStep')}</h2><button type="button" className="ml-btn" onClick={() => void upload()}><Upload size={15} />{t('lab.director.uploadSong')}</button></header>
      {all.length ? <div className="ml-songs">{all.map(a => <SongCard key={a.id} item={a} on={song?.uri === a.ref?.uri} onPick={() => void pick(a.ref!)} />)}</div>
        : <p className="ml-note">{t('lab.director.noSongsBefore')}<Link to="/audio">{t('lab.tabs.audio')}</Link>{t('lab.director.noSongsAfter')}</p>}
      {song && <div className="ml-song-detail">
        <Player song={song} />
        {analysis ? <p className="ml-note">{t('lab.director.analysis', { duration: clock(duration), bpm: analysis.bpm_estimate || '—', sections: sections.length })}</p> : <p className="ml-note"><Loader2 size={13} className="ml-spin" /> {t('lab.director.analyzing')}</p>}
      </div>}
    </section>

    <section className={`ml-step ${analysis ? '' : 'is-locked'}`}>
      <header><b>02</b><h2>{t('lab.director.conceptStep')}</h2></header>
      <div className="ml-form">
        <input value={title} onChange={e => setTitle(e.target.value)} placeholder={t('lab.director.titlePlaceholder')} aria-label={t('lab.director.titleLabel')} maxLength={120} />
        <textarea rows={4} value={brief} onChange={e => setBrief(e.target.value)} aria-label={t('lab.director.briefLabel')} maxLength={10000}
          placeholder={t('lab.director.briefPlaceholder')} />
        <textarea rows={4} value={lyrics} onChange={e => setLyrics(e.target.value)} aria-label={t('lab.director.lyricsLabel')} maxLength={20000} placeholder={t('lab.director.lyricsPlaceholder')} />
        <div className="ml-form-row">
          <Choice label={t('lab.director.format')} value={ratio} onChange={setRatio} options={[['16:9', '16:9'], ['9:16', '9:16'], ['1:1', '1:1']]} />
          <Choice label={t('lab.director.clips')} value={clips} onChange={setClips} options={[['base', 'H3'], ['turbo', 'H3 Turbo', !caps.h3Turbo], ['fused_turbo', 'H3 Fused', !caps.fusedTurbo]]} />
          <Choice label={t('lab.director.frames')} value={frames} onChange={setFrames} options={[['base', 'Qwen 2.1'], ['turbo', 'Turbo', !caps.turbo]]} />
          {frames === 'base' && <Choice label={t('lab.director.quality')} value={quality} onChange={setQuality} options={[['quality', t('lab.director.qualityHigh')], ['draft', t('lab.director.qualityDraft')]]} />}
        </div>
        <div className="ml-form-row is-end">
          {!provider.ready && <p className="ml-note">{t('lab.director.providerBefore')}<Link to="/account/providers">{t('lab.director.providerLink')}</Link>{t('lab.director.providerAfter')}</p>}
          <button type="button" className="ml-btn is-accent" disabled={!analysis || !brief.trim() || planning || !provider.ready} onClick={() => void plan()}>
            {planning ? <><Loader2 size={15} className="ml-spin" />{t('lab.director.planning')}</> : <><Sparkles size={15} />{scenes.length ? t('lab.director.replan') : t('lab.director.plan')}</>}</button>
        </div>
      </div>
    </section>

    {error && <p className="ml-error" role="alert">{error}</p>}

    <AnimatePresence>{scenes.length > 0 && <motion.section className="ml-step" initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
      <header><b>03</b><h2>{t('lab.director.storyboard')}</h2><span className="ml-count">{t('lab.director.sceneCount', { count: scenes.length })} · {clock(duration)}</span></header>
      <div className="ml-timeline" aria-hidden="true">
        {sections.map((s, i) => <i key={i} style={{ left: pct(Number(s.start) || 0), width: pct((Number(s.end) || 0) - (Number(s.start) || 0)), opacity: .2 + Math.min(.6, Number(s.energy) || .3) }} />)}
        {scenes.map((s, i) => <span key={i} className={s.lip_sync ? 'is-sync' : ''} style={{ left: pct(s.start), width: pct(s.end - s.start) }}>{i + 1}</span>)}
      </div>
      <div className="ml-scenes">{scenes.map((s, i) => <motion.article key={i} className="ml-scene" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 10) * .04 }}>
        <header><b>{String(i + 1).padStart(2, '0')}</b><span>{clock(s.start)} – {clock(s.end)} · {(s.end - s.start).toFixed(1)} s</span>
          <button type="button" className={`ml-chip ${s.lip_sync ? 'is-on' : ''}`} aria-pressed={!!s.lip_sync} disabled={s.end - s.start < 2} title={t('lab.director.lipSyncHint')} onClick={() => sync(i, !s.lip_sync)}><Mic2 size={13} />{t('lab.director.lipSync')}</button></header>
        <label><small>{t('lab.director.frame')}</small><textarea rows={3} value={s.image_prompt} onChange={e => edit(i, { image_prompt: e.target.value })} /></label>
        <label><small>{t('lab.director.motion')}</small><textarea rows={s.lip_sync ? 8 : 3} value={s.video_prompt} onChange={e => edit(i, { video_prompt: e.target.value })} /></label>
      </motion.article>)}</div>
      <div className="ml-produce">
        {job && <div className={`ml-produce-state is-${job.status}`}>
          <div className="ml-job-bar"><i style={{ transform: `scaleX(${(job.status === 'completed' ? 100 : job.progress?.pct ?? 0) / 100})` }} /></div>
          <span>{job.status === 'completed' ? t('lab.director.ready') : producing ? `${t('lab.director.producing', { pct: Math.round(job.progress?.pct ?? 0) })}${job.progress?.node ? ` · ${job.progress.node}` : ''}` : job.error || t('lab.director.stopped')}</span>
        </div>}
        {producing ? <button type="button" className="ml-btn" onClick={() => void state.cancel()}><X size={15} />{t('lab.director.cancel')}</button>
          : job && ['failed', 'cancelled', 'interrupted'].includes(job.status) ? <button type="button" className="ml-btn" onClick={resume}><RotateCcw size={15} />{t('lab.director.resume')}</button> : null}
        <button type="button" className="ml-btn is-accent is-big" disabled={!title.trim() || producing} onClick={produce}><Clapperboard size={16} />{t('lab.director.produce')}</button>
      </div>
      {!title.trim() && <p className="ml-note">{t('lab.director.needTitle')}</p>}
      {state.error && <p className="ml-error" role="alert">{state.error}</p>}
      {job?.status === 'completed' && <Result job={job} />}
    </motion.section>}</AnimatePresence>
    {!scenes.length && job && <section className="ml-step"><header><b>✦</b><h2>{t('lab.director.lastProduction')}</h2></header>
      <div className="ml-produce-state"><span>{job.status === 'completed' ? t('lab.director.ready') : producing ? t('lab.director.producing', { pct: Math.round(job.progress?.pct ?? 0) }) : job.error || t('lab.director.stopped')}</span></div>
      {job.status === 'completed' && <Result job={job} />}
      {producing && <button type="button" className="ml-btn" onClick={() => void state.cancel()}><X size={15} />{t('lab.director.cancel')}</button>}
      {['failed', 'cancelled', 'interrupted'].includes(job.status) && <button type="button" className="ml-btn" onClick={resume}><RotateCcw size={15} />{t('lab.director.resume')}</button>}
    </section>}
  </div>
}
