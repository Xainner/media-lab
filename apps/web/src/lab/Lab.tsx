import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { AnimatePresence, LayoutGroup, motion, useReducedMotion } from 'motion/react'
import gsap from 'gsap'
import { SplitText } from 'gsap/SplitText'
import { useGSAP } from '@gsap/react'
import { AlertTriangle, ArrowRight, ArrowUpRight, LogOut } from 'lucide-react'
import type { ArtifactRef } from '../studio/lib/api'
import Composer from './Composer'
import { removeMedia, submit, useCaps, useCreations, useLabJobs } from './live'
import { Lightbox, Masonry, Tile, type CanvasActions } from './Canvas'
import Library from './Library'
import Characters from './Characters'
import Jobs from './Jobs'
import Director from './Director'
import { Wordmark } from './Mark'
import { apps, feed, models, type Art, type Modality } from './data'
import './lab.css'

gsap.registerPlugin(SplitText, useGSAP)

const tabs = [
  { path: '/', label: 'Explorar' },
  { path: '/image', label: 'Imagen' },
  { path: '/video', label: 'Vídeo' },
  { path: '/audio', label: 'Audio' },
  { path: '/director', label: 'Director' },
  { path: '/library', label: 'Biblioteca' },
  { path: '/characters', label: 'Personajes' },
]
export type MenuGroup = { label: string; items: { path: string; title: string }[] }
const words = ['IMÁGENES', 'VÍDEO', 'MÚSICA', 'VOZ', 'PERSONAJES']

function Hero() {
  const root = useRef<HTMLElement>(null)
  const reduce = useReducedMotion()
  const [word, setWord] = useState(0)
  useEffect(() => { if (reduce) return; const t = setInterval(() => { if (!document.hidden) setWord(w => (w + 1) % words.length) }, 2200); return () => clearInterval(t) }, [reduce])
  useGSAP(() => {
    if (reduce) return
    const split = SplitText.create('.ml-hero-line', { type: 'chars', mask: 'chars' })
    gsap.from(split.chars, { yPercent: 110, rotate: 6, duration: .9, ease: 'expo.out', stagger: .025 })
    gsap.from('.ml-hero-sub, .ml-hero-cta', { y: 24, opacity: 0, duration: .8, ease: 'power3.out', delay: .45, stagger: .08 })
    return () => split.revert()
  }, { scope: root })
  const column = (offset: number) => feed.slice(offset).concat(feed.slice(0, offset))
  return <section ref={root} className="ml-hero">
    <div className="ml-hero-wall" aria-hidden="true">
      {[0, 4, 8, 2].map((o, c) => <div key={c} className={`ml-hero-col ${c % 2 ? 'is-down' : ''}`}>
        {[...column(o), ...column(o)].map((a, i) => <img key={i} src={a.src} alt="" style={{ aspectRatio: String(a.ratio) }} />)}
      </div>)}
    </div>
    <div className="ml-hero-copy">
      <h1><span className="ml-hero-line">CREA</span>
        <span className="ml-hero-word" aria-live="polite"><AnimatePresence mode="popLayout" initial={false}>
          <motion.span key={words[word]} initial={{ y: '100%' }} animate={{ y: 0 }} exit={{ y: '-100%' }} transition={{ duration: .6, ease: [.7, 0, .2, 1] }}>{words[word]}</motion.span>
        </AnimatePresence></span>
        <span className="ml-hero-line is-dim">EN TU PROPIO LAB</span></h1>
      <p className="ml-hero-sub">Imagen, vídeo, música y voz con modelos abiertos en tus dos GPU. Para ti y tus amigos.</p>
      <div className="ml-hero-cta"><Link to="/image" className="ml-btn is-accent is-big">Empezar a crear<ArrowRight size={17} /></Link><a href="#modelos" className="ml-btn is-big">Ver modelos</a></div>
    </div>
  </section>
}

type AppId = typeof apps[number]['id']

