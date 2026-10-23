/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// ── API module mock ───────────────────────────────────────────────────────────
// Program every mealsApi method MealsPage (on load) and the unified
// AddFoodPanel flow (search / inventory / recipes / confirm) call, so the page
// never touches the network. Built via vi.hoisted so the object exists before
// the hoisted vi.mock factory runs.
const mealsApi = vi.hoisted(() => ({
  // Called by MealsPage on initial load (Promise.allSettled).
  listFoods: vi.fn(),
  getInventory: vi.fn(),
  getDietary: vi.fn(),
  getTargets: vi.fn(),
  getPlan: vi.fn(),
  // Called by the unified AddFoodPanel / IncrementalSearchBox / FoodConfirm.
  search: vi.fn(),
  listRecipes: vi.fn(),
  addInventory: vi.fn(),
  addRecipeToInventory: vi.fn(),
  lookupBarcode: vi.fn(),
  // Present for completeness (CreateFoodForm / admin catalog etc.).
  createFood: vi.fn(),
  createRecipe: vi.fn(),
  removeInventory: vi.fn(),
}))

vi.mock('../lib/api', () => ({ mealsApi }))

// MealsPage reads `user?.is_admin` via useAuth; return a non-admin user so the
// admin-only catalog form stays hidden and the hook never needs a provider.
vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'u@test', is_admin: false, telegram_linked: false },
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}))

import { MealsPage } from './MealsPage'
import type { SearchResult } from '../lib/api'

// Force `prefers-reduced-motion`. `reduce=true` makes matchMedia report the
// reduce preference as matched; `false` reports no reduced motion.
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

beforeEach(() => {
  localStorage.clear()
  setReducedMotion(false)

  // Default load resolutions: an empty-but-valid page state.
  mealsApi.listFoods.mockResolvedValue({ data: [] })
  mealsApi.getInventory.mockResolvedValue({ data: [] })
  mealsApi.getDietary.mockResolvedValue({
    data: { vegetarian: false, vegan: false, gluten_free: false, allergens: [] },
  })
  mealsApi.getTargets.mockResolvedValue({ data: { message: 'Sin metas', disclaimer: '' } })
  mealsApi.getPlan.mockResolvedValue({ data: { message: 'Sin plan' } })

  // Default unified-panel resolutions.
  mealsApi.search.mockResolvedValue({ data: [] as SearchResult[] })
  mealsApi.listRecipes.mockResolvedValue({ data: [] })
  mealsApi.addInventory.mockResolvedValue({
    data: { food_id: 1, food_name: 'Avena', grams: 100 },
  })
  mealsApi.addRecipeToInventory.mockResolvedValue({
    data: { recipe_id: 7, recipe_name: 'Avena con leche', grams: 100 },
  })
})

// ── The page mounts the unified panel in place of the old add-food UI ───────────
describe('MealsPage unified Add_Food_Panel (Req 7.1, 7.2)', () => {
  it('renders the unified panel with the five Spanish actions once loaded', async () => {
    render(<MealsPage />)

    // The panel heading appears only after the initial load resolves (the page
    // shows a "Cargando..." loader until then).
    expect(await screen.findByText('Agregar alimento')).toBeInTheDocument()

    // The five tab actions render in Spanish, inside the tablist (Req 7.1).
    const tablist = screen.getByRole('tablist', { name: 'Agregar alimento' })
    const tabs = within(tablist)
    expect(tabs.getByRole('tab', { name: 'Escanear' })).toBeInTheDocument()
    expect(tabs.getByRole('tab', { name: 'Buscar' })).toBeInTheDocument()
    expect(tabs.getByRole('tab', { name: 'Inventario' })).toBeInTheDocument()
    expect(tabs.getByRole('tab', { name: 'Recetas' })).toBeInTheDocument()
    expect(tabs.getByRole('tab', { name: 'Crear nuevo' })).toBeInTheDocument()
  })

  it('defaults to the search tab and does not mount the scanner or full lists', async () => {
    render(<MealsPage />)

    // The search box is the default active tab's content (Req 7.2): only one
    // action's content is shown, not full catalog/pantry lists.
    expect(await screen.findByPlaceholderText('Buscar por nombre')).toBeInTheDocument()

    // The scanner is lazy and the scan tab is not active, so its camera button
    // is not present and getUserMedia is never requested (Req 6.1).
    expect(
      screen.queryByRole('button', { name: 'Activar cámara' }),
    ).not.toBeInTheDocument()

    // The old always-visible add-food section is gone: no full catalog list is
    // rendered up front (only the unified search input drives discovery).
    expect(screen.queryByText('Catálogo (admin)')).not.toBeInTheDocument()
  })

  it('shows only the active action content and hides the others when switching tabs (Req 7.2)', async () => {
    const user = userEvent.setup()
    render(<MealsPage />)

    // Start on search.
    expect(await screen.findByPlaceholderText('Buscar por nombre')).toBeInTheDocument()

    // Switching to Recetas shows the recipes content and hides the search box.
    await user.click(screen.getByRole('tab', { name: 'Recetas' }))
    expect(
      await screen.findByText('Aún no tienes recetas. Créalas en "Crear nuevo".'),
    ).toBeInTheDocument()
    expect(screen.queryByPlaceholderText('Buscar por nombre')).not.toBeInTheDocument()

    // Switching to Inventario shows the (empty) inventory content inside the
    // panel. (The preserved "Inventario / Despensa" page section also shows an
    // empty message, so scope the assertion to the panel's tablist region.)
    await user.click(screen.getByRole('tab', { name: 'Inventario' }))
    const panel = screen
      .getByRole('tablist', { name: 'Agregar alimento' })
      .closest('.card') as HTMLElement
    expect(
      await within(panel).findByText('Tu inventario está vacío.'),
    ).toBeInTheDocument()
    expect(
      screen.queryByText('Aún no tienes recetas. Créalas en "Crear nuevo".'),
    ).not.toBeInTheDocument()
  })
})

