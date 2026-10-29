import { ModelOptions, useModelOptions, optionsError, VideoResolution, VideoQuality, SeedField, seedError } from '../components/ModelOptions'
import MediaPreview from '../components/MediaPreview'
import { useEffect, useState } from 'react'
import { newSession, runtime, type ArtifactRef } from '../lib/api'
import { CreativeProgress, useCreativeJob } from './CreativeJob'
import { FLEX_FIXED, H3_PROFILE_HELP, h3Options, lipSyncTemplate, useH3Profile } from '../lib/h3'
import { SemanticData } from '../components/SemanticData'
import { Action, Actions, EmptyStage, Step, Tool } from '../components/Kit'
import { TURBO_FIXED, variantOptions } from '../components/ImageModel'
import { t } from '../../i18n'

type Scene = { start: number; end: number; image_prompt: string; video_prompt: string; image?: ArtifactRef; video?: ArtifactRef; lip_sync?: boolean }
export default function DirectorView({ incoming }: { incoming?: ArtifactRef | null }) {
  const [song, setSong] = useState<ArtifactRef | null>(null)
  const keyframeOptions = useModelOptions()
  const videoOptions = useModelOptions()
  const [ratio, setRatio] = useState('16:9')
  const [seed, setSeed] = useState('')
  const [keyQuality, setKeyQuality] = useState('quality')
  const [keyPrecision, setKeyPrecision] = useState<'int8' | 'bf16'>('int8')
  const [keyVariant, setKeyVariant] = useState<'base' | 'turbo'>('base')
  const [variants, setVariants] = useState<any>({})
  const [bf16, setBf16] = useState(false)
  const [twoK, setTwoK] = useState(false)
  const [keyResolution, setKeyResolution] = useState('1mp')
  const optionError = optionsError(keyframeOptions, 'image', twoK && keyPrecision === 'int8' ? 4500000 : 1200000) || optionsError(videoOptions, 'video', 1100000) || seedError(seed)
  useEffect(() => { void runtime('GET', '/v1/capabilities').then(c => { setVariants(c.model_variants || {}); setBf16(!!c.model_precisions?.bf16); setKeyPrecision(c.model_precisions?.bf16 ? 'bf16' : 'int8'); setTwoK(!!c.two_k_enabled) }).catch(() => {}) }, [])
  const [analysis, setAnalysis] = useState<any>(null)
  const [title, setTitle] = useState('')
  const [brief, setBrief] = useState('')
  const [lyrics, setLyrics] = useState('')
  const [scenes, setScenes] = useState<Scene[]>([])
  const [library, setLibrary] = useState<ArtifactRef[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const state = useCreativeJob('media-lab:production-job')
  const h3 = useH3Profile()
  useEffect(() => { if (incoming) void selectSong(incoming) }, [incoming?.uri])
  useEffect(() => { void runtime('GET', '/v1/library?limit=500').then(result => setLibrary(result.items || [])).catch(() => {}) }, [])
  async function selectSong(ref: ArtifactRef) {
    setSong(ref); setScenes([]); setError('')
    try { const result = await runtime('GET', `/v1/media/analyze?uri=${encodeURIComponent(ref.uri)}&sha256=${ref.sha256}`); setAnalysis(result) }
    catch (e) { setError(String(e)) }
  }
  async function upload() {
    try { const result = await window.visualLab.runtime.uploadMedia(newSession()); if (result) { if (!/\.(wav|flac|mp3|opus|ogg)$/i.test(result.data.uri)) throw new Error(t('agent.director.chooseAudio')); await selectSong(result.data) } }
    catch (e) { setError(String(e)) }
  }
  async function plan() {
    if (!analysis) return
    setLoading(true); setError('')
    try {
      const result = await window.visualLab.agent.directorPlan({ brief, lyrics, analysis })
      setScenes(result.scenes)
    } catch (e) { setError(String(e)) }
    finally { setLoading(false) }
  }
  function update(index: number, field: keyof Scene, value: string) {
    setScenes(current => current.map((scene, i) => i === index ? { ...scene, [field]: field === 'start' || field === 'end' ? Number(value) : value } : scene))
  }
  function lipSync(index: number, enabled: boolean) {
    setScenes(current => current.map((scene, i) => i !== index ? scene : { ...scene, lip_sync: enabled,
      video_prompt: enabled && !scene.video_prompt.includes('subject_definitions:') ? lipSyncTemplate(scene.video_prompt) : scene.video_prompt }))
  }
  function reuse(index: number, field: 'image' | 'video', uri: string) {
    const ref = library.find(item => item.uri === uri)
    setScenes(current => current.map((scene, i) => i === index ? { ...scene, [field]: ref ? { uri: ref.uri, sha256: ref.sha256 } : undefined } : scene))
  }
  function produce() {
    void runtime('GET', '/v1/capabilities').then(caps => state.submit('/v1/jobs/production', {
      title, song, brief, lyrics, scenes, aspect_ratio: ratio, session_id: newSession(),
      keyframe_precision: keyPrecision, keyframe_variant: keyVariant, keyframe_quality: keyQuality, keyframe_resolution: keyResolution,
      video_profile: h3.profile, video_steps: h3.steps, video_options: h3Options(h3.profile, videoOptions.payload),
      keyframe_options: variantOptions(keyVariant, keyframeOptions.payload), seed: seed ? Number(seed) : null,
    })).catch(e => setError(String(e)))
  }
  async function resume() {
    const id = state.job?.id || state.job?.job_id
    if (id) await state.submit(`/v1/jobs/${id}/resume`, undefined)
  }
  const duration = Number(analysis?.duration) || 0
  const pct = (at: number) => duration ? `${Math.max(0, Math.min(100, at / duration * 100))}%` : '0%'
  const busyJob = ['queued', 'running'].includes(state.job?.status || '')
  const sections: any[] = Array.isArray(analysis?.sections) ? analysis.sections : []
  return <Tool wide console={<>
    <Step n="01" title={t('agent.director.songTitle')} hint={t('agent.director.songHint')}>
      <div className="button-row"><button className="ghost" onClick={() => void upload()}>{t('agent.director.chooseSong')}</button></div>
      {song && <MediaPreview media={song} playable label={t('agent.director.songPreview')}/>}
      {analysis && <p className="hint">{t('agent.director.analysis', { duration: analysis.duration, bpm: analysis.bpm_estimate || '—', sections: analysis.sections?.length || 0 })}</p>}
    </Step>
    <Step n="02" title={t('agent.director.conceptTitle')}>
      <label>{t('agent.director.titleLabel')}<input value={title} onChange={e => setTitle(e.target.value)} placeholder={t('agent.director.titlePlaceholder')} /></label>
      <label>{t('agent.director.briefLabel')}<textarea rows={4} value={brief} onChange={e => setBrief(e.target.value)} placeholder={t('agent.director.briefPlaceholder')} /></label>
      <label>{t('agent.director.lyricsLabel')}<textarea rows={5} value={lyrics} onChange={e => setLyrics(e.target.value)} /></label>
      <details><summary>{t('agent.director.providerData')}</summary><SemanticData value={{ brief, lyrics, analysis }}/></details>
      <button className="primary" disabled={!analysis || !brief.trim() || loading} onClick={() => void plan()}>{loading ? t('agent.director.planning') : t('agent.director.plan')}</button>
    </Step>
    <Step n="03" title={t('agent.director.clipsTitle')} aside={t('agent.director.clipsAside', { ratio, steps: h3.steps })}>
      <label>{t('agent.director.clipModel')}<select value={h3.profile} onChange={e => h3.select(e.target.value)}><option value="base" disabled={!h3.profiles.base.ready}>{t('agent.director.h3Base')}</option><option value="turbo" disabled={!h3.profiles.turbo.ready}>{t('agent.director.h3Turbo')}{!h3.profiles.turbo.ready ? t('agent.director.unavailable') : ''}</option><option value="flex" disabled={!h3.profiles.flex.ready}>{t('agent.director.h3Flex')}{!h3.profiles.flex.ready ? t('agent.director.unavailable') : ''}</option><option value="fused_turbo" disabled={!h3.profiles.fused_turbo.ready}>{t('agent.director.h3FusedTurbo')}{!h3.profiles.fused_turbo.ready ? t('agent.director.unavailable') : ''}</option></select></label>
      <p className="hint">{H3_PROFILE_HELP[h3.profile]}</p>
      <div className="field-row">
        <label>{t('agent.director.clipSteps')}<input type="number" min={h3.limits.min} max={h3.limits.max} step="1" value={h3.steps} onChange={e => h3.setSteps(Number(e.target.value))} /></label>
        <label>{t('agent.director.ratio')}<select value={ratio} onChange={e => setRatio(e.target.value)}><option>16:9</option><option>9:16</option><option>1:1</option></select></label>
      </div>
      {h3.profile !== 'flex' && <VideoQuality profile={h3.profile} steps={h3.steps} setSteps={h3.setSteps}/>}
      <VideoResolution state={videoOptions} ratio={ratio}/>
      <ModelOptions state={videoOptions} kind="video" omit={h3.profile === 'flex' ? FLEX_FIXED : []}/>
      <small>{t('agent.director.reusedClips')}</small>
    </Step>
    <Step n="04" title={t('agent.director.keyframesTitle')}>
      <div className="field-row">
        {(variants.turbo?.precisions?.int8 || variants.turbo?.precisions?.bf16) && <label>{t('agent.director.imageModel')}<select aria-label={t('agent.director.imageModel')} value={keyVariant} onChange={e => { const v = e.target.value as 'base' | 'turbo'; setKeyVariant(v); if (!variants[v]?.precisions?.[keyPrecision]) setKeyPrecision('int8') }}><option value="base">{t('agent.director.qwenBase')}</option><option value="turbo">{t('agent.director.turbo')}</option></select></label>}
        {keyVariant === 'base' && <label>{t('agent.director.imageQuality')}<select value={keyQuality} onChange={e => setKeyQuality(e.target.value)}><option value="draft">{t('agent.director.qualityDraft')}</option><option value="quality">{t('agent.director.qualityHigh')}</option></select></label>}
        <label>{t('agent.director.imagePrecision')}<select value={keyPrecision} onChange={e => {setKeyPrecision(e.target.value as 'int8'|'bf16');if(e.target.value === 'bf16')setKeyResolution('1mp')}}><option value="int8">INT8</option>{(keyVariant === 'turbo' ? variants.turbo?.precisions?.bf16 : bf16) && <option value="bf16">{t('agent.director.bf16')}</option>}</select></label>
        <label>{t('agent.director.imageResolution')}<select value={keyResolution} onChange={e => setKeyResolution(e.target.value)}><option value="1mp">1 MP</option>{twoK && keyPrecision === 'int8' && <option value="2k">{t('agent.director.res2k')}</option>}</select></label>
      </div>
      <ModelOptions state={keyframeOptions} kind="image" omit={keyVariant === "turbo" ? TURBO_FIXED : []}/>
      <SeedField value={seed} onChange={setSeed}/>
    </Step>
    {optionError && <p className="error" role="alert">{optionError}</p>}
    {error && <p className="error">{error}</p>}
    {scenes.length > 0 && <Actions><Action disabled={!!optionError || !title.trim() || (!h3.valid && scenes.some(s => !s.video)) || busyJob} onClick={produce}>{t('agent.director.produce')}</Action></Actions>}
  </>} stage={<>
    {duration > 0 && <div className="timeline glass">
      <div className="timeline-head"><b>{title || t('agent.director.timelineFallback')}</b><span>{Math.floor(duration / 60)}:{String(Math.round(duration % 60)).padStart(2, '0')} · {t('agent.director.sceneCount', { count: scenes.length })}</span></div>
      <div className="timeline-track" aria-hidden="true">
        {sections.map((sec, i) => <i key={i} className="timeline-section" style={{ left: pct(Number(sec.start) || 0), width: pct((Number(sec.end) || 0) - (Number(sec.start) || 0)), opacity: .25 + Math.min(.6, Number(sec.energy) || .3) }} />)}
        {scenes.map((scene, i) => <span key={i} className={`timeline-scene ${scene.lip_sync ? 'is-sync' : ''} ${scene.video ? 'is-reused' : ''}`} style={{ left: pct(scene.start), width: pct(scene.end - scene.start) }}><b>{i + 1}</b></span>)}
      </div>
    </div>}
    {scenes.length > 0 && <div className="scene-list">{scenes.map((scene, index) => <article className="scene glass" key={index}>
      <div className="scene-visual">{scene.video || scene.image ? <MediaPreview media={(scene.video || scene.image)!} playable label={t('agent.director.sceneLabel', { n: index + 1 })}/> : <div className="storyboard-placeholder"><span>✦</span><b>{index+1}</b><small>{t('agent.director.imagePending')}</small></div>}</div>
      <div className="scene-body">
        <div className="scene-head"><b>{t('agent.director.sceneHeading', { n: index + 1 })}</b><span className="tag">{(scene.end - scene.start).toFixed(1)} s</span></div>
        <div className="field-row"><label>{t('agent.director.start')}<input type="number" value={scene.start} onChange={e => update(index, 'start', e.target.value)} /></label><label>{t('agent.director.end')}<input type="number" value={scene.end} onChange={e => update(index, 'end', e.target.value)} /></label></div>
        <label>{t('agent.director.imagePrompt')}<textarea rows={3} value={scene.image_prompt} onChange={e => update(index, 'image_prompt', e.target.value)} /></label>
        <label>{t('agent.director.videoPrompt')}<textarea rows={scene.lip_sync ? 10 : 3} value={scene.video_prompt} onChange={e => update(index, 'video_prompt', e.target.value)} /></label>
        <label className="toggle"><input type="checkbox" checked={!!scene.lip_sync} disabled={!!scene.video || scene.end - scene.start < 2} onChange={e => lipSync(index, e.target.checked)} /><i /> {t('agent.director.lipSync')}</label>
        {scene.lip_sync && <small>{t('agent.director.lipSyncHelp')}</small>}
        <div className="field-row">
          <label>{t('agent.director.reuseImage')}<select value={scene.image?.uri || ''} onChange={e => reuse(index, 'image', e.target.value)}><option value="">{t('agent.director.generateNewImage')}</option>{library.filter(item => item.uri.includes('/images/')).map(item => <option key={item.uri} value={item.uri}>{(item as any).title || (item as any).prompt?.slice(0,70) || t('agent.director.myCreation', { n: library.indexOf(item) })}</option>)}</select></label>
          <label>{t('agent.director.reuseClip')}<select value={scene.video?.uri || ''} onChange={e => reuse(index, 'video', e.target.value)}><option value="">{t('agent.director.generateNewClip')}</option>{library.filter(item => item.uri.includes('/videos/')).map(item => <option key={item.uri} value={item.uri}>{(item as any).title || (item as any).prompt?.slice(0,70) || t('agent.director.myCreation', { n: library.indexOf(item) })}</option>)}</select></label>
        </div>
      </div>
    </article>)}</div>}
    {!scenes.length && !state.job && <EmptyStage pose="clapper" title={t('agent.director.emptyTitle')}>{t('agent.director.emptyBody')}</EmptyStage>}
    <CreativeProgress state={state} />
    {state.job?.result?.media?.[1] && <button className="primary" onClick={() => void window.visualLab.runtime.saveMedia(state.job!.result!.media[1].uri)}>{t('agent.director.exportMaster')}</button>}
    {state.job && ['failed', 'cancelled', 'interrupted'].includes(state.job.status) && <button className="ghost" onClick={() => void resume()}>{t('agent.director.resume')}</button>}
  </>} />
}
