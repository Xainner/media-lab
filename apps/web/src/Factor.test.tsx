import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Factor from './Factor'

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
vi.mock('./bridge', () => ({ api }))
afterEach(() => { cleanup(); vi.resetAllMocks() })

describe('alta del autenticador mediante QR', () => {
  it('muestra el QR local, deja la clave manual plegada y confirma con seis dígitos', async () => {
    const done = vi.fn()
    api.mockResolvedValueOnce({ secret: 'FIXTURE-ONLY', qr_data_uri: 'data:image/png;base64,fixture' })
      .mockResolvedValueOnce({ recovery_codes: ['RECOVERY-FIXTURE'] })
    const user = userEvent.setup()
    render(<Factor current={{ role: 'admin', email: 'fixture@example.org', totp_enabled: false }} done={done} />)
    await user.click(screen.getByRole('button', { name: 'CONFIGURAR AUTENTICADOR' }))
    const qr = await screen.findByRole('img', { name: 'Código QR para vincular tu autenticador' })
    expect(qr.getAttribute('src')).toBe('data:image/png;base64,fixture')
    expect(screen.getByText('FIXTURE-ONLY').closest('details')?.open).toBe(false)
    await user.click(screen.getByText('¿No puedes escanear? Configuración manual'))
    expect(screen.getByText('FIXTURE-ONLY').closest('details')?.open).toBe(true)
    await user.type(screen.getByLabelText('Código de 6 dígitos del autenticador'), '123456')
    await user.click(screen.getByRole('button', { name: 'VERIFICAR' }))
    expect(api).toHaveBeenLastCalledWith('POST', '/v1/auth/2fa/confirm', { code: '123456' })
    await screen.findByText('RECOVERY-FIXTURE')
    expect(screen.queryByRole('img')).toBeNull()
    expect(screen.queryByText('FIXTURE-ONLY')).toBeNull()
    expect(done).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'HE GUARDADO LOS CÓDIGOS' }))
    expect(done).toHaveBeenCalledOnce()
  })

  it('no cambia el autenticador existente y permite códigos de recuperación', async () => {
    api.mockResolvedValueOnce({ ok: true })
    const done = vi.fn(), user = userEvent.setup()
    render(<Factor current={{ totp_enabled: true }} done={done} />)
    expect(screen.queryByRole('button', { name: 'CONFIGURAR AUTENTICADOR' })).toBeNull()
    expect(screen.queryByRole('img')).toBeNull()
    await user.type(screen.getByLabelText('Código TOTP o de recuperación'), 'recovery-fixture')
    await user.click(screen.getByRole('button', { name: 'VERIFICAR' }))
    expect(api).toHaveBeenCalledWith('POST', '/v1/auth/2fa/verify', { code: 'recovery-fixture' })
    expect(done).toHaveBeenCalledOnce()
  })

  it('no carga imágenes externas como QR', async () => {
    api.mockResolvedValueOnce({ secret: 'FIXTURE-ONLY', qr_data_uri: 'https://external.invalid/secret' })
    render(<Factor current={{ totp_enabled: false }} done={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: 'CONFIGURAR AUTENTICADOR' }))
    await screen.findByText('FIXTURE-ONLY')
    expect(screen.queryByRole('img')).toBeNull()
  })
})
