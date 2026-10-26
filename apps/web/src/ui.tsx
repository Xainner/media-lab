import { useEffect, useState, type ReactNode } from 'react'
import { AlertCircle, CheckCircle2, Sparkles } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './components/animate-ui/components/radix/dialog'
import { Brand as Lockup, Emblem } from './brand/Logo'
export type Pose = string
import { WordReveal } from './motion/effects'
import { catalogs, t, type MessageKey } from './i18n'

export { Button } from './components/animate-ui/components/buttons/button'
export { Progress } from './components/animate-ui/components/radix/progress'

export function Brand() { return <Lockup /> }

export function Notice({ error, success }: { error?: string; success?: string }) { return error || success ? <div role={error ? 'alert' : 'status'} className={`notice ${error ? 'is-error' : 'is-success'}`}>{error ? <AlertCircle size={18} /> : <CheckCircle2 size={18} />}<span>{error || success}</span></div> : null }

export function Loading({ label = t('common.loading') }: { label?: string }) { return <div className="loading-state" role="status"><span className="loading-orbit"><Emblem size={34} /></span>{label}</div> }

// `pose` is kept for callers written for the old mascot; empty states now show the Lab glyph.
export function Empty({ title = t('common.emptyTitle'), children }: { title?: string; children?: ReactNode; pose?: Pose }) {
  return <div className="empty"><span className="empty-glyph" aria-hidden="true"><Sparkles size={22} /></span><h3>{title}</h3><p>{children || t('common.emptyBody')}</p></div>
}

/** Section hero: plate art behind, eyebrow, revealed title, optional chibi and action. */
const LAB_PLATE: Record<string, string> = { home: 'app-agent', image: 'model-image', edit: 'app-character', video: 'model-video', music: 'model-music', director: 'model-director' }

export function PageHeading({ eyebrow, title, children, action, plate, chibi }: { eyebrow: string; title: string; children?: ReactNode; action?: ReactNode; plate?: string; chibi?: Pose }) {
  return <header className={`page-heading ${plate ? 'has-plate' : ''} ${action ? 'has-action' : ''}`}>
    {plate && <img className="page-plate" src={`/art/lab/${LAB_PLATE[plate] || 'feed-alley'}.webp`} alt="" aria-hidden="true" />}
    <div className="page-heading-copy">
      <p className="eyebrow"><Sparkles size={12} /> {eyebrow}</p>
      <WordReveal as="h1" text={title} />
      {children && <p className="page-lede">{children}</p>}
    </div>
    {action && <div className="page-action">{action}</div>}
  </header>
}

export function Modal({ open, onOpenChange, title, description, children }: { open: boolean; onOpenChange: (open: boolean) => void; title: string; description: string; children: ReactNode }) { return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="rvl app-dialog"><DialogHeader><DialogTitle>{title}</DialogTitle><DialogDescription>{description}</DialogDescription></DialogHeader>{children}</DialogContent></Dialog> }

export const statusLabel = (s: string) => { const key = `common.status.${s}` as MessageKey; return key in catalogs.es ? t(key) : s }

export function Badge({ status }: { status: string }) { return <span className={`status-badge status-${status}`}>{statusLabel(status)}</span> }

export function MediaThumb({ media }: { media: { uri: string; sha256: string } }) {
 const [src,setSrc] = useState('')
 useEffect(() => { let live = true; setSrc(''); void window.visualLab.runtime.preview(media).then(v => { if(live) setSrc(v) }).catch(() => {}); return () => { live = false } }, [media.uri,media.sha256])
 return src ? <img src={src} alt={t('common.preview')} loading="lazy" /> : <div className="thumb-placeholder"><Sparkles size={22} /></div>
}

/** Glass panel; `lit` adds the cursor spotlight border. */
export function Panel({ children, className = '', as: Tag = 'section', ...rest }: { children: ReactNode; className?: string; as?: 'section' | 'div' | 'article' | 'aside' } & Record<string, any>) {
  return <Tag className={`panel glass ${className}`} {...rest}>{children}</Tag>
}
