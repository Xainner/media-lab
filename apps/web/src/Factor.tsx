import { useState } from 'react'
import { api } from './bridge'
import { t } from './i18n'

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
  return <section className="panel auth-panel"><p className="eyebrow">{t('connect.factor.eyebrow')}</p><h2>{current.totp_enabled ? t('connect.factor.verifyTitle') : t('connect.factor.enableTitle')}</h2>
    {codes.length ? <><p>{t('connect.factor.codesOnce')}</p><div className="recovery-grid">{codes.map(value => <code key={value}>{value}</code>)}</div><button className="primary" onClick={done}>{t('connect.factor.codesSaved')}</button></>
      : <>{!current.totp_enabled && !setup && <><p>{current.role === 'admin' ? t('connect.factor.adminRequired') : t('connect.factor.protect')}</p><button disabled={busy} onClick={() => void configure()}>{t('connect.factor.configure')}</button></>}
      {setup && <div className="totp-enrollment">
        <p>{t('connect.factor.scanHint')}</p>
        {typeof setup.qr_data_uri === 'string' && /^data:image\/png;base64,/.test(setup.qr_data_uri) &&
          <img className="totp-qr" src={setup.qr_data_uri} alt={t('connect.factor.qrAlt')} />}
        <p>{t('connect.factor.account', { email: current.email })}</p>
        <details className="totp-manual"><summary>{t('connect.factor.manualSummary')}</summary>
          <p>{t('connect.factor.manualHint')}</p><code className="totp-secret">{setup.secret}</code>
        </details>
      </div>}
      {(current.totp_enabled || setup) && <form onSubmit={e => { e.preventDefault(); void act() }}><label>{setup ? t('connect.factor.setupCode') : t('connect.factor.loginCode')}<input autoComplete="one-time-code" value={code} onChange={e => setCode(e.target.value)} maxLength={setup ? 6 : 30} inputMode={setup ? 'numeric' : undefined} /></label><button className="primary" disabled={busy || !code.trim()}>{t('connect.factor.verify')}</button></form>}
    </>}{error && <p className="error">{error}</p>}</section>
}
