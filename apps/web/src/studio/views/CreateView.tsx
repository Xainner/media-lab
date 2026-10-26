import { ModelOptions, useModelOptions, optionsError } from '../components/ModelOptions'
import AdvancedOptions from '../components/AdvancedOptions'
import { useEffect, useRef, useState } from 'react'
import ArtifactResult from '../components/ArtifactResult'
import PromptEnhancePanel from '../components/PromptEnhancePanel'
import JobProgress from '../components/JobProgress'
import GenerationCanvas, { aspectFromRatio } from '../components/GenerationCanvas'
import { Action, Actions, EmptyStage, Step, Tool } from '../components/Kit'
import { ImageModelPicker, PrecisionSelect, TURBO_FIXED, useImageModel, variantLabel, variantOptions } from '../components/ImageModel'
import { cancelJob, clearRecoveryValue, enhancePrompt, getEnhancerMode, isAbortError, runtime, waitJob, type ArtifactRef, type EnhancerMode, type Job } from '../lib/api'
import { t, type MessageKey } from '../../i18n'

type AspectPreset = { id: string; label: string; orientation: string; width: number; height: number }
const FALLBACK_PRESETS: AspectPreset[] = [
  { id: '1:1', label: 'Cuadrado', orientation: 'square', width: 1024, height: 1024 },
  { id: '16:9', label: 'Panorámico', orientation: 'landscape', width: 1344, height: 768 },
  { id: '9:16', label: 'Historia vertical', orientation: 'portrait', width: 768, height: 1344 },
  { id: '4:3', label: 'Horizontal clásico', orientation: 'landscape', width: 1152, height: 864 },
  { id: '3:4', label: 'Retrato clásico', orientation: 'portrait', width: 864, height: 1152 },
  { id: '3:2', label: 'Foto horizontal', orientation: 'landscape', width: 1216, height: 832 },
  { id: '2:3', label: 'Foto vertical', orientation: 'portrait', width: 832, height: 1216 },
  { id: '5:4', label: 'Social horizontal', orientation: 'landscape', width: 1120, height: 896 },
  { id: '4:5', label: 'Social vertical', orientation: 'portrait', width: 896, height: 1120 },
]
// The runtime sends Spanish preset names; known ratios are shown in the active language, unknown ones as received.
const PRESET_LABELS: Record<string, MessageKey> = {
  '1:1': 'studio.create.preset.square', '16:9': 'studio.create.preset.landscape', '9:16': 'studio.create.preset.story',
  '4:3': 'studio.create.preset.classicLandscape', '3:4': 'studio.create.preset.classicPortrait', '3:2': 'studio.create.preset.photoLandscape',
  '2:3': 'studio.create.preset.photoPortrait', '5:4': 'studio.create.preset.socialLandscape', '4:5': 'studio.create.preset.socialPortrait',
}
const presetLabel = (p: AspectPreset) => PRESET_LABELS[p.id] ? t(PRESET_LABELS[p.id]) : p.label

