import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'motion/react'
import { AtSign, ExternalLink, ImagePlus, Link2, Loader2, Plus, SwatchBook, Trash2, X } from 'lucide-react'
import type { ArtifactRef } from '../studio/lib/api'
import { addLora, deleteCharacter, deleteLora, editLora, LORA_BASES, plain, saveCharacter, uploadImages, useCharacters, useMediaSrc,
  type Character, type CharacterDraft, type Lora } from './live'
import { t } from '../i18n'

const handleOf = (name: string) => name.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 24)
const size = (bytes?: number | null) => bytes ? `${(bytes / 1024 ** 2).toFixed(bytes > 100 * 1024 ** 2 ? 0 : 1)} MB` : ''

function Photo({ value, onRemove, main }: { value: ArtifactRef; onRemove?: () => void; main?: boolean }) {
  const src = useMediaSrc(value)
  return <span className={`ml-char-photo ${main ? 'is-main' : ''}`} style={src ? { backgroundImage: `url(${src})` } : undefined}>
    {main && <em>{t('lab.characters.main')}</em>}
    {onRemove && <button type="button" aria-label={t('lab.characters.removePhoto')} onClick={onRemove}><X size={12} /></button>}
  </span>
}

function Card({ c, onOpen, index }: { c: Character; onOpen: () => void; index: number }) {
  const src = useMediaSrc(c.references[0])
  return <motion.button type="button" className="ml-char-card" onClick={onOpen} layout
    initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * .03, duration: .5, ease: [.2, .8, .2, 1] }}>
    <span className="ml-char-img" style={src ? { backgroundImage: `url(${src})` } : undefined}>{!c.references.length && <ImagePlus size={22} />}</span>
    <span className="ml-char-text"><b>@{c.handle}</b><span>{c.name}</span>{c.description && <small>{c.description}</small>}</span>
    {c.lora && <i title={c.lora.name}><SwatchBook size={12} />LoRA</i>}
  </motion.button>
}

