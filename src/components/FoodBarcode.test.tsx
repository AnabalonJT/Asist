/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// ── API module mock ───────────────────────────────────────────────────────────
// mealsApi methods are vi.fn()s the tests program per-case. Built via
// vi.hoisted so the object exists before the hoisted vi.mock factory runs.
const mealsApi = vi.hoisted(() => ({
  addInventory: vi.fn(),
  searchFood: vi.fn(),
  lookupBarcode: vi.fn(),
}))

vi.mock('../lib/api', () => ({ mealsApi }))

// ── @zxing/browser mock ─────────────────────────────────────────────────────────
// Never touch a real camera/decoder. decodeFromVideoDevice is a vi.fn() each
// test programs: resolve → camera granted, reject → permission denied / no cam.
const zxing = vi.hoisted(() => {
  const decodeFromVideoDevice = vi.fn()
  const stop = vi.fn()
  class BrowserMultiFormatReader {
    decodeFromVideoDevice = decodeFromVideoDevice
  }
  return { decodeFromVideoDevice, stop, BrowserMultiFormatReader }
})

vi.mock('@zxing/browser', () => ({
  BrowserMultiFormatReader: zxing.BrowserMultiFormatReader,
}))

import { BarcodeScanner } from './BarcodeScanner'
import { FoodConfirm } from './FoodConfirm'
import { FoodSearchBox } from './FoodSearchBox'
import type { FoodCandidate } from '../lib/api'

/** Build an axios-like error whose Spanish `detail` the UI surfaces. */
function apiError(detail: string, status = 400) {
  return { response: { status, data: { detail } } }
}

beforeEach(() => {
  mealsApi.addInventory.mockReset()
  mealsApi.searchFood.mockReset()
  mealsApi.lookupBarcode.mockReset()
  zxing.decodeFromVideoDevice.mockReset()
  zxing.stop.mockReset()
})

// ── BarcodeScanner (Req 7.1, 7.3, 7.4) ──────────────────────────────────────────
describe('BarcodeScanner (Req 7.1, 7.3, 7.4)', () => {
  it('starts the camera when permission is granted (Req 7.1)', async () => {
    const user = userEvent.setup()
    // Camera granted: the reader resolves with controls and keeps scanning.
    zxing.decodeFromVideoDevice.mockResolvedValue({ stop: zxing.stop })
    const onDetected = vi.fn()

    render(<BarcodeScanner onDetected={onDetected} />)

    await user.click(screen.getByRole('button', { name: 'Activar cámara' }))

    // The reader was asked to decode from the video element, and the UI flips
    // to the "scanning" state (Detener cámara is now shown).
    await waitFor(() => {
      expect(zxing.decodeFromVideoDevice).toHaveBeenCalledTimes(1)
    })
    expect(
      await screen.findByRole('button', { name: 'Detener cámara' }),
    ).toBeInTheDocument()
  })

  it('shows a Spanish message and keeps manual entry when the camera is denied (Req 7.4)', async () => {
    const user = userEvent.setup()
    // Camera denied / unavailable: the reader rejects.
    zxing.decodeFromVideoDevice.mockRejectedValue(
      Object.assign(new Error('denied'), { name: 'NotAllowedError' }),
    )
    const onDetected = vi.fn()

    render(<BarcodeScanner onDetected={onDetected} />)

    await user.click(screen.getByRole('button', { name: 'Activar cámara' }))

    // Spanish error surfaced and manual entry remains available.
    expect(
      await screen.findByText(
        'No se pudo acceder a la cámara. Puedes ingresar el código manualmente.',
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Buscar código' }),
    ).toBeInTheDocument()
  })

  it('submits a manually typed code via onDetected (Req 7.3)', async () => {
    const user = userEvent.setup()
    const onDetected = vi.fn()

    render(<BarcodeScanner onDetected={onDetected} />)

    await user.type(
      screen.getByPlaceholderText('Ej. 7501234567890'),
      '7501234567890',
    )
    await user.click(screen.getByRole('button', { name: 'Buscar código' }))

    expect(onDetected).toHaveBeenCalledWith('7501234567890')
  })

  it('does not fire onDetected for an empty/whitespace manual code', async () => {
    const user = userEvent.setup()
    const onDetected = vi.fn()

    render(<BarcodeScanner onDetected={onDetected} />)

    await user.type(screen.getByPlaceholderText('Ej. 7501234567890'), '   ')
    await user.click(screen.getByRole('button', { name: 'Buscar código' }))

    expect(onDetected).not.toHaveBeenCalled()
  })
})

// ── FoodConfirm (Req 5.1, 5.2, 5.4, 5.5) ────────────────────────────────────────
const candidate: FoodCandidate = {
  name: 'Yogur natural',
  barcode: '7501234567890',
  kcal: 61,
  protein: 3.5,
  fat: 3.3,
  carbs: 4.7,
  fiber: 0,
  brand: 'MarcaX',
  image_url: 'https://example.test/yogur.jpg',
  source: 'off',
}

describe('FoodConfirm (Req 5.1, 5.2, 5.4, 5.5)', () => {
  it('renders the confirmation text and the candidate values (Req 5.1)', () => {
    render(
      <FoodConfirm candidate={candidate} onAdded={vi.fn()} onCancel={vi.fn()} />,
    )

    // Exact Confirmation_Step heading text.
    expect(
      screen.getByText('¿Es este el alimento que quieres agregar?'),
    ).toBeInTheDocument()
    // Candidate identity + nutrition pre-filled into the editable fields.
    expect(screen.getByDisplayValue('Yogur natural')).toBeInTheDocument()
    expect(screen.getByDisplayValue('7501234567890')).toBeInTheDocument()
    expect(screen.getByDisplayValue('61')).toBeInTheDocument()
    expect(screen.getByDisplayValue('3.5')).toBeInTheDocument()
    // Brand + image auxiliary info shown.
    expect(screen.getByText('MarcaX')).toBeInTheDocument()
    expect(screen.getByAltText('Yogur natural')).toBeInTheDocument()
  })

  it('calls addInventory with the candidate when the user confirms (Req 5.2)', async () => {
    const user = userEvent.setup()
    mealsApi.addInventory.mockResolvedValue({ data: {} })
    const onAdded = vi.fn()

    render(
      <FoodConfirm candidate={candidate} onAdded={onAdded} onCancel={vi.fn()} />,
    )

    await user.click(screen.getByRole('button', { name: 'Sí, agregar' }))

    await waitFor(() => {
      expect(mealsApi.addInventory).toHaveBeenCalledTimes(1)
    })
    expect(mealsApi.addInventory).toHaveBeenCalledWith(
      expect.objectContaining({
        food_name: 'Yogur natural',
        new_food: expect.objectContaining({
          name: 'Yogur natural',
          kcal: 61,
          protein: 3.5,
          fat: 3.3,
          carbs: 4.7,
          barcode: '7501234567890',
        }),
      }),
    )
    // Success callback fired after the API resolved.
    await waitFor(() => expect(onAdded).toHaveBeenCalledTimes(1))
  })

  it('discards without calling the API when the user cancels (Req 5.5)', async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()

    render(
      <FoodConfirm candidate={candidate} onAdded={vi.fn()} onCancel={onCancel} />,
    )

    await user.click(
      screen.getByRole('button', { name: 'No, volver a escanear' }),
    )

    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(mealsApi.addInventory).not.toHaveBeenCalled()
  })

  it('shows the Spanish range error and preserves the form on failure (Req 5.4)', async () => {
    const user = userEvent.setup()
    mealsApi.addInventory.mockRejectedValue(
      apiError('Las calorías deben estar entre 0 y 900.'),
    )
    const onAdded = vi.fn()

    render(
      <FoodConfirm candidate={candidate} onAdded={onAdded} onCancel={vi.fn()} />,
    )

    await user.click(screen.getByRole('button', { name: 'Sí, agregar' }))

    // Spanish detail is surfaced and the form (its values) survives the error.
    expect(
      await screen.findByText('Las calorías deben estar entre 0 y 900.'),
    ).toBeInTheDocument()
    expect(screen.getByDisplayValue('Yogur natural')).toBeInTheDocument()
    expect(onAdded).not.toHaveBeenCalled()
  })
})

