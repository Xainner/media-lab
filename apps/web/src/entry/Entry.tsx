import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import gsap from 'gsap'
import { ArrowRight, Eye, EyeOff, ShieldCheck } from 'lucide-react'
import { Mark, Wordmark } from '../lab/Mark'
import { nebula } from '../motion/Nebula'
import { motionAllowed, finePointer } from '../motion/prefs'
import { WordReveal, useMagnetic, useSpotlight } from '../motion/effects'
import { Loading, Notice } from '../ui'

export type EntryMode = 'login' | 'accept' | 'forgot' | 'reset'
const INTRO_KEY = 'rvl-intro-seen'
const TICKER = ['Imagen', 'Edición', 'Vídeo', 'Audio', 'Director', 'Agente', 'Qwen Image 2.1', 'MiniMax H3', 'YuE2']
// The showcase wall: four columns of Lab art drifting in alternate directions behind the access card.
const WALL = [
  ['feed-alley', 'model-video', 'feed-ocean', 'app-character'],
  ['model-image', 'feed-fashion', 'app-musicvideo', 'feed-desert'],
  ['feed-anime', 'app-camera', 'model-director', 'feed-product'],
  ['model-music', 'feed-miniature', 'app-cover', 'feed-food'],
]

/** Cinematic entrance: the Media Lab mark is drawn in light, the aperture opens onto a wall of
 * Lab creations behind the access panel. Purely presentational: auth lives in main.tsx. */