/** Create or edit one character: name, @handle, look, 1–4 photos and an optional LoRA. */
function Editor({ initial, loras, onClose }: { initial: Character | CharacterDraft; loras: Lora[]; onClose: () => void }) {
  const editing = 'id' in initial ? initial : null
  const [draft, setDraft] = useState<CharacterDraft>({ handle: initial.handle, name: initial.name, description: initial.description,
    references: initial.references, lora_id: editing ? editing.lora?.id ?? null : (initial as CharacterDraft).lora_id })
  const [touched, setTouched] = useState(!!editing)
  const [busy, setBusy] = useState<'' | 'upload' | 'save' | 'delete'>('')
  const [error, setError] = useState('')
  const file = useRef<HTMLInputElement>(null)
  const set = (patch: Partial<CharacterDraft>) => setDraft(d => ({ ...d, ...patch }))
  const valid = /^[a-z0-9_]{2,24}$/.test(draft.handle) && draft.name.trim() && draft.references.length > 0
  const upload = async (files: File[]) => {
    if (!files.length) return
    setBusy('upload'); setError('')
    try { const added = await uploadImages(files); setDraft(d => ({ ...d, references: [...d.references, ...added].slice(0, 4) })) }
    catch (e) { setError(plain(e)) } finally { setBusy('') }
  }
  const save = async () => {
    setBusy('save'); setError('')
    try { await saveCharacter(draft, editing?.id); onClose() } catch (e) { setError(plain(e)) } finally { setBusy('') }
  }
  const remove = async () => {
    if (!editing || !await window.visualLab.ui.confirm('character-remove')) return
    setBusy('delete'); setError('')
    try { await deleteCharacter(editing.id); onClose() } catch (e) { setError(plain(e)) } finally { setBusy('') }
  }
  useEffect(() => { const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }; document.addEventListener('keydown', esc); return () => document.removeEventListener('keydown', esc) }, [onClose])
  return <motion.div className="ml-sheet-back" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
    <motion.section className="ml-sheet" role="dialog" aria-modal="true" aria-label={editing ? t('lab.characters.editTitle', { handle: editing.handle }) : t('lab.characters.new')}
      initial={{ y: 40, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 30, opacity: 0 }} transition={{ type: 'spring', stiffness: 380, damping: 34 }}
      onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); void upload(Array.from(e.dataTransfer.files)) }}>
      <header><h2>{editing ? `@${editing.handle}` : t('lab.characters.new')}</h2><button type="button" className="ml-icon-btn" aria-label={t('lab.characters.close')} onClick={onClose}><X size={18} /></button></header>
      <div className="ml-char-photos">
        {draft.references.map((r, i) => <Photo key={r.sha256 + i} value={r} main={i === 0} onRemove={() => set({ references: draft.references.filter((_, k) => k !== i) })} />)}
        {draft.references.length < 4 && <button type="button" className="ml-char-add" onClick={() => file.current?.click()} disabled={busy === 'upload'}>
          {busy === 'upload' ? <Loader2 size={18} className="ml-spin" /> : <ImagePlus size={18} />}<span>{draft.references.length ? t('lab.characters.anotherPhoto') : t('lab.characters.uploadPhotos')}</span></button>}
      </div>
      <p className="ml-hint">{t('lab.characters.photosHint')}</p>
      <label className="ml-field"><span>{t('lab.characters.name')}</span>
        <input value={draft.name} maxLength={60} placeholder="Ana" onChange={e => set({ name: e.target.value, ...(touched ? {} : { handle: handleOf(e.target.value) }) })} /></label>
      <label className="ml-field"><span>{t('lab.characters.handle')}</span>
        <span className="ml-input-at"><AtSign size={14} /><input value={draft.handle} maxLength={24} placeholder="ana" aria-invalid={!!draft.handle && !/^[a-z0-9_]{2,24}$/.test(draft.handle)}
          onChange={e => { setTouched(true); set({ handle: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '') }) }} /></span>
        <small>{t('lab.characters.handleHint', { handle: draft.handle || t('lab.characters.handleFallback') })}</small></label>
      <label className="ml-field"><span>{t('lab.characters.look')} <em>{t('lab.characters.optional')}</em></span>
        <textarea rows={2} value={draft.description} maxLength={600} placeholder={t('lab.characters.lookPlaceholder')} onChange={e => set({ description: e.target.value })} /></label>
      <label className="ml-field"><span>LoRA <em>{t('lab.characters.optional')}</em></span>
        <select value={draft.lora_id || ''} onChange={e => set({ lora_id: e.target.value || null })}>
          <option value="">{t('lab.characters.noLora')}</option>
          {loras.filter(l => l.status === 'ready').map(l => <option key={l.id} value={l.id}>{l.name} · {l.base ? LORA_BASES[l.base] : ''}</option>)}
        </select>
        <small>{t('lab.characters.loraHint')}</small></label>
      {error && <p className="ml-error" role="alert">{error}</p>}
      <footer>
        {editing && <button type="button" className="ml-btn is-danger" disabled={!!busy} onClick={() => void remove()}><Trash2 size={15} />{t('lab.characters.delete')}</button>}
        <span />
        <button type="button" className="ml-btn" onClick={onClose}>{t('lab.characters.cancel')}</button>
        <button type="button" className="ml-btn is-accent" disabled={!valid || !!busy} onClick={() => void save()}>{busy === 'save' ? <Loader2 size={15} className="ml-spin" /> : null}{t('lab.characters.save')}</button>
      </footer>
      <input ref={file} type="file" accept="image/png,image/jpeg,image/webp" multiple hidden onChange={e => { void upload(Array.from(e.target.files || [])); e.target.value = '' }} />
    </motion.section>
  </motion.div>
}

function LoraRow({ l }: { l: Lora }) {
  const [trigger, setTrigger] = useState(l.trigger)
  const [strength, setStrength] = useState(l.strength)
  const [error, setError] = useState('')
  useEffect(() => { setTrigger(l.trigger); setStrength(l.strength) }, [l.trigger, l.strength])
  const save = (values: { trigger?: string; strength?: number }) => void editLora(l.id, values).catch(e => setError(plain(e)))
  const remove = async () => { if (await window.visualLab.ui.confirm('lora-remove')) await deleteLora(l.id).catch(e => setError(plain(e))) }
  const pct = l.total ? Math.min(100, Math.round((l.bytes || 0) / l.total * 100)) : null
  return <motion.li className={`ml-lora is-${l.status}`} layout initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
    <span className="ml-lora-icon"><SwatchBook size={17} /></span>
    <div className="ml-lora-main">
      <b>{l.name}</b>
      <span className="ml-lora-meta">
        {l.base && <em>{LORA_BASES[l.base]}</em>}
        {l.status === 'ready' && <span>{size(l.bytes)}</span>}
        {l.page && <a href={l.page} target="_blank" rel="noreferrer noopener">{t('lab.loras.source')}<ExternalLink size={11} /></a>}
      </span>
      {l.status === 'downloading' && <span className="ml-lora-bar" aria-label={t('lab.loras.downloading')}><i style={{ width: `${pct ?? 8}%` }} /><small>{pct !== null ? t('lab.loras.progress', { pct, size: size(l.total) }) : t('lab.loras.preparing')}</small></span>}
      {l.status === 'error' && <p className="ml-error">{l.error}</p>}
      {l.status === 'ready' && <div className="ml-lora-edit">
        <label><span>{t('lab.loras.trigger')}</span><input value={trigger} maxLength={300} placeholder={t('lab.loras.triggerPlaceholder')} onChange={e => setTrigger(e.target.value)} onBlur={() => trigger !== l.trigger && save({ trigger })} /></label>
        <label><span>{t('lab.loras.strength')} <b>{strength.toFixed(2)}</b></span><input type="range" min={0.05} max={2} step={0.05} value={strength} onChange={e => setStrength(Number(e.target.value))}
          onPointerUp={() => strength !== l.strength && save({ strength })} onKeyUp={() => strength !== l.strength && save({ strength })} /></label>
      </div>}
      {error && <p className="ml-error" role="alert">{error}</p>}
    </div>
    <button type="button" className="ml-icon-btn" aria-label={t('lab.loras.remove', { name: l.name })} onClick={() => void remove()}><Trash2 size={16} /></button>
  </motion.li>
}

