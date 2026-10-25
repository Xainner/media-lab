import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'motion/react'
import { AtSign, AudioWaveform, Camera, Check, ChevronRight, Clock3, Film, Gauge, Globe, Layers, Loader2, Mic, Minus, Move3d, Music2, Monitor, Paperclip, Plus, RectangleHorizontal, ScanSearch, ShieldCheck, Sparkles, SwatchBook, UserRound, WandSparkles, X, type LucideIcon } from 'lucide-react'
import { getEnhancerMode, setEnhancerMode, type ArtifactRef } from '../studio/lib/api'
import { FOLLOWS, GUIDES, K6_ASPECTS, models, nearestAspect, settings, SOUND_KINDS, SOUND_LENGTHS, SWAP_MODES, VOICES, type Modality, type Model } from './data'
import { droppedKind, improve, loraBase, mentioned, uploadAudio, uploadImages, useCharacters, useMediaSrc, useProvider, withCharacters, type Caps, type Character, type Lora, type LoraPick, type Submission } from './live'

const statusLabel = { ready: '', new: 'NUEVO', soon: 'PRONTO' }
const maxRefs: Record<Modality, number> = { image: 10, video: 9, audio: 0 }
const isVideo = (uri: string) => /\.(mp4|webm|mkv|mov)$/i.test(uri)

/** A model can run when it is installed here; Turbo variants also need their weights on Saturno. */
export const available = (m: Model, caps: Caps) => m.status !== 'soon' && (m.id !== 'qwen-turbo' || caps.turbo) && (m.id !== 'h3-turbo' || caps.h3Turbo) && (m.id !== 'fasth3-omni' || caps.omni) && (m.id !== 'h3-fused' || caps.fusedTurbo) && (m.id !== 'ace-step' || caps.ace) && (m.id !== 'moss-image' || caps.moss)
  && (m.id !== 'flux3-klein' || caps.flux3) && (m.id !== 'kandinsky6' || caps.kandinsky6) && (m.id !== 'stable-audio3' || Object.values(caps.sound).some(Boolean)) && (m.id !== 'qwen3-tts' || Object.values(caps.speech).some(Boolean))
// Audio settings that belong to one kind of audio model; the rest (type, stems, duration) are for songs.
const audioOnly: Record<string, string> = { sound: 'stable-audio3', length: 'stable-audio3', voice: 'qwen3-tts', speaker: 'qwen3-tts', language: 'qwen3-tts' }
// Models that rewrite or read the text themselves, so the IA chip stays off.
const selfWritten: Record<string, string> = { 'flux3-klein': 'FLUX reescribe tu idea con su propio modelo', 'stable-audio3': 'Stable Audio reescribe tu idea con su propio modelo', 'qwen3-tts': 'La voz dice tu texto exacto' }

function Popover({ open, onClose, children, className = '' }: { open: boolean; onClose: () => void; children: React.ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const away = (e: PointerEvent) => { if (!ref.current?.contains(e.target as Node)) onClose() }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    setTimeout(() => document.addEventListener('pointerdown', away))
    document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('pointerdown', away); document.removeEventListener('keydown', esc) }
  }, [open, onClose])
  return <AnimatePresence>{open && <motion.div ref={ref} className={`ml-pop ${className}`} role="dialog"
    initial={{ opacity: 0, y: 12, scale: .97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 8, scale: .98 }}
    transition={{ type: 'spring', stiffness: 420, damping: 32 }}>{children}</motion.div>}</AnimatePresence>
}

export function ModelPicker({ modality, value, caps, onPick, open, onClose }: { modality: Modality; value: Model; caps: Caps; onPick: (m: Model) => void; open: boolean; onClose: () => void }) {
  const list = models.filter(m => m.modality === modality)
  return <Popover open={open} onClose={onClose} className="ml-picker">
    <header><b>Modelo</b><span>{list.filter(m => available(m, caps)).length} de {list.length} listos</span></header>
    <div className="ml-picker-grid">
      {list.map((m, i) => <motion.button key={m.id} type="button" className={`ml-model-card ${m.id === value.id ? 'is-on' : ''}`} disabled={!available(m, caps)}
        initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: .03 * i }}
        onClick={() => { onPick(m); onClose() }}>
        <span className="ml-model-art" style={{ backgroundImage: `url(${m.art})` }} />
        <span className="ml-model-body">
          <b><span>{m.name}</span>{m.id === value.id && <Check size={15} />}</b>
          <small>{m.blurb}</small>
          <span className="ml-tags">{statusLabel[m.status] && <em data-status={m.status}>{statusLabel[m.status]}</em>}{m.tags.map(t => <em key={t}>{t}</em>)}</span>
        </span>
      </motion.button>)}
    </div>
  </Popover>
}

