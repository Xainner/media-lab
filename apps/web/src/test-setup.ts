import { setLocale } from './i18n'

// The suites assert the Spanish source wording; jsdom reports an English browser.
setLocale('es', { persist: false })