// ── FoodSearchBox (Req 7.5) ──────────────────────────────────────────────────────
describe('FoodSearchBox (Req 7.5)', () => {
  it('queries searchFood and renders the candidate results', async () => {
    const user = userEvent.setup()
    const results: FoodCandidate[] = [
      { name: 'Avena', barcode: null, kcal: 389, source: 'local' },
      { name: 'Avena instantánea', brand: 'MarcaY', kcal: 370, source: 'off' },
    ]
    mealsApi.searchFood.mockResolvedValue({ data: results })
    const onPick = vi.fn()

    render(<FoodSearchBox onPick={onPick} />)

    await user.type(screen.getByPlaceholderText('Buscar por nombre'), 'avena')
    await user.click(screen.getByRole('button', { name: 'Buscar' }))

    await waitFor(() => {
      expect(mealsApi.searchFood).toHaveBeenCalledWith('avena')
    })

    // Both candidate rows rendered.
    expect(await screen.findByText('Avena')).toBeInTheDocument()
    expect(screen.getByText('Avena instantánea')).toBeInTheDocument()

    // Picking a row surfaces the chosen candidate.
    await user.click(screen.getByText('Avena'))
    expect(onPick).toHaveBeenCalledWith(results[0])
  })

  it('shows an empty state when the search returns no results', async () => {
    const user = userEvent.setup()
    mealsApi.searchFood.mockResolvedValue({ data: [] })

    render(<FoodSearchBox onPick={vi.fn()} />)

    await user.type(screen.getByPlaceholderText('Buscar por nombre'), 'zzzzz')
    await user.click(screen.getByRole('button', { name: 'Buscar' }))

    expect(await screen.findByText('Sin resultados')).toBeInTheDocument()
  })

  it('does not query when the term is empty', async () => {
    const user = userEvent.setup()

    render(<FoodSearchBox onPick={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: 'Buscar' }))

    expect(mealsApi.searchFood).not.toHaveBeenCalled()
  })
})