function Explore({ onOpen, onApp }: { onOpen: (a: Art) => void; onApp: (id: AppId) => void }) {
  const navigate = useNavigate()
  const mine = useCreations()
  return <>
    <Hero />
    {mine.length > 0 && <section className="ml-section">
      <header className="ml-section-head"><h2>Tus creaciones</h2><Link to="/library" className="ml-more">Biblioteca<ArrowUpRight size={14} /></Link></header>
      <div className="ml-strip">{mine.map((a, i) => <div key={a.id} className="ml-strip-item" style={{ aspectRatio: String(a.ratio) }}><Tile item={a} index={i} onOpen={onOpen} /></div>)}</div>
    </section>}
    <section className="ml-section" id="modelos">
      <header className="ml-section-head"><h2>Modelos</h2><span>Los que ya están en el Lab y los que llegan</span></header>
      <div className="ml-rail">{models.map((m, i) => <motion.button type="button" key={m.id} className="ml-model" disabled={m.status === 'soon'} onClick={() => navigate(`/${m.modality}`, { state: { model: m.id } })}
        initial={{ opacity: 0, x: 40 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ delay: i * .04, duration: .6, ease: [.2, .8, .2, 1] }}>
        <span className="ml-model-img" style={{ backgroundImage: `url(${m.art})` }} />
        {m.status !== 'ready' && <i data-status={m.status}>{m.status === 'new' ? 'NUEVO' : 'PRONTO'}</i>}
        <span className="ml-model-text"><small>{m.maker}</small><b>{m.name}</b><span>{m.blurb}</span></span>
      </motion.button>)}</div>
    </section>
    <section className="ml-section">
      <header className="ml-section-head"><h2>Apps</h2><span>Flujos listos para producir</span></header>
      <div className="ml-bento">{apps.map((a, i) => <motion.button type="button" key={a.id} className={`ml-app is-${a.size}`} onClick={() => onApp(a.id)}
        initial={{ opacity: 0, scale: .96 }} whileInView={{ opacity: 1, scale: 1 }} viewport={{ once: true }} transition={{ delay: i * .05, duration: .6 }}>
        <span className="ml-app-img" style={{ backgroundImage: `url(${a.art})` }} />
        <span className="ml-app-text"><b>{a.title}</b><span>{a.blurb}</span></span><ArrowUpRight className="ml-app-go" size={20} />
      </motion.button>)}</div>
    </section>
    <div className="ml-ticker" aria-hidden="true"><div>{[0, 1].map(k => <span key={k}>{models.map(m => <span key={m.id}>{m.name}<i>✦</i></span>)}</span>)}</div></div>
    <section className="ml-section">
      <header className="ml-section-head"><h2>Inspiración</h2><span>Lo que puedes hacer en el Lab</span></header>
      <Masonry items={feed} onOpen={onOpen} />
    </section>
  </>
}

type Seed = { kind: Modality; prompt: string; ref?: ArtifactRef; mode?: string; nonce: number }

