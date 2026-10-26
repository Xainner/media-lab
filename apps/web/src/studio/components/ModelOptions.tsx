import { useEffect, useId, useState } from 'react'
import { runtime } from '../lib/api'
import AdvancedOptions from './AdvancedOptions'
import { formatNumber, t } from '../../i18n'

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
      if (live) { setCatalog(c.generation_options || null); setError(c.generation_options ? '' : t('shell.options.notAdvertised')) }
    }).catch(() => { if (live) setError(t('shell.options.loadFailed')) })
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
    if (value !== undefined && !f.choices && f.type !== 'text' && (!Number.isFinite(value) || value < f.min! || value > f.max! || (f.step === 1 && !Number.isInteger(value)))) return t('shell.options.invalidValue', { label: f.label })
  }
  if (kind === 'image' || kind === 'video') {
    if (kind === 'image' || v.resolution === 'custom') {
      if ((v.width === undefined) !== (v.height === undefined) || (v.resolution === 'custom' && !v.width)) return t('shell.options.sizePair')
      if (v.width && (v.width % 32 || v.height % 32)) return t('shell.options.multipleOf32')
      if (v.width && v.width * v.height > pixelLimit) return t('shell.options.pixelLimit', { mp: formatNumber(pixelLimit / 1000000) })
    }
    if (kind === 'video' && (v.codec || 'h264') === 'h264' && v.crf > 51) return t('shell.options.crfRange')
  }
  return ''
}

export function ModelOptionFields({ state, kind, omit = [], schedulerDefault }: { state: OptionState; kind: 'image' | 'edit' | 'video' | 'song'; omit?: string[]; schedulerDefault?: string }) {
  const id = useId()
  const fields = (state.catalog?.[kind] || []).filter(f => !omit.includes(f.path))
  const groups = [...new Set(fields.map(f => f.group))]
  return <div className="model-options">
    {state.error && <div role="status"><p>{state.error}</p><button className="ghost" onClick={state.retry}>{t('shell.options.retry')}</button></div>}
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
          <select id={`${id}-${f.path}`} value={current ?? ''} onChange={e => state.set(f.path, f.path === 'bit_depth' && e.target.value ? Number(e.target.value) : e.target.value)}><option value="">{defaultValue != null ? t('shell.options.defaultValue', { value: String(defaultValue) }) : t('shell.options.default')}</option>{choices.map(c => <option key={c} value={c}>{c}</option>)}</select> : f.type === 'text' ?
          <textarea id={`${id}-${f.path}`} rows={3} maxLength={20000} value={current ?? ''} onChange={e => state.set(f.path, e.target.value)} placeholder={t('shell.options.optional')}/> :
          <input id={`${id}-${f.path}`} type="number" min={f.min} max={f.path === 'crf' && (state.values.codec || 'h264') === 'h264' ? 51 : f.max} step={f.step} value={current ?? ''} placeholder={defaultValue == null ? t('shell.options.auto') : String(defaultValue)} onChange={e => state.set(f.path, e.target.value === '' ? '' : Number(e.target.value))}/>
          }{f.help && <small>{f.help}</small>}</div>
      })}
    </div>{group === 'Generación de partitura ABC' && <small>{state.catalog?.notes.score}</small>}</fieldset>)}
    {Object.keys(state.values).length > 0 && <button className="ghost" onClick={state.reset}>{t('shell.options.reset')}</button>}
  </div>
}

export function ModelOptions({ state, kind, ...props }: Parameters<typeof ModelOptionFields>[0]) {
  return <AdvancedOptions title={t('shell.options.title')}><ModelOptionFields state={state} kind={kind} {...props}/></AdvancedOptions>
}

export function VideoResolution({ state, ratio }: { state: OptionState; ratio: string }) {
  const resolution = state.values.resolution || 'preview'
  const dimensions = state.catalog?.video_resolutions?.[resolution]?.[ratio]
  return <div className="video-resolution"><label>{t('shell.options.resolution')}<select aria-label={t('shell.options.videoResolution')} value={resolution} onChange={e => state.set('resolution', e.target.value)}>
    <option value="preview">{t('shell.options.res.preview')}</option><option value="480p">{t('shell.options.res.480p')}</option><option value="720p">{t('shell.options.res.720p')}</option><option value="native">{t('shell.options.res.native')}</option><option value="custom">{t('shell.options.res.custom')}</option>
  </select></label>{dimensions && <small>{t('shell.options.pixels', { width: dimensions[0], height: dimensions[1] })}</small>}
  {resolution === 'custom' && <div className="field-row">{['width', 'height'].map(k => <label key={k}>{k === 'width' ? t('shell.options.width') : t('shell.options.height')}<input aria-label={k === 'width' ? t('shell.options.videoWidth') : t('shell.options.videoHeight')} type="number" min={32} max={16384} step={32} value={state.values[k] ?? ''} onChange={e => state.set(k, e.target.value ? Number(e.target.value) : '')}/></label>)}</div>}
  <p className="privacy">{state.catalog?.notes.video}</p></div>
}

export function VideoQuality({ profile, steps, setSteps }: { profile: string; steps: number; setSteps: (value: number) => void }) {
  const presets = profile === 'base' ? [8, 20, 40] : [4, 8, 12]
  return <label>{t('shell.options.samplingPreset')}<select aria-label={t('shell.options.videoQuality')} value={presets.includes(steps) ? String(steps) : 'custom'} onChange={e => { if (e.target.value !== 'custom') setSteps(Number(e.target.value)) }}>
    {presets.map((n, i) => <option key={n} value={n}>{t('shell.options.presetSteps', { name: t((profile === 'fused_turbo' ? ['shell.options.preset.recommended', 'shell.options.preset.sharper', 'shell.options.preset.max'] as const : ['shell.options.preset.draft', 'shell.options.preset.recommended', 'shell.options.preset.moreSteps'] as const)[i]), count: n })}</option>)}<option value="custom">{t('shell.options.preset.custom')}</option>
  </select></label>
}

export function SeedField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return <label>{t('shell.options.seedOptional')}<input aria-label={t('shell.options.seed')} type="number" min={0} max={Number.MAX_SAFE_INTEGER} step={1} value={value} onChange={e => onChange(e.target.value)} placeholder={t('shell.options.seedRandom')}/></label>
}
export function seedError(value: string) { return value && (!Number.isSafeInteger(Number(value)) || Number(value) < 0) ? t('shell.options.seedInvalid') : '' }
