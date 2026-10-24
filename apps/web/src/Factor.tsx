import { useState } from 'react'
import { api } from './bridge'

export default function Factor({ current, done }: { current: any; done: () => void }) {
  const [setup, setSetup] = useState<any>(null)
  const [code, setCode] = useState('')
  const [codes, setCodes] = useState<string[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function configure() {
    setBusy(true); setError('')
    try { setSetup(await api('POST', '/v1/auth/2fa/setup', {})) }
    catch (e) { setError(String(e)) } finally { setBusy(false) }
  }
  async function act() {
    setBusy(true); setError('')
    try {
      const result = await api('POST', setup ? '/v1/auth/2fa/confirm' : '/v1/auth/2fa/verify', { code: code.trim() })
      if (result.recovery_codes) { setCodes(result.recovery_codes); setSetup(null); setCode('') }
      else done()
    } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }
  return <section className="panel auth-panel"><p className="eyebrow">SEGUNDO FACTOR</p><h2>{current.totp_enabled ? 'Verifica tu acceso' : 'Activa 2FA'}</h2>
    {codes.length ? <><p>Estos códigos se muestran una sola vez. Guárdalos fuera de la aplicación; cada uno permite un único acceso de recuperación.</p><div className="recovery-grid">{codes.map(value => <code key={value}>{value}</code>)}</div><button className="primary" onClick={done}>HE GUARDADO LOS CÓDIGOS</button></>
      : <>{!current.totp_enabled && !setup && <><p>{current.role === 'admin' ? 'El administrador debe activar TOTP antes de acceder al estudio o al panel.' : 'Protege tu cuenta con un autenticador.'}</p><button disabled={busy} onClick={() => void configure()}>CONFIGURAR AUTENTICADOR</button></>}
      {setup && <div className="totp-enrollment">
        <p>En tu autenticador, elige añadir cuenta y escanear código QR.</p>
        {typeof setup.qr_data_uri === 'string' && /^data:image\/png;base64,/.test(setup.qr_data_uri) &&
          <img className="totp-qr" src={setup.qr_data_uri} alt="Código QR para vincular tu autenticador" />}
        <p>Cuenta: {current.email}. Después escribe el código de 6 dígitos que aparece en la app para confirmar.</p>
        <details className="totp-manual"><summary>¿No puedes escanear? Configuración manual</summary>
          <p>Añade esta clave como TOTP, 6 dígitos, 30 segundos.</p><code className="totp-secret">{setup.secret}</code>
        </details>
      </div>}
      {(current.totp_enabled || setup) && <form onSubmit={e => { e.preventDefault(); void act() }}><label>{setup ? 'Código de 6 dígitos del autenticador' : 'Código TOTP o de recuperación'}<input autoComplete="one-time-code" value={code} onChange={e => setCode(e.target.value)} maxLength={setup ? 6 : 30} inputMode={setup ? 'numeric' : undefined} /></label><button className="primary" disabled={busy || !code.trim()}>VERIFICAR</button></form>}
    </>}{error && <p className="error">{error}</p>}</section>
}
