/** One namespace of UI copy. Spanish is the source wording; `en` must carry exactly the same keys. */
export function defineMessages<T extends Record<string, string>>(messages: { es: T; en: { [K in keyof T]: string } }) {
  return messages
}
