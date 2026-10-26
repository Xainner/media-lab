// Shared canvas pieces: tiles, masonry and the lightbox used by every native Media Lab screen.
import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { AudioLines, Clapperboard, Contact, Download, Eraser, Film, Footprints, ImageIcon, Loader2, Maximize2, Move3d, Play, RefreshCcw, ScanFace, Trash2, UserRoundPen, UserRoundX, Wand2, X } from 'lucide-react'
import type { ArtifactRef } from '../studio/lib/api'
import UpscalePanel from '../studio/components/Upscale'
import { download, refineFace, useCaps, useMediaSrc, type FaceStrength } from './live'
import type { Art, Modality } from './data'
import { formatDateTime, t, type MessageKey } from '../i18n'

export const kindIcon = { image: ImageIcon, video: Film, audio: AudioLines }
export type Reuse = (kind: Modality, prompt: string, ref?: ArtifactRef, mode?: string) => void
export type CanvasActions = { onReuse: Reuse; onDirector: (song: ArtifactRef) => void; onCharacter: (photo: ArtifactRef) => void; onDelete: (item: Art) => Promise<boolean> }

export function Tile({ item, onOpen, index = 0 }: { item: Art; onOpen: (a: Art) => void; index?: number }) {
  const Icon = kindIcon[item.kind]
  const live = useMediaSrc(item.ref)
  const src = item.ref ? live : item.src
  const video = useRef<HTMLVideoElement>(null)
  const isVideo = item.kind === 'video' && !!item.ref
  return <motion.button type="button" layoutId={`art-${item.id ?? item.src}`} className={`ml-tile ${item.kind === 'audio' ? 'is-audio' : ''}`} style={{ aspectRatio: String(item.ratio) }} onClick={() => onOpen(item)}
    onPointerEnter={() => void video.current?.play().catch(() => {})} onPointerLeave={() => video.current?.pause()}
    initial={{ opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: '-40px' }} transition={{ duration: .6, delay: (index % 4) * .06, ease: [.2, .8, .2, 1] }}>
    {item.kind === 'audio' ? <span className="ml-audio-art"><AudioLines size={34} /><b>{item.prompt}</b></span>
      : isVideo ? (src && <video ref={video} src={src} muted loop playsInline preload="metadata" />)
      : src && <img src={src} alt={item.prompt} loading="lazy" />}
    {item.kind === 'video' && <span className="ml-play"><Play size={14} fill="currentColor" /></span>}
    <span className="ml-tile-meta"><Icon size={13} />{item.model}<span>{item.prompt}</span></span>
  </motion.button>
}

export function Masonry({ items, onOpen }: { items: Art[]; onOpen: (a: Art) => void }) {
  return <div className="ml-masonry">{items.map((a, i) => <Tile key={(a.id ?? a.src) + i} item={a} index={i} onOpen={onOpen} />)}</div>
}

function LightboxMedia({ item }: { item: Art }) {
  const live = useMediaSrc(item.ref)
  const src = item.ref ? live : item.src
  if (!src) return <div className="ml-lightbox-wait"><Loader2 className="ml-spin" /></div>
  if (item.kind === 'audio' && item.ref) return <div className="ml-lightbox-audio"><AudioLines size={56} /><audio src={src} controls autoPlay /></div>
  if (item.kind === 'video' && item.ref) return <video src={src} controls autoPlay loop playsInline />
  return <img src={src} alt={item.prompt} />
}

const STRENGTHS: [FaceStrength, MessageKey][] = [['light', 'creations.refine.light'], ['medium', 'creations.refine.medium'], ['strong', 'creations.refine.strong']]

/** Face refine for one video: pick how much H3 may redraw the face, queue it and point to Trabajos. */
function RefinePanel({ video }: { video: ArtifactRef }) {
  const [strength, setStrength] = useState<FaceStrength>('medium')
  const [state, setState] = useState<'' | 'sending' | 'sent'>('')
  const [error, setError] = useState('')
  const send = async () => {
    setState('sending'); setError('')
    try { await refineFace(video, strength); setState('sent') } catch (e) { setError(e instanceof Error ? e.message : String(e)); setState('') }
  }
  return <div className="ml-refine">
    <p>{t('creations.refine.intro')}</p>
    <div className="ml-seg" role="group" aria-label={t('creations.refine.strength')}><small>{t('creations.refine.strength')}</small>
      {STRENGTHS.map(([id, label]) => <button type="button" key={id} className={strength === id ? 'is-on' : ''} aria-pressed={strength === id} onClick={() => setStrength(id)}>{t(label)}</button>)}</div>
    {error && <p className="ml-error" role="alert">{error}</p>}
    {state === 'sent' ? <p className="ml-ok" role="status">{t('creations.refine.queued')}</p>
      : <button type="button" className="ml-btn is-accent" disabled={state === 'sending'} onClick={() => void send()}>
        {state === 'sending' ? <Loader2 size={15} className="ml-spin" /> : <ScanFace size={15} />}{t('creations.refine.action')}</button>}
  </div>
}

const when = (seconds?: number) => seconds ? formatDateTime(seconds) : ''

