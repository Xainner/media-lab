import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AnimatePresence, motion } from 'motion/react'
import { AudioLines, Check, Clapperboard, Download, Loader2, Mic2, RotateCcw, Sparkles, Upload, X } from 'lucide-react'
import { newSession, runtime, type ArtifactRef } from '../studio/lib/api'
import { useCreativeJob } from '../studio/views/CreativeJob'
import { lipSyncTemplate } from '../studio/lib/h3'
import { useCaps, useLibrary, useMediaSrc, useProvider } from './live'
import type { Art } from './data'

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
    <span><b>{item.prompt || 'Canción sin título'}</b><small>{item.model}</small></span>
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
    {master && <button type="button" className="ml-btn is-accent" onClick={() => void window.visualLab.runtime.saveMedia(master.uri)}><Download size={15} />Exportar master con audio original</button>}
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
      if (!/\.(wav|flac|mp3|opus|ogg)$/i.test(r.data.uri)) throw new Error('Elige un archivo de audio.')
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
  const pct = (t: number) => duration ? `${Math.max(0, Math.min(100, t / duration * 100))}%` : '0%'
  const sections: any[] = Array.isArray(analysis?.sections) ? analysis.sections : []
  const all = [...songs.items, ...uploads.items]
  return <div className="ml-page ml-director">
    <header className="ml-page-head">
      <div><small className="ml-kicker">De tu canción a un videoclip</small><h1>Director</h1></div>
      <Link to="/advanced/director" className="ml-more">Ajustes avanzados</Link>
    </header>

    <section className="ml-step">
      <header><b>01</b><h2>La canción</h2><button type="button" className="ml-btn" onClick={() => void upload()}><Upload size={15} />Subir canción</button></header>
      {all.length ? <div className="ml-songs">{all.map(a => <SongCard key={a.id} item={a} on={song?.uri === a.ref?.uri} onPick={() => void pick(a.ref!)} />)}</div>
        : <p className="ml-note">Crea una canción en <Link to="/audio">Audio</Link> o sube un archivo.</p>}
      {song && <div className="ml-song-detail">
        <Player song={song} />
        {analysis ? <p className="ml-note">{clock(duration)} · {analysis.bpm_estimate || '—'} BPM · {sections.length} secciones · analizada en tu servidor</p> : <p className="ml-note"><Loader2 size={13} className="ml-spin" /> Analizando la canción…</p>}
      </div>}
    </section>

    <section className={`ml-step ${analysis ? '' : 'is-locked'}`}>
      <header><b>02</b><h2>El concepto</h2></header>
      <div className="ml-form">
        <input value={title} onChange={e => setTitle(e.target.value)} placeholder="Título del videoclip" aria-label="Título" maxLength={120} />
        <textarea rows={4} value={brief} onChange={e => setBrief(e.target.value)} aria-label="Concepto visual" maxLength={10000}
          placeholder="Concepto visual: quién aparece, vestuario, lugares, luz y estilo. Ej.: la cantante recorre una ciudad flotante de noche, estética anime, neón cálido…" />
        <textarea rows={4} value={lyrics} onChange={e => setLyrics(e.target.value)} aria-label="Letra" maxLength={20000} placeholder="Letra o resumen (opcional): ayuda a cortar las escenas en los momentos clave." />
        <div className="ml-form-row">
          <Choice label="Formato" value={ratio} onChange={setRatio} options={[['16:9', '16:9'], ['9:16', '9:16'], ['1:1', '1:1']]} />
          <Choice label="Clips" value={clips} onChange={setClips} options={[['base', 'H3'], ['turbo', 'H3 Turbo', !caps.h3Turbo], ['fused_turbo', 'H3 Fused', !caps.fusedTurbo]]} />
          <Choice label="Fotogramas" value={frames} onChange={setFrames} options={[['base', 'Qwen 2.1'], ['turbo', 'Turbo', !caps.turbo]]} />
          {frames === 'base' && <Choice label="Calidad" value={quality} onChange={setQuality} options={[['quality', 'Calidad'], ['draft', 'Borrador']]} />}
        </div>
        <div className="ml-form-row is-end">
          {!provider.ready && <p className="ml-note">El storyboard lo escribe tu proveedor IA. <Link to="/account/providers">Configúralo</Link> para continuar.</p>}
          <button type="button" className="ml-btn is-accent" disabled={!analysis || !brief.trim() || planning || !provider.ready} onClick={() => void plan()}>
            {planning ? <><Loader2 size={15} className="ml-spin" />Escribiendo escenas</> : <><Sparkles size={15} />{scenes.length ? 'Rehacer storyboard' : 'Crear storyboard'}</>}</button>
        </div>
      </div>
    </section>

    {error && <p className="ml-error" role="alert">{error}</p>}

    <AnimatePresence>{scenes.length > 0 && <motion.section className="ml-step" initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
      <header><b>03</b><h2>Storyboard</h2><span className="ml-count">{scenes.length} {scenes.length === 1 ? "escena" : "escenas"} · {clock(duration)}</span></header>
      <div className="ml-timeline" aria-hidden="true">
        {sections.map((s, i) => <i key={i} style={{ left: pct(Number(s.start) || 0), width: pct((Number(s.end) || 0) - (Number(s.start) || 0)), opacity: .2 + Math.min(.6, Number(s.energy) || .3) }} />)}
        {scenes.map((s, i) => <span key={i} className={s.lip_sync ? 'is-sync' : ''} style={{ left: pct(s.start), width: pct(s.end - s.start) }}>{i + 1}</span>)}
      </div>
      <div className="ml-scenes">{scenes.map((s, i) => <motion.article key={i} className="ml-scene" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 10) * .04 }}>
        <header><b>{String(i + 1).padStart(2, '0')}</b><span>{clock(s.start)} – {clock(s.end)} · {(s.end - s.start).toFixed(1)} s</span>
          <button type="button" className={`ml-chip ${s.lip_sync ? 'is-on' : ''}`} aria-pressed={!!s.lip_sync} disabled={s.end - s.start < 2} title="La imagen de la escena es la identidad y el tramo de la canción guía la boca. Experimental; mínimo 2 s." onClick={() => sync(i, !s.lip_sync)}><Mic2 size={13} />Labios</button></header>
        <label><small>Fotograma</small><textarea rows={3} value={s.image_prompt} onChange={e => edit(i, { image_prompt: e.target.value })} /></label>
        <label><small>Movimiento</small><textarea rows={s.lip_sync ? 8 : 3} value={s.video_prompt} onChange={e => edit(i, { video_prompt: e.target.value })} /></label>
      </motion.article>)}</div>
      <div className="ml-produce">
        {job && <div className={`ml-produce-state is-${job.status}`}>
          <div className="ml-job-bar"><i style={{ transform: `scaleX(${(job.status === 'completed' ? 100 : job.progress?.pct ?? 0) / 100})` }} /></div>
          <span>{job.status === 'completed' ? 'Videoclip listo' : producing ? `Produciendo · ${Math.round(job.progress?.pct ?? 0)}%${job.progress?.node ? ` · ${job.progress.node}` : ''}` : job.error || 'La producción se detuvo'}</span>
        </div>}
        {producing ? <button type="button" className="ml-btn" onClick={() => void state.cancel()}><X size={15} />Cancelar</button>
          : job && ['failed', 'cancelled', 'interrupted'].includes(job.status) ? <button type="button" className="ml-btn" onClick={resume}><RotateCcw size={15} />Reanudar</button> : null}
        <button type="button" className="ml-btn is-accent is-big" disabled={!title.trim() || producing} onClick={produce}><Clapperboard size={16} />Producir videoclip</button>
      </div>
      {!title.trim() && <p className="ml-note">Ponle un título al videoclip para producirlo.</p>}
      {state.error && <p className="ml-error" role="alert">{state.error}</p>}
      {job?.status === 'completed' && <Result job={job} />}
    </motion.section>}</AnimatePresence>
    {!scenes.length && job && <section className="ml-step"><header><b>✦</b><h2>Última producción</h2></header>
      <div className="ml-produce-state"><span>{job.status === 'completed' ? 'Videoclip listo' : producing ? `Produciendo · ${Math.round(job.progress?.pct ?? 0)}%` : job.error || 'La producción se detuvo'}</span></div>
      {job.status === 'completed' && <Result job={job} />}
      {producing && <button type="button" className="ml-btn" onClick={() => void state.cancel()}><X size={15} />Cancelar</button>}
      {['failed', 'cancelled', 'interrupted'].includes(job.status) && <button type="button" className="ml-btn" onClick={resume}><RotateCcw size={15} />Reanudar</button>}
    </section>}
  </div>
}
