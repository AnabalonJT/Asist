/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// ── API module mock ───────────────────────────────────────────────────────────
// Calendar fetches a month of activities via the default axios-like client's
// `get`. We program it per test. Rather than freeze the clock (which clashes
// with userEvent/waitFor timers), the fixtures are anchored to the real current
// month so the rendered grid always contains the days under test.
const apiClient = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('../lib/api', () => ({ default: apiClient }))

import { Calendar } from './Calendar'
import type { Activity } from '../lib/api'

const now = new Date()
const YEAR = now.getFullYear()
const MONTH = now.getMonth()

// Two activities share a day early in the current month (the 5th), well within
// every month's length and distinct from the empty day (the 6th) we probe.
const ACTIVITY_DAY = 5
const EMPTY_DAY = 6

/** A strength activity with two sets logged at 08:30 on the activity day. */
const strengthActivity: Activity = {
  id: 1,
  activity_type: 'gym',
  exercise_name: 'Press banca',
  duration_minutes: null,
  distance_km: null,
  calories: 0,
  sets: [
    { reps: 10, weight_kg: 60 },
    { reps: 8, weight_kg: 65 },
  ],
  total_volume: 1120,
  timestamp: new Date(YEAR, MONTH, ACTIVITY_DAY, 8, 30, 0).toISOString(),
}

/** A sport activity with calories logged at 18:00 on the same day. */
const sportActivity: Activity = {
  id: 2,
  activity_type: 'running',
  exercise_name: null,
  duration_minutes: 30,
  distance_km: 5,
  calories: 320,
  sets: [],
  total_volume: 0,
  timestamp: new Date(YEAR, MONTH, ACTIVITY_DAY, 18, 0, 0).toISOString(),
}

beforeEach(() => {
  apiClient.get.mockReset()
  apiClient.get.mockResolvedValue({ data: [strengthActivity, sportActivity] })
})

async function renderCalendar() {
  render(<Calendar />)
  await waitFor(() => expect(apiClient.get).toHaveBeenCalled())
  // Wait for the fetched activities to render (the activity day gets a dot and
  // becomes an accent-styled button); the grid is ready once it's present.
  await screen.findByRole('button', { name: String(ACTIVITY_DAY) })
}

/** Click a day cell by its visible number. Several cells can share a number in
 *  jsdom only if duplicated; here day numbers are unique, so pick the first. */
async function clickDay(user: ReturnType<typeof userEvent.setup>, day: number) {
  const cells = screen.getAllByRole('button', { name: String(day) })
  await user.click(cells[0])
}

describe('Calendar day modal (dashboard UX)', () => {
  it('opens a dialog listing the day activities when a day is clicked', async () => {
    const user = userEvent.setup()
    await renderCalendar()

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    await clickDay(user, ACTIVITY_DAY)

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toBeInTheDocument()
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(screen.getByText('Press banca')).toBeInTheDocument()
    expect(screen.getByText('running')).toBeInTheDocument()
  })

  it('shows the strength sets detail + total volume and the sport calories', async () => {
    const user = userEvent.setup()
    await renderCalendar()

    await clickDay(user, ACTIVITY_DAY)
    await screen.findByRole('dialog')

    // Strength: two series + each set's reps×weight + total volume in kg.
    expect(screen.getByText(/2 series/)).toBeInTheDocument()
    expect(screen.getByText(/10×60kg/)).toBeInTheDocument()
    expect(screen.getByText(/8×65kg/)).toBeInTheDocument()
    expect(screen.getByText(/1[.,]?120 kg/)).toBeInTheDocument()

    // Sport: calories surfaced.
    expect(screen.getByText('320 cal')).toBeInTheDocument()
  })

  it('closes when the X button is pressed', async () => {
    const user = userEvent.setup()
    await renderCalendar()

    await clickDay(user, ACTIVITY_DAY)
    await screen.findByRole('dialog')

    await user.click(screen.getByRole('button', { name: 'Cerrar' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('closes when the backdrop (outside the content) is clicked', async () => {
    const user = userEvent.setup()
    await renderCalendar()

    await clickDay(user, ACTIVITY_DAY)
    const dialog = await screen.findByRole('dialog')

    // Clicking inside the dialog content keeps it open.
    await user.click(screen.getByText('Press banca'))
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    // Clicking the backdrop (the presentation wrapper) closes it.
    const backdrop = dialog.parentElement as HTMLElement
    await user.click(backdrop)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('closes when Escape is pressed', async () => {
    const user = userEvent.setup()
    await renderCalendar()

    await clickDay(user, ACTIVITY_DAY)
    await screen.findByRole('dialog')

    await user.keyboard('{Escape}')

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows an empty state for a day without activities', async () => {
    const user = userEvent.setup()
    await renderCalendar()

    await clickDay(user, EMPTY_DAY)
    await screen.findByRole('dialog')

    expect(screen.getByText('Sin actividades este día')).toBeInTheDocument()
  })
})