const choiceIcon: Record<string, LucideIcon> = { sound: AudioWaveform, length: Clock3, voice: Mic, speaker: UserRound, language: Globe, resolution: Monitor, aspect: RectangleHorizontal, quality: Gauge, duration: Clock3, mode: Layers, type: Music2, guide: ScanSearch, orbit: Move3d, height: Camera, distance: Camera }
// Image settings that belong to one image mode only.
const modeOnly: Record<string, string> = { guide: 'Estructura', orbit: 'Ángulo', height: 'Ángulo', distance: 'Ángulo', follow: 'Seguir vídeo', engine: 'Cambiar personaje', scale: 'Escalar', finish: 'Escalar' }
// Splitting a song has nothing to generate: only the number of stems is a choice.
const splitOnly: Record<string, boolean> = { type: true, stems: true }

function Choice({ id, label, options, value, onChange }: { id: string; label: string; options: string[]; value: string; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false)
  const Icon = choiceIcon[id] || Layers
  return <span className="ml-anchor">
    <button type="button" className="ml-chip" aria-label={`${label}: ${value}`} title={label} onClick={() => setOpen(v => !v)}><Icon size={14} />{value}</button>
    <Popover open={open} onClose={() => setOpen(false)} className="ml-menu">
      <small>{label}</small>
      {options.map(o => <button type="button" key={o} className={o === value ? 'is-on' : ''} onClick={() => { onChange(o); setOpen(false) }}>{o}{o === value && <Check size={14} />}</button>)}
    </Popover>
  </span>
}

function RefThumb({ value, onRemove }: { value: ArtifactRef; onRemove: () => void }) {
  const src = useMediaSrc(value)
  return <span className="ml-ref" style={src ? { backgroundImage: `url(${src})` } : undefined}>
    <button type="button" aria-label="Quitar referencia" onClick={onRemove}><X size={12} /></button>
  </span>
}

function CharacterRow({ c, on, onPick }: { c: Character; on: boolean; onPick: () => void }) {
  const src = useMediaSrc(c.references[0])
  return <button type="button" className={`ml-mention-row ${on ? 'is-on' : ''}`} onMouseDown={e => e.preventDefault()} onClick={onPick}>
    <span className="ml-mention-face" style={src ? { backgroundImage: `url(${src})` } : undefined} />
    <span><b>@{c.handle}</b><small>{c.name}{c.lora ? ' · LoRA' : ''}</small></span>
  </button>
}

/** @ list: the viewer's characters (inserted as @handle) and the LoRAs this job can take. */
function MentionMenu({ open, onClose, query, characters, loras, active, onCharacter, onLora }: { open: boolean; onClose: () => void; query: string; characters: Character[]; loras: Lora[]
  active: number; onCharacter: (c: Character) => void; onLora: (l: Lora) => void }) {
  return <Popover open={open} onClose={onClose} className="ml-mention">
    {characters.length > 0 && <small>Personajes</small>}
    {characters.map((c, i) => <CharacterRow key={c.id} c={c} on={i === active} onPick={() => onCharacter(c)} />)}
    {loras.length > 0 && <small>LoRAs</small>}
    {loras.map((l, i) => <button type="button" key={l.id} className={`ml-mention-row ${characters.length + i === active ? 'is-on' : ''}`} disabled={l.status !== 'ready'}
      onMouseDown={e => e.preventDefault()} onClick={() => onLora(l)}>
      <span className="ml-mention-face is-lora"><SwatchBook size={15} /></span>
      <span><b>{l.name}</b><small>{l.status === 'ready' ? l.trigger || 'Sin palabras clave' : l.status === 'downloading' ? 'Descargando…' : 'Con error'}</small></span>
    </button>)}
    {!characters.length && !loras.length && <p className="ml-mention-empty">{query ? `Nada con «${query}».` : 'Aún no tienes personajes ni LoRAs para esto.'}</p>}
    <Link to="/characters" className="ml-mention-manage" onClick={onClose}>Gestionar personajes y LoRAs<ChevronRight size={14} /></Link>
  </Popover>
}

