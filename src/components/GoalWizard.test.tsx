/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// ── API module mock ───────────────────────────────────────────────────────────
// Every goalPlanApi method is a vi.fn() the tests program per-case. Built via
// vi.hoisted so the object exists before the hoisted vi.mock factory runs.
const goalPlanApi = vi.hoisted(() => ({
  getState: vi.fn(),
  putProfile: vi.fn(),
  putGoal: vi.fn(),
  putEquipment: vi.fn(),
  derivePhases: vi.fn(),
  getPhases: vi.fn(),
  putTrainingDays: vi.fn(),
  generateRoutine: vi.fn(),
  generateRoutineChunk: vi.fn(),
  putRoutine: vi.fn(),
  putActiveTargets: vi.fn(),
  postWeight: vi.fn(),
}))

vi.mock('../lib/api', () => ({ goalPlanApi }))

import { GoalWizard } from './GoalWizard'

// ── Test helpers ───────────────────────────────────────────────────────────────

/** Build an axios-like error whose Spanish `detail` the UI surfaces. */
function apiError(detail: string, status = 400) {
  return { response: { status, data: { detail } } }
}

/** Default WizardState the backend would return, overridable per field. */
function wizardState(step: string, extra: Record<string, unknown> = {}) {
  return {
    data: {
      step,
      profile_complete: false,
      has_goal: false,
      has_plan: false,
      has_routine: false,
      ...extra,
    },
  }
}

/**
 * Force `prefers-reduced-motion`. `reduce=true` makes matchMedia report the
 * reduce preference as matched; `false` reports no reduced motion.
 */
function setReducedMotion(reduce: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: reduce && query.includes('prefers-reduced-motion: reduce'),
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
}

/**
 * Keep the wizard "fresh" so it resumes at the backend's step instead of
 * restarting at `profile` (the stale-session fallback).
 */
function keepSessionFresh() {
  localStorage.setItem('goalWizardLastActivity', String(Date.now()))
}

function renderWizard() {
  const onClose = vi.fn()
  const result = render(<GoalWizard onClose={onClose} />)
  return { onClose, ...result }
}

/**
 * The wizard's `Field` renders a <label> and its <input> as siblings inside one
 * wrapper without an htmlFor association, so getByLabelText cannot resolve them.
 * This finds the input that lives in the same wrapper as a label with `text`.
 */
function fieldInput(text: string | RegExp): HTMLInputElement {
  const label = screen.getByText(text)
  const wrapper = label.parentElement as HTMLElement
  const input = wrapper.querySelector('input') as HTMLInputElement | null
  if (!input) throw new Error(`No input found for field "${text}"`)
  return input
}

const phasePlan = {
  phases: [
    {
      index: 0,
      start_weight: 80,
      end_weight: 77.5,
      weeks: 3,
      kcal: 2100,
      protein_g: 160,
      fat_g: 60,
      carbs_g: 210,
      status: 'active' as const,
      maintenance: false,
    },
  ],
  active_phase: {
    index: 0,
    start_weight: 80,
    end_weight: 77.5,
    weeks: 3,
    kcal: 2100,
    protein_g: 160,
    fat_g: 60,
    carbs_g: 210,
    status: 'active' as const,
    maintenance: false,
  },
  goal_reached: false,
  disclaimer: 'Información orientativa. No es consejo médico.',
}

beforeEach(() => {
  localStorage.clear()
  setReducedMotion(false)
  // Reset default resolutions for each test.
  goalPlanApi.getState.mockReset()
  goalPlanApi.putProfile.mockReset()
  goalPlanApi.putGoal.mockReset()
  goalPlanApi.putEquipment.mockReset()
  goalPlanApi.derivePhases.mockReset()
  goalPlanApi.putTrainingDays.mockReset()
  goalPlanApi.generateRoutineChunk.mockReset()
  goalPlanApi.putActiveTargets.mockReset()
})

afterEach(() => {
  localStorage.clear()
})

// ── Profile step: Spanish error + preserved data (Req 1.4, 2.1) ─────────────────
describe('ProfileStep validation (Req 2.1, 1.4)', () => {
  it('shows the Spanish error from the API and keeps the entered values', async () => {
    const user = userEvent.setup()
    goalPlanApi.getState.mockResolvedValue(wizardState('profile'))
    goalPlanApi.putProfile.mockRejectedValue(
      apiError('El peso debe estar entre 30 y 300 kg.'),
    )

    renderWizard()

    await screen.findByText('Peso actual (kg)')
    await user.type(fieldInput('Peso actual (kg)'), '20')
    await user.type(fieldInput('Altura (cm)'), '175')
    await user.type(fieldInput('Edad'), '30')

    await user.click(screen.getByRole('button', { name: 'Continuar' }))

    // Spanish detail is rendered.
    expect(
      await screen.findByText('El peso debe estar entre 30 y 300 kg.'),
    ).toBeInTheDocument()
    // Entered values are preserved (not cleared) after the error.
    expect(fieldInput('Peso actual (kg)')).toHaveValue(20)
    expect(fieldInput('Altura (cm)')).toHaveValue(175)
    expect(fieldInput('Edad')).toHaveValue(30)
  })
})

