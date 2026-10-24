import { useEffect, useState } from 'react'
import { ANIMATION_EVENT, getAnimationMode } from '../studio/lib/api'

const query = () => typeof matchMedia === 'function' ? matchMedia('(prefers-reduced-motion: reduce)') : null

/** Motion is allowed unless the OS asks to reduce it or the studio preference is "off". */
export function motionAllowed() {
  return !query()?.matches && getAnimationMode() !== 'off'
}

export function useMotionAllowed() {
  const [allowed, setAllowed] = useState(motionAllowed)
  useEffect(() => {
    const sync = () => {
      const value = motionAllowed()
      setAllowed(value)
      document.documentElement.classList.toggle('motion-off', !value)
    }
    sync()
    const media = query()
    media?.addEventListener?.('change', sync)
    window.addEventListener(ANIMATION_EVENT, sync)
    return () => { media?.removeEventListener?.('change', sync); window.removeEventListener(ANIMATION_EVENT, sync) }
  }, [])
  return allowed
}

export const finePointer = () => typeof matchMedia === 'function' && matchMedia('(pointer: fine)').matches
