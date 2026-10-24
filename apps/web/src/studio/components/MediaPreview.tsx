import { useEffect, useState } from 'react'
import type { ArtifactRef } from '../lib/api'

export default function MediaPreview({ media, label = 'Vista previa', playable = false }: { media: ArtifactRef; label?: string; playable?: boolean }) {
  const [src, setSrc] = useState('')
  const image = /\/(images|references)\//.test(media.uri)
  const audio = /\.(flac|wav|mp3|opus|ogg)$/i.test(media.uri)
  useEffect(() => {
    let live = true
    setSrc('')
    const value = image ? window.visualLab.runtime.preview(media) : window.visualLab.runtime.mediaUrl(media.uri)
    void value.then(url => { if (live) setSrc(url) }).catch(() => {})
    return () => { live = false }
  }, [media.uri, media.sha256])
  if (image) return src ? <img className="media-preview" src={src} loading="lazy" alt={label} /> : <div className="media-preview-placeholder">✦</div>
  if (audio) return playable && src ? <audio aria-label={label} controls preload="metadata" src={src} /> : <div className="media-preview-placeholder">♫<span>Música</span></div>
  return src ? <video className="media-preview" src={src} controls={playable} muted={!playable} preload="metadata" aria-label={label} /> : <div className="media-preview-placeholder">▶<span>Vídeo</span></div>
}
