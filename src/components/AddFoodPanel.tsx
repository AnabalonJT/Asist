import React, { Suspense, useEffect, useState } from 'react'
import {
  mealsApi,
  FoodCandidate,
  InventoryItem,
  Recipe,
  SearchResult,
} from '../lib/api'
import { IncrementalSearchBox } from './IncrementalSearchBox'
import { FoodConfirm } from './FoodConfirm'

// Lazy-loaded components: only imported (and, for the scanner, only mounted so
// getUserMedia is initialized) when the relevant tab is active (Req 6.1–6.3).
// BarcodeScanner is a NAMED export, so map it to a default for React.lazy.
const BarcodeScanner = React.lazy(() =>
  import('./BarcodeScanner').then((m) => ({ default: m.BarcodeScanner })),
)
// CreateFoodForm and CreateRecipeForm both have default exports.
const CreateFoodForm = React.lazy(() => import('./CreateFoodForm'))
const CreateRecipeForm = React.lazy(() => import('./CreateRecipeForm'))

// Extract the Spanish `detail` from an API error, falling back to a message.
function apiError(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0 && detail[0]?.msg) return detail[0].msg
  return fallback
}

// The five Add_Food_Panel tabs (Req 7.1). English identifiers, Spanish labels.
type Tab = 'scan' | 'search' | 'inventory' | 'recipes' | 'create'

const TABS: { id: Tab; label: string }[] = [
  { id: 'scan', label: 'Escanear' },
  { id: 'search', label: 'Buscar' },
  { id: 'inventory', label: 'Inventario' },
  { id: 'recipes', label: 'Recetas' },
  { id: 'create', label: 'Crear nuevo' },
]

// Detect the user's reduced-motion preference so we can avoid applying motion
// classes to the tab switch (Req 7.5). Read once on mount; harmless default on
// non-browser environments.
function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    setReduced(mq.matches)
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])
  return reduced
}

// Spanish fallback shown while a lazy component is being imported (Req 6.3).
function Loading() {
  return <p className="text-sm text-text-dim">Cargando…</p>
}

interface AddFoodPanelProps {
  onChanged?: () => void // called after a food/recipe is added so the page can refresh
}

