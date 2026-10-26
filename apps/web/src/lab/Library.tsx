import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { LayoutGroup, motion } from 'motion/react'
import { Loader2, Search } from 'lucide-react'
import { Masonry } from './Canvas'
import { useLibrary } from './live'
import type { Art } from './data'
import { t, type MessageKey } from '../i18n'

const kinds: [string, MessageKey][] = [['', 'composer.library.kind.all'], ['images', 'composer.library.kind.images'], ['videos', 'composer.library.kind.videos'], ['songs', 'composer.library.kind.songs'],
  ['productions', 'composer.library.kind.productions'], ['references', 'composer.library.kind.references'], ['sources', 'composer.library.kind.sources']]

/** Everything the viewer made or uploaded, as one filterable canvas. /gallery opens it on images. */
export default function Library({ onOpen, initialKind = '' }: { onOpen: (a: Art) => void; initialKind?: string }) {
  const [kind, setKind] = useState(initialKind)
  const [text, setText] = useState('')
  const [query, setQuery] = useState('')
  useEffect(() => setKind(initialKind), [initialKind])
  // Search as the viewer types, without a request per keystroke.
  useEffect(() => { const timer = setTimeout(() => setQuery(text.trim()), 320); return () => clearTimeout(timer) }, [text])
  const { items, total, busy, error, more } = useLibrary(kind, query)
  return <div className="ml-page">
    <header className="ml-page-head">
      <div><small className="ml-kicker">{t('composer.library.kicker')}</small><h1>{t('composer.library.title')}</h1></div>
      <span className="ml-count">{busy && !items.length ? '…' : t('composer.library.count', { count: total })}</span>
    </header>
    <div className="ml-toolbar">
      <label className="ml-search"><Search size={15} /><input value={text} onChange={e => setText(e.target.value)} placeholder={t('composer.library.searchPlaceholder')} aria-label={t('composer.library.searchLabel')} maxLength={1000} /></label>
      <LayoutGroup><div className="ml-pills" role="group" aria-label={t('composer.library.kindLabel')}>{kinds.map(([value, label]) => <button key={value} type="button" aria-pressed={kind === value} className={kind === value ? 'is-on' : ''} onClick={() => setKind(value)}>
        {kind === value && <motion.span layoutId="ml-pill" className="ml-tab-pill" transition={{ type: 'spring', stiffness: 420, damping: 34 }} />}<span>{t(label)}</span></button>)}</div></LayoutGroup>
    </div>
    {error && <p className="ml-error" role="alert">{error}</p>}
    {!busy && !error && !items.length ? <div className="ml-blank">
      <h2>{t(query || kind ? 'composer.library.noResults' : 'composer.library.empty')}</h2>
      <p>{t(query || kind ? 'composer.library.noResultsHint' : 'composer.library.emptyHint')}</p>
      {!query && !kind && <Link to="/image" className="ml-btn is-accent">{t('composer.library.createFirst')}</Link>}
    </div> : <Masonry items={items} onOpen={onOpen} />}
    {(more || (busy && items.length > 0)) && <div className="ml-more-row"><button type="button" className="ml-btn" disabled={busy} onClick={() => more?.()}>{busy ? <><Loader2 size={15} className="ml-spin" />{t('composer.library.loading')}</> : t('composer.library.loadMore')}</button></div>}
  </div>
}