// ── Goal step: Spanish error + preserved data (Req 3.1, 1.4) ────────────────────
describe('GoalStep validation (Req 3.1, 1.4)', () => {
  it('shows the Spanish error and preserves the target weight/date', async () => {
    const user = userEvent.setup()
    keepSessionFresh()
    goalPlanApi.getState.mockResolvedValue(wizardState('goal'))
    goalPlanApi.putGoal.mockRejectedValue(
      apiError('La fecha objetivo debe ser posterior a hoy.'),
    )

    renderWizard()

    await screen.findByText('Peso objetivo (kg)')
    await user.type(fieldInput('Peso objetivo (kg)'), '75')
    await user.type(fieldInput('Fecha objetivo'), '2020-01-01')

    await user.click(screen.getByRole('button', { name: /Calcular ritmo/ }))

    expect(
      await screen.findByText('La fecha objetivo debe ser posterior a hoy.'),
    ).toBeInTheDocument()
    expect(fieldInput('Peso objetivo (kg)')).toHaveValue(75)
    expect(fieldInput('Fecha objetivo')).toHaveValue('2020-01-01')
  })
})

// ── Equipment step: Spanish error + preserved selection (Req 4.1, 1.4) ──────────
describe('EquipmentStep validation (Req 4.1, 1.4)', () => {
  it('shows the Spanish error and keeps the selected equipment', async () => {
    const user = userEvent.setup()
    keepSessionFresh()
    goalPlanApi.getState.mockResolvedValue(wizardState('equipment'))
    goalPlanApi.putEquipment.mockRejectedValue(apiError('Equipo inválido: foo.'))

    renderWizard()

    const dumbbells = await screen.findByLabelText(/Mancuernas/)
    await user.click(dumbbells)
    expect(dumbbells).toBeChecked()

    await user.click(screen.getByRole('button', { name: 'Continuar' }))

    expect(await screen.findByText('Equipo inválido: foo.')).toBeInTheDocument()
    // Selection survived the error.
    expect(screen.getByLabelText(/Mancuernas/)).toBeChecked()
  })
})

// ── Diet step: CookingAnimation while loading + reduced motion (Req 6.5, 6.6) ────
describe('DietStep animation (Req 6.5, 6.6)', () => {
  it('shows the CookingAnimation (animated) while deriving phases', async () => {
    keepSessionFresh()
    setReducedMotion(false)
    goalPlanApi.getState.mockResolvedValue(wizardState('diet'))
    // Never resolve: keep the step in its loading state.
    goalPlanApi.derivePhases.mockReturnValue(new Promise(() => {}))

    const { container } = renderWizard()

    // The loading caption from CookingAnimation.
    expect(await screen.findByText('Calculando tus fases...')).toBeInTheDocument()
    // With motion allowed, the themed animation injects keyframes.
    await waitFor(() => {
      expect(container.querySelector('style')?.textContent).toContain('cook-steam')
    })
  })

  it('respects prefers-reduced-motion: static alternative, no steam animation', async () => {
    keepSessionFresh()
    setReducedMotion(true)
    goalPlanApi.getState.mockResolvedValue(wizardState('diet'))
    goalPlanApi.derivePhases.mockReturnValue(new Promise(() => {}))

    const { container } = renderWizard()

    // Static alternative still communicates progress via the caption.
    expect(await screen.findByText('Calculando tus fases...')).toBeInTheDocument()
    // The animated steam paths are not rendered under reduced motion.
    await waitFor(() => {
      const styleText = container.querySelector('style')?.textContent ?? ''
      // Keyframes exist in the stylesheet, but no element references the steam
      // animation when reduced motion is on (steam group is not rendered).
      const animatedEls = container.querySelectorAll('[style*="cook-steam"]')
      expect(animatedEls.length).toBe(0)
      expect(styleText).toContain('cook-steam') // rules present but unused
    })
  })
})

// ── Routine step: incremental progress (Req 9.2) ────────────────────────────────
describe('RoutineStep incremental progress (Req 9.2)', () => {
  it('shows incremental block-by-block progress while generating', async () => {
    const user = userEvent.setup()
    keepSessionFresh()
    goalPlanApi.getState.mockResolvedValue(wizardState('routine'))

    const routine = {
      id: 1,
      goal_type: 'weight_target',
      structure: [{ day: 'Día 1', exercises: [] }],
      disclaimer: 'Orientativo.',
    }
    // First chunk resolves immediately; second chunk hangs so the "in progress"
    // message for a later block stays on screen to assert against.
    goalPlanApi.generateRoutineChunk
      .mockResolvedValueOnce({ data: routine })
      .mockReturnValueOnce(new Promise(() => {}))

    renderWizard()

    await user.click(await screen.findByRole('button', { name: 'Generar rutina' }))

    // Progress updates incrementally: after block 1 completes, block 2 is in
    // progress and the status announces the advance.
    expect(
      await screen.findByText(/Generando bloque 2 de 3/),
    ).toBeInTheDocument()
    expect(screen.getByText(/Bloque 1/)).toBeInTheDocument()
    // Announced politely to assistive tech.
    expect(screen.getByRole('status')).toBeInTheDocument()
  })
})

