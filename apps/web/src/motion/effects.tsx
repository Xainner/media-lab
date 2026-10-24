import { createElement, useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ElementType } from 'react'
import gsap from 'gsap'
import { finePointer, motionAllowed } from './prefs'

/** Words rise from below with blur; `play` toggles it (defaults to on mount). */
export function WordReveal({ text, as = 'span', className = '', play = true, delay = 0 }: { text: string; as?: ElementType; className?: string; play?: boolean; delay?: number }) {
  const ref = useRef<HTMLElement>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    el.classList.remove('is-on')
    if (!play) return
    void el.offsetWidth // reflow so the transition runs from the hidden state
    el.classList.add('is-on')
  }, [play, text])
  let i = 0
  const lines = text.split('\n').map((line, li) => <span className="line" key={li}>{line.split(' ').map((word, wi) => <span key={wi}><span className="w" style={{ '--i': i++ } as CSSProperties}>{word}</span>{wi < line.split(' ').length - 1 ? ' ' : ''}</span>)}</span>)
  return createElement(as, { ref, className: `words ${className}`, style: { '--d': `${delay}ms` } as CSSProperties, 'aria-label': text.replace(/\n/g, ' ') }, <span aria-hidden="true">{lines}</span>)
}

/** Adds .is-on when the element enters the viewport (once). */
export function useRise<T extends HTMLElement>(delay = 0) {
  const ref = useRef<T>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.setProperty('--d', `${delay}ms`)
    if (typeof IntersectionObserver === 'undefined') { el.classList.add('is-on'); return }
    const io = new IntersectionObserver(entries => { if (entries.some(e => e.isIntersecting)) { el.classList.add('is-on'); io.disconnect() } }, { threshold: .08 })
    io.observe(el)
    return () => io.disconnect()
  }, [delay])
  return ref
}

/** Cursor-lit border: writes --mx/--my on the element for the .lit effect. */
export function useSpotlight<T extends HTMLElement>() {
  return useCallback((el: T | null) => {
    if (!el || !finePointer()) return
    const move = (e: PointerEvent) => {
      const r = el.getBoundingClientRect()
      el.style.setProperty('--mx', `${e.clientX - r.left}px`)
      el.style.setProperty('--my', `${e.clientY - r.top}px`)
    }
    el.addEventListener('pointermove', move, { passive: true })
  }, [])
}

/** Magnetic hover for primary actions (fine pointers only, motion allowed). */
export function useMagnetic<T extends HTMLElement>(strength = .28) {
  const ref = useRef<T>(null)
  useEffect(() => {
    const el = ref.current
    if (!el || !finePointer() || !motionAllowed()) return
    const x = gsap.quickTo(el, 'x', { duration: .5, ease: 'power3.out' })
    const y = gsap.quickTo(el, 'y', { duration: .5, ease: 'power3.out' })
    const move = (e: PointerEvent) => {
      const r = el.getBoundingClientRect()
      x((e.clientX - r.left - r.width / 2) * strength); y((e.clientY - r.top - r.height / 2) * strength)
    }
    const leave = () => { x(0); y(0) }
    el.addEventListener('pointermove', move); el.addEventListener('pointerleave', leave)
    return () => { el.removeEventListener('pointermove', move); el.removeEventListener('pointerleave', leave); gsap.killTweensOf(el) }
  }, [strength])
  return ref
}

/** Number that counts up to its value. */
export function CountUp({ value, suffix = '' }: { value: number; suffix?: string }) {
  const [shown, setShown] = useState(motionAllowed() ? 0 : value)
  useEffect(() => {
    if (!motionAllowed()) { setShown(value); return }
    const state = { v: 0 }
    const tween = gsap.to(state, { v: value, duration: 1.2, ease: 'power3.out', onUpdate: () => setShown(Math.round(state.v)) })
    return () => { tween.kill() }
  }, [value])
  return <>{shown}{suffix}</>
}
