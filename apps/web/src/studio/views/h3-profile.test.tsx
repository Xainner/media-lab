import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import VideoView from './VideoView'

const submit = vi.hoisted(() => vi.fn())
vi.mock('./CreativeJob', () => ({ CreativeProgress: () => null, useCreativeJob: () => ({ submit }) }))
vi.mock('../lib/api', () => ({ newSession: () => 'session', formatUploadErrors: () => '', uploadFiles: vi.fn(),
  runtime: vi.fn(async () => ({ video: { profiles: {
    base: { ready: true, steps: { min: 8, max: 40, default: 20 } },
    fused_turbo: { ready: true, steps: { min: 4, max: 12, default: 4 } },
  } } })) }))
afterEach(() => { cleanup(); submit.mockClear() })

test('H3 profile switches defaults, validates bounds and submits explicit fused profile', async () => {
  const user = userEvent.setup()
  render(<VideoView />)
  expect(screen.getByLabelText('Pasos')).toHaveProperty('value', '20')
  await waitFor(() => expect((screen.getByText(/H3 Fused Turbo · rápido · 4 pasos/) as HTMLOptionElement).disabled).toBe(false))
  await user.selectOptions(screen.getByLabelText('Modelo H3'), 'fused_turbo')
  expect(screen.getByText(/usa 4 pasos; 8 o 12 solo afinan/)).toBeTruthy()
  expect(screen.getByLabelText('Pasos')).toHaveProperty('value', '4')
  expect(screen.getByLabelText('Pasos').getAttribute('max')).toBe('12')
  await user.type(screen.getByLabelText('Dirección visual'), 'A cup slowly rotates')
  await user.click(screen.getByRole('button', { name: 'GENERAR VIDEO' }))
  expect(submit).toHaveBeenCalledWith('/v1/jobs/video', expect.objectContaining({ profile: 'fused_turbo', steps: 4 }))
  await user.clear(screen.getByLabelText('Pasos'))
  await user.type(screen.getByLabelText('Pasos'), '13')
  expect((screen.getByRole('button', { name: 'GENERAR VIDEO' }) as HTMLButtonElement).disabled).toBe(true)
  await user.selectOptions(screen.getByLabelText('Modelo H3'), 'base')
  expect(screen.getByLabelText('Pasos')).toHaveProperty('value', '20')
})
