import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { useMagnetic, useSpotlight } from '../../motion/effects'
import { Sparkles } from 'lucide-react'
import type { Pose } from '../../ui'

/** Tool layout: the console (controls) and the stage (output). */
export function Tool({ console, stage, wide = false }: { console: ReactNode; stage: ReactNode; wide?: boolean }) {
  const spot = useSpotlight<HTMLElement>()
  return <div className={`tool ${wide ? 'is-wide' : ''}`}>
    <section ref={spot} className="console glass lit">{console}</section>
    <section className="stage" aria-live="polite">{stage}</section>
  </div>
}

/** Numbered console step. */
export function Step({ n, title, hint, children, aside }: { n: string; title: string; hint?: ReactNode; children: ReactNode; aside?: ReactNode }) {
  return <div className="step">
    <div className="step-head"><span className="step-n">{n}</span><h3>{title}</h3>{aside && <span className="step-aside">{aside}</span>}</div>
    {hint && <p className="hint step-hint">{hint}</p>}
    <div className="step-body">{children}</div>
  </div>
}

/** Segmented choice built from real buttons (keeps accessible names). */
export function Segmented<T extends string>({ value, options, onChange, label }: { value: T; options: { value: T; label: string; hint?: string; disabled?: boolean }[]; onChange: (v: T) => void; label?: string }) {
  return <div className="segmented" role="group" aria-label={label}>
    {options.map(o => <button key={o.value} type="button" className={value === o.value ? 'is-on' : ''} aria-pressed={value === o.value} disabled={o.disabled} onClick={() => onChange(o.value)}>{o.label}{o.hint && <small>{o.hint}</small>}</button>)}
  </div>
}

/** The big glowing action at the end of a console. */
export function Action({ children, className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  const ref = useMagnetic<HTMLButtonElement>(.22)
  return <button ref={ref} className={`primary action ${className}`} {...props}><span className="action-shine" aria-hidden="true" />{children}</button>
}

export function Actions({ children, note }: { children: ReactNode; note?: ReactNode }) {
  return <div className="actions">{children}{note && <p className="hint">{note}</p>}</div>
}

/** Stage placeholder that hints what will happen here. */
export function EmptyStage({ title, children }: { pose: Pose; title: string; children?: ReactNode }) {
  return <div className="empty-stage"><div className="empty-stage-glow" /><span className="empty-glyph" aria-hidden="true"><Sparkles size={22} /></span><b>{title}</b>{children && <span>{children}</span>}</div>
}