function Loras({ loras, ready }: { loras: Lora[]; ready: boolean }) {
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const add = async () => {
    setBusy(true); setError('')
    try { await addLora(url.trim()); setUrl('') } catch (e) { setError(plain(e)) } finally { setBusy(false) }
  }
  return <section className="ml-section-block">
    <header className="ml-section-head"><h2>LoRAs</h2><span>{t('lab.loras.sub')}</span></header>
    {!ready ? <p className="ml-hint">{t('lab.loras.disabled')}</p> : <>
      <form className="ml-lora-add" onSubmit={e => { e.preventDefault(); if (url.trim()) void add() }}>
        <label className="ml-search"><Link2 size={15} /><input value={url} onChange={e => setUrl(e.target.value)} placeholder={t('lab.loras.urlPlaceholder')} aria-label={t('lab.loras.urlLabel')} maxLength={600} /></label>
        <button type="submit" className="ml-btn is-accent" disabled={busy || !url.trim()}>{busy ? <Loader2 size={15} className="ml-spin" /> : <Plus size={15} />}{t('lab.loras.add')}</button>
      </form>
      <p className="ml-hint">{t('lab.loras.hint')}</p>
      {error && <p className="ml-error" role="alert">{error}</p>}
      {loras.length > 0 && <ul className="ml-loras"><AnimatePresence initial={false}>{loras.map(l => <LoraRow key={l.id} l={l} />)}</AnimatePresence></ul>}
    </>}
  </section>
}

/** Private @characters and the LoRA library they can carry. A photo sent from the lightbox opens a new character with it. */
export default function Characters() {
  const { characters, loras, ready, loaded } = useCharacters()
  const incoming = (useLocation().state as { photo?: ArtifactRef } | null)?.photo
  const [open, setOpen] = useState<Character | CharacterDraft | null>(null)
  const blank = (photo?: ArtifactRef): CharacterDraft => ({ handle: '', name: '', description: '', references: photo ? [photo] : [], lora_id: null })
  useEffect(() => { if (incoming) setOpen(blank(incoming)) }, [incoming?.sha256])
  return <div className="ml-page">
    <header className="ml-page-head">
      <div><small className="ml-kicker">{t('lab.characters.kicker')}</small><h1>{t('lab.tabs.characters')}</h1></div>
      <span className="ml-count">{loaded ? t('lab.characters.count', { count: characters.length }) : '…'}</span>
    </header>
    <p className="ml-lede">{t('lab.characters.ledeBefore')}<b>{t('lab.characters.ledeHandle')}</b>{t('lab.characters.ledeAfter')}</p>
    <div className="ml-char-grid">
      <button type="button" className="ml-char-card is-new" onClick={() => setOpen(blank())}><span className="ml-char-img"><Plus size={26} /></span><span className="ml-char-text"><b>{t('lab.characters.new')}</b><span>{t('lab.characters.newSub')}</span></span></button>
      {characters.map((c, i) => <Card key={c.id} c={c} index={i} onOpen={() => setOpen(c)} />)}
    </div>
    <Loras loras={loras} ready={ready} />
    <AnimatePresence>{open && <Editor key={'id' in open ? open.id : 'new'} initial={open} loras={loras} onClose={() => setOpen(null)} />}</AnimatePresence>
  </div>
}