export default function Entry({ mode, loading, factor, children, onSkipRef }: {
  mode: EntryMode; loading: boolean; factor: ReactNode | null; children: ReactNode
  onSkipRef?: (exit: () => Promise<void>) => void
}) {
  const root = useRef<HTMLDivElement>(null)
  const [introDone, setIntroDone] = useState(() => !motionAllowed() || sessionStorage.getItem(INTRO_KEY) === '1')
  const tl = useRef<gsap.core.Timeline>()
  const spotlight = useSpotlight<HTMLDivElement>()

  useEffect(() => { nebula.tone('entry') }, [])

  // Intro timeline (once per session; skippable; absent with reduced motion).
  useLayoutEffect(() => {
    const el = root.current
    if (!el || introDone) return
    const q = gsap.utils.selector(el)
    const paths = q('.logo-trace [data-draw]') as unknown as SVGGeometryElement[]
    paths.forEach(p => { const len = p.getTotalLength?.() || 400; gsap.set(p, { strokeDasharray: len, strokeDashoffset: len }) })
    nebula.warp(1)
    const t = gsap.timeline({ defaults: { ease: 'power3.out' }, onComplete: finish })
    t.set(q('.entry-scene'), { scale: 1.28, filter: 'blur(14px)' })
      .set(q('.entry-card, .entry-ticker'), { autoAlpha: 0 })
      .to(paths, { strokeDashoffset: 0, duration: 1.15, stagger: .045, ease: 'power2.inOut' }, .15)
      .fromTo(q('.intro-emblem'), { autoAlpha: 0, scale: .82, filter: 'blur(10px)' }, { autoAlpha: 1, scale: 1, filter: 'blur(0px)', duration: .7 }, 1.05)
      .to(q('.logo-trace'), { autoAlpha: 0, duration: .5 }, 1.35)
      .to(q('.intro-flare'), { autoAlpha: 1, scale: 1.6, duration: .45, ease: 'power2.out' }, 1.55)
      .to(q('.intro-flare'), { autoAlpha: 0, duration: .5 }, 1.95)
      .to(q('.intro-veil'), { '--hole': '160%', duration: 1.3, ease: 'expo.inOut' }, 1.7)
      .to(q('.intro-mark'), { scale: 3.2, autoAlpha: 0, duration: 1.1, ease: 'expo.in' }, 1.75)
      .add(() => nebula.warp(0), 1.9)
      .to(q('.entry-scene'), { scale: 1, filter: 'blur(0px)', duration: 1.8, ease: 'expo.out' }, 1.95)
      .fromTo(q('.entry-card'), { autoAlpha: 0, y: 40, rotateX: 12 }, { autoAlpha: 1, y: 0, rotateX: 0, duration: 1.1 }, 2.45)
      .to(q('.entry-ticker'), { autoAlpha: 1, duration: .8 }, 2.8)
    tl.current = t
    // Follow wall-clock time even when frames are throttled, and never let the intro outstay its welcome.
    gsap.ticker.lagSmoothing(0)
    const deadline = window.setTimeout(() => t.progress(1), 6500)
    function finish() { sessionStorage.setItem(INTRO_KEY, '1'); nebula.warp(0); setIntroDone(true) }
    const skip = (e: Event) => { if (e instanceof KeyboardEvent && ['Tab', 'Shift'].includes(e.key)) return; t.progress(1) }
    window.addEventListener('keydown', skip); el.querySelector('.intro')?.addEventListener('pointerdown', skip)
    return () => { window.removeEventListener('keydown', skip); window.clearTimeout(deadline); gsap.ticker.lagSmoothing(500, 33); t.kill() }
  }, [introDone])

  // Pointer parallax across the layered scene.
  useEffect(() => {
    const el = root.current
    if (!el || !finePointer() || !motionAllowed()) return
    const layers = Array.from(el.querySelectorAll<HTMLElement>('[data-depth]'))
    const setters = layers.map(l => ({ x: gsap.quickTo(l, 'x', { duration: 1.2, ease: 'power3.out' }), y: gsap.quickTo(l, 'y', { duration: 1.2, ease: 'power3.out' }), d: Number(l.dataset.depth) }))
    const move = (e: PointerEvent) => { const nx = e.clientX / innerWidth - .5, ny = e.clientY / innerHeight - .5; setters.forEach(s => { s.x(-nx * s.d); s.y(-ny * s.d * .6) }) }
    addEventListener('pointermove', move, { passive: true })
    return () => removeEventListener('pointermove', move)
  }, [])

  // Exit: the aperture closes on the emblem and the stars streak into the studio.
  useEffect(() => {
    onSkipRef?.(() => new Promise<void>(resolve => {
      const el = root.current
      if (!el || !motionAllowed()) return resolve()
      const q = gsap.utils.selector(el)
      nebula.warp(1)
      // Signing in must never wait on throttled frames: resolve by wall clock at the latest.
      const done = () => { window.clearTimeout(guard); nebula.warp(0); resolve() }
      const guard = window.setTimeout(done, 1600)
      gsap.timeline({ onComplete: done })
        .to(q('.entry-card'), { autoAlpha: 0, y: -20, scale: .97, duration: .45, ease: 'power2.in' }, .35)
        .to(q('.entry-scene'), { scale: 1.6, filter: 'blur(18px)', autoAlpha: 0, duration: .9, ease: 'expo.in' }, .4)
    }))
  }, [onSkipRef])

  const title = mode === 'login' ? 'Crea sin\nlímites.' : mode === 'accept' ? 'Tu lugar\nen el Lab.' : 'Volvamos\na crear.'
  return <div ref={root} className={`entry ${introDone ? 'is-ready' : 'is-intro'}`}>
    <div className="entry-scene" aria-hidden="true">
      <div className="entry-wall" data-depth="14">{WALL.map((column, c) => <div key={c} className="entry-column">
        {[...column, ...column].map((name, i) => <img key={i} src={`/art/lab/${name}.webp`} alt="" loading={i < 4 ? 'eager' : 'lazy'} decoding="async" />)}
      </div>)}</div>
      <div className="entry-portal-glow" data-depth="22" />
    </div>

    <main className="entry-stage">
      <div className="entry-card-wrap">
        <section ref={spotlight} className="entry-card glass lit" aria-labelledby="entry-title">
          <Wordmark />
          {loading ? <Loading /> : factor ? factor : <>
            <WordReveal as="h1" text={title} className="entry-title" play={introDone} delay={120} />
            <p className="entry-sub">{mode === 'login' ? 'Imagen, vídeo y música con IA, en tu propio servidor. Entra y dale vida a tu próxima idea.' : mode === 'accept' ? 'Tu invitación abre la puerta. Elige cómo te llamarás en el estudio.' : 'Te ayudamos a volver a tu espacio creativo.'}</p>
            <span id="entry-title" className="sr-only">{mode === 'login' ? 'Iniciar sesión' : mode === 'accept' ? 'Crear tu cuenta' : 'Recuperar acceso'}</span>
            {children}
          </>}
          <p className="entry-private"><ShieldCheck size={16} /> Tu estudio privado · solo por invitación · uso personal</p>
        </section>
      </div>
    </main>

    <div className="entry-ticker" aria-hidden="true"><div>{[...TICKER, ...TICKER].map((t, i) => <span key={i}>{t}<i>✦</i></span>)}</div></div>

    {!introDone && <div className="intro">
      <div className="intro-veil" aria-hidden="true" />
      <div className="intro-mark" aria-hidden="true">
        <svg className="logo-trace" viewBox="0 0 32 32" fill="none" stroke="var(--ml-accent)" strokeWidth=".5" strokeLinecap="round">
          <rect data-draw x="1" y="1" width="30" height="30" rx="9" /><circle data-draw cx="16" cy="16" r="8.2" /><circle data-draw cx="16" cy="16" r="2.7" />
        </svg>
        <span className="intro-emblem"><Mark size={260} /></span><span className="intro-flare" />
      </div>
      <button type="button" className="intro-skip" onClick={() => tl.current?.progress(1)}>Saltar intro</button>
    </div>}
  </div>
}

export function PasswordField({ value, onChange, visible, setVisible, mode }: {
  value: string; onChange: (v: string) => void; visible: boolean; setVisible: (v: boolean) => void; mode: EntryMode
}) {
  return <label>Contraseña<div className="password-field"><input type={visible ? 'text' : 'password'} required autoComplete={mode === 'login' ? 'current-password' : 'new-password'} placeholder="Tu contraseña" value={value} onChange={e => onChange(e.target.value)} minLength={mode === 'login' ? undefined : 15} maxLength={128} /><button type="button" className="icon-button" aria-label={visible ? 'Ocultar contraseña' : 'Mostrar contraseña'} onClick={() => setVisible(!visible)}>{visible ? <EyeOff size={18} /> : <Eye size={18} />}</button></div>{mode !== 'login' && <small>Entre 15 y 128 caracteres.</small>}</label>
}

export function SubmitButton({ busy, disabled, children }: { busy: boolean; disabled: boolean; children: ReactNode }) {
  const ref = useMagnetic<HTMLButtonElement>(.3)
  return <button ref={ref} type="submit" className="primary entry-submit" disabled={disabled}>{busy ? 'Un momento…' : children}<ArrowRight size={18} /></button>
}
