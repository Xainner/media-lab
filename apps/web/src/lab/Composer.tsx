import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'motion/react'
import { AtSign, AudioWaveform, Camera, Check, ChevronRight, Clock3, Film, Gauge, Globe, Layers, Loader2, Mic, Minus, Move3d, Music2, Monitor, Paperclip, Plus, RectangleHorizontal, ScanSearch, ShieldCheck, Sparkles, SwatchBook, UserRound, WandSparkles, X, type LucideIcon } from 'lucide-react'
import { getEnhancerMode, setEnhancerMode, type ArtifactRef } from '../studio/lib/api'
import { t, type MessageKey } from '../i18n'
import { FOLLOWS, GUIDES, K6_ASPECTS, TWO_K_REFS, label, models, nearestAspect, settings, SOUND_KINDS, SOUND_LENGTHS, SWAP_MODES, VOICES, type Modality, type Model } from './data'
import { droppedKind, improve, loraBase, mentioned, uploadAudio, uploadImages, useCharacters, useMediaSrc, useProvider, withCharacters, type Caps, type Character, type Lora, type LoraPick, type Submission } from './live'

const statusLabel = (status: Model['status']) => status === 'ready' ? '' : t(status === 'new' ? 'composer.model.status.new' : 'composer.model.status.soon')
const maxRefs: Record<Modality, number> = { image: 10, video: 9, audio: 0 }
const isVideo = (uri: string) => /\.(mp4|webm|mkv|mov)$/i.test(uri)

/** A model can run when it is installed here; Turbo variants also need their weights on the server. */
export const available = (m: Model, caps: Caps) => m.status !== 'soon' && (m.id !== 'qwen-turbo' || caps.turbo) && (m.id !== 'h3-turbo' || caps.h3Turbo) && (m.id !== 'fasth3-omni' || caps.omni) && (m.id !== 'h3-fused' || caps.fusedTurbo) && (m.id !== 'ace-step' || caps.ace) && (m.id !== 'moss-image' || caps.moss)
  && (m.id !== 'flux3-klein' || caps.flux3) && (m.id !== 'kandinsky6' || caps.kandinsky6) && (m.id !== 'stable-audio3' || Object.values(caps.sound).some(Boolean)) && (m.id !== 'qwen3-tts' || Object.values(caps.speech).some(Boolean))
// Audio settings that belong to one kind of audio model; the rest (type, stems, duration) are for songs.
const audioOnly: Record<string, string> = { sound: 'stable-audio3', length: 'stable-audio3', voice: 'qwen3-tts', speaker: 'qwen3-tts', language: 'qwen3-tts' }
// Models that rewrite or read the text themselves, so the IA chip stays off.
const selfWritten: Record<string, MessageKey> = { 'flux3-klein': 'composer.selfWritten.flux', 'stable-audio3': 'composer.selfWritten.stableAudio', 'qwen3-tts': 'composer.selfWritten.tts' }

function Popover({ open, onClose, children, className = '' }: { open: boolean; onClose: () => void; children: React.ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  // Popovers open from their button's left edge; on a phone that can run past the screen.
  const [shift, setShift] = useState(0)
  useLayoutEffect(() => {
    if (!open) { setShift(0); return }
    const box = ref.current?.getBoundingClientRect()
    if (!box) return
    const room = document.documentElement.clientWidth - 8
    setShift(box.right > room ? Math.max(8 - box.left, room - box.right) : 0)
  }, [open])
  useEffect(() => {
    if (!open) return
    const away = (e: PointerEvent) => { if (!ref.current?.contains(e.target as Node)) onClose() }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    setTimeout(() => document.addEventListener('pointerdown', away))
    document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('pointerdown', away); document.removeEventListener('keydown', esc) }
  }, [open, onClose])
  return <AnimatePresence>{open && <motion.div ref={ref} className={`ml-pop ${className}`} role="dialog" style={{ marginLeft: shift }}
    initial={{ opacity: 0, y: 12, scale: .97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 8, scale: .98 }}
    transition={{ type: 'spring', stiffness: 420, damping: 32 }}>{children}</motion.div>}</AnimatePresence>
}

