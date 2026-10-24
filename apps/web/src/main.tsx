import { useCallback, useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { MotionConfig } from 'motion/react'
import { api, clearBrowser, migrateStorage, prepareBrowser, session, setSession } from './bridge'
import Factor from './Factor'
import Studio from './Studio'
import { Notice } from './ui'
import Entry, { PasswordField, SubmitButton, type EntryMode } from './entry/Entry'
import Nebula from './motion/Nebula'
import { useMotionAllowed } from './motion/prefs'
import '@fontsource-variable/archivo/wdth.css'
import '@fontsource-variable/geist/wght.css'
import '@fontsource-variable/geist-mono/wght.css'
import './styles/index.css'

migrateStorage()

function WebApp() {
 const [current,setCurrent] = useState<any>(null)
 const [ready,setReady] = useState(false)
 const [loading,setLoading] = useState(true)
 const [error,setError] = useState('')
 const [success,setSuccess] = useState('')
 const [identity,setIdentity] = useState('')
 const [email,setEmail] = useState('')
 const [username,setUsername] = useState('')
 const [password,setPassword] = useState('')
 const [remember,setRemember] = useState(false)
 const [busy,setBusy] = useState(false)
 const [visible,setVisible] = useState(false)
 const exit = useRef<() => Promise<void>>(async () => {})
 useMotionAllowed()
 const [link] = useState(() => { const q = new URLSearchParams(location.hash.slice(1)); const value = { invite: q.get('invite') || q.get('bootstrap'), reset: q.get('reset') }; if(value.invite || value.reset) history.replaceState(null,'',location.pathname); return value })
 const [mode,setMode] = useState<EntryMode>(link.invite ? 'accept' : link.reset ? 'reset' : 'login')
 async function refresh() {
  setError('')
  try { const value = await session(); setCurrent(value); setSession(value); if(value.authenticated && value.mfa) { await prepareBrowser(value); setReady(true) } else { clearBrowser(); setSession(value); setReady(false) } }
  catch(e) { setError(String(e)) } finally { setLoading(false) }
 }
 useEffect(() => { void refresh(); const expired = () => { setReady(false); setCurrent(null); void refresh() }; window.addEventListener('rvl-logged-out',expired); return () => window.removeEventListener('rvl-logged-out',expired) }, [])
 async function submit() {
  setBusy(true); setError(''); setSuccess('')
  try {
   if(mode === 'login') {
    const v = await api('POST','/v1/auth/login',{identity,password,remember})
    if(v?.authenticated && v?.mfa) { await exit.current() }
    setSession(v); setCurrent(v); await refresh()
   }
   else if(mode === 'accept') { await api('POST','/v1/auth/accept',{email,username,password,token:link.invite}); setMode('login'); setIdentity(email); setSuccess('Tu cuenta está lista. Inicia sesión para entrar al estudio.') }
   else if(mode === 'reset') { await api('POST','/v1/auth/reset',{token:link.reset,password}); setMode('login'); setSuccess('Contraseña actualizada. Tu protección 2FA sigue activa.') }
   else { const v = await api('POST','/v1/auth/forgot',{email}); setSuccess(v.message) }
   setPassword('')
  } catch(e) { setError(e instanceof Error ? e.message : String(e)) } finally { setBusy(false) }
 }
 async function logout() { try { await api('POST','/v1/auth/logout',{}) } finally { clearBrowser(); setReady(false); setCurrent(null); setPassword(''); await refresh() } }
 const registerExit = useCallback((fn: () => Promise<void>) => { exit.current = fn }, [])
 const factor = current?.authenticated && !current.mfa
 if(ready) return <Studio key={current.user_id} current={current} refresh={refresh} logout={logout} />
 const factorNode = factor ? <div className="entry-factor"><Factor current={current} done={() => { void exit.current().then(refresh) }} /><button className="ghost" onClick={() => void logout()}>Cerrar sesión</button></div> : null
 return <Entry mode={mode} loading={loading} factor={factorNode} onSkipRef={registerExit}>
  <form className="entry-form" onSubmit={e => { e.preventDefault(); void submit() }}>
   {mode === 'login' && <label>Correo o nombre de usuario<input required autoComplete="username" placeholder="tú@ejemplo.com" value={identity} onChange={e => setIdentity(e.target.value)} maxLength={254} /></label>}
   {['accept','forgot'].includes(mode) && <label>Correo electrónico<input type="email" required autoComplete="email" placeholder="tú@ejemplo.com" value={email} onChange={e => setEmail(e.target.value)} maxLength={254} /></label>}
   {mode === 'accept' && <label>Nombre de usuario<input required autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} minLength={3} maxLength={40} /></label>}
   {mode !== 'forgot' && <PasswordField value={password} onChange={setPassword} visible={visible} setVisible={setVisible} mode={mode} />}
   {mode === 'login' && <div className="entry-options"><label className="check-label"><input type="checkbox" checked={remember} onChange={e => setRemember(e.target.checked)} /> Recordarme</label><button type="button" className="text-button" onClick={() => { setMode('forgot'); setError(''); setSuccess('') }}>¿Olvidaste tu contraseña?</button></div>}
   <Notice error={error} success={success} />
   {!current && !loading && <button type="button" className="ghost" onClick={()=>void refresh()}>Reintentar conexión</button>}
   <SubmitButton busy={busy} disabled={busy || !current}>{mode === 'login' ? 'Entrar al estudio' : mode === 'accept' ? 'Crear mi cuenta' : 'Continuar'}</SubmitButton>
   {mode !== 'login' && <button type="button" className="text-button entry-back" onClick={() => { setMode('login'); setError('') }}>Volver a iniciar sesión</button>}
  </form>
 </Entry>
}

function Root() {
 return <MotionConfig reducedMotion="user"><Nebula /><BrowserRouter future={{v7_startTransition:true,v7_relativeSplatPath:true}}><div className="rvl"><WebApp /></div></BrowserRouter></MotionConfig>
}
createRoot(document.getElementById('root')!).render(<Root />)
