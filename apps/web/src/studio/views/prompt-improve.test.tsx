import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import VideoView from './VideoView'
import MusicView from './MusicView'

const submit = vi.hoisted(() => vi.fn())
vi.mock('./CreativeJob', () => ({ CreativeProgress: () => null, useCreativeJob: () => ({ submit }) }))
vi.mock('../lib/api', () => ({ newSession: () => 'session', formatUploadErrors: () => '', uploadFiles: vi.fn(),
  runtime: vi.fn(async () => ({})) }))

const frame = { uri: 'rvl://images/first.png', sha256: 'a'.repeat(64), mime: 'image/png' } as any
const improve = vi.fn()
beforeEach(() => {
  improve.mockReset()
  window.visualLab = { agent: { improve }, runtime: { preview: async () => 'data:image/png;base64,', mediaUrl: async () => '' } } as unknown as Window['visualLab']
})
afterEach(() => { cleanup(); submit.mockClear() })

test('Video propone un prompt H3 con modo y segundos y sólo lo aplica al aceptarlo', async () => {
  const user = userEvent.setup()
  improve.mockResolvedValue({ prompt: 'scene: a cup rotates\naudio: soft hum' })
  render(<VideoView />)
  const input = screen.getByLabelText('Dirección visual') as HTMLTextAreaElement
  await user.type(input, 'Una taza gira')
  await user.clear(screen.getByLabelText('Segundos'))
  await user.type(screen.getByLabelText('Segundos'), '8')
  await user.click(screen.getByRole('button', { name: 'PROPONER MEJORA EXTERNA' }))
  expect(improve).toHaveBeenCalledWith('Una taza gira', 't2v', [], 8)
  expect(await screen.findByText(/scene: a cup rotates/)).toBeTruthy()
  expect(input.value).toBe('Una taza gira')
  await user.click(screen.getByRole('button', { name: 'ACEPTAR ESTA PROPUESTA' }))
  expect(input.value).toBe('scene: a cup rotates\naudio: soft hum')
  expect(submit).not.toHaveBeenCalled()
})

test('Video desde imagen envía el fotograma inicial como referencia y exige tenerlo', async () => {
  const user = userEvent.setup()
  improve.mockResolvedValue({ prompt: 'H3 I2VA' })
  const { rerender } = render(<VideoView />)
  await user.click(screen.getByRole('button', { name: 'Desde imagen' }))
  await user.type(screen.getByLabelText('Dirección visual'), 'Avanza la cámara')
  expect((screen.getByRole('button', { name: 'PROPONER MEJORA EXTERNA' }) as HTMLButtonElement).disabled).toBe(true)
  rerender(<VideoView incoming={frame} />)
  await user.click(screen.getByRole('button', { name: 'PROPONER MEJORA EXTERNA' }))
  expect(improve).toHaveBeenCalledWith('Avanza la cámara', 'i2v', [{ uri: frame.uri, sha256: frame.sha256 }], 5)
})

test('Video con referencias no exige imágenes y muestra el error del proveedor en español', async () => {
  const user = userEvent.setup()
  improve.mockRejectedValue(new Error('Runtime 400: Operación no disponible'))
  render(<VideoView />)
  await user.click(screen.getByRole('button', { name: 'Con referencias' }))
  await user.type(screen.getByLabelText('Dirección visual'), 'Usa <Video 1>')
  await user.click(screen.getByRole('button', { name: 'PROPONER MEJORA EXTERNA' }))
  expect(improve).toHaveBeenCalledWith('Usa <Video 1>', 'r2v', [], 5)
  expect(await screen.findByText('Proveedor externo: Runtime 400: Operación no disponible')).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'ACEPTAR ESTA PROPUESTA' })).toBeNull()
})

test('Música propone estilo y letra y rellena ambos campos sólo al aceptar', async () => {
  const user = userEvent.setup()
  improve.mockResolvedValue({ prompt: 'pop, female vocal, 100 bpm', lyrics: '[Verse]\nMar de luz\n[Chorus]\nVuelve' })
  render(<MusicView />)
  const style = screen.getByLabelText('Estilo') as HTMLTextAreaElement
  const lyrics = screen.getByLabelText('Letra') as HTMLTextAreaElement
  expect((screen.getByRole('button', { name: 'PROPONER MEJORA EXTERNA' }) as HTMLButtonElement).disabled).toBe(true)
  await user.type(style, 'pop luminoso')
  await user.type(lyrics, 'Mar de luz')
  await user.click(screen.getByRole('button', { name: 'PROPONER MEJORA EXTERNA' }))
  expect(improve).toHaveBeenCalledWith('Style: pop luminoso\n\nLyrics:\nMar de luz', 'song', [], undefined)
  expect(await screen.findByText('pop, female vocal, 100 bpm')).toBeTruthy()
  expect(style.value).toBe('pop luminoso')
  await user.click(screen.getByRole('button', { name: 'ACEPTAR ESTA PROPUESTA' }))
  expect(style.value).toBe('pop, female vocal, 100 bpm')
  expect(lyrics.value).toBe('[Verse]\nMar de luz\n[Chorus]\nVuelve')
  expect(submit).not.toHaveBeenCalled()
})
