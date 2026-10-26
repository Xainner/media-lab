import { Fragment, useEffect, useState, type ReactNode } from 'react'
import { Cable, Check, Copy, KeyRound, Plus, RefreshCw, ShieldCheck, Sparkles, Trash2 } from 'lucide-react'
import { api } from './bridge'
import { Badge, Loading, Modal, Notice, PageHeading } from './ui'
import { formatDateTime, t, type MessageKey } from './i18n'

type Token = { id: string; label: string; scopes: string[]; created_at: number; expires_at: number; last_used_at: number | null; revoked_at: number | null }
type Connection = { enabled: boolean; endpoint: string; items: Token[] }
const permissions: { id: string; label: MessageKey; detail: MessageKey }[] = [
 { id: 'read', label: 'connect.mcp.perm.readLabel', detail: 'connect.mcp.perm.readDetail' },
 { id: 'create', label: 'connect.mcp.perm.createLabel', detail: 'connect.mcp.perm.createDetail' },
 { id: 'agent', label: 'connect.mcp.perm.agentLabel', detail: 'connect.mcp.perm.agentDetail' },
 { id: 'delete', label: 'connect.mcp.perm.deleteLabel', detail: 'connect.mcp.perm.deleteDetail' },
]
/** English brief an agent can keep in its instructions; never includes the token. */
export const agentBrief = (endpoint: string) => `Media Lab is a remote MCP server at ${endpoint} (Streamable HTTP, Bearer token configured in the client).
Every model and GPU runs on the server: install nothing locally. Connect only to that https URL, even on the same network.
Start with the capabilities and prompt_guide tools, then follow the model guides.
Sending local files: call create_uploads with one entry per file, upload each with
  curl -sS -T ./file.ext "<url>"
and pass the returned reference {uri, sha256} to the creation tools. Send as many references as capabilities.inputs.references allows.
Creation tools take {"body": {...}, "idempotency_key": "..."}; the tool schemas describe every field.
Getting results: call wait_for_job (repeat while still_running; with an MCP progressToken one call can wait up to 10 minutes and streams progress); each output comes with a 1-hour url:
  curl -sS -o ./result.ext "<url>"   (the X-Content-SHA256 header matches the output's sha256)
artifact:// URIs are identifiers inside the studio, not local files: your own file or artifact tools cannot open them. View with inspect_media, download with the links (get_download_links for any owned file).
If a call is rejected, read the reason, fix it and submit again. Do not use the HTTP API, SSH or local scripts: the MCP tools cover everything.
Never put the MCP token in prompts, URLs or files, and never share transfer links.`
const date = (value: number) => formatDateTime(value, { dateStyle: 'medium', timeStyle: 'short' })
/** Places inline markup where a translated sentence has `{slot}` placeholders. */
const rich = (text: string, slots: Record<string, ReactNode>) => text.split(/(\{\w+\})/).map((part, i) => { const slot = /^\{(\w+)\}$/.exec(part)?.[1]; return <Fragment key={i}>{slot && slot in slots ? slots[slot] : part}</Fragment> })

