import { useEffect, useState } from 'react'
import type { ArtifactRef } from '../lib/api'
import { t } from '../../i18n'

type Props = {
  media: ArtifactRef
  operation?: 'generate' | 'edit'
  seed?: number
  compact?: boolean
}

export default function ExportActions({ media, operation = 'generate', seed, compact = false }: Props) {
  const [settings, setSettings] = useState<ExportSettings | null>(null)
  const [open, setOpen] = useState(false)
  const [format, setFormat] = useState<ExportFormat>('png')
  const [quality, setQuality] = useState(92)
  const [background, setBackground] = useState('#ffffff')
  const [busy, setBusy] = useState(false)
  const [savedPath, setSavedPath] = useState('')
  const [error, setError] = useState('')
  const web = window.visualLab.platform === 'web'
  const [downloadRequested, setDownloadRequested] = useState(false)

  useEffect(() => {
    setOpen(false)
    setSavedPath('')
    setDownloadRequested(false)
    setError('')
  }, [media.uri, media.sha256])

  async function toggleOpen() {
    const next = !open
    setOpen(next)
    if (!next) return
    try {
      const value = await window.visualLab.export.getSettings()
      setSettings(value)
      setFormat(value.format)
      setQuality(value.format === 'webp' ? value.webpQuality : value.jpegQuality)
      setBackground(value.jpegBackground)
    } catch (error: any) { setError(error.message) }
  }

  function chooseFormat(next: ExportFormat) {
    setFormat(next)
    if (settings) setQuality(next === 'webp' ? settings.webpQuality : settings.jpegQuality)
  }

  async function saveAs() {
    setBusy(true); setError(''); setSavedPath('')
    try {
      const result = await window.visualLab.export.saveAs({
        media, operation, seed, format, quality, background,
      })
      if (!result.cancelled && result.path) { setSavedPath(result.path); setOpen(false) }
      if (web && !result.cancelled) { setDownloadRequested(true); setOpen(false) }
    } catch (error: any) { setError(error.message) }
    finally { setBusy(false) }
  }

  async function quickSave() {
    setBusy(true); setError(''); setSavedPath('')
    try {
      const result = await window.visualLab.export.quickSave({ media, operation, seed })
      if (!result.cancelled && result.path) setSavedPath(result.path)
      if (web && !result.cancelled) setDownloadRequested(true)
    } catch (error: any) { setError(error.message) }
    finally { setBusy(false) }
  }

  return <div className={`export-block ${compact ? 'compact' : ''}`}>
    <div className="export-buttons">
      <button type="button" className="ghost" onClick={() => void toggleOpen()} disabled={busy}>
        {open ? t('shell.export.close') : web ? t('shell.export.formatQuality') : t('shell.export.saveAs')}
      </button>
      <button type="button" className="primary" onClick={quickSave} disabled={busy}>
        {busy ? (web ? t('shell.export.preparing') : t('shell.export.saving')) : web ? t('shell.export.download') : t('shell.export.quickSave')}
      </button>
    </div>
    {open && <div className="export-options">
      <div><label>{t('shell.export.fileFormat')}</label><select value={format} onChange={event => chooseFormat(event.target.value as ExportFormat)}>
        <option value="png">{t('shell.export.png')}</option>
        <option value="jpeg">{t('shell.export.jpeg')}</option>
        <option value="webp">{t('shell.export.webp')}</option>
      </select></div>
      {format !== 'png' && <div><label>{t('shell.export.quality', { quality })}</label><input type="range" min="1" max="100" value={quality} onChange={event => setQuality(Number(event.target.value))} /></div>}
      {format === 'jpeg' && <div className="jpeg-background">
        <label>{t('shell.export.jpegBackground')}</label>
        <div><button type="button" onClick={() => setBackground('#ffffff')}>{t('shell.export.white')}</button><button type="button" onClick={() => setBackground('#000000')}>{t('shell.export.black')}</button><input aria-label={t('shell.export.backgroundColor')} type="color" value={background} onChange={event => setBackground(event.target.value)} /></div>
        {media.has_alpha && <p className="warning">{t('shell.export.alphaWarning')}</p>}
      </div>}
      <button type="button" className="primary" onClick={saveAs} disabled={busy}>{web ? t('shell.export.downloadFile') : t('shell.export.chooseDestination')}</button>
    </div>}
    {savedPath && <div className="save-confirmation"><span>{t('shell.export.savedIn')} <code>{savedPath}</code></span><button type="button" onClick={() => window.visualLab.export.showInFolder(savedPath)}>{t('shell.export.showInFolder')}</button></div>}
    {web && downloadRequested && <p className="save-confirmation">{t('shell.export.downloadRequested')}</p>}
    {error && <p className="error">{error}</p>}
  </div>
}
