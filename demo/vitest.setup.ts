// Loaded before every test file: the jest-dom matchers for the component tests, which run under
// jsdom through a docblock at the top of each file, and a cleanup after each test.
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => {
  cleanup()
})