export default function CreateView({ active }: { active: boolean }) {
  const modelOptions = useModelOptions()
  const recoveryKey = 'media-lab:create-job'
  const operationController = useRef<AbortController | null>(null)
  const [prompt, setPrompt] = useState('')
  const [ratio, setRatio] = useState('1:1')
  const [quality, setQuality] = useState('quality')
  const [transparent, setTransparent] = useState(false)
  const [tier, setTier] = useState('1mp')
  const [twoK, setTwoK] = useState(false)
  const model = useImageModel(active)
  const { precision, turbo } = model
  const [seed, setSeed] = useState('')
  const optionError = optionsError(modelOptions, 'image', twoK && precision === 'int8' ? 4500000 : 1200000)
  const [comparison, setComparison] = useState<{ media: ArtifactRef; meta: any } | null>(null)
  const [lastRequest, setLastRequest] = useState<any>(null)
  const [presets, setPresets] = useState<AspectPreset[]>(FALLBACK_PRESETS)
  const [job, setJob] = useState<Job | null>(null)
  const [media, setMedia] = useState<ArtifactRef | null>(null)
  const [meta, setMeta] = useState<any>(null)
  const [recovering, setRecovering] = useState(false)
  const [cancelError, setCancelError] = useState('')
  const [cancelling, setCancelling] = useState(false)
  const [enhancer, setEnhancer] = useState<EnhancerMode>(getEnhancerMode)
  const [enhancing, setEnhancing] = useState(false)
  const [usedPrompt, setUsedPrompt] = useState('')

  useEffect(() => { if (active) setEnhancer(getEnhancerMode()) }, [active])

  useEffect(() => {
    if (!active) return
    let cancelled = false
    runtime('GET', '/v1/capabilities').then(c => {
      if (cancelled) return
      setTwoK(c.two_k_enabled)
      if (Array.isArray(c.resolution_presets) && c.resolution_presets.length) setPresets(c.resolution_presets)
    }).catch(() => {})
    return () => { cancelled = true }
  }, [active])

  useEffect(() => {
    if (!active) return
    const jobId = localStorage.getItem(recoveryKey)
    if (!jobId) {
      setRecovering(false)
      return
    }
    const controller = new AbortController()
    let cancelled = false
    setRecovering(true)
    waitJob(jobId, value => { if (!cancelled && !controller.signal.aborted) setJob(value) }, controller.signal).then(final => {
      if (cancelled || controller.signal.aborted) return
      clearRecoveryValue(recoveryKey, jobId)
      if (final.status === 'completed' && final.result) {
        setMedia(final.result.media[0]); setMeta(final.result.data)
      }
    }).catch(error => {
      if (cancelled || controller.signal.aborted || isAbortError(error)) return
      clearRecoveryValue(recoveryKey, jobId)
      setJob({ id: jobId, session_id: '', operation: 'generate', status: 'failed', activity: [], error: error.message })
    }).finally(() => {
      if (!cancelled) setRecovering(false)
    })
    return () => { cancelled = true; controller.abort() }
  }, [active])

  useEffect(() => () => operationController.current?.abort(), [])

  // A comparison repeats the last request with the same seed, flipping either the
  // precision (INT8/BF16) or the model (Qwen 2.1/Turbo).
  function comparisonRequest(kind: 'precision' | 'variant') {
    if (!lastRequest || !Number.isSafeInteger(meta?.seed) || lastRequest.resolution_tier === '2k') return null
    const variant = lastRequest.model_variant || 'base'
    if (kind === 'precision') {
      const other = lastRequest.model_precision === 'bf16' ? 'int8' : 'bf16'
      return model.ready[variant as 'base' | 'turbo'][other] ? { ...lastRequest, model_precision: other, seed: meta.seed } : null
    }
    const other = variant === 'turbo' ? 'base' : 'turbo'
    if (!model.ready[other][lastRequest.model_precision as 'int8' | 'bf16']) return null
    return { ...lastRequest, model_variant: other, seed: meta.seed, options: variantOptions(other, lastRequest.options) }
  }

  async function generate(compare: false | 'precision' | 'variant' = false, skipEnhance = false) {
    if ((!compare && !prompt.trim()) || recovering || enhancing || ['queued', 'running'].includes(job?.status || '')) return
    if (compare && (!media || !comparisonRequest(compare))) return
    const controller = new AbortController()
    operationController.current?.abort()
    operationController.current = controller
    setCancelError('')
    if (!compare) { setMedia(null); setMeta(null); setComparison(null); setUsedPrompt('') }
    let acceptedJobId = ''
    try {
      const requestedSeed = seed.trim() ? Number(seed) : null
      if (!compare && requestedSeed !== null && (!Number.isSafeInteger(requestedSeed) || requestedSeed < 0)) {
        throw new Error(t('studio.create.seedInvalid'))
      }
      let finalPrompt = prompt.trim()
      if (!compare && !skipEnhance && enhancer === 'external') {
        setEnhancing(true)
        try { finalPrompt = (await enhancePrompt(enhancer, finalPrompt, 't2i')).trim() || finalPrompt }
        catch (error: any) { throw new Error(t('studio.shared.enhanceFailed', { message: error.message })) }
        finally { setEnhancing(false) }
        if (controller.signal.aborted) return
        setUsedPrompt(finalPrompt)
      }
      const request = compare
        ? comparisonRequest(compare)
        : { prompt: finalPrompt, aspect_ratio: ratio, quality, transparent, resolution_tier: tier,
            model_precision: precision, model_variant: model.variant, seed: requestedSeed,
            options: variantOptions(model.variant, modelOptions.payload) }
      const accepted = await runtime('POST', '/v1/jobs/generate', request)
      if (controller.signal.aborted) return
      acceptedJobId = accepted.job_id
      const initial = { ...accepted, id: accepted.job_id, operation: 'generate', activity: [] } as Job
      localStorage.setItem(recoveryKey, accepted.job_id)
      setJob(initial)
      const final = await waitJob(accepted.job_id, value => { if (!controller.signal.aborted) setJob(value) }, controller.signal)
      if (controller.signal.aborted) return
      clearRecoveryValue(recoveryKey, accepted.job_id)
      if (final.status === 'completed' && final.result) {
        if (compare) setComparison({ media: final.result.media[0], meta: final.result.data })
        else { setMedia(final.result.media[0]); setMeta(final.result.data); setLastRequest(request); setSeed(String(final.result.data.seed)) }
      }
    } catch (error: any) {
      if (controller.signal.aborted || isAbortError(error)) return
      clearRecoveryValue(recoveryKey, acceptedJobId)
      setJob({ id: 'local', session_id: '', operation: 'generate', status: 'failed', activity: [], error: error.message })
    } finally {
      if (operationController.current === controller) operationController.current = null
    }
  }

  async function cancel() {
    const id = job?.id || job?.job_id
    if (!id || cancelling) return
    setCancelError('')
    setCancelling(true)
    try { await cancelJob(id) }
    catch (error: any) { setCancelError(t('studio.shared.cancelFailed', { message: error.message })) }
    finally { setCancelling(false) }
  }

  const busyJob = ['queued', 'running'].includes(job?.status || '')
  const blocked = !!optionError || !prompt.trim() || recovering || enhancing || busyJob
  const preset = presets.find(p => p.id === ratio)
  return <Tool console={<>
    <Step n="01" title={t('studio.create.describeTitle')} hint={t('studio.create.describeHint')}>
      <label htmlFor="create-prompt" className="field-label">{t('studio.create.promptLabel')}</label>
      <textarea id="create-prompt" className="prompt-input" value={prompt} onChange={e => setPrompt(e.target.value)} placeholder={t('studio.create.promptPlaceholder')} rows={7} />
      <div className="prompt-meta"><span>{t('studio.create.words', { count: prompt.trim() ? prompt.trim().split(/\s+/).length : 0 })}</span>{enhancer === 'external' && <span className="tag">{t('studio.create.autoEnhanceOn')}</span>}</div>
      {enhancer === 'manual' && <PromptEnhancePanel prompt={prompt} onAccept={setPrompt} mode="t2i" onAspectRatio={value => { if (presets.some(p => p.id === value)) setRatio(value) }} />}
    </Step>
    <Step n="02" title={t('studio.create.formatTitle')} aside={preset ? `${preset.width}×${preset.height}` : undefined}>
      <div className="aspect-grid">{presets.map(p => <button type="button" key={p.id} className={`aspect-card ${ratio === p.id ? 'is-on' : ''}`} aria-pressed={ratio === p.id} onClick={() => setRatio(p.id)}>
        <i style={{ aspectRatio: p.id.replace(':', ' / ') }} />
        <span><b>{presetLabel(p)}</b><small>{p.id}</small></span>
      </button>)}</div>
    </Step>
    <Step n="03" title={t('studio.create.qualityTitle')} aside={turbo ? t('studio.shared.steps8') : undefined}>
      <ImageModelPicker state={model} />
      {turbo && <p className="hint">{t('studio.create.turboHint')}</p>}
      <div className="field-row">
        {!turbo && <label>{t('studio.shared.qualityLabel')}<select aria-label={t('studio.shared.qualityLabel')} value={quality} onChange={e => setQuality(e.target.value)}><option value="draft">{t('studio.create.qualityDraft')}</option><option value="quality">{t('studio.create.qualityFull')}</option></select></label>}
        <label>{t('studio.shared.resolution')}<select aria-label={t('studio.shared.resolution')} value={twoK ? tier : '1mp'} onChange={e => setTier(e.target.value)}><option value="1mp">1 MP</option>{twoK && precision === 'int8' && <option value="2k">{t('studio.create.native2k')}</option>}</select></label>
      </div>
      <AdvancedOptions>
        <div className="field-row">
          <PrecisionSelect state={model} onChange={value => { if (value === 'bf16') setTier('1mp') }} />
          <label>{t('studio.create.seedLabel')}<input aria-label={t('studio.create.seedAria')} type="number" min="0" max="9007199254740991" value={seed} onChange={e => setSeed(e.target.value)} placeholder={t('studio.create.seedPlaceholder')} /></label>
        </div>
        <label className="toggle"><input type="checkbox" checked={transparent} onChange={e => setTransparent(e.target.checked)} /><i /> {t('studio.create.transparent')}</label>
      </AdvancedOptions>
      <ModelOptions state={modelOptions} kind="image" omit={turbo ? TURBO_FIXED : []}/>
      <p className="hint">{modelOptions.catalog?.notes.image}{!turbo && modelOptions.values.steps ? t('studio.create.effectiveSteps', { steps: modelOptions.values.steps }) : ''}</p>
    </Step>
    {optionError && <p className="error" role="alert">{optionError}</p>}
    <Actions note={t(enhancer === 'external' ? 'studio.create.noteExternal' : enhancer === 'off' ? 'studio.create.noteOff' : 'studio.create.noteManual')}>
      <Action onClick={() => void generate()} disabled={blocked}>{enhancing ? t('studio.shared.enhancing') : t('studio.create.generate')}</Action>
      {enhancer === 'external' && <button className="ghost" onClick={() => void generate(false, true)} disabled={blocked}>{t('studio.create.generateRaw')}</button>}
    </Actions>
  </>} stage={<>
    {!job && !media && <EmptyStage pose="paint" title={t('studio.create.emptyTitle')}>{t('studio.create.emptyBody')}</EmptyStage>}
    <GenerationCanvas job={job} aspect={aspectFromRatio(ratio)} />
    <JobProgress job={job} onCancel={cancel} actionError={cancelError} cancelDisabled={cancelling} />
    {usedPrompt && <div className="proposal"><label>{t('studio.shared.usedPrompt')}</label><p className="proposal-text">{usedPrompt}</p></div>}
    {media && <><p className="eyebrow">{t('studio.create.result', { variant: variantLabel(meta?.model_variant), precision: meta?.model_precision?.toUpperCase() ?? '' })}</p><ArtifactResult media={media} meta={meta} fresh />
      {!comparison && <div className="button-row">
        {comparisonRequest('variant') && <button className="ghost" onClick={() => void generate('variant')} disabled={recovering || busyJob}>{t('studio.create.compareVariant', { model: meta?.model_variant === 'turbo' ? 'QWEN 2.1' : 'TURBO' })}</button>}
        {comparisonRequest('precision') && <button className="ghost" onClick={() => void generate('precision')} disabled={recovering || busyJob}>{t('studio.create.comparePrecision', { precision: meta?.model_precision === 'bf16' ? 'INT8' : 'BF16' })}</button>}
      </div>}
    </>}
    {comparison && <><p className="eyebrow">{t('studio.create.comparison', { variant: variantLabel(comparison.meta?.model_variant), precision: comparison.meta?.model_precision?.toUpperCase() ?? '' })}</p><ArtifactResult media={comparison.media} meta={comparison.meta} fresh /></>}
  </>} />
}
