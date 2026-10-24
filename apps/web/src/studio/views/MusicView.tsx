import { ModelOptions, useModelOptions, optionsError, SeedField, seedError } from '../components/ModelOptions'
import AdvancedOptions from '../components/AdvancedOptions'
import MediaPreview from '../components/MediaPreview'
import { useState } from 'react'
import { newSession, type ArtifactRef } from '../lib/api'
import { CreativeProgress, useCreativeJob } from './CreativeJob'
import PromptEnhancePanel from '../components/PromptEnhancePanel'
import { Action, Actions, EmptyStage, Segmented, Step, Tool } from '../components/Kit'

export default function MusicView() {
  const [style, setStyle] = useState('')
  const modelOptions = useModelOptions()
  const [seed, setSeed] = useState('')
  const [steps, setSteps] = useState(32)
  const optionError = optionsError(modelOptions, 'song') || seedError(seed) || (!Number.isInteger(steps) || steps < 4 || steps > 80 ? 'Pasos de música: 4–80.' : '')
  const [lyrics, setLyrics] = useState('')
  const [abc, setAbc] = useState('')
  const [mode, setMode] = useState<'direct' | 'full' | 'melody'>('direct')
  const [source, setSource] = useState<ArtifactRef | null>(null)
  const [duration, setDuration] = useState(120)
  const [uploadError, setUploadError] = useState('')
  const state = useCreativeJob('media-lab:song-job')
  const brief = [style.trim() && `Style: ${style.trim()}`, lyrics.trim() && `Lyrics:\n${lyrics.trim()}`].filter(Boolean).join('\n\n')
  async function chooseAudio() {
    try { const result = await window.visualLab.runtime.uploadMedia(newSession()); if (result) { if (!/\.(wav|flac|mp3|opus|ogg)$/i.test(result.data.uri)) throw new Error('Elige un archivo de audio.'); setSource(result.data) } }
    catch (e) { setUploadError(String(e)) }
  }
  const busyJob = ['queued', 'running'].includes(state.job?.status || '')
  return <Tool console={<>
    <Step n="01" title="El sonido" hint="Estilo como etiquetas: género, ánimo, instrumentos, voz y tempo. Ej.: city pop, groovy bass, voz femenina cálida.">
      <label>Estilo<textarea rows={3} value={style} onChange={e => setStyle(e.target.value)} placeholder="Synth-pop soñador, pads cálidos, batería electrónica suave, voz femenina, medio tempo…" /></label>
      <label>Letra<textarea className="prompt-input" rows={8} value={lyrics} onChange={e => setLyrics(e.target.value)} placeholder={'[Verse]\nLa ciudad se apaga lento…\n\n[Chorus]\nBuenas noches, luna llena…'} /></label>
      <small>Sin letra se genera una pieza instrumental.</small>
      <PromptEnhancePanel prompt={brief} onAccept={setStyle} onLyrics={setLyrics} mode="song" />
    </Step>
    <Step n="02" title="Composición" hint={mode === 'direct' ? 'Directa: rápida, sin partitura previa.' : mode === 'full' ? 'Arreglo completo: planifica melodía y acordes en ABC antes de cantar.' : 'Melodía: planifica solo la melodía; ideal para covers.'}>
      <Segmented label="Modo de composición" value={mode} onChange={setMode} options={[{ value: 'direct', label: 'Composición directa' }, { value: 'full', label: 'Arreglo completo' }, { value: 'melody', label: 'Melodía' }]} />
      {mode !== 'direct' && <AdvancedOptions title="Partitura ABC avanzada"><label>Score ABC · editable<textarea rows={6} value={abc} onChange={e => setAbc(e.target.value)} placeholder="Opcional: deja vacío para generar ABC automáticamente" /></label></AdvancedOptions>}
      {mode !== 'direct' && <div className="audio-reference"><button className="ghost" onClick={() => void chooseAudio()}>COVER DESDE AUDIO</button>{source && <><MediaPreview media={source} playable label="Audio de referencia"/><button onClick={()=>setSource(null)}>Quitar referencia</button></>}</div>}
    </Step>
    <Step n="03" title="Duración y calidad" aside={`${duration} s · ${steps} pasos`}>
      <label>Duración máxima · <span className="range-value">{duration} s</span><input type="range" min="10" max="900" step="10" value={duration} onChange={e => setDuration(Number(e.target.value))} /></label>
      <label>Calidad de muestreo<select aria-label="Calidad de música" value={[16,32,64].includes(steps) ? String(steps) : 'custom'} onChange={e => { if (e.target.value !== 'custom') setSteps(Number(e.target.value)) }}><option value="16">Rápida · 16 pasos</option><option value="32">Equilibrada · 32 pasos</option><option value="64">Más pasos · 64</option><option value="custom">Personalizada</option></select></label>
      <AdvancedOptions title="Pasos y semilla"><label>Pasos de difusión<input aria-label="Pasos de música" type="number" min={4} max={80} step={1} value={steps} onChange={e => setSteps(Number(e.target.value))}/></label><SeedField value={seed} onChange={setSeed}/></AdvancedOptions>
      <ModelOptions state={modelOptions} kind="song"/>
    </Step>
    {optionError && <p className="error" role="alert">{optionError}</p>}
    {uploadError && <p className="error">{uploadError}</p>}
    <Actions><Action disabled={!!optionError || !style.trim() || busyJob} onClick={() => void state.submit('/v1/jobs/song', { style, lyrics: lyrics.trim() || '[Instrumental]', mode, abc, source_audio: mode === 'direct' ? null : source, max_duration: duration, steps, seed: seed ? Number(seed) : null, options: modelOptions.payload, session_id: newSession() })}>GENERAR CANCIÓN</Action></Actions>
  </>} stage={<>
    {!state.job && <EmptyStage pose="dj" title="El estudio está listo para sonar">Describe el estilo y escribe la letra. Yo me encargo de la voz y el arreglo.</EmptyStage>}
    {busyJob && <div className="empty-stage"><div className="empty-stage-glow"/><div className="equalizer" aria-hidden="true">{Array.from({ length: 14 }, (_, i) => <i key={i}/>)}</div><b>{state.job?.status === 'queued' ? 'En cola…' : 'Componiendo tu canción'}</b><span>{state.job?.progress?.node || 'Escribiendo la partitura y cantando cada verso.'}</span></div>}
    <CreativeProgress state={state} />
    {state.job?.result?.data?.abc && <div className="score-card"><h3>Score ABC generado</h3><pre>{state.job.result.data.abc}</pre><button className="ghost" onClick={() => { setAbc(state.job!.result!.data.abc); setMode(state.job!.result!.data.mode === 'melody' ? 'melody' : 'full') }}>REVISAR Y REUTILIZAR SCORE</button></div>}
  </>} />
}
