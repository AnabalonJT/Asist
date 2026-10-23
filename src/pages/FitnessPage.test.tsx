/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock the whole API module so the page never touches the network. Every call
// resolves to the minimal shape the page reads on load.
vi.mock('../lib/api', () => {
  const rejected404 = () => Promise.reject({ response: { status: 404 } })
  return {
    fitnessApi: {
      getProfile: vi.fn(rejected404),
      getPlan: vi.fn(() => Promise.resolve({ data: { message: 'Sin rutina' } })),
      getProgress: vi.fn(() => Promise.resolve({ data: { series: [], target_weight_kg: null } })),
      getAdherence: vi.fn(() => Promise.resolve({ data: { available: false, message: 'n/a' } })),
      putProfile: vi.fn(),
      putGoal: vi.fn(),
      postWeight: vi.fn(),
    },
    // GoalWizard (mounted by the page) calls getState on mount.
    goalPlanApi: {
      getState: vi.fn(() =>
        Promise.resolve({
          data: { step: 'profile', profile_complete: false, has_goal: false, has_plan: false, has_routine: false },
        }),
      ),
      generateRoutineChunk: vi.fn(),
    },
  }
})

import { FitnessPage } from './FitnessPage'

describe('FitnessPage — Goal Wizard launch (Req 1.1)', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('renders the "Realizar objetivo" button once the page finishes loading', async () => {
    render(<FitnessPage />)
    // Page shows a loader until loadProfile resolves.
    const button = await screen.findByRole('button', { name: 'Realizar objetivo' })
    expect(button).toBeInTheDocument()
  })

  it('mounts the GoalWizard when the button is clicked', async () => {
    const user = userEvent.setup()
    render(<FitnessPage />)

    const button = await screen.findByRole('button', { name: 'Realizar objetivo' })
    await user.click(button)

    // The wizard renders as a dialog with the Spanish aria-label.
    const dialog = await screen.findByRole('dialog', { name: 'Asistente de objetivo' })
    expect(dialog).toBeInTheDocument()
  })
})
