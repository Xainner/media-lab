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
        throw new Error('La seed debe ser un entero entre 0 y 9007199254740991.')
      }
      let finalPrompt = prompt.trim()
      if (!compare && !skipEnhance && enhancer === 'external') {
        setEnhancing(true)
        try { finalPrompt = (await enhancePrompt(enhancer, finalPrompt, 't2i')).trim() || finalPrompt }
        catch (error: any) { throw new Error(`No se pudo mejorar el prompt (proveedor externo): ${error.message}`) }
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
    catch (error: any) { setCancelError(`No se pudo cancelar: ${error.message}`) }
    finally { setCancelling(false) }
  }

  const busyJob = ['queued', 'running'].includes(job?.status || '')
  const blocked = !!optionError || !prompt.trim() || recovering || enhancing || busyJob
  const preset = presets.find(p => p.id === ratio)
  return <Tool console={<>
    <Step n="01" title="Describe tu imagen" hint="Cuanto más concreto, mejor: sujeto, composición, luz, materiales y texto visible entre comillas.">
      <label htmlFor="create-prompt" className="field-label">DESCRIPCIÓN</label>
      <textarea id="create-prompt" className="prompt-input" value={prompt} onChange={e => setPrompt(e.target.value)} placeholder="Una ilustración nocturna de una ciudad flotante sobre nubes violetas, con un letrero que dice “Abierto”…" rows={7} />
      <div className="prompt-meta"><span>{prompt.trim() ? prompt.trim().split(/\s+/).length : 0} palabras</span>{enhancer === 'external' && <span className="tag">Mejora automática activa</span>}</div>
      {enhancer === 'manual' && <PromptEnhancePanel prompt={prompt} onAccept={setPrompt} mode="t2i" onAspectRatio={value => { if (presets.some(p => p.id === value)) setRatio(value) }} />}
    </Step>
    <Step n="02" title="Formato y orientación" aside={preset ? `${preset.width}×${preset.height}` : undefined}>
      <div className="aspect-grid">{presets.map(p => <button type="button" key={p.id} className={`aspect-card ${ratio === p.id ? 'is-on' : ''}`} aria-pressed={ratio === p.id} onClick={() => setRatio(p.id)}>
        <i style={{ aspectRatio: p.id.replace(':', ' / ') }} />
        <span><b>{p.label}</b><small>{p.id}</small></span>
      </button>)}</div>
    </Step>
    <Step n="03" title="Calidad y modelo" aside={turbo ? '8 pasos' : undefined}>
      <ImageModelPicker state={model} />
      {turbo && <p className="hint">Turbo usa su propio calendario fijo de 8 pasos: mismas instrucciones, resultado en segundos. Para el máximo detalle vuelve a Qwen 2.1.</p>}
      <div className="field-row">
        {!turbo && <label>Calidad de generación<select aria-label="Calidad de generación" value={quality} onChange={e => setQuality(e.target.value)}><option value="draft">Borrador · 25 pasos · más rápido</option><option value="quality">Calidad · 40 pasos · más detalle</option></select></label>}
        <label>Resolución<select aria-label="Resolución" value={twoK ? tier : '1mp'} onChange={e => setTier(e.target.value)}><option value="1mp">1 MP</option>{twoK && precision === 'int8' && <option value="2k">2K nativo · experimental</option>}</select></label>
      </div>
      <AdvancedOptions>
        <div className="field-row">
          <PrecisionSelect state={model} onChange={value => { if (value === 'bf16') setTier('1mp') }} />
          <label>Semilla · opcional<input aria-label="Semilla" type="number" min="0" max="9007199254740991" value={seed} onChange={e => setSeed(e.target.value)} placeholder="Aleatoria" /></label>
        </div>
        <label className="toggle"><input type="checkbox" checked={transparent} onChange={e => setTransparent(e.target.checked)} /><i /> Salida RGBA transparente</label>
      </AdvancedOptions>
      <ModelOptions state={modelOptions} kind="image" omit={turbo ? TURBO_FIXED : []}/>
      <p className="hint">{modelOptions.catalog?.notes.image}{!turbo && modelOptions.values.steps ? ` Pasos efectivos: ${modelOptions.values.steps}.` : ''}</p>
    </Step>
    {optionError && <p className="error" role="alert">{optionError}</p>}
    <Actions note={enhancer === 'external' ? 'Al generar, el prompt se envía al proveedor externo para mejorarlo.' : enhancer === 'off' ? 'Se genera con el prompt exacto.' : 'Generar directamente no envía el prompt al proveedor externo. La mejora manual sí lo hace, sólo al pulsarla.'}>
      <Action onClick={() => void generate()} disabled={blocked}>{enhancing ? 'MEJORANDO PROMPT…' : 'GENERAR'}</Action>
      {enhancer === 'external' && <button className="ghost" onClick={() => void generate(false, true)} disabled={blocked}>GENERAR SIN MEJORA</button>}
    </Actions>
  </>} stage={<>
    {!job && !media && <EmptyStage pose="paint" title="El lienzo está listo">Describe tu idea y pulsa Generar. Verás la imagen tomar forma aquí, en vivo.</EmptyStage>}
    <GenerationCanvas job={job} aspect={aspectFromRatio(ratio)} />
    <JobProgress job={job} onCancel={cancel} actionError={cancelError} cancelDisabled={cancelling} />
    {usedPrompt && <div className="proposal"><label>PROMPT MEJORADO USADO</label><p className="proposal-text">{usedPrompt}</p></div>}
    {media && <><p className="eyebrow">Resultado {variantLabel(meta?.model_variant)} · {meta?.model_precision?.toUpperCase()}</p><ArtifactResult media={media} meta={meta} fresh />
      {!comparison && <div className="button-row">
        {comparisonRequest('variant') && <button className="ghost" onClick={() => void generate('variant')} disabled={recovering || busyJob}>COMPARAR CON {meta?.model_variant === 'turbo' ? 'QWEN 2.1' : 'TURBO'} · MISMA SEED</button>}
        {comparisonRequest('precision') && <button className="ghost" onClick={() => void generate('precision')} disabled={recovering || busyJob}>COMPARAR CON {meta?.model_precision === 'bf16' ? 'INT8' : 'BF16'} · MISMO PROMPT Y SEED</button>}
      </div>}
    </>}
    {comparison && <><p className="eyebrow">Comparación {variantLabel(comparison.meta?.model_variant)} · {comparison.meta?.model_precision?.toUpperCase()}</p><ArtifactResult media={comparison.media} meta={comparison.meta} fresh /></>}
  </>} />
}
