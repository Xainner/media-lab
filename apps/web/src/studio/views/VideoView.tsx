import { ModelOptions, useModelOptions, optionsError, VideoResolution, VideoQuality, SeedField, seedError } from '../components/ModelOptions'
import { useEffect, useState } from 'react'
import { formatUploadErrors, newSession, uploadFiles, type ArtifactRef } from '../lib/api'
import { CreativeProgress, useCreativeJob } from './CreativeJob'
import UpscalePanel from '../components/Upscale'
import { FLEX_FIXED, H3_PROFILE_HELP, h3Options, useH3Profile } from '../lib/h3'
import MediaPreview from '../components/MediaPreview'
import AdvancedOptions from '../components/AdvancedOptions'
import PromptEnhancePanel from '../components/PromptEnhancePanel'
import { Action, Actions, EmptyStage, Segmented, Step, Tool } from '../components/Kit'
import { t } from '../../i18n'

export default function VideoView({ incoming }: { incoming?: ArtifactRef | null }) {
  const [prompt, setPrompt] = useState('')
  const modelOptions = useModelOptions()
  const [seed, setSeed] = useState('')
  const [videos, setVideos] = useState<ArtifactRef[]>([])
  const [audios, setAudios] = useState<ArtifactRef[]>([])
  const optionError = optionsError(modelOptions, 'video', 1100000) || seedError(seed)
  const [mode, setMode] = useState<'t2v' | 'i2v' | 'r2v'>('t2v')
  const [first, setFirst] = useState<ArtifactRef | null>(null)
  const [last, setLast] = useState<ArtifactRef | null>(null)
  const [refs, setRefs] = useState<ArtifactRef[]>([])
  const [ratio, setRatio] = useState('16:9')
  const [seconds, setSeconds] = useState(5)
  const h3 = useH3Profile()
  const [uploadError, setUploadError] = useState('')
  const state = useCreativeJob('media-lab:video-job')
  useEffect(() => { if (incoming) { setFirst(incoming); setMode('i2v') } }, [incoming?.uri])
  async function images(files: File[] | FileList | null, target: 'first' | 'last' | 'refs') {
    if (!files?.length) return
    try {
    const result = await uploadFiles(Array.from(files), newSession())
    setUploadError(formatUploadErrors(result.errors))
    if (target === 'first') setFirst(result.refs[0] || null)
    else if (target === 'last') setLast(result.refs[0] || null)
    else setRefs(result.refs.slice(0, 9))
    } catch(e) { setUploadError(String(e)) }
  }
  async function addMedia(kind: 'video' | 'audio') {
    try {
      const result = await window.visualLab.runtime.uploadMedia(newSession())
      if (!result) return
      if (kind === 'video' && !/\.(mp4|mkv|webm)$/i.test(result.data.uri)) throw new Error(t('studio.video.pickVideo'))
      if (kind === 'audio' && !/\.(wav|flac|mp3|opus|ogg)$/i.test(result.data.uri)) throw new Error(t('studio.video.pickAudio'))
      if (kind === 'video') setVideos(v => [...v, result.data].slice(0, 3)); else setAudios(v => [...v, result.data].slice(0, 3))
      setUploadError('')
    } catch(e) { setUploadError(String(e)) }
  }
  // Supplied frames are <Picture 1> (first) and <Picture 2> (last); r2v uses the reference images in order.
  const improveRefs = (mode === 'i2v' ? [first, last].filter((ref): ref is ArtifactRef => !!ref) : mode === 'r2v' ? refs : []).map(({ uri, sha256 }) => ({ uri, sha256 }))
  function generate() {
    void state.submit('/v1/jobs/video', { prompt, mode, first_frame: first, last_frame: last,
      references: mode === 'r2v' ? refs : [], reference_videos: mode === 'r2v' ? videos : [], reference_audios: mode === 'r2v' ? audios : [], options: h3Options(h3.profile, modelOptions.payload), seed: seed ? Number(seed) : null, aspect_ratio: ratio, seconds, profile: h3.profile, steps: h3.steps, session_id: newSession() })
  }
  const frame = (target: 'first' | 'last') => {
    const value = target === 'first' ? first : last
    return <div className="frame-slot" key={target}>
      <span className="field-label">{target === 'first' ? t('studio.video.firstFrame') : t('studio.video.lastFrameOptional')}</span>
      <label className="dropzone" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();void images(Array.from(e.dataTransfer.files),target)}}>
        {value ? <MediaPreview media={value} label={target==='first'?t('studio.video.firstFrame'):t('studio.video.lastFrame')}/> : <><strong>＋ {target === 'first' ? t('studio.video.start') : t('studio.video.end')}</strong><small>{t('studio.video.dropImage')}</small></>}
        <input hidden type="file" accept="image/png,image/jpeg,image/webp" onChange={e=>{void images(e.target.files,target);e.target.value=''}}/>
      </label>
      {value && <button className="text-button" onClick={()=>target==='first'?setFirst(null):setLast(null)}>{t('studio.video.removeFrame')}</button>}
    </div>
  }
  const busyJob = ['queued', 'running'].includes(state.job?.status || '')
  return <Tool console={<>
    <Step n="01" title={t('studio.video.modelModeTitle')}>
      <label>{t('studio.video.h3Model')}<select value={h3.profile} onChange={e => h3.select(e.target.value)}><option value="base" disabled={!h3.profiles.base.ready}>{t('studio.video.profileBase')}</option><option value="turbo" disabled={!h3.profiles.turbo.ready}>{t('studio.video.profileTurbo')}{!h3.profiles.turbo.ready ? t('studio.video.unavailable') : ''}</option><option value="flex" disabled={!h3.profiles.flex.ready}>{t('studio.video.profileFlex')}{!h3.profiles.flex.ready ? t('studio.video.unavailable') : ''}</option><option value="fused_turbo" disabled={!h3.profiles.fused_turbo.ready}>{t('studio.video.profileFused')}{!h3.profiles.fused_turbo.ready ? t('studio.video.unavailable') : ''}</option></select></label>
      <p className="hint">{H3_PROFILE_HELP[h3.profile]}</p>
      <Segmented label={t('studio.video.modeLabel')} value={mode} onChange={setMode} options={[{ value: 't2v', label: t('studio.video.modeText') }, { value: 'i2v', label: t('studio.video.modeImage') }, { value: 'r2v', label: t('studio.video.modeRefs') }]} />
    </Step>
    <Step n="02" title={t('studio.video.directionTitle')} hint={t('studio.video.directionHint')}>
      <label>{t('studio.video.directionTitle')}<textarea className="prompt-input" value={prompt} onChange={e => setPrompt(e.target.value)} placeholder={t('studio.video.promptPlaceholder')} rows={6} /></label>
      {mode === 'i2v' && <div className="video-frames">{frame('first')}{frame('last')}</div>}
      {mode === 'r2v' && <>
        <label className="dropzone" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();void images(Array.from(e.dataTransfer.files),'refs')}}><strong>{t('studio.video.refImages')}</strong><small>{t('studio.video.refImagesHint')}</small><input hidden type="file" multiple accept="image/png,image/jpeg,image/webp" onChange={e=>{void images(e.target.files,'refs');e.target.value=''}}/></label>
        {refs.length > 0 && <div className="refs">{refs.map((ref,index)=><div className="ref" key={ref.uri}><MediaPreview media={ref} label={t('studio.video.refLabel', { n: index + 1 })}/><span className="ref-tag">{`<Picture ${index+1}>`}</span><div className="ref-tools"><button aria-label={t('studio.video.removeRef', { n: index + 1 })} className="danger" onClick={()=>setRefs(v=>v.filter(r=>r.uri!==ref.uri))}>×</button></div></div>)}</div>}
        <small>{t('studio.video.refCount', { count: refs.length })}</small>
        <div className="media-refs">{(['video','audio'] as const).map(kind => {
          const items = kind === 'video' ? videos : audios
          return <div key={kind} className="media-refs">
            <button className="ghost" disabled={items.length >= 3} onClick={() => void addMedia(kind)}>{t(kind === 'video' ? 'studio.video.addVideo' : 'studio.video.addAudio', { count: items.length })}</button>
            {items.map((ref, i) => <div className="media-ref-row" key={ref.uri}><MediaPreview media={ref} playable label={t(kind === 'video' ? 'studio.video.videoRefLabel' : 'studio.video.audioRefLabel', { n: i + 1 })}/><span className="tag">{kind === 'video' ? `<Video ${i+1}>` : `Audio ${i+1}`}</span><button aria-label={t(kind === 'video' ? 'studio.video.removeVideo' : 'studio.video.removeAudio', { n: i + 1 })} onClick={() => kind === 'video' ? setVideos(v => v.filter(r => r.uri !== ref.uri)) : setAudios(v => v.filter(r => r.uri !== ref.uri))}>{t('studio.video.remove')}</button></div>)}
          </div>
        })}</div>
        <small>{t('studio.video.mediaHint')}</small>
      </>}
      <PromptEnhancePanel key={mode} prompt={prompt} onAccept={setPrompt} mode={mode} references={improveRefs} seconds={seconds} needsReferences={mode === 'i2v'} />
    </Step>
    <Step n="03" title={t('studio.video.durationTitle')} aside={t('studio.video.durationAside', { seconds, steps: h3.steps })}>
      <div className="field-row">
        <label>{t('studio.video.format')}<select value={ratio} onChange={e => setRatio(e.target.value)}><option>16:9</option><option>9:16</option><option>1:1</option></select></label>
        <label>{t('studio.video.seconds')}<input type="number" min="5" max="15" step="1" value={seconds} onChange={e => setSeconds(Number(e.target.value))} /></label>
        <label>{t('studio.video.steps')}<input type="number" min={h3.limits.min} max={h3.limits.max} step="1" value={h3.steps} onChange={e => h3.setSteps(Number(e.target.value))} /></label>
      </div>
      {h3.profile !== 'flex' && <VideoQuality profile={h3.profile} steps={h3.steps} setSteps={h3.setSteps}/>}
      <VideoResolution state={modelOptions} ratio={ratio}/>
      <AdvancedOptions title={t('studio.video.seed')}><SeedField value={seed} onChange={setSeed}/></AdvancedOptions>
      <ModelOptions state={modelOptions} kind="video" omit={h3.profile === 'flex' ? FLEX_FIXED : []} schedulerDefault={mode === 'r2v' && h3.profile === 'base' ? 'beta' : 'simple'}/>
    </Step>
    {optionError && <p className="error" role="alert">{optionError}</p>}
    {uploadError && <p className="error">{uploadError}</p>}
    <Actions><Action disabled={!!optionError || !h3.valid || !prompt.trim() || (mode === 'i2v' && !first) || (mode === 'r2v' && !refs.length && !videos.length && !audios.length) || busyJob} onClick={generate}>{t('studio.video.generate')}</Action></Actions>
  </>} stage={<>
    {!state.job && <EmptyStage pose="clapper" title={t('studio.video.emptyTitle')}>{t('studio.video.emptyBody')}</EmptyStage>}
    {busyJob && <div className="gen-canvas" style={{ aspectRatio: ratio.replace(':', ' / ') }}><div className="gen-aurora"><i /><i /><i /></div><div className="gen-grain" /><div className="gen-scan" /><div className="gen-caption"><span>{state.job?.status === 'queued' ? t('studio.video.queued', { position: state.job?.queue_position ?? 0 }) : t('studio.video.rendering')}</span><b>{state.job?.progress?.pct ?? 0}%</b></div></div>}
    <CreativeProgress state={state} />
    {state.job?.status === 'completed' && <UpscalePanel media={state.job.result?.media?.[0]} recoveryKey="media-lab:video-upscale-job" />}
  </>} />
}