// ── Summary step: editing active-phase targets (Req 10.1) ───────────────────────
describe('SummaryStep editing (Req 10.1)', () => {
  it('lets the user open the editor and persist targets via putActiveTargets', async () => {
    const user = userEvent.setup()
    keepSessionFresh()

    // Drive the wizard from the diet step forward so a phase plan and routine
    // are captured into reducer state; SummaryStep only offers editing when an
    // active phase exists. Every intermediate API resolves.
    goalPlanApi.getState.mockResolvedValue(wizardState('diet'))
    goalPlanApi.derivePhases.mockResolvedValue({ data: phasePlan })
    goalPlanApi.putTrainingDays.mockResolvedValue({ data: {} })
    goalPlanApi.generateRoutineChunk.mockResolvedValue({
      data: {
        id: 1,
        goal_type: 'weight_target',
        structure: [{ day: 'Día 1', exercises: [] }],
        disclaimer: 'Orientativo.',
      },
    })
    const edited = {
      ...phasePlan,
      active_phase: { ...phasePlan.active_phase, kcal: 1900 },
      phases: [{ ...phasePlan.phases[0], kcal: 1900 }],
    }
    goalPlanApi.putActiveTargets.mockResolvedValue({ data: edited })

    renderWizard()

    // diet → wait for auto-derived phase card, then continue
    await screen.findByText('2100')
    await user.click(await screen.findByRole('button', { name: 'Continuar' }))

    // training_days → continue
    await user.click(await screen.findByRole('button', { name: 'Continuar' }))

    // routine → generate (3 chunks all resolve), then continue
    await user.click(await screen.findByRole('button', { name: 'Generar rutina' }))
    await user.click(await screen.findByRole('button', { name: 'Continuar' }))

    // summary → the edit affordance is present because an active phase exists
    expect(await screen.findByRole('heading', { name: 'Resumen' })).toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: 'Editar metas' }))

    // Change the calories and save.
    await screen.findByText('Calorías (kcal)')
    const kcal = fieldInput('Calorías (kcal)')
    await user.clear(kcal)
    await user.type(kcal, '1900')
    await user.click(screen.getByRole('button', { name: 'Guardar metas' }))

    // Edit persisted through the API and the success message is shown.
    await waitFor(() => {
      expect(goalPlanApi.putActiveTargets).toHaveBeenCalledWith(
        expect.objectContaining({ kcal: 1900 }),
      )
    })
    expect(await screen.findByText('✅ Metas actualizadas')).toBeInTheDocument()
  })

  it('shows the Spanish error and preserves edited values when targets are invalid (Req 10.1)', async () => {
    const user = userEvent.setup()
    keepSessionFresh()

    goalPlanApi.getState.mockResolvedValue(wizardState('diet'))
    goalPlanApi.derivePhases.mockResolvedValue({ data: phasePlan })
    goalPlanApi.putTrainingDays.mockResolvedValue({ data: {} })
    goalPlanApi.generateRoutineChunk.mockResolvedValue({
      data: {
        id: 1,
        goal_type: 'weight_target',
        structure: [{ day: 'Día 1', exercises: [] }],
        disclaimer: 'Orientativo.',
      },
    })
    goalPlanApi.putActiveTargets.mockRejectedValue(
      apiError('Las calorías deben estar entre 800 y 6000.'),
    )

    renderWizard()

    await screen.findByText('2100')
    await user.click(await screen.findByRole('button', { name: 'Continuar' }))
    await user.click(await screen.findByRole('button', { name: 'Continuar' }))
    await user.click(await screen.findByRole('button', { name: 'Generar rutina' }))
    await user.click(await screen.findByRole('button', { name: 'Continuar' }))

    await user.click(await screen.findByRole('button', { name: 'Editar metas' }))
    await screen.findByText('Calorías (kcal)')
    const kcal = fieldInput('Calorías (kcal)')
    await user.clear(kcal)
    await user.type(kcal, '100')
    await user.click(screen.getByRole('button', { name: 'Guardar metas' }))

    // Spanish error shown; the invalid value the user typed is preserved.
    expect(
      await screen.findByText('Las calorías deben estar entre 800 y 6000.'),
    ).toBeInTheDocument()
    expect(fieldInput('Calorías (kcal)')).toHaveValue(100)
  })
})