function Create({ modality, onOpen, seed }: { modality: Modality; onOpen: (a: Art) => void; seed: Seed | null }) {
  const { jobs, loaded, add, busy } = useLabJobs(modality)
  const caps = useCaps()
  const pool = feed.filter(a => a.kind === modality || modality === 'audio')
  const progress = busy.length ? busy[0].pct : null
  const title = { image: 'Imagen', video: 'Vídeo', audio: 'Audio' }[modality]
  const active = (status: string) => status === 'queued' || status === 'running'
  return <div className="ml-create">
    {loaded && jobs.length === 0 ? <div className="ml-empty">
      <motion.h1 key={modality} initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .7, ease: [.2, .8, .2, 1] }}>
        EMPIEZA A CREAR<span>{title.toUpperCase()}</span></motion.h1>
      <p>Escribe abajo lo que imaginas. Los resultados aparecen aquí, en tu lienzo.</p>
      <div className="ml-empty-strip">{pool.slice(0, 5).map((a, i) => <motion.img key={a.src} src={a.src} alt="" initial={{ opacity: 0, y: 40, rotate: (i - 2) * 4 }} animate={{ opacity: .9, y: 0, rotate: (i - 2) * 4 }} transition={{ delay: .15 + i * .06, type: 'spring', stiffness: 160, damping: 18 }} />)}</div>
    </div> : <div className="ml-masonry is-canvas">
      <AnimatePresence initial={false}>{jobs.flatMap(j => j.status === 'completed' && j.ref
        ? [{ ref: j.ref, prompt: j.prompt }, ...j.more || []].map((m, i) => <Tile key={i ? `${j.id}-${i}` : j.id} item={{ id: i ? `${j.id}-${i}` : j.id, src: '', ref: m.ref, ratio: j.ratio, prompt: m.prompt, kind: j.kind, model: j.model }} onOpen={onOpen} />)
        : <motion.div key={j.id} className={`ml-pending ${active(j.status) ? '' : 'is-failed'}`} style={{ aspectRatio: String(j.ratio) }} layout initial={{ opacity: 0, scale: .9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}>
          {active(j.status)
            ? <><span className="ml-pending-noise" /><b>{j.status === 'queued' ? 'EN COLA' : `${Math.round(j.pct)}%`}</b><small>{j.status === 'queued' && j.queue ? `Posición ${j.queue} · ` : ''}{j.model}</small></>
            : <><AlertTriangle size={22} /><b className="is-small">{j.status === 'cancelled' ? 'Cancelado' : 'No se pudo generar'}</b><small title={j.error}>{j.error || j.prompt}</small></>}
        </motion.div>)}</AnimatePresence>
    </div>}
    <div className="ml-dock"><Composer modality={modality} caps={caps} progress={progress} seed={seed} onGenerate={s => submit(s, add)} /></div>
  </div>
}

function Telemetry({ health }: { health: any }) {
  const workers: any[] = health?.workers || []
  const queue = health?.queue ? Object.entries(health.queue).filter(([k]) => ['queued', 'pending', 'running'].includes(k)).reduce((n, [, v]) => n + (Number(v) || 0), 0) : 0
  const busy = workers.filter(w => w.busy).length
  return <Link to="/jobs" className={`ml-gpus ${health ? '' : 'is-off'}`} title="Mis trabajos" aria-label={health ? `${workers.length} GPU, ${busy} creando, ${queue} en cola. Ver mis trabajos.` : 'Sin conexión con el estudio'}>
    <i />{health ? <>{workers.length} GPU{busy > 0 && <b>{busy} creando</b>}{queue > 0 && <b>cola {queue}</b>}</> : 'Sin conexión'}
  </Link>
}

