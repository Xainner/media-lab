import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { LayoutGroup, motion } from 'motion/react'
import { Loader2, Search } from 'lucide-react'
import { Masonry } from './Canvas'
import { useLibrary } from './live'
import type { Art } from './data'

const kinds: [string, string][] = [['', 'Todo'], ['images', 'Imágenes'], ['videos', 'Vídeos'], ['songs', 'Audio'], ['productions', 'Videoclips'], ['references', 'Referencias'], ['sources', 'Audio subido']]

/** Everything the viewer made or uploaded, as one filterable canvas. /gallery opens it on images. */
export default function Library({ onOpen, initialKind = '' }: { onOpen: (a: Art) => void; initialKind?: string }) {
  const [kind, setKind] = useState(initialKind)
  const [text, setText] = useState('')
  const [query, setQuery] = useState('')
  useEffect(() => setKind(initialKind), [initialKind])
  // Search as the viewer types, without a request per keystroke.
  useEffect(() => { const t = setTimeout(() => setQuery(text.trim()), 320); return () => clearTimeout(t) }, [text])
  const { items, total, busy, error, more } = useLibrary(kind, query)
  return <div className="ml-page">
    <header className="ml-page-head">
      <div><small className="ml-kicker">Tu espacio</small><h1>Biblioteca</h1></div>
      <span className="ml-count">{busy && !items.length ? '…' : `${total} ${total === 1 ? 'archivo' : 'archivos'}`}</span>
    </header>
    <div className="ml-toolbar">
      <label className="ml-search"><Search size={15} /><input value={text} onChange={e => setText(e.target.value)} placeholder="Buscar por prompt, título o estilo" aria-label="Buscar en la biblioteca" maxLength={1000} /></label>
      <LayoutGroup><div className="ml-pills" role="group" aria-label="Tipo de archivo">{kinds.map(([value, label]) => <button key={value} type="button" aria-pressed={kind === value} className={kind === value ? 'is-on' : ''} onClick={() => setKind(value)}>
        {kind === value && <motion.span layoutId="ml-pill" className="ml-tab-pill" transition={{ type: 'spring', stiffness: 420, damping: 34 }} />}<span>{label}</span></button>)}</div></LayoutGroup>
    </div>
    {error && <p className="ml-error" role="alert">{error}</p>}
    {!busy && !error && !items.length ? <div className="ml-blank">
      <h2>{query || kind ? 'Nada por aquí' : 'Tu biblioteca está vacía'}</h2>
      <p>{query || kind ? 'Prueba otra búsqueda o cambia el filtro.' : 'Todo lo que crees o subas aparece aquí.'}</p>
      {!query && !kind && <Link to="/image" className="ml-btn is-accent">Crear mi primera imagen</Link>}
    </div> : <Masonry items={items} onOpen={onOpen} />}
    {(more || (busy && items.length > 0)) && <div className="ml-more-row"><button type="button" className="ml-btn" disabled={busy} onClick={() => more?.()}>{busy ? <><Loader2 size={15} className="ml-spin" />Cargando</> : 'Cargar más'}</button></div>}
  </div>
}
