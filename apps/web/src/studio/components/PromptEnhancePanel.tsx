import { useState } from 'react'
import { type ArtifactRef, type ImproveMode } from '../lib/api'

type Proposal = { source: string; prompt: string; lyrics?: string; aspectRatio?: string }

const SENT: Record<ImproveMode, string> = {
  t2i: 'el prompt',
  i2i: 'el prompt y las previews numeradas de las referencias si admite visión',
  t2v: 'el prompt y la duración',
  i2v: 'el prompt, la duración y las previews de los fotogramas inicial y final si admite visión',
  r2v: 'el prompt, la duración y las previews numeradas de las imágenes de referencia si admite visión',
  moss: 'el prompt',
  kandinsky: 'la escena, la voz y los sonidos, y la preview del primer fotograma si admite visión',
  song: 'el estilo y la letra',
  ace_song: 'la idea y la letra',
}

export default function PromptEnhancePanel({ prompt, onAccept, onLyrics, mode, references = [], seconds, needsReferences = mode === 'i2i' || mode === 'i2v', onAspectRatio }: {
  prompt: string
  onAccept: (value: string) => void
  onLyrics?: (value: string) => void
  mode: ImproveMode
  references?: ArtifactRef[]
  seconds?: number
  needsReferences?: boolean
  onAspectRatio?: (value: string) => void
}) {
  const [busy, setBusy] = useState(false)
  const [proposals, setProposals] = useState<Proposal[]>([])
  const [errors, setErrors] = useState<string[]>([])
  const blocked = !prompt.trim() || busy || (needsReferences && !references.length)

  async function compare() {
    if (blocked) return
    setBusy(true); setProposals([]); setErrors([])
    const exact = prompt.trim()
    const next: Proposal[] = []
    const failures: string[] = []
    try {
      const value = await window.visualLab.agent.improve(exact, mode, references, seconds)
      next.push({ source: 'Proveedor externo', prompt: value.prompt, lyrics: value.lyrics })
    } catch (error: any) { failures.push(`Proveedor externo: ${error.message || error}`) }
    setProposals(next); setErrors(failures); setBusy(false)
  }

  return <div className="prompt-enhance">
    <button type="button" className="ghost" onClick={() => void compare()} disabled={blocked}>
      {busy ? 'PREPARANDO PROPUESTA…' : 'PROPONER MEJORA EXTERNA'}
    </button>
    <p className="privacy">Sólo al pulsar: el proveedor externo recibe {SENT[mode]}. Ninguna propuesta se usa sin tu aceptación.</p>
    {errors.map((error, index) => <p className="error" key={index}>{error}</p>)}
    {proposals.map((proposal, index) => <div className="proposal inline-proposal" key={`${proposal.source}:${index}`}>
      <label>{proposal.source.toUpperCase()}{proposal.aspectRatio ? ` · SUGIERE ${proposal.aspectRatio}` : ''}</label>
      {mode === 'song' ? <>
        <small>Estilo</small><p className="proposal-text">{proposal.prompt}</p>
        {proposal.lyrics && <><small>Letra</small><p className="proposal-text">{proposal.lyrics}</p></>}
      </> : <p className="proposal-text">{proposal.prompt}</p>}
      <button type="button" className="primary" onClick={() => {
        onAccept(proposal.prompt)
        if (proposal.lyrics !== undefined && onLyrics) onLyrics(proposal.lyrics)
        if (proposal.aspectRatio && onAspectRatio) onAspectRatio(proposal.aspectRatio)
        setProposals([])
      }}>ACEPTAR ESTA PROPUESTA</button>
    </div>)}
  </div>
}
