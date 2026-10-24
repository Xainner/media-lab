import { useEffect, useState } from 'react'
import { dataUrl, type ArtifactRef } from '../lib/api'
import ExportActions from './ExportActions'
import { RevealImage, useAnimationMode } from './GenerationCanvas'

export default function ArtifactResult({ media, meta, operation = 'generate', fresh = false }: {
  media: ArtifactRef | null
  meta?: any
  operation?: 'generate' | 'edit'
  fresh?: boolean
}) {
  const [src, setSrc] = useState('')
  const animation = useAnimationMode()
  useEffect(() => {
    setSrc('')
    if (media) dataUrl(media.uri).then(setSrc).catch(() => setSrc(''))
  }, [media?.uri])
  if (!media) return null
  return (
    <div className="result-card">
      <div className="checker">{src ? <RevealImage key={media.uri} src={src} alt="Resultado generado" animate={fresh && animation !== 'off'} /> : <div className="loading">Cargando artefacto…</div>}</div>
      <div className="result-meta">
        <span>{media.width}×{media.height}</span>
        <span>{media.has_alpha ? 'RGBA' : 'RGB'}</span>
        {meta?.seed !== undefined && <span>seed {meta.seed}</span>}
        {meta?.model_variant === 'turbo' && <span>TURBO · 8 pasos</span>}
        {meta?.model_precision && <span>{String(meta.model_precision).toUpperCase()}</span>}
        {meta?.generation_ms && <span>{(meta.generation_ms / 1000).toFixed(1)} s</span>}
      </div>
      <code className="uri">{media.uri}</code>
      <ExportActions key={`${media.uri}:${media.sha256}`} media={media} operation={operation} seed={meta?.seed} />
    </div>
  )
}
