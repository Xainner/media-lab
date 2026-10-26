import { createContext, useContext, type ReactNode, type ComponentType } from 'react'
import { t } from '../../i18n'

export type AdvancedProps = { title?: string; children: ReactNode }
// The web shell supplies the presentation through AdvancedRenderer.
export const AdvancedRenderer = createContext<ComponentType<AdvancedProps> | null>(null)
export default function AdvancedOptions({ title = t('shell.advanced.title'), children }: AdvancedProps) {
  const Renderer = useContext(AdvancedRenderer)
  return Renderer ? <Renderer title={title}>{children}</Renderer> : <details className="advanced-options"><summary>{title}</summary>{children}</details>
}