export function ModelPicker({ modality, value, caps, onPick, open, onClose }: { modality: Modality; value: Model; caps: Caps; onPick: (m: Model) => void; open: boolean; onClose: () => void }) {
  const list = models.filter(m => m.modality === modality)
  return <Popover open={open} onClose={onClose} className="ml-picker">
    <header><b>{t('composer.picker.title')}</b><span>{t('composer.picker.ready', { ready: list.filter(m => available(m, caps)).length, total: list.length })}</span></header>
    <div className="ml-picker-grid">
      {list.map((m, i) => <motion.button key={m.id} type="button" className={`ml-model-card ${m.id === value.id ? 'is-on' : ''}`} disabled={!available(m, caps)}
        initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: .03 * i }}
        onClick={() => { onPick(m); onClose() }}>
        <span className="ml-model-art" style={{ backgroundImage: `url(${m.art})` }} />
        <span className="ml-model-body">
          <b><span>{m.name}</span>{m.id === value.id && <Check size={15} />}</b>
          <small>{m.blurb}</small>
          <span className="ml-tags">{statusLabel(m.status) && <em data-status={m.status}>{statusLabel(m.status)}</em>}{m.tags.map(tag => <em key={tag}>{label(tag)}</em>)}</span>
        </span>
      </motion.button>)}
    </div>
  </Popover>
}

const choiceIcon: Record<string, LucideIcon> = { sound: AudioWaveform, length: Clock3, voice: Mic, speaker: UserRound, language: Globe, resolution: Monitor, aspect: RectangleHorizontal, quality: Gauge, size: Monitor, duration: Clock3, mode: Layers, type: Music2, guide: ScanSearch, orbit: Move3d, height: Camera, distance: Camera }
// Image settings that belong to one image mode only.
const modeOnly: Record<string, string> = { guide: 'Estructura', orbit: 'Ángulo', height: 'Ángulo', distance: 'Ángulo', follow: 'Seguir vídeo', engine: 'Cambiar personaje', scale: 'Escalar', finish: 'Escalar' }
// Splitting a song has nothing to generate: only the number of stems is a choice.
const splitOnly: Record<string, boolean> = { type: true, stems: true }

function Choice({ id, name, options, value, onChange }: { id: string; name: string; options: string[]; value: string; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false)
  const Icon = choiceIcon[id] || Layers
  return <span className="ml-anchor">
    <button type="button" className="ml-chip" aria-label={`${name}: ${label(value)}`} title={name} onClick={() => setOpen(v => !v)}><Icon size={14} />{label(value)}</button>
    <Popover open={open} onClose={() => setOpen(false)} className="ml-menu">
      <small>{name}</small>
      {options.map(o => <button type="button" key={o} className={o === value ? 'is-on' : ''} onClick={() => { onChange(o); setOpen(false) }}>{label(o)}{o === value && <Check size={14} />}</button>)}
    </Popover>
  </span>
}

