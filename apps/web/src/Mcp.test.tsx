import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Mcp from './Mcp'
const api = vi.hoisted(() => vi.fn())
vi.mock('./bridge', () => ({ api }))
vi.mock('./ui', () => ({
 Loading: () => <p>Cargando</p>, Badge: ({ status }: any) => <span>{status}</span>,
 Notice: ({ error, success }: any) => <p>{error || success}</p>,
 PageHeading: ({ title }: any) => <h1>{title}</h1>,
 Modal: ({ open, title, children }: any) => open ? <div role="dialog" aria-label={title}>{children}</div> : null,
}))
let connection: any
beforeEach(() => {
 connection = { enabled: true, endpoint: 'https://studio.example/mcp', items: [] }
 api.mockImplementation(async (method, route, body) => {
  if (route === '/v1/account/mcp') { if (method === 'PUT') connection.enabled = body.enabled; return { ...connection } }
  if (route === '/v1/account/mcp/tokens') return { id: 'one', token: 'rvl_mcp_test_one_time_secret' }
  return { ok: true }
 })
})
afterEach(() => { cleanup(); api.mockReset() })
test('token creation sends explicitly chosen permissions and factors, and forgets the one-time secret', async () => {
 const user = userEvent.setup(); const view = render(<Mcp current={{ totp_enabled: true }}/>)
 await user.click(await screen.findByRole('button', { name: 'Crear token' }))
 await user.click(screen.getByLabelText(/Usar Rinari y mi proveedor/))
 await user.type(screen.getByLabelText('Confirma tu contraseña'), 'private-password')
 await user.type(screen.getByLabelText('Código 2FA o de recuperación'), '123456')
 await user.click(within(screen.getByRole('dialog', { name: 'Crear token de acceso' })).getByRole('button', { name: 'Crear token', exact: true }))
 await waitFor(() => expect(api).toHaveBeenCalledWith('POST', '/v1/account/mcp/tokens', { label: 'Mi agente AI', days: 90, scopes: ['read', 'create'], password: 'private-password', code: '123456' }))
 expect((await screen.findByLabelText('Token MCP nuevo') as HTMLInputElement).type).toBe('password')
 expect(localStorage.length).toBe(0)
 await user.click(screen.getByRole('button', { name: 'Ya lo he guardado' }))
 expect(screen.queryByLabelText('Token MCP nuevo')).toBeNull()
 view.unmount(); render(<Mcp current={{ totp_enabled: true }}/>)
 await screen.findByRole('heading', { name: 'Conexiones MCP' })
 expect(screen.queryByDisplayValue('rvl_mcp_test_one_time_secret')).toBeNull()
})
test('disabling MCP requires a deliberate confirmation and prevents new tokens', async () => {
 const user = userEvent.setup(); render(<Mcp current={{ totp_enabled: false }}/>)
 await user.click(await screen.findByRole('button', { name: 'Deshabilitar MCP' }))
 expect(api).not.toHaveBeenCalledWith('PUT', '/v1/account/mcp', expect.anything())
 await user.click(screen.getByRole('button', { name: 'Confirmar' }))
 await waitFor(() => expect(api).toHaveBeenCalledWith('PUT', '/v1/account/mcp', { enabled: false }))
 await screen.findByRole('button', { name: 'Habilitar MCP' })
 expect((screen.getByRole('button', { name: 'Crear token' }) as HTMLButtonElement).disabled).toBe(true)
})
test('agent instructions explain the remote server and file links without exposing a token', async () => {
 const user = userEvent.setup(); render(<Mcp current={{ totp_enabled: true }}/>)
 const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
 const brief = (await screen.findByText(/Media Lab is a remote MCP server/)).textContent || ''
 expect(brief).toContain('https://studio.example/mcp')
 for (const tool of ['create_uploads', 'get_download_links', 'capabilities.inputs.references']) expect(brief).toContain(tool)
 expect(brief).not.toMatch(/rvl_mcp_/)
 await user.click(screen.getByRole('button', { name: 'Copiar instrucciones para el agente' }))
 expect(writeText).toHaveBeenCalledWith(brief)
})
