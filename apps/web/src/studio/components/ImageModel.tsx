import { useEffect, useState } from 'react'
import { runtime } from '../lib/api'
import { Segmented } from './Kit'

export type Variant = 'base' | 'turbo'
export type Precision = 'int8' | 'bf16'
type Availability = Record<Variant, Record<Precision, boolean>>

const KEY = 'media-lab:image-variant'
/** Turbo always runs its fixed 8-step schedule: these options are rejected by the runtime. */
export const TURBO_FIXED = ['steps', 'scheduler', 'denoise']

function stored(): Variant {
  try { return localStorage.getItem(KEY) === 'turbo' ? 'turbo' : 'base' } catch { return 'base' }
}

/** Live Qwen-Image 2.1 / Turbo availability per precision, plus the remembered choice. */
export function useImageModel(active = true) {
  const [variant, setVariantState] = useState<Variant>(stored)
  const [precision, setPrecision] = useState<Precision>('int8')
  const [ready, setReady] = useState<Availability>({ base: { int8: true, bf16: false }, turbo: { int8: false, bf16: false } })
  useEffect(() => {
    if (!active) return
    let live = true
    runtime('GET', '/v1/capabilities').then(c => {
      if (!live) return
      const variants = c.model_variants || {}
      setReady({
        base: { int8: variants.base?.precisions?.int8 ?? true, bf16: Boolean(variants.base?.precisions?.bf16 ?? c.model_precisions?.bf16) },
        turbo: { int8: Boolean(variants.turbo?.precisions?.int8), bf16: Boolean(variants.turbo?.precisions?.bf16) },
      })
    }).catch(() => {})
    return () => { live = false }
  }, [active])
  const turboReady = ready.turbo.int8 || ready.turbo.bf16
  const effective: Variant = variant === 'turbo' && !turboReady ? 'base' : variant
  const effectivePrecision: Precision = ready[effective][precision] ? precision : 'int8'
  function setVariant(value: Variant) {
    setVariantState(value)
    try { localStorage.setItem(KEY, value) } catch { /* per-viewer convenience only */ }
  }
  return { variant: effective, setVariant, precision: effectivePrecision, setPrecision, ready, turboReady,
    turbo: effective === 'turbo', bf16: ready[effective].bf16 }
}
export type ImageModelState = ReturnType<typeof useImageModel>

/** Drop the options Turbo rejects so a value left over from Qwen 2.1 never blocks a job. */
export function variantOptions(variant: Variant, payload: Record<string, any> | undefined) {
  if (variant !== 'turbo' || !payload) return payload
  const kept = Object.fromEntries(Object.entries(payload).filter(([key]) => !TURBO_FIXED.includes(key)))
  return Object.keys(kept).length ? kept : undefined
}

export const variantLabel = (variant?: string) => variant === 'turbo' ? 'Turbo' : 'Qwen 2.1'

export function ImageModelPicker({ state }: { state: ImageModelState }) {
  if (!state.turboReady) return null
  return <Segmented<Variant> label="Modelo de imagen" value={state.variant} onChange={state.setVariant} options={[
    { value: 'base', label: 'Qwen 2.1', hint: 'Máxima calidad · 25–40 pasos' },
    { value: 'turbo', label: 'Turbo', hint: 'Rápido · 8 pasos' },
  ]} />
}

export function PrecisionSelect({ state, onChange }: { state: ImageModelState; onChange?: (value: Precision) => void }) {
  return <label>Pesos de difusión<select aria-label="Precisión del modelo" value={state.precision} onChange={e => { state.setPrecision(e.target.value as Precision); onChange?.(e.target.value as Precision) }}>
    <option value="int8">INT8 · actual</option>
    {state.bf16 && <option value="bf16">BF16 · experimental</option>}
  </select></label>
}
