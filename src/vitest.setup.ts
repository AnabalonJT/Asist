import '@testing-library/jest-dom/vitest'
import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

// Unmount React trees and clear mocks between tests so component state and
// module mocks never leak across cases.
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

// jsdom does not implement matchMedia. Provide a default (no reduced motion)
// stub so components that read `prefers-reduced-motion` on mount do not throw.
// Individual tests override this to simulate the "reduce" preference.
if (!window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string): MediaQueryList =>
      ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }) as unknown as MediaQueryList,
  })
}
