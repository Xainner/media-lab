import { useState } from 'react'
import { type ArtifactRef, type ImproveMode } from '../lib/api'
import { t, type MessageKey } from '../../i18n'

type Proposal = { source: string; prompt: string; lyrics?: string; aspectRatio?: string }

const SENT: Record<ImproveMode, MessageKey> = {
  t2i: 'shell.enhance.sent.t2i',
  i2i: 'shell.enhance.sent.i2i',
  t2v: 'shell.enhance.sent.t2v',
  i2v: 'shell.enhance.sent.i2v',
  r2v: 'shell.enhance.sent.r2v',
  moss: 'shell.enhance.sent.t2i',
  kandinsky: 'shell.enhance.sent.kandinsky',
  song: 'shell.enhance.sent.song',
  ace_song: 'shell.enhance.sent.aceSong',
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
      next.push({ source: t('shell.enhance.external'), prompt: value.prompt, lyrics: value.lyrics })
    } catch (error: any) { failures.push(t('shell.enhance.failure', { message: String(error.message || error) })) }
    setProposals(next); setErrors(failures); setBusy(false)
  }

  return <div className="prompt-enhance">
    <button type="button" className="ghost" onClick={() => void compare()} disabled={blocked}>
      {busy ? t('shell.enhance.preparing') : t('shell.enhance.propose')}
    </button>
    <p className="privacy">{t('shell.enhance.privacy', { sent: t(SENT[mode]) })}</p>
    {errors.map((error, index) => <p className="error" key={index}>{error}</p>)}
    {proposals.map((proposal, index) => <div className="proposal inline-proposal" key={`${proposal.source}:${index}`}>
      <label>{proposal.source.toUpperCase()}{proposal.aspectRatio ? t('shell.enhance.suggests', { ratio: proposal.aspectRatio }) : ''}</label>
      {mode === 'song' ? <>
        <small>{t('shell.enhance.style')}</small><p className="proposal-text">{proposal.prompt}</p>
        {proposal.lyrics && <><small>{t('shell.enhance.lyrics')}</small><p className="proposal-text">{proposal.lyrics}</p></>}
      </> : <p className="proposal-text">{proposal.prompt}</p>}
      <button type="button" className="primary" onClick={() => {
        onAccept(proposal.prompt)
        if (proposal.lyrics !== undefined && onLyrics) onLyrics(proposal.lyrics)
        if (proposal.aspectRatio && onAspectRatio) onAspectRatio(proposal.aspectRatio)
        setProposals([])
      }}>{t('shell.enhance.accept')}</button>
    </div>)}
  </div>
}
