import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LOCALE_KEY, catalogs, detectLocale, formatDateTime, getLocale, setLocale, t, useLocale, type MessageKey } from '.'
import LanguageSwitch from './LanguageSwitch'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); setLocale('es', { persist: false }) })

const placeholders = (text: string) => [...text.matchAll(/\{(\w+)(?:, plural)?/g)].map(m => m[1]).sort()

test('every Spanish key has an English translation and nothing extra', () => {
  expect(Object.keys(catalogs.en).sort()).toEqual(Object.keys(catalogs.es).sort())
})

test('translations are non-empty and keep the same placeholders', () => {
  for (const key of Object.keys(catalogs.es) as MessageKey[]) {
    expect(catalogs.es[key].trim(), key).not.toBe('')
    expect(catalogs.en[key].trim(), key).not.toBe('')
    expect(placeholders(catalogs.en[key]), key).toEqual(placeholders(catalogs.es[key]))
  }
})

test('interpolates values and picks plural forms per language', () => {
  expect(t('account.gib', { n: 3 })).toBe('3 GiB')
  expect(t('admin.deleteDialogBody', { username: 'ana' })).toContain('Escribe ana')
  const plural = Object.entries(catalogs.es).find(([, v]) => /\{(\w+), plural,/.test(v)) as [MessageKey, string] | undefined
  expect(plural).toBeTruthy()
  const name = /\{(\w+), plural,/.exec(plural![1])![1]
  expect(t(plural![0], { [name]: 1 })).not.toBe(t(plural![0], { [name]: 2 }))
  expect(t(plural![0], { [name]: 2 })).not.toContain('plural')
})

test('detects the browser language, prefers the saved choice and falls back to English', () => {
  vi.stubGlobal('navigator', { language: 'es-MX', languages: ['es-MX', 'en'] })
  expect(detectLocale()).toBe('es')
  vi.stubGlobal('navigator', { language: 'fr-FR', languages: ['fr-FR', 'en-GB'] })
  expect(detectLocale()).toBe('en')
  vi.stubGlobal('navigator', { language: 'de-DE', languages: ['de-DE'] })
  expect(detectLocale()).toBe('en')
  localStorage.setItem(LOCALE_KEY, 'es')
  expect(detectLocale()).toBe('es')
})

test('dates follow the active language', () => {
  const when = Date.UTC(2026, 0, 15, 12) / 1000
  setLocale('en', { persist: false })
  expect(formatDateTime(when, { month: 'long', timeZone: 'UTC' })).toBe('January')
  setLocale('es', { persist: false })
  expect(formatDateTime(when, { month: 'long', timeZone: 'UTC' })).toBe('enero')
})

function Probe() { useLocale(); return <p>{t('auth.submitLogin')}</p> }

test('the switcher changes the language at once, updates <html lang> and remembers the choice', async () => {
  const user = userEvent.setup()
  render(<><LanguageSwitch /><Probe /></>)
  expect(screen.getByText('Entrar al estudio')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'ES' }).getAttribute('aria-pressed')).toBe('true')
  await user.click(screen.getByRole('button', { name: 'EN' }))
  expect(screen.getByText('Enter the studio')).toBeTruthy()
  expect(getLocale()).toBe('en')
  expect(document.documentElement.lang).toBe('en')
  expect(localStorage.getItem(LOCALE_KEY)).toBe('en')
  expect(screen.getByRole('group', { name: 'Language' })).toBeTruthy()
  expect(screen.getByRole('button', { name: 'EN' }).getAttribute('aria-pressed')).toBe('true')
  await user.click(screen.getByRole('button', { name: 'ES' }))
  expect(screen.getByText('Entrar al estudio')).toBeTruthy()
  expect(document.documentElement.lang).toBe('es')
})