export default function Composer({ modality, caps, progress, onGenerate, seed }: { modality: Modality; caps: Caps; progress: number | null; onGenerate: (s: Submission) => Promise<void>; seed?: { kind: Modality; prompt: string; ref?: ArtifactRef; mode?: string; nonce: number } | null }) {
  // A model card on Explore opens its creator with that model already picked.
  const wanted = (useLocation().state as { model?: string } | null)?.model
  const pick = () => models.find(m => m.id === wanted && m.modality === modality && available(m, caps)) || models.find(m => m.modality === modality && available(m, caps)) || models.find(m => m.modality === modality && m.status !== 'soon')!
  const [model, setModel] = useState(pick)
  const [prompt, setPrompt] = useState('')
  const [lyrics, setLyrics] = useState('')
  const [values, setValues] = useState<Record<string, string>>({})
  const [count, setCount] = useState(1)
  const [refs, setRefs] = useState<ArtifactRef[]>([])
  const [source, setSource] = useState<ArtifactRef | null>(null)
  const [picker, setPicker] = useState(false)
  const [chosen, setChosen] = useState(false)
  const [sending, setSending] = useState<'' | 'improving' | 'sending'>('')
  // Shared with the advanced creators: 'external' rewrites every prompt with the viewer's provider before generating.
  const [ai, setAi] = useState(() => getEnhancerMode() === 'external')
  const provider = useProvider()
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  // Nested drag enter/leave pairs; above zero a file is being dragged over the composer.
  const [dragging, setDragging] = useState(0)
  useEffect(() => {
    // A file dropped outside the composer would otherwise open in the tab and lose what was typed.
    const guard = (e: DragEvent) => { if (e.dataTransfer?.types.includes('Files')) e.preventDefault() }
    const reset = () => setDragging(0)
    window.addEventListener('dragover', guard); window.addEventListener('drop', guard); window.addEventListener('drop', reset); window.addEventListener('dragend', reset)
    return () => { window.removeEventListener('dragover', guard); window.removeEventListener('drop', guard); window.removeEventListener('drop', reset); window.removeEventListener('dragend', reset) }
  }, [])
  const [loras, setLoras] = useState<LoraPick[]>([])
  // Typing @word opens the list filtered by word; the chip opens it unfiltered.
  const [mention, setMention] = useState<{ start: number; query: string } | null>(null)
  const [atOpen, setAtOpen] = useState(false)
  const [active, setActive] = useState(0)
  const library = useCharacters()
  const area = useRef<HTMLTextAreaElement>(null)
  // Where the caret goes once an inserted mention is on screen.
  const nextCaret = useRef<number | null>(null)
  useLayoutEffect(() => { const el = area.current; if (el && nextCaret.current !== null) { el.focus(); el.setSelectionRange(nextCaret.current, nextCaret.current); nextCaret.current = null } })
  const file = useRef<HTMLInputElement>(null)
  useEffect(() => { setModel(pick()); setChosen(false); setValues({}); setCount(1); setRefs([]); setSource(null); setError(''); setLoras([]) }, [modality])
  useEffect(() => { if (!chosen || !available(model, caps)) setModel(pick()) }, [caps])
  const applied = useRef(0)
  useEffect(() => {
    // Navigation commits after the seed, so wait until the composer shows the seed's modality.
    if (!seed || seed.kind !== modality || applied.current === seed.nonce) return
    applied.current = seed.nonce
    setPrompt(seed.prompt)
    if (seed.ref && modality === 'audio') { setSource(seed.ref); setValues(v => ({ ...v, type: seed.mode || 'Cover' })) }
    else if (seed.ref && isVideo(seed.ref.uri)) {
      setSource(seed.ref); setValues(v => ({ ...v, mode: seed.mode || 'Cambiar personaje' }))
      if (seed.mode === 'Seguir vídeo' && model.id !== 'h3-turbo') { setModel(models.find(m => m.id === 'h3')!); setChosen(true) }
    }
    else if (seed.ref && seed.mode) { setRefs([seed.ref]); setValues(v => ({ ...v, mode: seed.mode! })) }
    else if (seed.ref) { setRefs(r => [...r, seed.ref!].slice(0, maxRefs[modality])); if (modality === 'video') setValues(v => ({ ...v, mode: 'Imagen inicial' })) }
    // Explore apps open a creator in one mode, with nothing attached yet.
    else if (seed.mode) setValues(v => ({ ...v, [modality === 'audio' ? 'type' : 'mode']: seed.mode! }))
    area.current?.focus()
  }, [seed?.nonce, modality])
  useEffect(() => { const el = area.current; if (el) { el.style.height = '0px'; el.style.height = Math.min(el.scrollHeight, 168) + 'px' } }, [prompt])
  const k6 = model.id === 'kandinsky6', tts = model.id === 'qwen3-tts', sfx = model.id === 'stable-audio3'
  const song = modality === 'audio' && !tts && !sfx
  // FastH3 Omni is a Ref2VA checkpoint: it only generates from references. Kandinsky makes 5 s clips from text or a first frame,
  // in two shapes; each Stable Audio kind has its own lengths.
  const value = (id: string): string => {
    const chosen = values[id] ?? settings[modality].find(c => c.id === id)?.options[0] ?? ''
    if (id === 'mode' && modality === 'video' && chosen === 'Escalar') return chosen
    if (id === 'mode' && model.id === 'fasth3-omni') return 'Referencias'
    if (id === 'mode' && k6) return chosen === 'Imagen inicial' ? chosen : 'Texto'
    if (id === 'aspect' && k6) return K6_ASPECTS.includes(chosen) ? chosen : '16:9'
    if (id === 'length') { const options = SOUND_LENGTHS[SOUND_KINDS[value('sound')]]; return options.includes(chosen) ? chosen : options[0] }
    return chosen
  }
  const voice = tts ? VOICES[value('voice')] : undefined
  const [consent, setConsent] = useState(false)
  const swap = modality === 'video' ? SWAP_MODES[value('mode')] : undefined
  const imageMode = modality === 'image' ? value('mode') : ''
  const guided = imageMode === 'Estructura', angle = imageMode === 'Ángulo', cutout = imageMode === 'Quitar fondo'
  const split = song && value('type') === 'Separar pistas'
  // Following a clip runs on H3 Ref2VA (base or Turbo); the clip sets format and length.
  const follow = modality === 'video' && value('mode') === 'Seguir vídeo'
  // FlashVSR upscales an existing clip: no prompt, no model choice; scale and speed are the only settings.
  const upscale = modality === 'video' && value('mode') === 'Escalar'
  const followReady = (model.id === 'h3' || model.id === 'h3-turbo') && Object.values(caps.follow).some(Boolean)
  const imageModeReady = (o: string) => o === 'Crear' || (o === 'Estructura' ? Object.values(caps.control).some(Boolean) : o === 'Quitar fondo' ? caps.cutout : caps.camera)
  // Swap modes only show up once their LoRAs are installed; the clip decides format and length.
  // Angle re-shoots and cutouts keep the photo's frame and a fixed recipe, so format and quality go away.
  const choices = settings[modality].filter(c => !(c.id === 'quality' && model.id === 'qwen-turbo') && !(swap && c.id !== 'mode' && c.id !== 'engine') && !(upscale && c.id !== 'mode' && c.id !== 'scale' && c.id !== 'finish')
      && (!modeOnly[c.id] || modeOnly[c.id] === value('mode')) && !(follow && (c.id === 'aspect' || c.id === 'duration')) && !((angle || cutout) && (c.id === 'aspect' || c.id === 'quality'))
      && (modality !== 'audio' || (audioOnly[c.id] ? audioOnly[c.id] === model.id : song)) && !(c.id === 'speaker' && voice !== 'preset')
      && !(k6 && (c.id === 'duration' || c.id === 'resolution'))
      && (split ? splitOnly[c.id] : c.id !== 'stems'))
    .map(c => c.id === 'mode' ? { ...c, options: c.options.filter(o => modality === 'image' ? imageModeReady(o) : o === 'Escalar' ? caps.upscale : model.id === 'fasth3-omni' ? o === 'Referencias' : k6 ? o === 'Texto' || o === 'Imagen inicial' : o === 'Seguir vídeo' ? followReady : !SWAP_MODES[o] || caps.swap[SWAP_MODES[o]]) }
      : c.id === 'aspect' && k6 ? { ...c, options: K6_ASPECTS }
      : c.id === 'sound' ? { ...c, options: c.options.filter(o => caps.sound[SOUND_KINDS[o]]) }
      : c.id === 'length' ? { ...c, options: SOUND_LENGTHS[SOUND_KINDS[value('sound')]] }
      : c.id === 'voice' ? { ...c, options: c.options.filter(o => caps.speech[VOICES[o]]) }
      : c.id === 'guide' ? { ...c, options: c.options.filter(o => caps.control[GUIDES[o]]) }
      : c.id === 'follow' ? { ...c, options: c.options.filter(o => caps.follow[FOLLOWS[o]]) }
      : c.id === 'engine' ? { ...c, options: c.options.filter(o => o !== 'SCAIL-2' || caps.swap.scail) }
      : c.id === 'type' ? { ...c, options: c.options.filter(o => o !== 'Separar pistas' || caps.stems) } : c)
    .filter(c => c.options.length > 1 || c.id !== 'mode')
  const cover = song && value('type') === 'Cover'
  const enhance = ai && provider.ready && !cover && !swap && !upscale && !angle && !split && !cutout && !selfWritten[model.id]
  // MOSS-Image only creates; editing stays on Qwen. Klein edits up to 4 photos; Kandinsky takes one opening frame.
  const limit = upscale ? 0 : swap || guided || angle || cutout ? 1 : model.id === 'moss-image' ? 0 : model.id === 'flux3-klein' ? 4 : k6 ? (value('mode') === 'Imagen inicial' ? 1 : 0) : maxRefs[modality]
  const fixed = !!swap || upscale || angle || split || cutout
  const toggleAi = () => setAi(on => { setEnhancerMode(on ? 'manual' : 'external'); return !on })
  const base = loraBase({ kind: modality, modelId: model.id, values: { mode: value('mode') } })
  const people = mentioned(prompt, library.characters)
  const picked = loras.map(p => library.loras.find(l => l.id === p.id)).filter((l): l is Lora => !!l && l.base === base)
  const mentions = modality !== 'audio' && !split && !cutout && !angle && !upscale
  const needle = (atOpen ? '' : mention?.query || '').toLowerCase()
  const listed = library.characters.filter(c => c.handle.includes(needle) || c.name.toLowerCase().includes(needle))
  const listedLoras = base && caps.loras ? library.loras.filter(l => l.base === base && !loras.some(p => p.id === l.id) && l.name.toLowerCase().includes(needle)) : []
  const menuOpen = mentions && (atOpen || !!mention)
  const closeMenu = () => { setAtOpen(false); setMention(null); setActive(0) }
  // Replace the typed @word (or insert at the caret) and put the caret after the new text.
  const insert = (text: string) => {
    const el = area.current, caret = el?.selectionStart ?? prompt.length
    const start = mention ? mention.start : caret
    const before = prompt.slice(0, start), after = prompt.slice(caret)
    const glue = before && !/\s$/.test(before) ? ' ' : ''
    const next = before + glue + text + (after.startsWith(' ') ? '' : ' ') + after.trimStart()
    setPrompt(next); closeMenu()
    nextCaret.current = (before + glue + text).length + 1
  }
  const pickCharacter = (c: Character) => insert(`@${c.handle}`)
  const pickLora = (l: Lora) => {
    setLoras(v => v.some(p => p.id === l.id) ? v : [...v, { id: l.id }].slice(0, 4))
    // Trigger words are what wake a LoRA up; they go where the @ was.
    if (l.trigger && !prompt.toLowerCase().includes(l.trigger.toLowerCase())) insert(l.trigger)
    else if (mention) insert('')
    else closeMenu()
  }
  const track = (text: string, caret: number) => {
    const m = /(^|\s)@([A-Za-z0-9_]{0,24})$/.exec(text.slice(0, caret))
    setMention(m && mentions ? { start: caret - m[2].length - 1, query: m[2] } : null)
    setAtOpen(false); setActive(0)
  }
  const cast = people.some(c => c.references.length > 0)
  const ready = !sending && !uploading && (swap === 'remove' || split || upscale ? source : follow ? source && prompt.trim() : swap ? source && (refs.length > 0 || cast) : angle || cutout ? refs.length > 0 : guided ? prompt.trim() && refs.length > 0
    : tts ? prompt.trim() && (voice !== 'design' || lyrics.trim()) && (voice !== 'clone' || (source && consent))
    : k6 ? prompt.trim() && (value('mode') === 'Texto' || refs.length > 0)
    : prompt.trim() && (!cover || source) && !(modality === 'video' && value('mode') !== 'Texto' && !refs.length && !cast))
  const submit = async () => {
    if (!ready) return
    setError('')
    // @handles become references and LoRAs before the prompt is improved or sent.
    let submission: Submission = withCharacters({ kind: modality, prompt: prompt.trim(), lyrics, modelId: model.id, count, refs, source, consent,
      values: Object.fromEntries(settings[modality].map(c => [c.id, value(c.id)])), loras: picked.map(l => ({ id: l.id })) }, library.characters)
    try {
      if (enhance) {
        setSending('improving')
        try { submission = await improve(submission) }
        catch (e) { throw new Error(`No se pudo mejorar el prompt con ${provider.model || 'tu proveedor'}: ${e instanceof Error ? e.message : String(e)}. Desactiva IA para generar con tu texto exacto.`) }
      }
      setSending('sending')
      await onGenerate(submission)
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) } finally { setSending('') }
  }
  const attach = async (files: File[]) => {
    if (!files.length) return
    setUploading(true); setError('')
    try {
      const added = await uploadImages(files)
      setRefs(r => (swap || guided || angle || cutout ? [...added, ...r] : [...r, ...added]).slice(0, limit))
      // The guide is center-cropped to the format, so follow its shape.
      const first = added[0]
      if (guided && first?.width && first.height) setValues(v => ({ ...v, aspect: nearestAspect(first.width!, first.height!) }))
    }
    catch (e) { setError(e instanceof Error ? e.message : String(e)) } finally { setUploading(false) }
  }
  const attachSource = async (file?: File) => {
    setUploading(true); setError('')
    try {
      const ref = await uploadAudio(file)
      if (ref && split && isVideo(ref.uri)) throw new Error('Elige una canción o un audio, no un vídeo.')
      if (ref && tts) setConsent(false)
      if (ref && follow && !isVideo(ref.uri)) throw new Error('Elige un vídeo de 2 a 15 segundos.')
      if (ref && upscale && !isVideo(ref.uri)) throw new Error('Elige un vídeo para escalar.')
      if (ref && swap && !isVideo(ref.uri)) throw new Error(swap === 'remove' ? 'Elige un vídeo de 1 a 10 segundos (mejor hasta 5, una sola toma).' : 'Elige un vídeo de 2 a 15 segundos (mejor hasta 5, una sola toma).')
      if (ref) setSource(ref)
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) } finally { setUploading(false) }
  }
  // Dropped images become references and a dropped audio or video becomes the mode's source, each only where the mode takes it.
  const takesSource = cover || split || voice === 'clone' || !!swap || follow || upscale
  const dropHint = swap === 'remove' ? 'Suelta el vídeo o el fotograma limpio' : swap ? 'Suelta el vídeo original o la imagen del personaje'
    : upscale ? 'Suelta el vídeo a escalar' : follow ? 'Suelta el vídeo a seguir o imágenes de referencia' : voice === 'clone' ? 'Suelta el audio o vídeo con la voz'
    : cover || split ? 'Suelta la canción' : limit ? (limit === 1 ? 'Suelta la imagen' : 'Suelta las imágenes') : 'Este modo no usa archivos'
  const drop = (files: File[]) => {
    setDragging(0)
    const images = files.filter(f => droppedKind(f) === 'image'), media = files.filter(f => droppedKind(f) === 'media')
    if (!images.length && !media.length) return setError('Suelta imágenes PNG, JPEG o WebP, o un audio o vídeo.')
    const refused = (images.length && !limit) || (media.length && !takesSource)
    if (refused) setError(media.length && !takesSource
      ? (modality === 'audio' ? 'Para usar una canción o una voz elige Cover, Separar pistas o Clonar voz.' : 'Este modo no usa audio ni vídeo.')
      : 'Este modelo o modo no usa imágenes.')
    if (media.length && takesSource) void attachSource(media[0])
    if (images.length && limit) void attach(images)
  }
  const placeholder = swap ? `${swap === 'remove' ? '¿A quién quitar?' : swap === 'head' ? '¿A quién le cambias la cabeza?' : '¿A quién reemplazar?'} Opcional, p. ej. «el chico de la sudadera amarilla»`
    : guided ? 'Describe la imagen nueva completa; la foto guía solo marca la pose, los bordes o la profundidad…'
    : follow ? 'Describe quién aparece, dónde y cómo se ve; el movimiento sale del vídeo…'
    : angle ? 'Opcional: otros cambios además del ángulo (lo más limpio es solo el ángulo)'
    : split ? 'Sube una canción o abre una de tu biblioteca y pulsa Separar voz'
    : upscale ? 'Sube o suelta un vídeo: FlashVSR lo escala ×2 o ×4 y conserva el audio; no hace falta texto'
    : cutout ? 'Se recorta lo principal de la foto sobre un fondo transparente (PNG); no hace falta texto'
    : tts ? 'Escribe lo que dirá la voz, con puntuación normal…'
    : sfx ? 'Describe el sonido: género, instrumentos y ánimo; o la fuente, el material y el espacio de un efecto…'
    : k6 ? 'Describe la escena y lo que pasa; lo que dicen, entre comillas: «Hola, ¿qué tal?»'
    : song && enhance ? 'Describe tu canción: tema, género, ánimo, voz e idioma. La IA escribe el estilo y la letra…'
    : { image: refs.length ? 'Describe qué cambiar en la imagen…' : 'Describe la imagen que imaginas…', video: 'Describe la escena, el movimiento de cámara y el sonido…', audio: 'Estilo: género, ánimo, instrumentos, voz…' }[modality]
  const files = (e: React.DragEvent) => e.dataTransfer.types.includes('Files')
  return <div className={`ml-composer ${dragging ? 'is-dropping' : ''} ${dragging && !limit && !takesSource ? 'is-refusing' : ''}`} data-drop={dropHint}
    onDragEnter={e => { if (files(e)) setDragging(n => n + 1) }} onDragLeave={e => { if (files(e)) setDragging(n => Math.max(0, n - 1)) }}
    onDragOver={e => { if (files(e)) e.preventDefault() }} onDrop={e => { if (!files(e)) return; e.preventDefault(); drop(Array.from(e.dataTransfer.files)) }}>
    {(refs.length > 0 || uploading || source || picked.length > 0 || people.length > 0) && <div className="ml-refs">
      {refs.map((r, i) => <RefThumb key={r.sha256 + i} value={r} onRemove={() => setRefs(v => v.filter((_, k) => k !== i))} />)}
      {source && <span className="ml-ref ml-ref-audio" title={swap ? 'Vídeo original' : 'Canción'}>{isVideo(source.uri) ? <Film size={16} /> : <Music2 size={16} />}<button type="button" aria-label={isVideo(source.uri) ? 'Quitar vídeo' : 'Quitar audio'} onClick={() => setSource(null)}><X size={12} /></button></span>}
      {uploading && <span className="ml-ref is-loading"><Loader2 size={16} /></span>}
      {mentions && people.map(c => <span key={c.id} className="ml-ref-tag" title={c.description || c.name}><AtSign size={12} />{c.handle}</span>)}
      {picked.map(l => <span key={l.id} className="ml-ref-tag is-lora" title={l.trigger ? `Palabras clave: ${l.trigger}` : l.name}><SwatchBook size={12} />{l.name}
        <button type="button" aria-label={`Quitar LoRA ${l.name}`} onClick={() => setLoras(v => v.filter(p => p.id !== l.id))}><X size={11} /></button></span>)}
    </div>}
    <textarea ref={area} rows={1} value={split || cutout || upscale ? '' : prompt} placeholder={placeholder} disabled={split || cutout || upscale} aria-label={tts ? 'Texto' : sfx ? 'Sonido' : song && enhance ? 'Idea' : modality === 'audio' ? 'Estilo' : 'Prompt'}
      onChange={e => { setPrompt(e.target.value); track(e.target.value, e.target.selectionStart) }}
      onKeyDown={e => {
        const total = listed.length + listedLoras.length
        if (menuOpen && total && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) { e.preventDefault(); setActive(i => (i + (e.key === 'ArrowDown' ? 1 : total - 1)) % total); return }
        if (menuOpen && total && (e.key === 'Enter' || e.key === 'Tab') && !e.ctrlKey && !e.metaKey) {
          e.preventDefault(); const i = Math.min(active, total - 1)
          if (i < listed.length) pickCharacter(listed[i]); else if (listedLoras[i - listed.length].status === 'ready') pickLora(listedLoras[i - listed.length])
          return
        }
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) void submit()
      }} />
    {song && value('type') !== 'Instrumental' && !split && <textarea className="ml-lyrics" rows={3} value={lyrics} aria-label="Letra"
      placeholder={enhance ? 'Letra (opcional): déjala vacía y la IA la escribe; si la escribes, se canta tal cual' : '[Verse]\nEscribe la letra, una frase por línea\n\n[Chorus]\n…'} onChange={e => setLyrics(e.target.value)} />}
    {(tts || k6) && <textarea className="ml-lyrics" rows={2} value={lyrics} onChange={e => setLyrics(e.target.value)}
      aria-label={k6 ? 'Voz y sonidos' : voice === 'design' ? 'Descripción de la voz' : voice === 'clone' ? 'Texto de la referencia' : 'Cómo lo dice'}
      placeholder={k6 ? 'Voz y sonidos (opcional): «voz grave y tranquila, lluvia de fondo, música suave»'
        : voice === 'design' ? 'Describe la voz: «mujer de 30 años, voz cálida y segura, acento mexicano, ritmo pausado»'
        : voice === 'clone' ? 'Opcional: lo que dice el audio de referencia, palabra por palabra (mejora el parecido)'
        : 'Opcional, cómo lo dice: «susurrando», «emocionado y rápido», «como un locutor de radio»'} />}
    {error && <p className="ml-error" role="alert">{error}</p>}
    <div className="ml-composer-row">
      <div className="ml-chips">
        {limit > 0 && <button type="button" className={`ml-chip ${swap || guided || angle || cutout ? (refs.length ? 'is-on' : '') : 'ml-chip-icon'}`} aria-label={swap === 'remove' ? 'Primer fotograma sin la persona' : swap === 'head' ? 'Foto de la cara nueva' : swap ? 'Imagen del personaje' : guided ? 'Foto guía' : angle ? 'Foto a re-encuadrar' : cutout ? 'Foto a recortar' : 'Añadir imagen de referencia'}
          title={swap === 'remove' ? 'Opcional: el primer fotograma ya sin la persona; si no, se crea solo' : swap === 'head' ? 'Una foto clara de frente de la cara nueva' : swap ? 'Imagen del personaje: cara, pelo y ropa visibles' : guided ? 'Foto cuya pose, bordes o profundidad seguirá la imagen nueva'
            : angle ? 'La foto que se vuelve a tomar desde otro ángulo' : cutout ? 'La foto cuyo fondo se quita' : modality === 'image' ? 'Añadir imágenes para editar' : 'Imagen inicial o referencias'}
          onClick={() => file.current?.click()}><Paperclip size={15} />{swap ? ({ remove: 'Fondo', head: 'Cara', character: 'Personaje' } as const)[swap] : guided ? 'Guía' : angle || cutout ? 'Foto' : null}</button>}
        {(cover || split) && <button type="button" className={`ml-chip ${source ? 'is-on' : ''}`} onClick={() => void attachSource()}><Music2 size={14} />{source ? 'Audio listo' : 'Subir canción'}</button>}
        {voice === 'clone' && <button type="button" className={`ml-chip ${source ? 'is-on' : ''}`} title="Audio o vídeo de 3 a 30 s con una sola voz clara y poco ruido" onClick={() => void attachSource()}><Mic size={14} />{source ? 'Voz lista' : 'Subir voz'}</button>}
        {voice === 'clone' && <button type="button" className={`ml-chip ${consent ? 'is-on' : ''}`} aria-pressed={consent} onClick={() => setConsent(v => !v)}
          title="Solo clona tu voz o la de alguien que te dio permiso; nunca para engañar ni hacerse pasar por otra persona"><ShieldCheck size={14} />Tengo permiso</button>}
        {(swap || follow || upscale) && <button type="button" className={`ml-chip ${source ? 'is-on' : ''}`} title={upscale ? 'Vídeo a escalar: ×4 solo para vídeos pequeños (hasta 480p); conserva el audio y crea un vídeo nuevo' : follow ? 'Vídeo de 2 a 15 s cuyo movimiento, bordes o profundidad seguirá el nuevo; también marca formato y duración' : swap === 'remove' ? 'Vídeo de 1 a 10 s (mejor hasta 5, una toma con cámara estable); se conservan la escena y el audio' : 'Vídeo de 2 a 15 s (mejor hasta 5, una sola toma); se conservan movimiento, cámara y audio'}
          onClick={() => void attachSource()}><Film size={14} />{source ? 'Vídeo listo' : 'Subir vídeo'}</button>}
        <button type="button" className={`ml-chip ml-chip-ai ${enhance ? 'is-on' : ''}`} aria-pressed={enhance} disabled={!provider.ready || cover || fixed || !!selfWritten[model.id]} onClick={toggleAi}
          title={!provider.ready ? 'Configura un proveedor en Cuenta → Proveedores IA para mejorar tus prompts' : cover ? 'Los covers usan tu texto exacto' : fixed ? 'Usa la receta fija del modelo' : selfWritten[model.id] ? selfWritten[model.id] : enhance ? `${provider.model} reescribe el prompt con la guía del modelo antes de generar` : 'Generar con tu texto exacto'}>
          <WandSparkles size={14} />IA</button>
        {mentions && <span className="ml-anchor">
          <button type="button" className={`ml-chip ml-chip-icon ${people.length || picked.length ? 'is-on' : ''}`} aria-label="Mencionar personaje o LoRA" aria-expanded={menuOpen}
            title="@ personajes y LoRAs: escribe @ en el prompt o pulsa aquí" onClick={() => { setMention(null); setActive(0); setAtOpen(v => !v) }}><AtSign size={15} /></button>
          <MentionMenu open={menuOpen} onClose={closeMenu} query={needle} characters={listed} loras={listedLoras} active={active} onCharacter={pickCharacter} onLora={pickLora} />
        </span>}
        {!fixed && <span className="ml-anchor">
          <button type="button" className="ml-chip ml-chip-model" onClick={() => setPicker(v => !v)}>
            <span className="ml-dot" style={{ backgroundImage: `url(${model.art})` }} /><span className="ml-chip-name">{model.name}</span><ChevronRight size={14} />
          </button>
          <ModelPicker modality={modality} value={model} caps={caps} onPick={m => { setModel(m); setChosen(true); if (m.id === 'moss-image') { setRefs([]); setValues(v => ({ ...v, mode: 'Crear' })) }
            if (m.id === 'flux3-klein') { setRefs(r => r.slice(0, 4)); setValues(v => ({ ...v, mode: 'Crear' })) }
            if (m.id === 'kandinsky6') setRefs(r => r.slice(0, value('mode') === 'Imagen inicial' ? 1 : 0))
            if (modality === 'audio') { setSource(null); setLyrics('') }
            if (follow && m.id !== 'h3' && m.id !== 'h3-turbo') setValues(v => ({ ...v, mode: 'Referencias' })) }} open={picker} onClose={() => setPicker(false)} />
        </span>}
        {choices.map(c => <Choice key={c.id} id={c.id} label={c.label} options={c.options} value={value(c.id)} onChange={v => {
          setValues(s => ({ ...s, [c.id]: v }))
          if (c.id === 'mode' && (SWAP_MODES[v] || v === 'Estructura' || v === 'Ángulo' || v === 'Quitar fondo')) setRefs(r => r.slice(0, 1))
          if (c.id === 'mode' && v === 'Escalar') setRefs([])
          // Structure and angle run on Qwen; MOSS and Klein only create (Klein also edits from the main mode).
          if (c.id === 'mode' && v !== 'Crear' && (model.id === 'moss-image' || model.id === 'flux3-klein')) { setModel(models.find(m => m.id === 'qwen-quality')!); setChosen(true) }
          if (c.id === 'mode' && k6 && v === 'Texto') setRefs([])
          if (c.id === 'voice') { setSource(null); setConsent(false) }
          // Covers only exist in YuE2.
          if (c.id === 'type' && v === 'Cover' && model.id === 'ace-step') { setModel(models.find(m => m.id === 'yue2')!); setChosen(true) }
        }} />)}
        {modality === 'image' && !cutout && <span className="ml-stepper" aria-label="Cantidad">
          <button type="button" aria-label="Menos" onClick={() => setCount(c => Math.max(1, c - 1))}><Minus size={13} /></button>
          <b>{count}/4</b>
          <button type="button" aria-label="Más" onClick={() => setCount(c => Math.min(4, c + 1))}><Plus size={13} /></button>
        </span>}
      </div>
      <button type="button" className={`ml-generate ${progress !== null ? 'is-busy' : ''}`} onClick={() => void submit()} disabled={!ready}>
        <span className="ml-generate-fill" style={{ transform: `scaleX(${progress !== null ? progress / 100 : 0})` }} />
        <span className="ml-generate-label">{sending ? <><Loader2 size={16} className="ml-spin" />{sending === 'improving' ? 'Mejorando' : 'Enviando'}</> : progress !== null ? (progress > 0 ? <>Generando <b>{Math.round(progress)}%</b></> : <><Loader2 size={15} className="ml-spin" />En cola</>) : <>{enhance ? <WandSparkles size={16} /> : <Sparkles size={16} />}{upscale ? 'Escalar' : 'Generar'}</>}</span>
        {progress === null && !sending && <kbd>Ctrl ↵</kbd>}
      </button>
    </div>
    <input ref={file} type="file" accept="image/png,image/jpeg,image/webp" multiple={limit > 1} hidden onChange={e => { void attach(Array.from(e.target.files || [])); e.target.value = '' }} />
  </div>
}
