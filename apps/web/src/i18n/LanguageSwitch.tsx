import { LOCALES, LOCALE_NAMES, setLocale, t, useLocale } from '.'

/** Two-option language toggle; the choice applies at once and is remembered on this device. */
export default function LanguageSwitch({ className = '' }: { className?: string }) {
  const locale = useLocale()
  return <div className={`language-switch ${className}`} role="group" aria-label={t('common.language')}>
    {LOCALES.map(l => <button key={l} type="button" lang={l} aria-pressed={locale === l} className={locale === l ? 'is-on' : ''} onClick={() => setLocale(l)} title={LOCALE_NAMES[l]}>
      {l.toUpperCase()}
    </button>)}
  </div>
}