export function Lightbox({ item, onClose, actions }: { item: Art | null; onClose: () => void; actions: CanvasActions }) {
  const [upscale, setUpscale] = useState(false)
  const [refine, setRefine] = useState(false)
  const [busy, setBusy] = useState(false)
  const caps = useCaps()
  useEffect(() => { setUpscale(false); setRefine(false) }, [item?.id])
  useEffect(() => { const esc = (e: KeyboardEvent) => e.key === 'Escape' && onClose(); window.addEventListener('keydown', esc); return () => window.removeEventListener('keydown', esc) }, [onClose])
  const ref = item?.ref
  const image = item?.kind === 'image' && ref
  const song = item?.kind === 'audio' && ref && /\/songs\//.test(ref.uri)
  const video = item?.kind === 'video' && ref
  const remove = async () => { if (!item) return; setBusy(true); try { if (await actions.onDelete(item)) onClose() } finally { setBusy(false) } }
  return <AnimatePresence>{item && <motion.div className="ml-lightbox" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
    <motion.figure layoutId={`art-${item.id ?? item.src}`} className="ml-lightbox-media" onClick={e => e.stopPropagation()} transition={{ type: 'spring', stiffness: 260, damping: 30 }}>
      <LightboxMedia item={item} />
    </motion.figure>
    <motion.aside className="ml-lightbox-info" onClick={e => e.stopPropagation()} initial={{ x: 40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 40, opacity: 0 }} transition={{ delay: .08 }}>
      <button type="button" className="ml-icon" aria-label={t('creations.lightbox.close')} onClick={onClose}><X size={18} /></button>
      <small className="ml-kicker">{item.model}</small>
      {item.prompt && <p className="ml-prompt">{item.prompt}</p>}
      {(item.created || ref?.width) && <dl className="ml-facts">
        {item.created ? <><dt>{t('creations.lightbox.created')}</dt><dd>{when(item.created)}</dd></> : null}
        {ref?.width && ref?.height ? <><dt>{t('creations.lightbox.size')}</dt><dd>{ref.width}×{ref.height}</dd></> : null}
      </dl>}
      <div className="ml-actions">
        {item.prompt && item.model !== 'Hybrid Demucs' && <button type="button" className="ml-btn is-accent" onClick={() => { actions.onReuse(item.kind, item.prompt); onClose() }}><RefreshCcw size={15} />{t('creations.lightbox.recreate')}</button>}
        {image && <button type="button" className="ml-btn" onClick={() => { actions.onReuse('image', '', ref); onClose() }}><Wand2 size={15} />{t('creations.lightbox.edit')}</button>}
        {image && caps.camera && <button type="button" className="ml-btn" onClick={() => { actions.onReuse('image', '', ref, 'Ángulo'); onClose() }}><Move3d size={15} />{t('creations.lightbox.otherAngle')}</button>}
        {image && caps.cutout && <button type="button" className="ml-btn" onClick={() => { actions.onReuse('image', '', ref, 'Quitar fondo'); onClose() }}><Eraser size={15} />{t('creations.lightbox.removeBackground')}</button>}
        {image && <button type="button" className="ml-btn" onClick={() => { actions.onReuse('video', '', ref); onClose() }}><Clapperboard size={15} />{t('creations.lightbox.animate')}</button>}
        {image && ref && <button type="button" className="ml-btn" onClick={() => { actions.onCharacter(ref); onClose() }}><Contact size={15} />{t('creations.lightbox.createCharacter')}</button>}
        {song && <button type="button" className="ml-btn" onClick={() => { actions.onDirector(ref); onClose() }}><Clapperboard size={15} />{t('creations.lightbox.createMusicVideo')}</button>}
        {item.kind === 'audio' && ref && caps.stems && <button type="button" className="ml-btn" onClick={() => { actions.onReuse('audio', '', ref, 'Separar pistas'); onClose() }}><AudioLines size={15} />{t('creations.lightbox.separateVocals')}</button>}
        {video && <button type="button" className="ml-btn" onClick={() => { actions.onReuse('video', '', ref); onClose() }}><UserRoundPen size={15} />{t('creations.lightbox.swapCharacter')}</button>}
        {video && Object.values(caps.follow).some(Boolean) && <button type="button" className="ml-btn" onClick={() => { actions.onReuse('video', '', ref, 'Seguir vídeo'); onClose() }}><Footprints size={15} />{t('creations.lightbox.copyMotion')}</button>}
        {video && caps.swap.remove && <button type="button" className="ml-btn" onClick={() => { actions.onReuse('video', '', ref, 'Quitar persona'); onClose() }}><UserRoundX size={15} />{t('creations.lightbox.removePerson')}</button>}
        {video && caps.faceRefine && <button type="button" className={`ml-btn ${refine ? 'is-on' : ''}`} aria-expanded={refine} onClick={() => { setRefine(v => !v); setUpscale(false) }}><ScanFace size={15} />{t('creations.refine.action')}</button>}
        {video && <button type="button" className={`ml-btn ${upscale ? 'is-on' : ''}`} aria-expanded={upscale} onClick={() => { setUpscale(v => !v); setRefine(false) }}><Maximize2 size={15} />{t('creations.lightbox.upscale')}</button>}
        {ref ? <button type="button" className="ml-btn" onClick={() => void download(ref)}><Download size={15} />{t('creations.lightbox.download')}</button>
          : <a className="ml-btn" href={item.src} download><Download size={15} />{t('creations.lightbox.download')}</a>}
        {ref && <button type="button" className="ml-btn is-danger" disabled={busy} onClick={() => void remove()}><Trash2 size={15} />{t('creations.lightbox.delete')}</button>}
      </div>
      {refine && video && <RefinePanel key={ref.uri} video={ref} />}
      {upscale && video && <div className="rvl ml-embed"><UpscalePanel key={ref.uri} media={ref as any} recoveryKey="media-lab:library-upscale-job" /></div>}
    </motion.aside>
  </motion.div>}</AnimatePresence>
}
