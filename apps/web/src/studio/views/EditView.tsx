import { ModelOptions, useModelOptions, optionsError, SeedField, seedError } from '../components/ModelOptions'
import AdvancedOptions from '../components/AdvancedOptions'
import { useEffect, useRef, useState, type DragEvent } from 'react'
import ArtifactResult from '../components/ArtifactResult'
import JobProgress from '../components/JobProgress'
import GenerationCanvas from '../components/GenerationCanvas'
import PromptEnhancePanel from '../components/PromptEnhancePanel'
import { Action, Actions, EmptyStage, Step, Tool } from '../components/Kit'
import { ImageModelPicker, PrecisionSelect, TURBO_FIXED, useImageModel, variantOptions } from '../components/ImageModel'
import { cancelJob, clearRecoveryValue, dataUrl, enhancePrompt, formatUploadErrors, getEnhancerMode, isAbortError, newSession, runtime, uploadFiles, waitJob, type ArtifactRef, type EnhancerMode, type Job } from '../lib/api'
import { t } from '../../i18n'

type RefWithPreview = ArtifactRef & { preview: string }
export type EditHandoff = { ref: ArtifactRef; nonce: number }

export default function EditView({ active, incoming }: { active: boolean; incoming?: EditHandoff | null }) {
  const recoveryKey = 'media-lab:edit-job'
  const session = useRef(newSession())
  const operationController = useRef<AbortController | null>(null)
  const [refs, setRefs] = useState<RefWithPreview[]>([])
  const [prompt, setPrompt] = useState('')
  const modelOptions = useModelOptions()
  const [seed, setSeed] = useState('')
  const [quality, setQuality] = useState('quality')
  const [resolution, setResolution] = useState(0)
  const optionError = optionsError(modelOptions, 'edit') || seedError(seed) || (!Number.isInteger(resolution) || resolution < 0 || resolution > 1024 || resolution % 32 ? t('studio.edit.resolutionInvalid') : '')
  const model = useImageModel(active)
  const { precision, turbo } = model
  const [transparent, setTransparent] = useState(false)
  const [job, setJob] = useState<Job | null>(null)
  const [media, setMedia] = useState<ArtifactRef | null>(null)
  const [meta, setMeta] = useState<any>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [recovering, setRecovering] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [cancelError, setCancelError] = useState('')
  const [cancelling, setCancelling] = useState(false)
  const [enhancer, setEnhancer] = useState<EnhancerMode>(getEnhancerMode)
  const [enhancing, setEnhancing] = useState(false)
  const [usedPrompt, setUsedPrompt] = useState('')

  useEffect(() => { if (active) setEnhancer(getEnhancerMode()) }, [active])

  useEffect(() => {
    if (!incoming) return
    let cancelled = false
    const { uri, sha256, width, height, has_alpha } = incoming.ref
    const ref: ArtifactRef = { uri, sha256, width, height, has_alpha }
    dataUrl(uri).catch(() => '').then(preview => {
      if (cancelled) return
      setRefs(current => [{ ...ref, preview }, ...current.filter(item => item.uri !== uri)].slice(0, 10))
      setUploadError('')
    })
    return () => { cancelled = true }
  }, [incoming?.nonce])


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
      setJob({ id: jobId, session_id: session.current, operation: 'edit', status: 'failed', activity: [], error: error.message })
    }).finally(() => {
      if (!cancelled) setRecovering(false)
    })
    return () => { cancelled = true; controller.abort() }
  }, [active])

  useEffect(() => () => operationController.current?.abort(), [])

  async function addFiles(files: File[]) {
    if (!files.length || uploading) return
    const room = Math.max(0, 10 - refs.length)
    if (!room) {
      setUploadError(t('studio.edit.maxRefs'))
      return
    }
    setUploadError('')
    setUploading(true)
    try {
      const result = await uploadFiles(files.slice(0, room), session.current)
      const errors = [...result.errors]
      if (files.length > room) errors.push({ name: t('studio.edit.extraFiles'), message: t('studio.edit.refsExceeded') })
      const withPreview: RefWithPreview[] = []
      for (const ref of result.refs) {
        try { withPreview.push({ ...ref, preview: await dataUrl(ref.uri) }) }
        catch (error: any) {
          withPreview.push({ ...ref, preview: '' })
          errors.push({ name: ref.uri, message: t('studio.edit.previewFailed', { message: error.message }) })
        }
      }
      setRefs(current => [...current, ...withPreview].slice(0, 10))
      if (errors.length) setUploadError(formatUploadErrors(errors))
    } catch (error: any) {
      setUploadError(error.message)
    } finally { setUploading(false) }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault()
    setDragging(false)
    void addFiles(Array.from(event.dataTransfer.files))
  }

  function move(index: number, delta: number) {
    setRefs(current => {
      const next = [...current], target = index + delta
      if (target < 0 || target >= next.length) return current
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })
  }

  async function edit(skipEnhance = false) {
    if (!prompt.trim() || refs.length === 0 || recovering || uploading || enhancing || ['queued', 'running'].includes(job?.status || '')) return
    const controller = new AbortController()
    operationController.current?.abort()
    operationController.current = controller
    setCancelError('')
    setMedia(null); setMeta(null); setUsedPrompt('')
    let acceptedJobId = ''
    try {
      const references = refs.map(({ uri, sha256 }) => ({ uri, sha256 }))
      let finalPrompt = prompt.trim()
      if (!skipEnhance && enhancer === 'external') {
        setEnhancing(true)
        try { finalPrompt = (await enhancePrompt(enhancer, finalPrompt, 'i2i', references)).trim() || finalPrompt }
        catch (error: any) { throw new Error(t('studio.shared.enhanceFailed', { message: error.message })) }
        finally { setEnhancing(false) }
        if (controller.signal.aborted) return
        setUsedPrompt(finalPrompt)
      }
      const accepted = await runtime('POST', '/v1/jobs/edit', {
        prompt: finalPrompt, references,
        quality, transparent, resolution: resolution === 0 && (refs[0]?.width || 0) * (refs[0]?.height || 0) > 1_200_000 ? 1024 : resolution,
        model_precision: precision, model_variant: model.variant, session_id: session.current,
        options: variantOptions(model.variant, modelOptions.payload), seed: seed ? Number(seed) : null,
      })
      if (controller.signal.aborted) return
      acceptedJobId = accepted.job_id
      localStorage.setItem(recoveryKey, accepted.job_id)
      setJob({ ...accepted, id: accepted.job_id, operation: 'edit', activity: [] })
      const final = await waitJob(accepted.job_id, value => { if (!controller.signal.aborted) setJob(value) }, controller.signal)
      if (controller.signal.aborted) return
      clearRecoveryValue(recoveryKey, accepted.job_id)
      if (final.status === 'completed' && final.result) { setMedia(final.result.media[0]); setMeta(final.result.data) }
    } catch (error: any) {
      if (controller.signal.aborted || isAbortError(error)) return
      clearRecoveryValue(recoveryKey, acceptedJobId)
      setJob({ id: 'local', session_id: session.current, operation: 'edit', status: 'failed', activity: [], error: error.message })
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
  const blocked = !!optionError || !prompt.trim() || !refs.length || recovering || uploading || enhancing || busyJob
  return <Tool console={<>
    <Step n="01" title={t('studio.edit.imagesTitle')} aside={`${refs.length}/10`} hint={t('studio.edit.imagesHint')}>
      <label className="field-label">{t('studio.edit.refsLabel', { count: refs.length })}</label>
      <label className={`dropzone ${dragging ? 'dragging' : ''}`} onDragOver={event => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={onDrop}>
        <strong>{uploading ? t('studio.edit.uploading') : dragging ? t('studio.edit.dropHere') : t('studio.edit.addImages')}</strong><small>{t('studio.edit.dropHint')}</small>
        <input type="file" accept="image/png,image/jpeg,image/webp" multiple hidden disabled={uploading} onChange={e => { void addFiles(Array.from(e.target.files || [])); e.target.value = '' }} />
      </label>
      {uploadError && <p className="error">{uploadError}</p>}
      {refs.length > 0 && <div className="refs">{refs.map((ref, index) => <div className={`ref ${index === 0 ? 'is-target' : ''}`} key={ref.uri}>
        {ref.preview ? <img src={ref.preview} alt={t('studio.edit.refAlt', { n: index + 1 })} /> : <span className="ref-missing">?</span>}
        <span className="ref-tag">{index === 0 ? t('studio.edit.target') : `<image${index + 1}>`}</span>
        <div className="ref-tools"><button aria-label={t('studio.edit.moveUp', { n: index + 1 })} onClick={() => move(index, -1)}>↑</button><button aria-label={t('studio.edit.moveDown', { n: index + 1 })} onClick={() => move(index, 1)}>↓</button><button aria-label={t('studio.edit.removeRef', { n: index + 1 })} className="danger" onClick={() => setRefs(r => r.filter((_, i) => i !== index))}>×</button></div>
      </div>)}</div>}
    </Step>
    <Step n="02" title={t('studio.edit.changeTitle')} hint={t('studio.edit.changeHint')}>
      <label htmlFor="edit-prompt" className="field-label">{t('studio.edit.promptLabel')}</label>
      <textarea id="edit-prompt" className="prompt-input" value={prompt} onChange={e => setPrompt(e.target.value)} rows={6} placeholder={t('studio.edit.promptPlaceholder')} />
      {enhancer === 'manual' && <PromptEnhancePanel prompt={prompt} onAccept={setPrompt} mode="i2i" references={refs.map(({ uri, sha256 }) => ({ uri, sha256 }))} />}
    </Step>
    <Step n="03" title={t('studio.edit.qualityTitle')} aside={turbo ? t('studio.shared.steps8') : undefined}>
      <ImageModelPicker state={model} />
      {turbo && <p className="hint">{t('studio.edit.turboHint')}</p>}
      <div className="field-row">
        {!turbo && <label>{t('studio.shared.qualityLabel')}<select aria-label={t('studio.shared.qualityLabel')} value={quality} onChange={e => setQuality(e.target.value)}><option value="draft">{t('studio.edit.qualityDraft')}</option><option value="quality">{t('studio.edit.qualityFull')}</option></select></label>}
        <label>{t('studio.shared.resolution')}<select aria-label={t('studio.shared.resolution')} value={resolution} onChange={e => setResolution(Number(e.target.value))}><option value={0}>{t('studio.edit.resKeep')}</option><option value={512}>{t('studio.edit.res512')}</option><option value={768}>768 px</option><option value={1024}>1 MP</option>{![0,512,768,1024].includes(resolution) && <option value={resolution}>{t('studio.edit.resCustomOption', { px: resolution })}</option>}</select></label>
      </div>
      <AdvancedOptions>
        <PrecisionSelect state={model} />
        <label>{t('studio.edit.resCustom')}<input aria-label={t('studio.edit.resCustom')} type="number" min={0} max={1024} step={32} value={resolution} onChange={e => setResolution(Number(e.target.value))}/><small>{t('studio.edit.resCustomHint')}</small></label>
        <SeedField value={seed} onChange={setSeed}/>
        <label className="toggle"><input type="checkbox" checked={transparent} onChange={e => setTransparent(e.target.checked)} /><i /> {t('studio.edit.alpha')}</label>
      </AdvancedOptions>
      <ModelOptions state={modelOptions} kind="edit" omit={turbo ? TURBO_FIXED : []}/>
      {!turbo && modelOptions.values.steps && <small>{t('studio.shared.effectiveSteps', { steps: modelOptions.values.steps })}</small>}
    </Step>
    {optionError && <p className="error" role="alert">{optionError}</p>}
    <Actions note={t('studio.edit.note')}>
      <Action onClick={() => void edit()} disabled={blocked}>{enhancing ? t('studio.shared.enhancing') : t('studio.edit.edit')}</Action>
      {enhancer === 'external' && <button className="ghost" onClick={() => void edit(true)} disabled={blocked}>{t('studio.edit.editRaw')}</button>}
    </Actions>
  </>} stage={<>
    {!job && !media && <EmptyStage pose="cut" title={t('studio.edit.emptyTitle')}>{t('studio.edit.emptyBody')}</EmptyStage>}
    <GenerationCanvas job={job} aspect={refs[0]?.width && refs[0]?.height ? refs[0].width / refs[0].height : 1} />
    <JobProgress job={job} onCancel={cancel} actionError={cancelError} cancelDisabled={cancelling} />
    {usedPrompt && <div className="proposal"><label>{t('studio.shared.usedPrompt')}</label><p className="proposal-text">{usedPrompt}</p></div>}
    <ArtifactResult media={media} meta={meta} operation="edit" fresh />
  </>} />
}
