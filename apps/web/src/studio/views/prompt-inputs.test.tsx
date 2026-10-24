import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import CreateView from './CreateView'
import EditView from './EditView'

beforeEach(() => {
  localStorage.clear()
  window.visualLab = {
    runtime: { request: vi.fn(async () => ({ two_k_enabled: false, model_precisions: { bf16: false } })) },
  } as unknown as Window['visualLab']
})
afterEach(cleanup)

test.each([
  ['Crear', 'DESCRIPCIÓN', CreateView],
  ['Editar', 'INSTRUCCIÓN', EditView],
] as const)('%s permite escribir, seleccionar, copiar, cortar y pegar texto multilínea', async (_name, label, View) => {
  // user-event supplies a clipboard stub. These tests never touch Windows
  // windows, the system clipboard, the image runtime, or the provider.
  const user = userEvent.setup()
  const { rerender } = render(<View active />)
  const input = screen.getByRole('textbox', { name: label }) as HTMLTextAreaElement
  expect(input.disabled).toBe(false)
  expect(input.readOnly).toBe(false)
  await user.type(input, 'Una taza azul, café y piñón.{Enter}Conservar <image2> y «texto exacto».')
  const expected = 'Una taza azul, café y piñón.\nConservar <image2> y «texto exacto».'
  expect(input.value).toBe(expected)

  input.setSelectionRange(0, input.value.length)
  await user.copy()
  expect(await navigator.clipboard.readText()).toBe(expected)
  await user.cut()
  expect(input.value).toBe('')
  await user.paste()
  expect(input.value).toBe(expected)

  rerender(<View active={false} />)
  rerender(<View active />)
  expect(input.value).toBe(expected)
  expect(vi.mocked(window.visualLab.runtime.request).mock.calls.every(([, route]) => route === '/v1/capabilities')).toBe(true)
})

test('un prompt copiado de Crear se pega en Editar sin perder saltos, acentos ni referencias', async () => {
  const user = userEvent.setup()
  render(<><CreateView active /><EditView active /></>)
  const source = screen.getByRole('textbox', { name: 'DESCRIPCIÓN' }) as HTMLTextAreaElement
  const target = screen.getByRole('textbox', { name: 'INSTRUCCIÓN' }) as HTMLTextAreaElement
  await user.type(source, 'Retrato de un dragón.{Enter}Usar el color de <image2>.')
  source.setSelectionRange(0, source.value.length)
  await user.copy()
  await user.click(target)
  await user.paste()
  expect(target.value).toBe(source.value)
})
