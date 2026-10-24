import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import VideoView from './VideoView'
import MusicView from './MusicView'

const submit = vi.hoisted(() => vi.fn())
vi.mock('./CreativeJob', () => ({ CreativeProgress: () => null, useCreativeJob: () => ({ submit }) }))
vi.mock('../lib/api', () => ({ newSession: () => 'session', formatUploadErrors: () => '', uploadFiles: vi.fn(), runtime: vi.fn(async () => ({
  video: { profiles: { base: { ready: true, steps: { min: 8, max: 40, default: 20 } }, fused_turbo: { ready: true, steps: { min: 4, max: 12, default: 4 } } } },
  generation_options: {
    video: [{ path: 'codec', label: 'Códec', group: 'Archivo de salida', default: 'h264', choices: ['h264','av1'] }, { path: 'crf', label: 'CRF', group: 'Archivo de salida', min: 0, max: 63, step: 1 }],
    song: [{ path: 'composition.temperature', label: 'Temperatura', group: 'Composición', default: 1, min: 0, max: 5, step: .01 },
      { path: 'score.temperature', label: 'Temperatura', group: 'Generación de partitura ABC', default: .7, min: 0, max: 5, step: .01 },
      { path: 'format', label: 'Formato de audio', group: 'Archivo de salida', default: 'flac', choices: ['flac','mp3','opus'] },
      { path: 'audio_quality', label: 'Calidad de compresión', group: 'Archivo de salida', choices: ['V0','128k','320k'] }],
    image: [], edit: [], video_resolutions: { '720p': { '16:9': [1280,704] } }, notes: {},
  },
})) }))
afterEach(() => { cleanup(); submit.mockClear() })

test.each(['base','fused_turbo'])('video %s submits resolution, compression and seed instead of dropping them', async profile => {
  const user = userEvent.setup()
  render(<VideoView/>)
  await waitFor(() => expect(screen.getByLabelText('Códec')).toBeTruthy())
  await user.selectOptions(screen.getByLabelText('Modelo H3'), profile)
  await user.selectOptions(screen.getByLabelText('Resolución de vídeo'), '720p')
  expect(screen.getByText('1280 × 704 píxeles')).toBeTruthy()
  await user.click(screen.getByText('Ajustes del modelo y archivo'))
  await user.selectOptions(screen.getByLabelText('Códec'), 'av1')
  await user.type(screen.getByLabelText('CRF'), '18')
  await user.click(screen.getByText('Semilla', { selector: 'summary' }))
  await user.type(screen.getByLabelText('Semilla'), '0')
  await user.type(screen.getByLabelText('Dirección visual'), 'A violet nebula slowly rotates')
  await user.click(screen.getByRole('button', { name: 'GENERAR VIDEO' }))
  expect(submit).toHaveBeenCalledWith('/v1/jobs/video', expect.objectContaining({ profile, seed: 0,
    steps: profile === 'base' ? 20 : 4, options: { resolution: '720p', codec: 'av1', crf: 18 } }))
  await user.selectOptions(screen.getByLabelText('Resolución de vídeo'), 'custom')
  await user.type(screen.getByLabelText('Ancho de vídeo'), '2048')
  await user.type(screen.getByLabelText('Alto de vídeo'), '2048')
  expect((screen.getByRole('button', { name: 'GENERAR VIDEO' }) as HTMLButtonElement).disabled).toBe(true)
})

test('music keeps composition and ABC parameters separate and exposes only compatible encoding quality', async () => {
  const user = userEvent.setup()
  render(<MusicView/>)
  await waitFor(() => expect(screen.getByLabelText('Formato de audio')).toBeTruthy())
  await user.click(screen.getByText('Ajustes del modelo y archivo'))
  await user.type(within(screen.getByRole('group', { name: 'Composición' })).getByLabelText('Temperatura'), '1.4')
  await user.type(within(screen.getByRole('group', { name: 'Generación de partitura ABC' })).getByLabelText('Temperatura'), '0.6')
  expect(screen.queryByLabelText('Calidad de compresión')).toBeNull()
  await user.selectOptions(screen.getByLabelText('Formato de audio'), 'mp3')
  await user.selectOptions(screen.getByLabelText('Calidad de compresión'), '320k')
  await user.type(screen.getByLabelText('Estilo'), 'Dream pop')
  await user.click(screen.getByRole('button', { name: 'Arreglo completo' }))
  await user.click(screen.getByRole('button', { name: 'GENERAR CANCIÓN' }))
  expect(submit).toHaveBeenCalledWith('/v1/jobs/song', expect.objectContaining({ mode: 'full', steps: 32,
    options: { composition: { temperature: 1.4 }, score: { temperature: .6 }, format: 'mp3', audio_quality: '320k' } }))
  await user.selectOptions(screen.getByLabelText('Formato de audio'), 'flac')
  expect(screen.queryByLabelText('Calidad de compresión')).toBeNull()
})
