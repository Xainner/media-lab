import { useEffect, useState } from 'react'
import { Cable, Check, Copy, KeyRound, Plus, RefreshCw, ShieldCheck, Sparkles, Trash2 } from 'lucide-react'
import { api } from './bridge'
import { Badge, Loading, Modal, Notice, PageHeading } from './ui'

type Token = { id: string; label: string; scopes: string[]; created_at: number; expires_at: number; last_used_at: number | null; revoked_at: number | null }
type Connection = { enabled: boolean; endpoint: string; items: Token[] }
const permissions = [
 { id: 'read', label: 'Consultar mi estudio', detail: 'Biblioteca, trabajos, conversaciones, capacidades y descargas.' },
 { id: 'create', label: 'Crear multimedia', detail: 'Imagen, edición, vídeo, música, Director, referencias y trabajos.' },
 { id: 'agent', label: 'Usar Rinari y mi proveedor', detail: 'Conversaciones del agente, mejora de prompts y planificación. Puede generar multimedia y consumir tu cuota.' },
 { id: 'delete', label: 'Eliminar archivos', detail: 'Permite borrar definitivamente recursos de tu biblioteca.' },
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
const date = (value: number) => new Date(value * 1000).toLocaleString('es', { dateStyle: 'medium', timeStyle: 'short' })

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
 async function copy(value: string) { try { await navigator.clipboard.writeText(value); setSuccess('Copiado al portapapeles.'); setError('') } catch { setError('No se pudo copiar. Selecciona el campo y cópialo manualmente.') } }
 function openEditor(token: Token | null = null) {
  setRotation(token); setLabel(token?.label || 'Mi agente AI'); setDays('90'); setScopes(token?.scopes || ['read', 'create', 'agent']); setPassword(''); setCode(''); setEditor(true); setError(''); setSuccess('')
 }
 async function mint() {
  await act(async () => {
   const value = await api('POST', rotation ? `/v1/account/mcp/tokens/${rotation.id}/rotate` : '/v1/account/mcp/tokens', { label, days: Number(days), scopes, password, code })
   setPassword(''); setCode(''); setEditor(false); setSecret(value.token); setShowSecret(false)
  }, rotation ? 'Token reemplazado. El anterior ya no permite conectarse.' : 'Token creado. Cópialo antes de cerrar esta ventana.')
 }
 function downloadConfig() {
  if (!connection || !secret) return
  const blob = new Blob([JSON.stringify({ mcpServers: { 'media-lab': { type: 'http', url: connection.endpoint, headers: { Authorization: `Bearer ${secret}` } } } }, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob), link = document.createElement('a'); link.href = url; link.download = 'rinari-mcp.json'; link.click(); URL.revokeObjectURL(url)
 }
 if (!connection) return <><Notice error={error}/><Loading/></>
 return <>
  <PageHeading eyebrow="TU ESTUDIO, CONECTADO" title="Conexiones MCP">Dale a tus agentes AI acceso a las herramientas de Rinari, con los permisos que tú elijas.</PageHeading>
  <Notice error={!editor && !secret ? error : ''} success={!secret ? success : ''}/>
  <section className="mcp-hero panel">
   <div className="mcp-mark"><Cable size={34}/></div><div><h2>Un puente hacia tu creatividad</h2><p className="muted">Tus agentes pueden descubrir funciones, aprender a escribir prompts y crear imagen, vídeo y música en tu cuenta.</p><Badge status={connection.enabled ? 'enabled' : 'disabled'}/></div>
   <button disabled={busy} className={connection.enabled ? 'ghost' : 'primary'} onClick={() => connection.enabled ? setConfirmation('disable') : void act(async () => { await api('PUT', '/v1/account/mcp', { enabled: true }) }, 'Conexión habilitada. Crea un token para tu agente.')}>{connection.enabled ? 'Deshabilitar MCP' : 'Habilitar MCP'}</button>
  </section>
  <div className="mcp-layout"><section className="panel settings-panel"><p className="eyebrow"><Cable size={15}/> CÓMO CONECTARSE</p><h2>Configura tu cliente MCP</h2><ol className="mcp-steps"><li><b>Añade un servidor remoto</b><p>Elige transporte <strong>Streamable HTTP</strong> en un cliente que permita enviar un token Bearer.</p></li><li><b>Usa la dirección de tu estudio</b><label>URL del servidor<div className="mcp-copy"><input readOnly value={connection.endpoint} aria-label="URL del servidor MCP"/><button aria-label="Copiar URL MCP" onClick={() => void copy(connection.endpoint)}><Copy size={16}/></button></div></label><p>Usa siempre esta dirección, también desde tu red local: el servidor no responde por IP ni por otros nombres.</p></li><li><b>Añade tu token de acceso</b><p>Cabecera <code>Authorization</code>, valor <code>Bearer</code> seguido de un espacio y tu token. Nunca lo incluyas en la URL.</p></li><li><b>Deja que tu agente explore</b><p>Conéctate y descubre herramientas, la guía de prompts y la plantilla de un brief creativo. Consulta primero las capacidades disponibles.</p></li><li><b>Envía y recibe archivos</b><p>El estudio es remoto: tu agente no instala nada. Para usar sus imágenes, audios o vídeos pide enlaces con <code>create_uploads</code> y sube cada archivo con <code>curl -T</code>; para traer resultados usa <code>get_download_links</code>. Los enlaces caducan y no llevan tu token.</p></li></ol><div className="mcp-brief"><div><b>Instrucciones para tu agente</b><button aria-label="Copiar instrucciones para el agente" onClick={() => void copy(agentBrief(connection.endpoint))}><Copy size={15}/> Copiar</button></div><p className="muted">Pégalas en las instrucciones de tu agente (están en inglés, como la guía del MCP). No incluyen tu token.</p><pre>{agentBrief(connection.endpoint)}</pre></div><p className="muted">Cada token es personal. Usa uno por cliente para poder retirar su acceso por separado. El archivo de configuración descargable incluye el token: guárdalo en un lugar privado.</p></section>
  <section className="panel settings-panel"><p className="eyebrow"><Sparkles size={15}/> TODO TU ESTUDIO</p><h2>De la idea al resultado</h2><div className="mcp-features">{[
   ['Imagen y edición', 'Prompts descriptivos, transparencias y referencias propias.'],
   ['Vídeo H3 y música YuE2', 'Fotogramas, movimiento, estilo musical, letra y melodía ABC.'],
   ['Director y agente Rinari', 'Storyboard, escenas y tareas con tu proveedor activo.'],
   ['Biblioteca y trabajos', 'Buscar, analizar, cancelar y consultar el progreso.'],
   ['Tus archivos, en ambos sentidos', 'Imágenes, audio y vídeo de hasta 500 MiB con enlaces temporales; resultados descargables sin exponer el token.'],
  ].map(([title, detail]) => <div key={title}><Check size={16}/><span><b>{title}</b><p>{detail}</p></span></div>)}</div><div className="mcp-privacy"><ShieldCheck size={22}/><p>El acceso respeta tus cuotas y tus archivos privados. Las claves de proveedores y las funciones administrativas quedan fuera del MCP.</p></div><p className="muted">La guía explica los parámetros reales y cómo consultar trabajos asíncronos. Los permisos de creación y agente pueden consumir recursos de tu cuenta.</p></section></div>
  <div className="section-title"><div><h2>Tus tokens de acceso</h2><p className="muted">Puedes revocarlos o reemplazarlos cuando quieras.</p></div><div className="button-row"><button aria-label="Actualizar tokens" disabled={busy} onClick={() => void act(load, 'Lista actualizada.')}><RefreshCw size={16}/></button><button className="primary" disabled={busy || !connection.enabled} onClick={() => openEditor()}><Plus size={17}/> Crear token</button></div></div>
  <div className="mcp-token-list">{connection.items.length ? connection.items.map(token => {
   const status = token.revoked_at ? 'revoked' : token.expires_at <= Date.now()/1000 ? 'expired' : 'enabled'
   return <article className="panel mcp-token" key={token.id}><div className="mcp-token-heading"><KeyRound size={20}/><h3>{token.label}</h3><Badge status={status}/></div><div className="mcp-permissions">{token.scopes.map(scope => <span className="pill" key={scope}>{permissions.find(p => p.id === scope)?.label || scope}</span>)}</div><dl><div><dt>Creado</dt><dd>{date(token.created_at)}</dd></div><div><dt>Caduca</dt><dd>{date(token.expires_at)}</dd></div><div><dt>Última conexión</dt><dd>{token.last_used_at ? date(token.last_used_at) : 'Todavía sin conexiones'}</dd></div></dl>{status === 'enabled' && <div className="button-row"><button disabled={busy || !connection.enabled} onClick={() => openEditor(token)}><RefreshCw size={15}/> Reemplazar</button><button className="danger ghost" disabled={busy} onClick={() => setConfirmation(token)}><Trash2 size={15}/> Revocar</button></div>}</article>
  }) : <div className="panel mcp-empty"><KeyRound size={28}/><h3>Tu próximo agente empieza aquí</h3><p className="muted">Habilita la conexión y crea un token. Solo tú puedes autorizar el acceso a tu estudio.</p></div>}</div>
  <Modal open={editor} onOpenChange={open => { if (!busy) { setEditor(open); if (!open) { setPassword(''); setCode('') } } }} title={rotation ? 'Reemplazar token' : 'Crear token de acceso'} description={rotation ? 'El token anterior se revocará al crear el nuevo.' : 'El token se mostrará una sola vez. Elige los permisos de este agente.'}>
   <Notice error={error}/><form onSubmit={e => { e.preventDefault(); void mint() }}><label>Nombre del cliente<input value={label} onChange={e => setLabel(e.target.value)} maxLength={80} required disabled={busy}/></label><label>Caducidad<select value={days} onChange={e => setDays(e.target.value)} disabled={busy}><option value="7">7 días</option><option value="30">30 días</option><option value="90">90 días</option><option value="365">Un año</option></select></label><fieldset className="mcp-scope-picker"><legend>Permisos del token</legend>{permissions.map(permission => <label key={permission.id}><input type="checkbox" checked={scopes.includes(permission.id)} disabled={busy || permission.id === 'read'} onChange={e => setScopes(value => e.target.checked ? [...value, permission.id] : value.filter(v => v !== permission.id))}/><span><b>{permission.label}</b><small>{permission.detail}</small></span></label>)}</fieldset><label>Confirma tu contraseña<input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required maxLength={128} disabled={busy}/></label>{current.totp_enabled && <label>Código 2FA o de recuperación<input autoComplete="one-time-code" value={code} onChange={e => setCode(e.target.value)} required maxLength={30} disabled={busy}/></label>}<button className="primary" disabled={busy}>{busy ? 'Creando…' : rotation ? 'Reemplazar token' : 'Crear token'}</button></form>
  </Modal>
  <Modal open={Boolean(secret)} onOpenChange={open => { if (!open) { setSecret(''); setShowSecret(false) } }} title="Guarda tu token" description="Cópialo ahora. Rinari guarda únicamente su huella y no podrá volver a mostrarlo."><Notice error={error} success={success}/><label>Token MCP<div className="mcp-copy"><input aria-label="Token MCP nuevo" type={showSecret ? 'text' : 'password'} readOnly value={secret} autoComplete="off"/><button aria-label="Copiar token MCP" onClick={() => void copy(secret)}><Copy size={17}/></button></div></label><div className="button-row"><button onClick={() => setShowSecret(v => !v)}>{showSecret ? 'Ocultar' : 'Mostrar'} token</button><button onClick={downloadConfig}>Descargar configuración</button></div><p className="muted">Si lo pierdes, reemplázalo por uno nuevo. No compartas el token ni la configuración con otros usuarios.</p><button className="primary" onClick={() => { setSecret(''); setShowSecret(false) }}>Ya lo he guardado</button></Modal>
  <Modal open={Boolean(confirmation)} onOpenChange={open => { if (!open && !busy) setConfirmation(null) }} title={confirmation === 'disable' ? 'Deshabilitar MCP' : 'Revocar token'} description={confirmation === 'disable' ? 'Todos tus tokens se revocarán. Los agentes perderán el acceso; los trabajos ya enviados seguirán visibles en Mis trabajos.' : `El cliente «${confirmation && typeof confirmation !== 'string' ? confirmation.label : ''}» perderá el acceso con este token.`}><button className="danger" disabled={busy} onClick={() => void act(async () => { if (confirmation === 'disable') await api('PUT', '/v1/account/mcp', { enabled: false }); else if (confirmation) await api('DELETE', `/v1/account/mcp/tokens/${confirmation.id}`); setSecret(''); setConfirmation(null) }, confirmation === 'disable' ? 'MCP deshabilitado y tokens revocados.' : 'Token revocado.')}>{busy ? 'Aplicando…' : 'Confirmar'}</button></Modal>
 </>
}