function AccountMenu({ current, groups, onLogout }: { current: any; groups: MenuGroup[]; onLogout: () => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const { pathname } = useLocation()
  useEffect(() => setOpen(false), [pathname])
  useEffect(() => {
    if (!open) return
    const away = (e: PointerEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('pointerdown', away); document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('pointerdown', away); document.removeEventListener('keydown', esc) }
  }, [open])
  return <div className="ml-account" ref={ref}>
    <button type="button" className="ml-avatar" aria-label="Menú de la cuenta" aria-expanded={open} onClick={() => setOpen(v => !v)}>{current.username?.slice(0, 1).toUpperCase()}</button>
    <AnimatePresence>{open && <motion.nav className="ml-account-menu" aria-label="Cuenta y herramientas" initial={{ opacity: 0, y: -8, scale: .98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -6 }} transition={{ type: 'spring', stiffness: 420, damping: 32 }}>
      <header><b>{current.username}</b><small>{current.role === 'admin' ? 'Administrador' : 'Miembro'}</small></header>
      {groups.map(g => <div key={g.label}><small>{g.label}</small>{g.items.map(i => <Link key={i.path} to={i.path} className={pathname === i.path ? 'is-on' : ''}>{i.title}</Link>)}</div>)}
      <button type="button" onClick={onLogout}><LogOut size={14} />Cerrar sesión</button>
    </motion.nav>}</AnimatePresence>
  </div>
}

/** Media Lab shell for every route: Explore, the creators, library, jobs and director are native; the rest renders `classic` reskinned. */
export default function Lab({ current, health, groups, onLogout, classic, tone }: { current: any; health: any; groups: MenuGroup[]; onLogout: () => void; classic: React.ReactNode; tone: string }) {
  const { pathname } = useLocation()
  const [open, setOpen] = useState<Art | null>(null)
  const [seed, setSeed] = useState<Seed | null>(null)
  const [song, setSong] = useState<ArtifactRef | null>(null)
  const navigate = useNavigate()
  const actions: CanvasActions = {
    onReuse: (kind, prompt, ref, mode) => { setSeed({ kind, prompt, ref, mode, nonce: Date.now() }); navigate(`/${kind}`) },
    onDirector: ref => { setSong(ref); navigate('/director') },
    onCharacter: ref => navigate('/characters', { state: { photo: ref } }),
    onDelete: async item => { try { return item.ref ? await removeMedia(item.ref) : false } catch (e) { window.alert(String(e)); return false } },
  }
  // Each Explore app opens the page or creator mode that does it.
  const openApp = (id: AppId) => {
    if (id === 'cover') { setSeed({ kind: 'audio', prompt: '', mode: 'Cover', nonce: Date.now() }); navigate('/audio') }
    else if (id === 'camera') { setSeed({ kind: 'image', prompt: '', mode: 'Ángulo', nonce: Date.now() }); navigate('/image') }
    else if (id === 'upscale') { setSeed({ kind: 'video', prompt: '', mode: 'Escalar', nonce: Date.now() }); navigate('/video') }
    else navigate(({ musicvideo: '/director', character: '/characters', agent: '/agent' } as const)[id])
  }
  const wantedKind = (useLocation().state as { kind?: string } | null)?.kind
  const scroller = useRef<HTMLDivElement>(null)
  const modality = (['image', 'video', 'audio'] as const).find(m => pathname === `/${m}`)
  const page = pathname === '/' ? <Explore onOpen={setOpen} onApp={openApp} />
    : pathname === '/library' || pathname === '/gallery' ? <Library onOpen={setOpen} initialKind={pathname === '/gallery' ? 'images' : wantedKind || ''} />
    : pathname === '/jobs' ? <Jobs onOpen={setOpen} />
    : pathname === '/characters' ? <Characters />
    : pathname === '/director' ? <Director incoming={song} />
    : null
  const native = !!modality || !!page
  useEffect(() => { if (scroller.current) scroller.current.scrollTop = 0 }, [pathname])
  return createPortal(<div className="ml" ref={scroller}>
    <a className="ml-skip" href="#ml-main">Saltar al contenido</a>
    <header className="ml-nav">
      <Link to="/" className="ml-home" aria-label="Media Lab, explorar"><Wordmark /></Link>
      <LayoutGroup><nav className="ml-tabs" aria-label="Secciones">{tabs.map(t => { const on = pathname === t.path; return <Link key={t.path} to={t.path} className={on ? 'is-on' : ''} aria-current={on ? 'page' : undefined}>
        {on && <motion.span layoutId="ml-tab" className="ml-tab-pill" transition={{ type: 'spring', stiffness: 420, damping: 34 }} />}
        <span>{t.label}</span></Link> })}</nav></LayoutGroup>
      <div className="ml-nav-end"><Telemetry health={health} /><AccountMenu current={current} groups={groups} onLogout={onLogout} /></div>
    </header>
    <main id="ml-main" className="ml-main" tabIndex={-1}>{modality ? <Create modality={modality} onOpen={setOpen} seed={seed} /> : page}
      {/* Classic tools stay mounted (hidden) on native routes so their running jobs keep state. */}
      <div className="rvl ml-classic" data-tone={tone} hidden={native}>{classic}</div></main>
    {native && <Lightbox item={open} onClose={() => setOpen(null)} actions={actions} />}
  </div>, document.body)
}