// Add_Food_Panel: the inline (no-modal) panel that unifies the add-food actions
// behind tabs — scan, search, inventory, recipes, create new. Only the ACTIVE
// tab's content is rendered (Req 7.1, 7.2): there are no always-visible full
// catalog/pantry lists. The barcode scanner is only imported and mounted when
// the scan tab is active (Req 6.1, 6.2) and releases the camera on unmount
// (Req 6.5), which happens automatically when switching away from scan.
export function AddFoodPanel({ onChanged }: AddFoodPanelProps) {
  const [tab, setTab] = useState<Tab>('search')
  const reducedMotion = usePrefersReducedMotion()

  // When a candidate is set, the Confirmation_Step replaces the active-tab body
  // (mirrors the Meals_Page pattern). `lookupErr` surfaces barcode-lookup and
  // recipe-add failures without crashing the panel.
  const [candidate, setCandidate] = useState<FoodCandidate | null>(null)
  const [lookupErr, setLookupErr] = useState('')

  // Inventory + recipes are fetched lazily, only when their tab becomes active
  // (Req 7.2) — nothing is loaded up front.
  const [inventory, setInventory] = useState<InventoryItem[]>([])
  const [invLoading, setInvLoading] = useState(false)
  const [invErr, setInvErr] = useState('')

  const [recipes, setRecipes] = useState<Recipe[]>([])
  const [recLoading, setRecLoading] = useState(false)
  const [recErr, setRecErr] = useState('')

  // Load the user's own inventory when the Inventario tab is opened.
  useEffect(() => {
    if (tab !== 'inventory') return
    let cancelled = false
    setInvLoading(true)
    setInvErr('')
    mealsApi
      .getInventory()
      .then(({ data }) => {
        if (!cancelled) setInventory(data)
      })
      .catch((e: any) => {
        if (!cancelled) setInvErr(apiError(e, 'No se pudo cargar el inventario.'))
      })
      .finally(() => {
        if (!cancelled) setInvLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [tab])

  // Load the user's recipes when the Recetas tab is opened.
  useEffect(() => {
    if (tab !== 'recipes') return
    let cancelled = false
    setRecLoading(true)
    setRecErr('')
    mealsApi
      .listRecipes()
      .then(({ data }) => {
        if (!cancelled) setRecipes(data)
      })
      .catch((e: any) => {
        if (!cancelled) setRecErr(apiError(e, 'No se pudieron cargar las recetas.'))
      })
      .finally(() => {
        if (!cancelled) setRecLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [tab])

  // ── Selection handlers: route each result to the confirm / add flow ──

  // After FoodConfirm adds the candidate to the inventory, close the confirm
  // step and let the page refresh its data.
  function handleAdded() {
    setCandidate(null)
    onChanged?.()
  }

  // Add a Recipe to the inventory as a single unit, shared by the recipe search
  // result and the recipes-tab list pick (Req 7.4).
  async function addRecipeUnit(recipeId: number) {
    setLookupErr('')
    try {
      // Add the recipe to the inventory as one unit. Grams default to 100 (a
      // recipe's nutrition is per 100 g); the backend validates 1..100000.
      await mealsApi.addRecipeToInventory({ recipe_id: recipeId, grams: 100 })
      onChanged?.()
    } catch (e) {
      setLookupErr(apiError(e, 'No se pudo agregar la receta al inventario.'))
    }
  }

  // Route a search result (Req 7.3): catalog/inventory/off → FoodConfirm;
  // recipe → add to the inventory as a unit.
  function handlePick(result: SearchResult) {
    if (result.kind === 'recipe' && result.id != null) return addRecipeUnit(result.id)
    setCandidate({
      name: result.name,
      barcode: result.barcode ?? null,
      kcal: result.kcal ?? null,
      protein: result.protein ?? null,
      fat: result.fat ?? null,
      carbs: result.carbs ?? null,
      fiber: result.fiber ?? null,
      brand: result.brand ?? null,
      image_url: result.image_url ?? null,
      source: result.kind === 'off' ? 'off' : 'local',
    })
  }

  // Look up a decoded/manual barcode via Food_Barcode, then confirm (Req 6.4).
  async function handleBarcode(code: string) {
    setLookupErr('')
    try {
      const { data } = await mealsApi.lookupBarcode(code)
      setCandidate(data)
    } catch (e) {
      // A 404/503 just shows the Spanish detail; the panel keeps working.
      setLookupErr(apiError(e, 'No se pudo buscar el código.'))
    }
  }

  // Pick an item already in the inventory as an add-target (Req 7.3). Nutrition
  // is unknown here, so FoodConfirm lets the user fill it in and adjust grams.
  function handlePickInventory(item: InventoryItem) {
    setCandidate({
      name: item.food_name,
      barcode: null,
      kcal: null,
      protein: null,
      fat: null,
      carbs: null,
      fiber: null,
      brand: null,
      image_url: null,
      source: 'local',
    })
  }

  // Add a recipe from the recipes tab to the inventory as a unit (Req 7.4).
  function handlePickRecipe(recipe: Recipe) {
    return addRecipeUnit(recipe.id)
  }

  // Jump to the "Crear nuevo" tab when a search yields nothing (Req 7.6).
  function handleCreateNew() {
    setTab('create')
  }

  // Only apply a motion transition when the user has not requested reduced
  // motion (Req 7.5). With reduced motion, no motion classes are applied.
  const contentMotion = reducedMotion ? '' : 'transition-opacity duration-150'

  return (
    <div className="card space-y-4">
      <h2 className="text-base font-semibold text-text-primary">Agregar alimento</h2>

      {/* When a candidate is selected, the Confirmation_Step replaces the tab
          UI entirely (mirrors the Meals_Page pattern). Cancelling clears the
          candidate and restores the active tab. */}
      {candidate ? (
        <FoodConfirm
          candidate={candidate}
          onAdded={handleAdded}
          onCancel={() => setCandidate(null)}
        />
      ) : (
        <>
          {/* Tab bar */}
          <div role="tablist" aria-label="Agregar alimento" className="flex flex-wrap gap-2">
            {TABS.map((t) => {
              const active = t.id === tab
              return (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => setTab(t.id)}
                  className={active ? 'btn-primary text-sm' : 'btn-ghost text-sm'}
                >
                  {t.label}
                </button>
              )
            })}
          </div>

          {/* A barcode lookup / recipe-add failure is shown here without
              tearing down the panel. */}
          {lookupErr && <p className="text-xs text-danger">{lookupErr}</p>}

          {/* Only the active tab's content is rendered (Req 7.2). */}
          <div className={contentMotion}>
            {tab === 'scan' && (
              <Suspense fallback={<Loading />}>
                <BarcodeScanner onDetected={handleBarcode} />
              </Suspense>
            )}

            {tab === 'search' && (
              <IncrementalSearchBox onPick={handlePick} onCreateNew={handleCreateNew} />
            )}

            {tab === 'inventory' && (
              <div className="space-y-2">
                {invLoading && <p className="text-sm text-text-dim">Cargando inventario…</p>}
                {invErr && <p className="text-xs text-danger">{invErr}</p>}
                {!invLoading && !invErr && inventory.length === 0 && (
                  <p className="text-sm text-text-dim">Tu inventario está vacío.</p>
                )}
                {inventory.length > 0 && (
                  <ul className="space-y-1">
                    {inventory.map((item) => (
                      <li key={item.food_id}>
                        <button
                          type="button"
                          onClick={() => handlePickInventory(item)}
                          className="w-full text-left border border-bg-border rounded-lg px-3 py-2 hover:border-accent"
                        >
                          <span className="text-sm text-text-primary">{item.food_name}</span>
                          {item.grams != null && (
                            <span className="text-xs text-text-dim"> · {item.grams} g</span>
                          )}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {tab === 'recipes' && (
              <div className="space-y-2">
                {recLoading && <p className="text-sm text-text-dim">Cargando recetas…</p>}
                {recErr && <p className="text-xs text-danger">{recErr}</p>}
                {!recLoading && !recErr && recipes.length === 0 && (
                  <p className="text-sm text-text-dim">
                    Aún no tienes recetas. Créalas en "Crear nuevo".
                  </p>
                )}
                {recipes.length > 0 && (
                  <ul className="space-y-1">
                    {recipes.map((r) => (
                      <li key={r.id}>
                        <button
                          type="button"
                          onClick={() => handlePickRecipe(r)}
                          className="w-full text-left border border-bg-border rounded-lg px-3 py-2 hover:border-accent"
                        >
                          <span className="text-sm text-text-primary">{r.name}</span>
                          <span className="text-xs text-text-dim">
                            {' '}
                            · {Math.round(r.nutrition.kcal)} kcal/100g
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {tab === 'create' && (
              <div className="space-y-4">
                <Suspense fallback={<Loading />}>
                  <CreateFoodForm onAdded={onChanged} />
                </Suspense>
                <Suspense fallback={<Loading />}>
                  <CreateRecipeForm onCreated={() => onChanged?.()} />
                </Suspense>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
