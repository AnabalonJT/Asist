/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, act, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// ── API module mock ───────────────────────────────────────────────────────────
// mealsApi.search is the only method this component calls; it is a vi.fn() the
// tests program per-case. Built via vi.hoisted so the object exists before the
// hoisted vi.mock factory runs. Never hits the network.
const mealsApi = vi.hoisted(() => ({
  search: vi.fn(),
}))

vi.mock('../lib/api', () => ({ mealsApi }))

import { IncrementalSearchBox } from './IncrementalSearchBox'
import type { SearchResult } from '../lib/api'

// The debounce the component implements (SEARCH_DEBOUNCE_MS). Rapid keystrokes
// within this window collapse to a single request fired after the user pauses.
const DEBOUNCE_MS = 300

beforeEach(() => {
  mealsApi.search.mockReset()
  // Default: an empty local+remote result set so the empty state renders.
  mealsApi.search.mockResolvedValue({ data: [] as SearchResult[] })
})

afterEach(() => {
  vi.useRealTimers()
})

describe('IncrementalSearchBox debounce (Req 2.4)', () => {
  // NOTE: these tests drive the input with fireEvent.change rather than
  // userEvent, because userEvent's internal async delays deadlock against
  // Vitest fake timers. fireEvent.change is synchronous, so we control the
  // clock explicitly with advanceTimersByTimeAsync (which also flushes the
  // promise the debounced effect awaits).

  it('does not fire a search until the debounce interval elapses after typing', async () => {
    vi.useFakeTimers()

    render(<IncrementalSearchBox onPick={vi.fn()} />)
    const input = screen.getByPlaceholderText('Buscar por nombre')

    // A single "typed" term sets the value in one change event.
    fireEvent.change(input, { target: { value: 'avena' } })

    // Immediately after typing — before the debounce elapses — no request yet.
    expect(mealsApi.search).not.toHaveBeenCalled()

    // Advance to just before the threshold: still no request.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS - 1)
    })
    expect(mealsApi.search).not.toHaveBeenCalled()

    // Cross the threshold: the single debounced request fires.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })
    expect(mealsApi.search).toHaveBeenCalledTimes(1)
    expect(mealsApi.search).toHaveBeenCalledWith('avena')
  })

  it('fires only ONE search for a burst of rapid keystrokes', async () => {
    vi.useFakeTimers()

    render(<IncrementalSearchBox onPick={vi.fn()} />)
    const input = screen.getByPlaceholderText('Buscar por nombre')

    // Simulate rapid keystrokes: set each growing prefix with only a small
    // gap (< DEBOUNCE_MS) between them, so every keystroke resets the pending
    // timer and none elapses mid-burst.
    const keystrokes = ['a', 'av', 'ave', 'aven', 'avena']
    for (const value of keystrokes) {
      fireEvent.change(input, { target: { value } })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(DEBOUNCE_MS - 100)
      })
    }

    // No request has fired yet — the burst kept resetting the timer.
    expect(mealsApi.search).not.toHaveBeenCalled()

    // Now the user pauses: let the remaining debounce window elapse once.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEBOUNCE_MS)
    })

    // Exactly one request for the whole burst, with the final term.
    expect(mealsApi.search).toHaveBeenCalledTimes(1)
    expect(mealsApi.search).toHaveBeenCalledWith('avena')
  })
})

describe('IncrementalSearchBox empty state (Req 7.6)', () => {
  it('shows no empty state and does not query while the term is empty', async () => {
    vi.useFakeTimers()

    render(<IncrementalSearchBox onPick={vi.fn()} onCreateNew={vi.fn()} />)

    // Let any pending timers run — nothing should be scheduled for an empty term.
    await act(async () => {
      vi.advanceTimersByTime(DEBOUNCE_MS * 2)
    })

    expect(mealsApi.search).not.toHaveBeenCalled()
    // The "create new" empty-state prompt is not shown before any search ran.
    expect(
      screen.queryByText(/¿Quieres crear un alimento o una receta nueva\?/),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Crear nuevo' }),
    ).not.toBeInTheDocument()
  })

  it('shows the Spanish empty state with "Crear nuevo" when the search returns no results', async () => {
    const user = userEvent.setup()
    // Search resolves with zero results → empty state branch.
    mealsApi.search.mockResolvedValue({ data: [] as SearchResult[] })
    const onCreateNew = vi.fn()

    render(<IncrementalSearchBox onPick={vi.fn()} onCreateNew={onCreateNew} />)

    await user.type(screen.getByPlaceholderText('Buscar por nombre'), 'zzzzz')

    // After the debounced search resolves with no results, the prompt appears.
    expect(
      await screen.findByText(
        "No se encontró 'zzzzz'. ¿Quieres crear un alimento o una receta nueva?",
      ),
    ).toBeInTheDocument()

    // The "Crear nuevo" affordance is offered and wired to onCreateNew.
    const createBtn = screen.getByRole('button', { name: 'Crear nuevo' })
    await user.click(createBtn)
    expect(onCreateNew).toHaveBeenCalledTimes(1)
  })

  it('renders results instead of the empty state when the search returns matches', async () => {
    const user = userEvent.setup()
    const results: SearchResult[] = [
      { kind: 'catalog', id: 1, name: 'Avena', brand: 'MarcaY', kcal: 389 },
      { kind: 'recipe', id: 7, name: 'Avena con leche', kcal: 120 },
    ]
    mealsApi.search.mockResolvedValue({ data: results })
    const onPick = vi.fn()

    render(<IncrementalSearchBox onPick={onPick} onCreateNew={vi.fn()} />)

    await user.type(screen.getByPlaceholderText('Buscar por nombre'), 'avena')

    // Both result rows render; the empty-state prompt does not.
    expect(await screen.findByText('Avena')).toBeInTheDocument()
    expect(screen.getByText('Avena con leche')).toBeInTheDocument()
    expect(
      screen.queryByText(/¿Quieres crear un alimento o una receta nueva\?/),
    ).not.toBeInTheDocument()

    // Picking a row surfaces the chosen Search_Result.
    await user.click(screen.getByText('Avena'))
    expect(onPick).toHaveBeenCalledWith(results[0])
  })
})
