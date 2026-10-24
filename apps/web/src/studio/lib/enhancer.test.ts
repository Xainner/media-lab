import { beforeEach, expect, test } from 'vitest'
import { getEnhancerMode } from './api'
const key = 'media-lab:enhancer-mode'
beforeEach(() => localStorage.clear())
test.each(['qwen', 'compare'])('migrates %s to manual, never automatic external sends', old => {
  localStorage.setItem(key, old)
  expect(getEnhancerMode()).toBe('manual')
  expect(localStorage.getItem(key)).toBe('manual')
})
test.each(['external', 'off', 'manual'] as const)('preserves %s', value => {
  localStorage.setItem(key, value)
  expect(getEnhancerMode()).toBe(value)
})
