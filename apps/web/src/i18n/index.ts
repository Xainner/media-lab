import { useSyncExternalStore } from 'react'
import common from './messages/common'
import auth from './messages/auth'
import account from './messages/account'
import admin from './messages/admin'
import composer from './messages/composer'
import creations from './messages/creations'
import lab from './messages/lab'
import connect from './messages/connect'
import studio from './messages/studio'
import agent from './messages/agent'
import shell from './messages/shell'

export const LOCALES = ['es', 'en'] as const
export type Locale = typeof LOCALES[number]
/** Each language names itself, so the switcher reads the same in every locale. */
export const LOCALE_NAMES: Record<Locale, string> = { es: 'Español', en: 'English' }

const namespaces = [common, auth, account, admin, composer, creations, lab, connect, studio, agent, shell]
export type Messages = typeof common.es & typeof auth.es & typeof account.es & typeof admin.es & typeof composer.es & typeof creations.es
  & typeof lab.es & typeof connect.es & typeof studio.es & typeof agent.es & typeof shell.es
export type MessageKey = keyof Messages & string
export const catalogs = {
  es: Object.assign({}, ...namespaces.map(n => n.es)) as Record<MessageKey, string>,
  en: Object.assign({}, ...namespaces.map(n => n.en)) as Record<MessageKey, string>,
}

// Not under `media-lab:`: logout clears that prefix, and the choice belongs to the device, not the account.
export const LOCALE_KEY = 'media-lab-locale'
const isLocale = (v: unknown): v is Locale => (LOCALES as readonly unknown[]).includes(v)

/** Saved choice first, then the browser's preferred languages; English when none matches. */
export function detectLocale(): Locale {
  try { const saved = localStorage.getItem(LOCALE_KEY); if (isLocale(saved)) return saved } catch { /* storage blocked */ }
  const nav = typeof navigator === 'undefined' ? undefined : navigator
  for (const tag of nav?.languages?.length ? nav.languages : [nav?.language || '']) {
    const base = tag.slice(0, 2).toLowerCase()
    if (isLocale(base)) return base
  }
  return 'en'
}

let current: Locale = detectLocale()
const listeners = new Set<() => void>()
const syncDocument = () => { if (typeof document !== 'undefined') document.documentElement.lang = current }
syncDocument()

export const getLocale = () => current

/** Switches the UI language; `persist: false` keeps it out of storage (tests, previews). */
export function setLocale(locale: Locale, { persist = true }: { persist?: boolean } = {}) {
  if (persist) try { localStorage.setItem(LOCALE_KEY, locale) } catch { /* storage blocked */ }
  if (locale === current) return
  current = locale
  syncDocument()
  listeners.forEach(fn => fn())
}

export function subscribeLocale(fn: () => void) { listeners.add(fn); return () => { listeners.delete(fn) } }

/** Re-renders the caller when the language changes. The app root uses it, so every screen follows. */
export function useLocale() { return useSyncExternalStore(subscribeLocale, getLocale, getLocale) }

export type Vars = Record<string, string | number>

const plurals: Partial<Record<Locale, Intl.PluralRules>> = {}
const pluralOf = (n: number) => (plurals[current] ??= new Intl.PluralRules(current)).select(n)

/**
 * Translates `key` into the active language. `{name}` takes `vars.name`; `{n, plural, one {# file} other {# files}}`
 * picks the form for `vars.n` (`=0 {…}` matches exactly) and writes the number where `#` is.
 */
export function t(key: MessageKey, vars?: Vars): string {
  const template = catalogs[current][key] ?? catalogs.es[key] ?? key
  if (!vars) return template
  return template
    .replace(/\{(\w+)\}/g, (match, name) => name in vars ? String(vars[name]) : match)
    .replace(/\{(\w+), plural,((?:\s*=?\w+\s*\{[^{}]*\})+)\s*\}/g, (match, name, body: string) => {
      if (!(name in vars)) return match
      const n = Number(vars[name])
      const forms: Record<string, string> = {}
      for (const [, form, text] of body.matchAll(/(=?\w+)\s*\{([^{}]*)\}/g)) forms[form] = text
      return (forms[`=${n}`] ?? forms[pluralOf(n)] ?? forms.other ?? '').replace(/#/g, formatNumber(n))
    })
}

/** Same as `t`, for components that want to subscribe on their own (outside the app root). */
export function useT() { useLocale(); return t }

export const formatNumber = (n: number, options?: Intl.NumberFormatOptions) => n.toLocaleString(current, options)

/** Dates from the API come in Unix seconds; `Date` objects and milliseconds are accepted too. */
export function formatDateTime(value: number | Date, options: Intl.DateTimeFormatOptions = { dateStyle: 'medium', timeStyle: 'short' }) {
  const date = value instanceof Date ? value : new Date(value < 1e11 ? value * 1000 : value)
  return date.toLocaleString(current, options)
}