export default function Mcp({ current }: { current: { totp_enabled: boolean } }) {
 const [connection, setConnection] = useState<Connection | null>(null)
 const [busy, setBusy] = useState(false), [error, setError] = useState(''), [success, setSuccess] = useState('')
 const [editor, setEditor] = useState(false), [rotation, setRotation] = useState<Token | null>(null)
 const [label, setLabel] = useState(''), [days, setDays] = useState('90'), [scopes, setScopes] = useState(['read', 'create', 'agent'])
 const [password, setPassword] = useState(''), [code, setCode] = useState(''), [secret, setSecret] = useState(''), [showSecret, setShowSecret] = useState(false)
 const [confirmation, setConfirmation] = useState<Token | 'disable' | null>(null)
 async function load() { setConnection(await api('GET', '/v1/account/mcp')) }
 useEffect(() => { let live = true; void api('GET', '/v1/account/mcp').then(v => { if (live) setConnection(v) }).catch(e => { if (live) setError(String(e)) }); return () => { live = false } }, [])
 async function act(action: () => Promise<void>, message: string) {
  setBusy(true); setError(''); setSuccess('')
  try { await action(); await load(); setSuccess(message) } catch (e) { setError(String(e)) } finally { setBusy(false) }
 }
 async function copy(value: string) { try { await navigator.clipboard.writeText(value); setSuccess(t('connect.mcp.copied')); setError('') } catch { setError(t('connect.mcp.copyFailed')) } }
 function openEditor(token: Token | null = null) {
  setRotation(token); setLabel(token?.label || t('connect.mcp.defaultLabel')); setDays('90'); setScopes(token?.scopes || ['read', 'create', 'agent']); setPassword(''); setCode(''); setEditor(true); setError(''); setSuccess('')
 }
 async function mint() {
  await act(async () => {
   const value = await api('POST', rotation ? `/v1/account/mcp/tokens/${rotation.id}/rotate` : '/v1/account/mcp/tokens', { label, days: Number(days), scopes, password, code })
   setPassword(''); setCode(''); setEditor(false); setSecret(value.token); setShowSecret(false)
  }, rotation ? t('connect.mcp.tokenReplaced') : t('connect.mcp.tokenCreated'))
 }
 function downloadConfig() {
  if (!connection || !secret) return
  const blob = new Blob([JSON.stringify({ mcpServers: { 'media-lab': { type: 'http', url: connection.endpoint, headers: { Authorization: `Bearer ${secret}` } } } }, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob), link = document.createElement('a'); link.href = url; link.download = 'rinari-mcp.json'; link.click(); URL.revokeObjectURL(url)
 }
 if (!connection) return <><Notice error={error}/><Loading/></>
 return <>
  <PageHeading eyebrow={t('connect.mcp.eyebrow')} title={t('connect.mcp.title')}>{t('connect.mcp.intro')}</PageHeading>
  <Notice error={!editor && !secret ? error : ''} success={!secret ? success : ''}/>
  <section className="mcp-hero panel">
   <div className="mcp-mark"><Cable size={34}/></div><div><h2>{t('connect.mcp.hero.title')}</h2><p className="muted">{t('connect.mcp.hero.text')}</p><Badge status={connection.enabled ? 'enabled' : 'disabled'}/></div>
   <button disabled={busy} className={connection.enabled ? 'ghost' : 'primary'} onClick={() => connection.enabled ? setConfirmation('disable') : void act(async () => { await api('PUT', '/v1/account/mcp', { enabled: true }) }, t('connect.mcp.enabledNotice'))}>{connection.enabled ? t('connect.mcp.disable') : t('connect.mcp.enable')}</button>
  </section>
  <div className="mcp-layout"><section className="panel settings-panel"><p className="eyebrow"><Cable size={15}/> {t('connect.mcp.setup.eyebrow')}</p><h2>{t('connect.mcp.setup.title')}</h2><ol className="mcp-steps"><li><b>{t('connect.mcp.setup.step1Title')}</b><p>{rich(t('connect.mcp.setup.step1Text'), { transport: <strong>Streamable HTTP</strong> })}</p></li><li><b>{t('connect.mcp.setup.step2Title')}</b><label>{t('connect.mcp.setup.serverUrl')}<div className="mcp-copy"><input readOnly value={connection.endpoint} aria-label={t('connect.mcp.setup.serverUrlAria')}/><button aria-label={t('connect.mcp.setup.copyUrl')} onClick={() => void copy(connection.endpoint)}><Copy size={16}/></button></div></label><p>{t('connect.mcp.setup.step2Text')}</p></li><li><b>{t('connect.mcp.setup.step3Title')}</b><p>{rich(t('connect.mcp.setup.step3Text'), { header: <code>Authorization</code>, bearer: <code>Bearer</code> })}</p></li><li><b>{t('connect.mcp.setup.step4Title')}</b><p>{t('connect.mcp.setup.step4Text')}</p></li><li><b>{t('connect.mcp.setup.step5Title')}</b><p>{rich(t('connect.mcp.setup.step5Text'), { uploads: <code>create_uploads</code>, curl: <code>curl -T</code>, downloads: <code>get_download_links</code> })}</p></li></ol><div className="mcp-brief"><div><b>{t('connect.mcp.brief.title')}</b><button aria-label={t('connect.mcp.brief.copyAria')} onClick={() => void copy(agentBrief(connection.endpoint))}><Copy size={15}/> {t('connect.mcp.brief.copy')}</button></div><p className="muted">{t('connect.mcp.brief.hint')}</p><pre>{agentBrief(connection.endpoint)}</pre></div><p className="muted">{t('connect.mcp.setup.personalNote')}</p></section>
  <section className="panel settings-panel"><p className="eyebrow"><Sparkles size={15}/> {t('connect.mcp.features.eyebrow')}</p><h2>{t('connect.mcp.features.title')}</h2><div className="mcp-features">{(['image', 'video', 'director', 'library', 'files'] as const).map(area => <div key={area}><Check size={16}/><span><b>{t(`connect.mcp.features.${area}Title`)}</b><p>{t(`connect.mcp.features.${area}Detail`)}</p></span></div>)}</div><div className="mcp-privacy"><ShieldCheck size={22}/><p>{t('connect.mcp.features.privacy')}</p></div><p className="muted">{t('connect.mcp.features.guideNote')}</p></section></div>
  <div className="section-title"><div><h2>{t('connect.mcp.tokens.title')}</h2><p className="muted">{t('connect.mcp.tokens.subtitle')}</p></div><div className="button-row"><button aria-label={t('connect.mcp.tokens.refresh')} disabled={busy} onClick={() => void act(load, t('connect.mcp.tokens.refreshed'))}><RefreshCw size={16}/></button><button className="primary" disabled={busy || !connection.enabled} onClick={() => openEditor()}><Plus size={17}/> {t('connect.mcp.tokens.create')}</button></div></div>
  <div className="mcp-token-list">{connection.items.length ? connection.items.map(token => {
   const status = token.revoked_at ? 'revoked' : token.expires_at <= Date.now()/1000 ? 'expired' : 'enabled'
   return <article className="panel mcp-token" key={token.id}><div className="mcp-token-heading"><KeyRound size={20}/><h3>{token.label}</h3><Badge status={status}/></div><div className="mcp-permissions">{token.scopes.map(scope => <span className="pill" key={scope}>{(label => label ? t(label) : scope)(permissions.find(p => p.id === scope)?.label)}</span>)}</div><dl><div><dt>{t('connect.mcp.tokens.created')}</dt><dd>{date(token.created_at)}</dd></div><div><dt>{t('connect.mcp.tokens.expires')}</dt><dd>{date(token.expires_at)}</dd></div><div><dt>{t('connect.mcp.tokens.lastUsed')}</dt><dd>{token.last_used_at ? date(token.last_used_at) : t('connect.mcp.tokens.neverUsed')}</dd></div></dl>{status === 'enabled' && <div className="button-row"><button disabled={busy || !connection.enabled} onClick={() => openEditor(token)}><RefreshCw size={15}/> {t('connect.mcp.tokens.replace')}</button><button className="danger ghost" disabled={busy} onClick={() => setConfirmation(token)}><Trash2 size={15}/> {t('connect.mcp.tokens.revoke')}</button></div>}</article>
  }) : <div className="panel mcp-empty"><KeyRound size={28}/><h3>{t('connect.mcp.empty.title')}</h3><p className="muted">{t('connect.mcp.empty.text')}</p></div>}</div>
  <Modal open={editor} onOpenChange={open => { if (!busy) { setEditor(open); if (!open) { setPassword(''); setCode('') } } }} title={rotation ? t('connect.mcp.editor.replaceTitle') : t('connect.mcp.editor.createTitle')} description={rotation ? t('connect.mcp.editor.replaceDescription') : t('connect.mcp.editor.createDescription')}>
   <Notice error={error}/><form onSubmit={e => { e.preventDefault(); void mint() }}><label>{t('connect.mcp.editor.clientName')}<input value={label} onChange={e => setLabel(e.target.value)} maxLength={80} required disabled={busy}/></label><label>{t('connect.mcp.editor.expiry')}<select value={days} onChange={e => setDays(e.target.value)} disabled={busy}>{[7, 30, 90].map(count => <option key={count} value={count}>{t('connect.mcp.editor.days', { count })}</option>)}<option value="365">{t('connect.mcp.editor.oneYear')}</option></select></label><fieldset className="mcp-scope-picker"><legend>{t('connect.mcp.editor.scopes')}</legend>{permissions.map(permission => <label key={permission.id}><input type="checkbox" checked={scopes.includes(permission.id)} disabled={busy || permission.id === 'read'} onChange={e => setScopes(value => e.target.checked ? [...value, permission.id] : value.filter(v => v !== permission.id))}/><span><b>{t(permission.label)}</b><small>{t(permission.detail)}</small></span></label>)}</fieldset><label>{t('connect.mcp.editor.password')}<input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required maxLength={128} disabled={busy}/></label>{current.totp_enabled && <label>{t('connect.mcp.editor.code')}<input autoComplete="one-time-code" value={code} onChange={e => setCode(e.target.value)} required maxLength={30} disabled={busy}/></label>}<button className="primary" disabled={busy}>{busy ? t('connect.mcp.editor.creating') : rotation ? t('connect.mcp.editor.replaceTitle') : t('connect.mcp.tokens.create')}</button></form>
  </Modal>
  <Modal open={Boolean(secret)} onOpenChange={open => { if (!open) { setSecret(''); setShowSecret(false) } }} title={t('connect.mcp.secret.title')} description={t('connect.mcp.secret.description')}><Notice error={error} success={success}/><label>{t('connect.mcp.secret.label')}<div className="mcp-copy"><input aria-label={t('connect.mcp.secret.newAria')} type={showSecret ? 'text' : 'password'} readOnly value={secret} autoComplete="off"/><button aria-label={t('connect.mcp.secret.copyAria')} onClick={() => void copy(secret)}><Copy size={17}/></button></div></label><div className="button-row"><button onClick={() => setShowSecret(v => !v)}>{showSecret ? t('connect.mcp.secret.hide') : t('connect.mcp.secret.show')}</button><button onClick={downloadConfig}>{t('connect.mcp.secret.download')}</button></div><p className="muted">{t('connect.mcp.secret.lostHint')}</p><button className="primary" onClick={() => { setSecret(''); setShowSecret(false) }}>{t('connect.mcp.secret.saved')}</button></Modal>
  <Modal open={Boolean(confirmation)} onOpenChange={open => { if (!open && !busy) setConfirmation(null) }} title={confirmation === 'disable' ? t('connect.mcp.disable') : t('connect.mcp.confirm.revokeTitle')} description={confirmation === 'disable' ? t('connect.mcp.confirm.disableDescription') : t('connect.mcp.confirm.revokeDescription', { label: confirmation && typeof confirmation !== 'string' ? confirmation.label : '' })}><button className="danger" disabled={busy} onClick={() => void act(async () => { if (confirmation === 'disable') await api('PUT', '/v1/account/mcp', { enabled: false }); else if (confirmation) await api('DELETE', `/v1/account/mcp/tokens/${confirmation.id}`); setSecret(''); setConfirmation(null) }, confirmation === 'disable' ? t('connect.mcp.confirm.disabled') : t('connect.mcp.confirm.revoked'))}>{busy ? t('connect.mcp.confirm.applying') : t('connect.mcp.confirm.confirm')}</button></Modal>
 </>
}
