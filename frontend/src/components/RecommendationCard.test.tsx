import { expect, afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'
import * as matchers from '@testing-library/jest-dom/matchers'

expect.extend(matchers)

if (typeof process !== 'undefined' && process.stdout) {
  const stdout = process.stdout as NodeJS.WriteStream & {
    columns?: number
    getWindowSize?: () => [number, number]
  }
  if (!stdout.columns || !Number.isFinite(stdout.columns)) {
    stdout.columns = 80
  }
  if (typeof stdout.getWindowSize !== 'function') {
    stdout.getWindowSize = () => [24, stdout.columns ?? 80]
  }
}

afterEach(() => {
  cleanup()
})
