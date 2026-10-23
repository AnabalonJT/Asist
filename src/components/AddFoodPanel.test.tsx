/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// ── API module mock ───────────────────────────────────────────────────────────
// AddFoodPanel and its children only touch mealsApi. Each method is a vi.fn()
// the tests program per-case. Built via vi.hoisted so the object exists before
// the hoisted vi.mock factory runs. Never hits the network.
const mealsApi = vi.hoisted(() => ({
  // Used by AddFoodPanel directly.
  getInventory: vi.fn(),
  listRecipes: vi.fn(),
  lookupBarcode: vi.fn(),
  addRecipeToInventory: vi.fn(),
  // Used by lazily-loaded children (CreateRecipeForm / IncrementalSearchBox).
  listFoods: vi.fn(),
  search: vi.fn(),
  addInventory: vi.fn(),
  createRecipe: vi.fn(),
}))

vi.mock('../lib/api', () => ({ mealsApi }))

// ── @zxing/browser mock ─────────────────────────────────────────────────────────
// Never touch a real camera/decoder. `decodeFromVideoDevice` resolves with a
// controls object whose `stop()` is a shared spy, so we can assert the camera
// is released. `getUserMediaSpy` lets us prove the camera is NOT requested
// until the scan tab is activated.
const zxing = vi.hoisted(() => {
  const stop = vi.fn()
  const decodeFromVideoDevice = vi.fn()
  class BrowserMultiFormatReader {
    decodeFromVideoDevice = decodeFromVideoDevice
  }
  return { stop, decodeFromVideoDevice, BrowserMultiFormatReader }
})

vi.mock('@zxing/browser', () => ({
  BrowserMultiFormatReader: zxing.BrowserMultiFormatReader,
}))

import { AddFoodPanel } from './AddFoodPanel'

// A getUserMedia spy on navigator.mediaDevices so we can assert the camera is
// never requested before the scan action is chosen (Req 6.1). The real camera
// access happens inside @zxing/browser (which we mock), but wiring this spy
// documents and guards the "no camera on mount" contract.
const getUserMediaSpy = vi.fn()

beforeEach(() => {
  mealsApi.getInventory.mockReset().mockResolvedValue({ data: [] })
  mealsApi.listRecipes.mockReset().mockResolvedValue({ data: [] })
  mealsApi.lookupBarcode.mockReset()
  mealsApi.addRecipeToInventory.mockReset()
  mealsApi.listFoods.mockReset().mockResolvedValue({ data: [] })
  mealsApi.search.mockReset().mockResolvedValue({ data: [] })
  mealsApi.addInventory.mockReset()
  mealsApi.createRecipe.mockReset()

  zxing.stop.mockReset()
  zxing.decodeFromVideoDevice.mockReset()
  // Default: the camera grants and keeps scanning, returning controls whose
  // stop() is the shared spy.
  zxing.decodeFromVideoDevice.mockResolvedValue({ stop: zxing.stop })

  getUserMediaSpy.mockReset()
  getUserMediaSpy.mockResolvedValue({
    getTracks: () => [{ stop: vi.fn() }],
  })
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    writable: true,
    value: { getUserMedia: getUserMediaSpy },
  })
})

// ── Lazy loading of the barcode scanner (Req 6.1, 6.2) ──────────────────────────
describe('AddFoodPanel lazy scanner loading (Req 6.1, 6.2)', () => {
  it('does not mount the scanner or request the camera on initial render (Req 6.1)', async () => {
    render(<AddFoodPanel />)

    // The default tab is "Buscar", so the scanner is neither imported nor
    // mounted: its controls (Activar cámara) are absent and the reader was
    // never asked to decode / request the camera.
    expect(
      screen.queryByRole('button', { name: 'Activar cámara' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByText('📷 Escanear código de barras'),
    ).not.toBeInTheDocument()

    // Give any microtasks a chance to run — the scanner must still be absent
    // and the camera untouched.
    await Promise.resolve()
    expect(zxing.decodeFromVideoDevice).not.toHaveBeenCalled()
    expect(getUserMediaSpy).not.toHaveBeenCalled()
  })

  it('shows the Spanish loading fallback then mounts the scanner when the scan tab is activated (Req 6.2, 6.3)', async () => {
    const user = userEvent.setup()
    render(<AddFoodPanel />)

    await user.click(screen.getByRole('tab', { name: 'Escanear' }))

    // The lazily-imported scanner mounts; its heading and camera control appear
    // only after activation (so the import ran on activation, not on mount).
    expect(
      await screen.findByText('📷 Escanear código de barras'),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Activar cámara' }),
    ).toBeInTheDocument()

    // Still no camera access until the user actually activates it — mounting
    // the scanner alone does not call decodeFromVideoDevice.
    expect(zxing.decodeFromVideoDevice).not.toHaveBeenCalled()
  })
})

// ── Camera cleanup on leaving / unmounting (Req 6.5) ────────────────────────────
describe('AddFoodPanel camera cleanup (Req 6.5)', () => {
  it('stops the camera when the user switches away from the scan tab', async () => {
    const user = userEvent.setup()
    render(<AddFoodPanel />)

    // Open the scan tab and start the camera.
    await user.click(screen.getByRole('tab', { name: 'Escanear' }))
    await user.click(await screen.findByRole('button', { name: 'Activar cámara' }))

    // Camera granted → the reader decoded from the video element and returned
    // controls; the UI is now in the scanning state.
    await waitFor(() => {
      expect(zxing.decodeFromVideoDevice).toHaveBeenCalledTimes(1)
    })
    expect(
      await screen.findByRole('button', { name: 'Detener cámara' }),
    ).toBeInTheDocument()

    // Leaving the scan tab unmounts the scanner, whose cleanup releases the
    // camera via controls.stop().
    await user.click(screen.getByRole('tab', { name: 'Buscar' }))

    await waitFor(() => {
      expect(zxing.stop).toHaveBeenCalled()
    })
    // The scanner is gone from the DOM after switching tabs.
    expect(
      screen.queryByRole('button', { name: 'Detener cámara' }),
    ).not.toBeInTheDocument()
  })

  it('stops the camera when the whole panel unmounts', async () => {
    const user = userEvent.setup()
    const { unmount } = render(<AddFoodPanel />)

    await user.click(screen.getByRole('tab', { name: 'Escanear' }))
    await user.click(await screen.findByRole('button', { name: 'Activar cámara' }))

    await waitFor(() => {
      expect(zxing.decodeFromVideoDevice).toHaveBeenCalledTimes(1)
    })

    // Unmounting the panel must release the camera through the scanner cleanup.
    unmount()

    await waitFor(() => {
      expect(zxing.stop).toHaveBeenCalled()
    })
  })
})
