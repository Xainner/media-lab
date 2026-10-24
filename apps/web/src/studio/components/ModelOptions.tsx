import { useEffect, useId, useState } from 'react'
import { runtime } from '../lib/api'
import AdvancedOptions from './AdvancedOptions'

type Field = { path: string; label: string; group: string; default: any; choices?: (string | number)[]; type?: string; min?: number; max?: number; step?: number; help?: string }
export type ModelSettings = Record<string, any>
type Catalog = { image: Field[]; edit: Field[]; video: Field[]; song: Field[]; video_resolutions: Record<string, Record<string, number[]>>; notes: Record<string, string> }

export function useModelOptions() {
  const [values, setValues] = useState<ModelSettings>({})
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [error, setError] = useState('')
  const [revision, retry] = useState(0)
  useEffect(() => {
    let live = true
    void runtime('GET', '/v1/capabilities').then(c => {
      if (live) { setCatalog(c.generation_options || null); setError(c.generation_options ? '' : 'El servidor todavía no anuncia los ajustes avanzados.') }
    }).catch(() => { if (live) setError('No se pudieron cargar los ajustes del modelo.') })
    return () => { live = false }
  }, [revision])
  function set(path: string, value: any) {
    setValues(current => {
      const next = { ...current }
      const [parent, child] = path.split('.')
      if (child) {
        next[parent] = { ...next[parent] }
        if (value === '') delete next[parent][child]; else next[parent][child] = value
        if (!Object.keys(next[parent]).length) delete next[parent]
      } else if (value === '') delete next[parent]; else next[parent] = value
      // Only compatible output combinations are offered.
      if (path === 'container' && value === 'webm') next.codec = 'av1'
      if (path === 'codec' && value === '' && next.container === 'webm') next.codec = 'av1'
      if (path === 'codec' && value === 'h264' && next.crf > 51) delete next.crf
      if (path === 'format') delete next.audio_quality
      if (path === 'resolution' && value !== 'custom') { delete next.width; delete next.height }
      return next
    })
  }
  return { values, set, catalog, error, retry: () => retry(v => v + 1), reset: () => setValues({}),
    payload: Object.keys(values).length ? values : undefined }
}
export type OptionState = ReturnType<typeof useModelOptions>

export function optionsError(state: OptionState, kind: 'image' | 'edit' | 'video' | 'song', pixelLimit = 1200000) {
  const v = state.values
  const get = (path: string) => path.split('.').reduce<any>((value, key) => value?.[key], v)
  for (const f of state.catalog?.[kind] || []) {
    const value = get(f.path)
    if (value !== undefined && !f.choices && f.type !== 'text' && (!Number.isFinite(value) || value < f.min! || value > f.max! || (f.step === 1 && !Number.isInteger(value)))) return `${f.label}: revisa el valor permitido.`
  }
  if (kind === 'image' || kind === 'video') {
    if (kind === 'image' || v.resolution === 'custom') {
      if ((v.width === undefined) !== (v.height === undefined) || (v.resolution === 'custom' && !v.width)) return 'Indica ancho y alto juntos.'
      if (v.width && (v.width % 32 || v.height % 32)) return 'El ancho y el alto deben ser múltiplos de 32.'
      if (v.width && v.width * v.height > pixelLimit) return `El tamaño supera el límite de ${(pixelLimit / 1000000).toLocaleString('es')} MP.`
    }
    if (kind === 'video' && (v.codec || 'h264') === 'h264' && v.crf > 51) return 'CRF H.264 debe estar entre 0 y 51.'
  }
  return ''
}

