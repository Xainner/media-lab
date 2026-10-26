import { useEffect, useState } from 'react'
import { runtime, type ArtifactRef } from '../lib/api'
import { CreativeProgress, useCreativeJob } from '../views/CreativeJob'
import { Segmented } from './Kit'
import { t } from '../../i18n'

type Caps = { ready: boolean; max_seconds: number; max_input_pixels: Record<string, number> }
type Video = ArtifactRef & { width?: number; height?: number }

export const isVideo = (media?: { uri: string } | null) => !!media && /\.(mp4|mkv|webm)$/i.test(media.uri)

/** FlashVSR v1.1 2x/4x upscaling of an owned video; the original stays untouched. */
export default function UpscalePanel({ media, recoveryKey = 'media-lab:upscale-job' }: { media?: Video | null; recoveryKey?: string }) {
  const state = useCreativeJob(recoveryKey)
  const [caps, setCaps] = useState<Caps | null>(null)
  const [scale, setScale] = useState<'2' | '4'>('2')
  const [quality, setQuality] = useState<'fast' | 'quality'>('fast')
  useEffect(() => {
    let live = true
    runtime('GET', '/v1/capabilities').then(c => { if (live) setCaps(c.upscale || null) }).catch(() => {})
    return () => { live = false }
  }, [])
  const busy = ['queued', 'running'].includes(state.job?.status || '')
  if (!caps?.ready || (!isVideo(media) && !state.job)) return null
  const pixels = media?.width && media?.height ? media.width * media.height : 0
  const fits = (value: '2' | '4') => !pixels || pixels <= (caps.max_input_pixels[value] || 0)
  const size = (value: number) => pixels ? ` · ${media!.width! * value}×${media!.height! * value}` : ''
  const chosen = fits(scale) ? scale : '2'
  return <section className="upscale-panel" aria-label={t('shell.upscale.label')}>
    <div className="upscale-head"><p className="eyebrow">FlashVSR v1.1</p><h3>{t('shell.upscale.label')}</h3></div>
    {isVideo(media) && <>
      <Segmented<'2' | '4'> label={t('shell.upscale.factor')} value={chosen} onChange={setScale} options={[
        { value: '2', label: 'x2', hint: t('shell.upscale.recommended', { size: size(2) }), disabled: !fits('2') },
        { value: '4', label: 'x4', hint: fits('4') ? t('shell.upscale.smallVideos', { size: size(4) }) : t('shell.upscale.only480p'), disabled: !fits('4') },
      ]} />
      <label>{t('shell.upscale.mode')}<select aria-label={t('shell.upscale.modeLabel')} value={quality} onChange={e => setQuality(e.target.value as 'fast' | 'quality')}>
        <option value="fast">{t('shell.upscale.fast')}</option>
        <option value="quality">{t('shell.upscale.quality')}</option>
      </select></label>
      {!fits('2') && <p className="hint">{t('shell.upscale.tooLarge')}</p>}
      <button className="primary" disabled={busy || !fits(chosen)} onClick={() => media && void state.submit('/v1/jobs/upscale', {
        video: { uri: media.uri, sha256: media.sha256 }, scale: Number(chosen), quality })}>{busy ? t('shell.upscale.busy') : t('shell.upscale.action', { scale: chosen })}</button>
      <p className="hint">{t('shell.upscale.note', { minutes: Math.round(caps.max_seconds / 60) })}</p>
    </>}
    <CreativeProgress state={state} />
  </section>
}
