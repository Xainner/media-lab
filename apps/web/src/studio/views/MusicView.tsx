import { ModelOptions, useModelOptions, optionsError, SeedField, seedError } from '../components/ModelOptions'
import AdvancedOptions from '../components/AdvancedOptions'
import MediaPreview from '../components/MediaPreview'
import { useState } from 'react'
import { newSession, type ArtifactRef } from '../lib/api'
import { CreativeProgress, useCreativeJob } from './CreativeJob'
import PromptEnhancePanel from '../components/PromptEnhancePanel'
import { Action, Actions, EmptyStage, Segmented, Step, Tool } from '../components/Kit'
import { t } from '../../i18n'

export default function MusicView() {
  const [style, setStyle] = useState('')
  const modelOptions = useModelOptions()
  const [seed, setSeed] = useState('')
  const [steps, setSteps] = useState(32)
  const optionError = optionsError(modelOptions, 'song') || seedError(seed) || (!Number.isInteger(steps) || steps < 4 || steps > 80 ? t('agent.music.stepsError') : '')
  const [lyrics, setLyrics] = useState('')
  const [abc, setAbc] = useState('')
  const [mode, setMode] = useState<'direct' | 'full' | 'melody'>('direct')
  const [source, setSource] = useState<ArtifactRef | null>(null)
  const [duration, setDuration] = useState(120)
  const [uploadError, setUploadError] = useState('')
  const state = useCreativeJob('media-lab:song-job')
  const brief = [style.trim() && `Style: ${style.trim()}`, lyrics.trim() && `Lyrics:\n${lyrics.trim()}`].filter(Boolean).join('\n\n')
  async function chooseAudio() {
    try { const result = await window.visualLab.runtime.uploadMedia(newSession()); if (result) { if (!/\.(wav|flac|mp3|opus|ogg)$/i.test(result.data.uri)) throw new Error(t('agent.director.chooseAudio')); setSource(result.data) } }
    catch (e) { setUploadError(String(e)) }
  }
  const busyJob = ['queued', 'running'].includes(state.job?.status || '')
  return <Tool console={<>
    <Step n="01" title={t('agent.music.soundTitle')} hint={t('agent.music.soundHint')}>
      <label>{t('agent.music.style')}<textarea rows={3} value={style} onChange={e => setStyle(e.target.value)} placeholder={t('agent.music.stylePlaceholder')} /></label>
      <label>{t('agent.music.lyrics')}<textarea className="prompt-input" rows={8} value={lyrics} onChange={e => setLyrics(e.target.value)} placeholder={t('agent.music.lyricsPlaceholder')} /></label>
      <small>{t('agent.music.instrumentalHint')}</small>
      <PromptEnhancePanel prompt={brief} onAccept={setStyle} onLyrics={setLyrics} mode="song" />
    </Step>
    <Step n="02" title={t('agent.music.compositionTitle')} hint={t(mode === 'direct' ? 'agent.music.hintDirect' : mode === 'full' ? 'agent.music.hintFull' : 'agent.music.hintMelody')}>
      <Segmented label={t('agent.music.modeLabel')} value={mode} onChange={setMode} options={[{ value: 'direct', label: t('agent.music.modeDirect') }, { value: 'full', label: t('agent.music.modeFull') }, { value: 'melody', label: t('agent.music.modeMelody') }]} />
      {mode !== 'direct' && <AdvancedOptions title={t('agent.music.abcTitle')}><label>{t('agent.music.abcLabel')}<textarea rows={6} value={abc} onChange={e => setAbc(e.target.value)} placeholder={t('agent.music.abcPlaceholder')} /></label></AdvancedOptions>}
      {mode !== 'direct' && <div className="audio-reference"><button className="ghost" onClick={() => void chooseAudio()}>{t('agent.music.coverFromAudio')}</button>{source && <><MediaPreview media={source} playable label={t('agent.music.referenceAudio')}/><button onClick={()=>setSource(null)}>{t('agent.music.removeReference')}</button></>}</div>}
    </Step>
    <Step n="03" title={t('agent.music.durationTitle')} aside={t('agent.music.durationAside', { duration, steps })}>
      <label>{t('agent.music.maxDuration')}<span className="range-value">{t('agent.music.seconds', { n: duration })}</span><input type="range" min="10" max="900" step="10" value={duration} onChange={e => setDuration(Number(e.target.value))} /></label>
      <label>{t('agent.music.sampling')}<select aria-label={t('agent.music.qualityLabel')} value={[16,32,64].includes(steps) ? String(steps) : 'custom'} onChange={e => { if (e.target.value !== 'custom') setSteps(Number(e.target.value)) }}><option value="16">{t('agent.music.fast')}</option><option value="32">{t('agent.music.balanced')}</option><option value="64">{t('agent.music.moreSteps')}</option><option value="custom">{t('agent.music.custom')}</option></select></label>
      <AdvancedOptions title={t('agent.music.stepsSeed')}><label>{t('agent.music.diffusionSteps')}<input aria-label={t('agent.music.stepsLabel')} type="number" min={4} max={80} step={1} value={steps} onChange={e => setSteps(Number(e.target.value))}/></label><SeedField value={seed} onChange={setSeed}/></AdvancedOptions>
      <ModelOptions state={modelOptions} kind="song"/>
    </Step>
    {optionError && <p className="error" role="alert">{optionError}</p>}
    {uploadError && <p className="error">{uploadError}</p>}
    <Actions><Action disabled={!!optionError || !style.trim() || busyJob} onClick={() => void state.submit('/v1/jobs/song', { style, lyrics: lyrics.trim() || '[Instrumental]', mode, abc, source_audio: mode === 'direct' ? null : source, max_duration: duration, steps, seed: seed ? Number(seed) : null, options: modelOptions.payload, session_id: newSession() })}>{t('agent.music.generate')}</Action></Actions>
  </>} stage={<>
    {!state.job && <EmptyStage pose="dj" title={t('agent.music.emptyTitle')}>{t('agent.music.emptyBody')}</EmptyStage>}
    {busyJob && <div className="empty-stage"><div className="empty-stage-glow"/><div className="equalizer" aria-hidden="true">{Array.from({ length: 14 }, (_, i) => <i key={i}/>)}</div><b>{state.job?.status === 'queued' ? t('agent.music.queued') : t('agent.music.composing')}</b><span>{state.job?.progress?.node || t('agent.music.composingDetail')}</span></div>}
    <CreativeProgress state={state} />
    {state.job?.result?.data?.abc && <div className="score-card"><h3>{t('agent.music.scoreTitle')}</h3><pre>{state.job.result.data.abc}</pre><button className="ghost" onClick={() => { setAbc(state.job!.result!.data.abc); setMode(state.job!.result!.data.mode === 'melody' ? 'melody' : 'full') }}>{t('agent.music.reuseScore')}</button></div>}
  </>} />
}