export function ModelOptionFields({ state, kind, omit = [], schedulerDefault }: { state: OptionState; kind: 'image' | 'edit' | 'video' | 'song'; omit?: string[]; schedulerDefault?: string }) {
  const id = useId()
  const fields = (state.catalog?.[kind] || []).filter(f => !omit.includes(f.path))
  const groups = [...new Set(fields.map(f => f.group))]
  return <div className="model-options">
    {state.error && <div role="status"><p>{state.error}</p><button className="ghost" onClick={state.retry}>Reintentar</button></div>}
    <p className="privacy">{state.catalog?.notes.sampling}</p>
    {groups.map(group => <fieldset key={group}><legend>{group}</legend><div className="model-option-grid">
      {fields.filter(f => f.group === group).map(f => {
        const current = f.path.split('.').reduce<any>((v, key) => v?.[key], state.values)
        const defaultValue = f.path === 'scheduler' && schedulerDefault ? schedulerDefault : f.default
        let choices = f.choices
        if (f.path === 'codec' && state.values.container === 'webm') choices = ['av1']
        if (f.path === 'audio_quality') {
          const format = state.values.format || 'flac'
          if (format === 'flac') return null
          choices = format === 'mp3' ? ['V0', '128k', '320k'] : ['64k', '96k', '128k', '192k', '320k']
        }
        return <div key={f.path}><label htmlFor={`${id}-${f.path}`}>{f.label}</label>{choices ?
          <select id={`${id}-${f.path}`} value={current ?? ''} onChange={e => state.set(f.path, f.path === 'bit_depth' && e.target.value ? Number(e.target.value) : e.target.value)}><option value="">Predeterminado{defaultValue != null ? ` · ${defaultValue}` : ''}</option>{choices.map(c => <option key={c} value={c}>{c}</option>)}</select> : f.type === 'text' ?
          <textarea id={`${id}-${f.path}`} rows={3} maxLength={20000} value={current ?? ''} onChange={e => state.set(f.path, e.target.value)} placeholder="Opcional"/> :
          <input id={`${id}-${f.path}`} type="number" min={f.min} max={f.path === 'crf' && (state.values.codec || 'h264') === 'h264' ? 51 : f.max} step={f.step} value={current ?? ''} placeholder={defaultValue == null ? 'Automático' : String(defaultValue)} onChange={e => state.set(f.path, e.target.value === '' ? '' : Number(e.target.value))}/>
          }{f.help && <small>{f.help}</small>}</div>
      })}
    </div>{group === 'Generación de partitura ABC' && <small>{state.catalog?.notes.score}</small>}</fieldset>)}
    {Object.keys(state.values).length > 0 && <button className="ghost" onClick={state.reset}>Restaurar ajustes del modelo</button>}
  </div>
}

export function ModelOptions({ state, kind, ...props }: Parameters<typeof ModelOptionFields>[0]) {
  return <AdvancedOptions title="Ajustes del modelo y archivo"><ModelOptionFields state={state} kind={kind} {...props}/></AdvancedOptions>
}

export function VideoResolution({ state, ratio }: { state: OptionState; ratio: string }) {
  const resolution = state.values.resolution || 'preview'
  const dimensions = state.catalog?.video_resolutions?.[resolution]?.[ratio]
  return <div className="video-resolution"><label>Resolución de generación<select aria-label="Resolución de vídeo" value={resolution} onChange={e => state.set('resolution', e.target.value)}>
    <option value="preview">Vista previa · menor consumo</option><option value="480p">Estándar · 480p</option><option value="720p">Alta · 720p alineado</option><option value="native">Nativa · ~1 MP</option><option value="custom">Personalizada</option>
  </select></label>{dimensions && <small>{dimensions[0]} × {dimensions[1]} píxeles</small>}
  {resolution === 'custom' && <div className="field-row">{['width', 'height'].map(k => <label key={k}>{k === 'width' ? 'Ancho' : 'Alto'}<input aria-label={k === 'width' ? 'Ancho de vídeo' : 'Alto de vídeo'} type="number" min={32} max={16384} step={32} value={state.values[k] ?? ''} onChange={e => state.set(k, e.target.value ? Number(e.target.value) : '')}/></label>)}</div>}
  <p className="privacy">{state.catalog?.notes.video}</p></div>
}

export function VideoQuality({ profile, steps, setSteps }: { profile: string; steps: number; setSteps: (value: number) => void }) {
  const presets = profile === 'base' ? [8, 20, 40] : [4, 8, 12]
  return <label>Preset de muestreo<select aria-label="Calidad de vídeo" value={presets.includes(steps) ? String(steps) : 'custom'} onChange={e => { if (e.target.value !== 'custom') setSteps(Number(e.target.value)) }}>
    {presets.map((n, i) => <option key={n} value={n}>{(profile === 'fused_turbo' ? ['Recomendado', 'Más nitidez', 'Máximo'] : ['Borrador', 'Recomendado', 'Más pasos'])[i]} · {n} pasos</option>)}<option value="custom">Personalizado</option>
  </select></label>
}

export function SeedField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return <label>Semilla · opcional<input aria-label="Semilla" type="number" min={0} max={Number.MAX_SAFE_INTEGER} step={1} value={value} onChange={e => onChange(e.target.value)} placeholder="Aleatoria"/></label>
}
export function seedError(value: string) { return value && (!Number.isSafeInteger(Number(value)) || Number(value) < 0) ? 'La semilla debe ser un entero entre 0 y 9007199254740991.' : '' }