function RefThumb({ value, onRemove }: { value: ArtifactRef; onRemove: () => void }) {
  const src = useMediaSrc(value)
  return <span className="ml-ref" style={src ? { backgroundImage: `url(${src})` } : undefined}>
    <button type="button" aria-label={t('composer.refs.remove')} onClick={onRemove}><X size={12} /></button>
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
    {characters.length > 0 && <small>{t('composer.mention.characters')}</small>}
    {characters.map((c, i) => <CharacterRow key={c.id} c={c} on={i === active} onPick={() => onCharacter(c)} />)}
    {loras.length > 0 && <small>LoRAs</small>}
    {loras.map((l, i) => <button type="button" key={l.id} className={`ml-mention-row ${characters.length + i === active ? 'is-on' : ''}`} disabled={l.status !== 'ready'}
      onMouseDown={e => e.preventDefault()} onClick={() => onLora(l)}>
      <span className="ml-mention-face is-lora"><SwatchBook size={15} /></span>
      <span><b>{l.name}</b><small>{l.status === 'ready' ? l.trigger || t('composer.mention.noTriggers') : l.status === 'downloading' ? t('composer.mention.downloading') : t('composer.mention.failed')}</small></span>
    </button>)}
    {!characters.length && !loras.length && <p className="ml-mention-empty">{query ? t('composer.mention.noMatch', { query }) : t('composer.mention.empty')}</p>}
    <Link to="/characters" className="ml-mention-manage" onClick={onClose}>{t('composer.mention.manage')}<ChevronRight size={14} /></Link>
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
  // 2K covers Qwen creation and plain edits; angle, cutout and structure keep their 1 MP recipes.
  const sized = imageMode === 'Crear' && caps.twoK && (model.id === 'qwen-quality' || model.id === 'qwen-turbo')
  const twoK = sized && value('size') === '2K'
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
      && !(k6 && (c.id === 'duration' || c.id === 'resolution')) && (c.id !== 'size' || sized)
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
  const limit = upscale ? 0 : swap || guided || angle || cutout ? 1 : model.id === 'moss-image' ? 0 : model.id === 'flux3-klein' ? 4 : k6 ? (value('mode') === 'Imagen inicial' ? 1 : 0) : twoK ? TWO_K_REFS : maxRefs[modality]
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
      values: { ...Object.fromEntries(settings[modality].map(c => [c.id, value(c.id)])), size: twoK ? '2K' : '1 MP' }, loras: picked.map(l => ({ id: l.id })) }, library.characters)
    try {
      if (enhance) {
        setSending('improving')
        try { submission = await improve(submission) }
        catch (e) { throw new Error(t('composer.error.improve', { provider: provider.model || t('composer.error.yourProvider'), error: e instanceof Error ? e.message : String(e) })) }
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
      if (ref && split && isVideo(ref.uri)) throw new Error(t('composer.error.splitNeedsAudio'))
      if (ref && tts) setConsent(false)
      if (ref && follow && !isVideo(ref.uri)) throw new Error(t('composer.error.followNeedsVideo'))
      if (ref && upscale && !isVideo(ref.uri)) throw new Error(t('composer.error.upscaleNeedsVideo'))
      if (ref && swap && !isVideo(ref.uri)) throw new Error(t(swap === 'remove' ? 'composer.error.removeNeedsVideo' : 'composer.error.swapNeedsVideo'))
      if (ref) setSource(ref)
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) } finally { setUploading(false) }
  }
  // Dropped images become references and a dropped audio or video becomes the mode's source, each only where the mode takes it.
  const takesSource = cover || split || voice === 'clone' || !!swap || follow || upscale
  const dropHint = t(swap === 'remove' ? 'composer.drop.removeVideo' : swap ? 'composer.drop.swapVideo'
    : upscale ? 'composer.drop.upscaleVideo' : follow ? 'composer.drop.followVideo' : voice === 'clone' ? 'composer.drop.voice'
    : cover || split ? 'composer.drop.song' : limit ? (limit === 1 ? 'composer.drop.image' : 'composer.drop.images') : 'composer.drop.none')
  const drop = (files: File[]) => {
    setDragging(0)
    const images = files.filter(f => droppedKind(f) === 'image'), media = files.filter(f => droppedKind(f) === 'media')
    if (!images.length && !media.length) return setError(t('composer.error.dropUnsupported'))
    const refused = (images.length && !limit) || (media.length && !takesSource)
    if (refused) setError(media.length && !takesSource
      ? t(modality === 'audio' ? 'composer.error.audioNeedsMode' : 'composer.error.noMedia')
      : t('composer.error.noImages'))
    if (media.length && takesSource) void attachSource(media[0])
    if (images.length && limit) void attach(images)
  }
  const placeholder = t(swap ? (swap === 'remove' ? 'composer.placeholder.swapRemove' : swap === 'head' ? 'composer.placeholder.swapHead' : 'composer.placeholder.swapCharacter')
    : guided ? 'composer.placeholder.guided'
    : follow ? 'composer.placeholder.follow'
    : angle ? 'composer.placeholder.angle'
    : split ? 'composer.placeholder.split'
    : upscale ? 'composer.placeholder.upscale'
    : cutout ? 'composer.placeholder.cutout'
    : tts ? 'composer.placeholder.tts'
    : sfx ? 'composer.placeholder.sfx'
    : k6 ? 'composer.placeholder.k6'
    : song && enhance ? 'composer.placeholder.songIdea'
    : ({ image: refs.length ? 'composer.placeholder.imageEdit' : 'composer.placeholder.image', video: 'composer.placeholder.video', audio: 'composer.placeholder.audio' } as const)[modality])
  const files = (e: React.DragEvent) => e.dataTransfer.types.includes('Files')
  return <div className={`ml-composer ${dragging ? 'is-dropping' : ''} ${dragging && !limit && !takesSource ? 'is-refusing' : ''}`} data-drop={dropHint}
    onDragEnter={e => { if (files(e)) setDragging(n => n + 1) }} onDragLeave={e => { if (files(e)) setDragging(n => Math.max(0, n - 1)) }}
    onDragOver={e => { if (files(e)) e.preventDefault() }} onDrop={e => { if (!files(e)) return; e.preventDefault(); drop(Array.from(e.dataTransfer.files)) }}>
    {(refs.length > 0 || uploading || source || picked.length > 0 || people.length > 0) && <div className="ml-refs">
      {refs.map((r, i) => <RefThumb key={r.sha256 + i} value={r} onRemove={() => setRefs(v => v.filter((_, k) => k !== i))} />)}
      {source && <span className="ml-ref ml-ref-audio" title={t(swap ? 'composer.source.video' : 'composer.source.song')}>{isVideo(source.uri) ? <Film size={16} /> : <Music2 size={16} />}<button type="button" aria-label={t(isVideo(source.uri) ? 'composer.source.removeVideo' : 'composer.source.removeAudio')} onClick={() => setSource(null)}><X size={12} /></button></span>}
      {uploading && <span className="ml-ref is-loading"><Loader2 size={16} /></span>}
      {mentions && people.map(c => <span key={c.id} className="ml-ref-tag" title={c.description || c.name}><AtSign size={12} />{c.handle}</span>)}
      {picked.map(l => <span key={l.id} className="ml-ref-tag is-lora" title={l.trigger ? t('composer.lora.triggers', { trigger: l.trigger }) : l.name}><SwatchBook size={12} />{l.name}
        <button type="button" aria-label={t('composer.lora.remove', { name: l.name })} onClick={() => setLoras(v => v.filter(p => p.id !== l.id))}><X size={11} /></button></span>)}
    </div>}
    <textarea ref={area} rows={1} value={split || cutout || upscale ? '' : prompt} placeholder={placeholder} disabled={split || cutout || upscale} aria-label={t(tts ? 'composer.field.text' : sfx ? 'composer.field.sound' : song && enhance ? 'composer.field.idea' : modality === 'audio' ? 'composer.field.style' : 'composer.field.prompt')}
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
    {song && value('type') !== 'Instrumental' && !split && <textarea className="ml-lyrics" rows={3} value={lyrics} aria-label={t('composer.field.lyrics')}
      placeholder={t(enhance ? 'composer.field.lyricsAiPlaceholder' : 'composer.field.lyricsPlaceholder')} onChange={e => setLyrics(e.target.value)} />}
    {(tts || k6) && <textarea className="ml-lyrics" rows={2} value={lyrics} onChange={e => setLyrics(e.target.value)}
      aria-label={t(k6 ? 'composer.field.k6Audio' : voice === 'design' ? 'composer.field.voiceDescription' : voice === 'clone' ? 'composer.field.referenceText' : 'composer.field.delivery')}
      placeholder={t(k6 ? 'composer.field.k6AudioPlaceholder'
        : voice === 'design' ? 'composer.field.voiceDescriptionPlaceholder'
        : voice === 'clone' ? 'composer.field.referenceTextPlaceholder'
        : 'composer.field.deliveryPlaceholder')} />}
    {error && <p className="ml-error" role="alert">{error}</p>}
    <div className="ml-composer-row">
      <div className="ml-chips">
        {limit > 0 && <button type="button" className={`ml-chip ${swap || guided || angle || cutout ? (refs.length ? 'is-on' : '') : 'ml-chip-icon'}`} aria-label={t(swap === 'remove' ? 'composer.image.removeFrame' : swap === 'head' ? 'composer.image.newFace' : swap ? 'composer.image.character' : guided ? 'composer.image.guide' : angle ? 'composer.image.reframe' : cutout ? 'composer.image.cutout' : 'composer.image.addReference')}
          title={t(swap === 'remove' ? 'composer.image.removeFrameHint' : swap === 'head' ? 'composer.image.newFaceHint' : swap ? 'composer.image.characterHint' : guided ? 'composer.image.guideHint'
            : angle ? 'composer.image.reframeHint' : cutout ? 'composer.image.cutoutHint' : modality === 'image' ? 'composer.image.editHint' : 'composer.image.videoHint')}
          onClick={() => file.current?.click()}><Paperclip size={15} />{swap ? t(({ remove: 'composer.image.chipBackground', head: 'composer.image.chipFace', character: 'composer.image.chipCharacter' } as const)[swap]) : guided ? t('composer.image.chipGuide') : angle || cutout ? t('composer.image.chipPhoto') : null}</button>}
        {(cover || split) && <button type="button" className={`ml-chip ${source ? 'is-on' : ''}`} onClick={() => void attachSource()}><Music2 size={14} />{t(source ? 'composer.audio.ready' : 'composer.audio.uploadSong')}</button>}
        {voice === 'clone' && <button type="button" className={`ml-chip ${source ? 'is-on' : ''}`} title={t('composer.voice.hint')} onClick={() => void attachSource()}><Mic size={14} />{t(source ? 'composer.voice.ready' : 'composer.voice.upload')}</button>}
        {voice === 'clone' && <button type="button" className={`ml-chip ${consent ? 'is-on' : ''}`} aria-pressed={consent} onClick={() => setConsent(v => !v)}
          title={t('composer.voice.consentHint')}><ShieldCheck size={14} />{t('composer.voice.consent')}</button>}
        {(swap || follow || upscale) && <button type="button" className={`ml-chip ${source ? 'is-on' : ''}`} title={t(upscale ? 'composer.video.upscaleHint' : follow ? 'composer.video.followHint' : swap === 'remove' ? 'composer.video.removeHint' : 'composer.video.swapHint')}
          onClick={() => void attachSource()}><Film size={14} />{t(source ? 'composer.video.ready' : 'composer.video.upload')}</button>}
        <button type="button" className={`ml-chip ml-chip-ai ${enhance ? 'is-on' : ''}`} aria-pressed={enhance} disabled={!provider.ready || cover || fixed || !!selfWritten[model.id]} onClick={toggleAi}
          title={!provider.ready ? t('composer.ai.noProvider') : cover ? t('composer.ai.cover') : fixed ? t('composer.ai.fixed') : selfWritten[model.id] ? t(selfWritten[model.id]) : enhance ? t('composer.ai.on', { model: provider.model }) : t('composer.ai.off')}>
          <WandSparkles size={14} />{t('composer.ai.label')}</button>
        {mentions && <span className="ml-anchor">
          <button type="button" className={`ml-chip ml-chip-icon ${people.length || picked.length ? 'is-on' : ''}`} aria-label={t('composer.mention.button')} aria-expanded={menuOpen}
            title={t('composer.mention.hint')} onClick={() => { setMention(null); setActive(0); setAtOpen(v => !v) }}><AtSign size={15} /></button>
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
        {choices.map(c => <Choice key={c.id} id={c.id} name={c.label} options={c.options} value={value(c.id)} onChange={v => {
          setValues(s => ({ ...s, [c.id]: v }))
          if (c.id === 'mode' && (SWAP_MODES[v] || v === 'Estructura' || v === 'Ángulo' || v === 'Quitar fondo')) setRefs(r => r.slice(0, 1))
          if (c.id === 'mode' && v === 'Escalar') setRefs([])
          if (c.id === 'size' && v === '2K') setRefs(r => r.slice(0, TWO_K_REFS))
          // Structure and angle run on Qwen; MOSS and Klein only create (Klein also edits from the main mode).
          if (c.id === 'mode' && v !== 'Crear' && (model.id === 'moss-image' || model.id === 'flux3-klein')) { setModel(models.find(m => m.id === 'qwen-quality')!); setChosen(true) }
          if (c.id === 'mode' && k6 && v === 'Texto') setRefs([])
          if (c.id === 'voice') { setSource(null); setConsent(false) }
          // Covers only exist in YuE2.
          if (c.id === 'type' && v === 'Cover' && model.id === 'ace-step') { setModel(models.find(m => m.id === 'yue2')!); setChosen(true) }
        }} />)}
        {modality === 'image' && !cutout && <span className="ml-stepper" aria-label={t('composer.count.label')}>
          <button type="button" aria-label={t('composer.count.less')} onClick={() => setCount(c => Math.max(1, c - 1))}><Minus size={13} /></button>
          <b>{count}/4</b>
          <button type="button" aria-label={t('composer.count.more')} onClick={() => setCount(c => Math.min(4, c + 1))}><Plus size={13} /></button>
        </span>}
      </div>
      <button type="button" className={`ml-generate ${progress !== null ? 'is-busy' : ''}`} onClick={() => void submit()} disabled={!ready}>
        <span className="ml-generate-fill" style={{ transform: `scaleX(${progress !== null ? progress / 100 : 0})` }} />
        <span className="ml-generate-label">{sending ? <><Loader2 size={16} className="ml-spin" />{t(sending === 'improving' ? 'composer.generate.improving' : 'composer.generate.sending')}</> : progress !== null ? (progress > 0 ? <>{t('composer.generate.generating')} <b>{Math.round(progress)}%</b></> : <><Loader2 size={15} className="ml-spin" />{t('composer.generate.queued')}</>) : <>{enhance ? <WandSparkles size={16} /> : <Sparkles size={16} />}{t(upscale ? 'composer.generate.upscale' : 'composer.generate.generate')}</>}</span>
        {progress === null && !sending && <kbd>Ctrl ↵</kbd>}
      </button>
    </div>
    <input ref={file} type="file" accept="image/png,image/jpeg,image/webp" multiple={limit > 1} hidden onChange={e => { void attach(Array.from(e.target.files || [])); e.target.value = '' }} />
  </div>
}