// ── Selecting a search result flows into the confirmation step (Req 11.2 / 7.3) ─
describe('MealsPage search → confirmation wiring (Req 7.3)', () => {
  it('routes a catalog search result into the Food confirmation step', async () => {
    const user = userEvent.setup()
    const results: SearchResult[] = [
      { kind: 'catalog', id: 1, name: 'Avena', brand: 'MarcaY', kcal: 389 },
    ]
    mealsApi.search.mockResolvedValue({ data: results })

    render(<MealsPage />)

    // Type into the unified search box; the debounced search resolves with a hit.
    const input = await screen.findByPlaceholderText('Buscar por nombre')
    await user.type(input, 'avena')

    // The result row appears; picking it enters the FoodConfirm step.
    await user.click(await screen.findByText('Avena'))

    // The confirmation step replaces the tab UI with its Spanish prompt and the
    // "Sí, agregar" action (Req 7.3 confirmation before adding).
    expect(
      await screen.findByText('¿Es este el alimento que quieres agregar?'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sí, agregar' })).toBeInTheDocument()
    // The candidate name carried through into the editable form.
    expect(screen.getByDisplayValue('Avena')).toBeInTheDocument()
  })

  it('adds a recipe search result to the inventory as a single unit (Req 7.4)', async () => {
    const user = userEvent.setup()
    const results: SearchResult[] = [
      { kind: 'recipe', id: 7, name: 'Avena con leche', kcal: 120 },
    ]
    mealsApi.search.mockResolvedValue({ data: results })

    render(<MealsPage />)

    const input = await screen.findByPlaceholderText('Buscar por nombre')
    await user.type(input, 'avena')

    await user.click(await screen.findByText('Avena con leche'))

    // A recipe pick adds it to the inventory as one unit, not the confirm step.
    expect(mealsApi.addRecipeToInventory).toHaveBeenCalledWith({
      recipe_id: 7,
      grams: 100,
    })
    expect(
      screen.queryByText('¿Es este el alimento que quieres agregar?'),
    ).not.toBeInTheDocument()
  })
})

// ── prefers-reduced-motion disables the panel's motion transition (Req 7.5) ─────
describe('MealsPage reduced motion (Req 7.5)', () => {
  it('does not apply a motion transition class when reduced motion is requested', async () => {
    setReducedMotion(true)
    const { container } = render(<MealsPage />)

    // Wait for the panel to render.
    await screen.findByText('Agregar alimento')

    // The reduced-motion preference is read in an effect that re-renders the
    // panel; once it settles, the content wrapper carries no transition/
    // animation utility class.
    await waitFor(() => {
      expect(container.querySelector('.transition-opacity')).not.toBeInTheDocument()
    })
    expect(container.querySelector('.duration-150')).not.toBeInTheDocument()
  })

  it('applies the motion transition class when reduced motion is NOT requested (Req 7.5)', async () => {
    setReducedMotion(false)
    const { container } = render(<MealsPage />)

    await screen.findByText('Agregar alimento')

    // Without reduced motion, the content wrapper animates the tab switch.
    expect(container.querySelector('.transition-opacity')).toBeInTheDocument()
  })
})
