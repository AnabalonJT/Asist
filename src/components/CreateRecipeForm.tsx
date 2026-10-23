import { useState, useEffect, useMemo, FormEvent } from 'react'
import { mealsApi, Food, Recipe } from '../lib/api'

// Extract the Spanish `detail` from an API error, falling back to a message.
function apiError(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0 && detail[0]?.msg) return detail[0].msg
  return fallback
}

interface CreateRecipeFormProps {
  onCreated?: (recipe: Recipe) => void
}

// A selected ingredient: a catalog Food plus its mass in grams.
interface SelectedIngredient {
  food: Food
  grams: number
}

// Client-side mirror of the backend `compute_recipe_nutrition`: a grams-weighted
// average of each food's per-100 g values. For each macro, the absolute amount
// contributed by an ingredient is value_per_100g / 100 * grams; summing those and
// renormalizing by total_grams / 100 yields the recipe's per-100 g value. Fiber is
// null only when every ingredient's fiber is null; otherwise missing fiber is 0.
function computeNutrition(ingredients: SelectedIngredient[]) {
  let totalGrams = 0
  let kcal = 0
  let protein = 0
  let fat = 0
  let carbs = 0
  let fiberSum = 0
  let anyFiber = false

  for (const { food, grams } of ingredients) {
    if (!(grams > 0)) continue
    totalGrams += grams
    kcal += (food.kcal / 100) * grams
    protein += (food.protein / 100) * grams
    fat += (food.fat / 100) * grams
    carbs += (food.carbs / 100) * grams
    if (food.fiber != null) {
      anyFiber = true
      fiberSum += (food.fiber / 100) * grams
    }
  }

  if (totalGrams <= 0) {
    return { kcal: 0, protein: 0, fat: 0, carbs: 0, fiber: anyFiber ? 0 : null }
  }

  const factor = 100 / totalGrams
  return {
    kcal: kcal * factor,
    protein: protein * factor,
    fat: fat * factor,
    carbs: carbs * factor,
    fiber: anyFiber ? fiberSum * factor : null,
  }
}

// Round to one decimal for display.
function fmt(v: number): string {
  return (Math.round(v * 10) / 10).toString()
}

// Recipe creation form: pick catalog foods with grams, preview the estimated
// aggregate per-100 g nutrition client-side, and submit to `createRecipe`.
export function CreateRecipeForm({ onCreated }: CreateRecipeFormProps) {
  const [name, setName] = useState('')
  const [catalog, setCatalog] = useState<Food[]>([])
  const [ingredients, setIngredients] = useState<SelectedIngredient[]>([])
  const [selectedFoodId, setSelectedFoodId] = useState('')
  const [grams, setGrams] = useState('')
  const [err, setErr] = useState('')
  const [loadErr, setLoadErr] = useState('')
  const [saving, setSaving] = useState(false)

  // Load the catalog on mount so the user can pick ingredients.
  useEffect(() => {
    let cancelled = false
    mealsApi
      .listFoods()
      .then(({ data }) => {
        if (!cancelled) setCatalog(data)
      })
      .catch((e: any) => {
        if (!cancelled) setLoadErr(apiError(e, 'No se pudo cargar el catálogo de alimentos.'))
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Recompute the estimated nutrition whenever the ingredient list changes.
  const nutrition = useMemo(() => computeNutrition(ingredients), [ingredients])

  function handleAddIngredient() {
    setErr('')
    const foodId = Number(selectedFoodId)
    const food = catalog.find((f) => f.id === foodId)
    if (!food) {
      setErr('Selecciona un alimento.')
      return
    }
    const g = Number(grams)
    if (!(g >= 1 && g <= 100000)) {
      setErr('Los gramos deben estar entre 1 y 100000.')
      return
    }
    setIngredients((prev) => [...prev, { food, grams: g }])
    setSelectedFoodId('')
    setGrams('')
  }

  function handleRemove(index: number) {
    setIngredients((prev) => prev.filter((_, i) => i !== index))
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!name.trim()) {
      setErr('El nombre no puede estar vacío.')
      return
    }
    if (ingredients.length === 0) {
      setErr('Agrega al menos un ingrediente.')
      return
    }
    setSaving(true)
    setErr('')
    try {
      const { data } = await mealsApi.createRecipe({
        name: name.trim(),
        ingredients: ingredients.map((i) => ({ food_id: i.food.id, grams: i.grams })),
      })
      onCreated?.(data)
      // Reset the form for the next recipe.
      setName('')
      setIngredients([])
      setSelectedFoodId('')
      setGrams('')
    } catch (e: any) {
      setErr(apiError(e, 'No se pudo crear la receta.'))
    } finally {
      setSaving(false)
    }
  }

  const disabled = saving || !name.trim() || ingredients.length === 0

  return (
    <form onSubmit={handleSubmit} className="card space-y-3">
      <h2 className="text-sm font-semibold text-text-primary">Crear receta</h2>

      <div>
        <label className="text-xs text-text-secondary">Nombre</label>
        <input
          type="text"
          className="input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={100}
          placeholder="Ej. Ensalada de pollo"
          required
        />
      </div>

      {/* Ingredient picker: a catalog food + grams + "Añadir ingrediente". */}
      <div>
        <label className="text-xs text-text-secondary">Ingredientes</label>
        <div className="grid grid-cols-2 gap-3">
          <select
            className="input"
            value={selectedFoodId}
            onChange={(e) => setSelectedFoodId(e.target.value)}
          >
            <option value="">Selecciona un alimento</option>
            {catalog.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
                {f.brand ? ` — ${f.brand}` : ''}
              </option>
            ))}
          </select>
          <input
            type="number"
            step="1"
            min={1}
            max={100000}
            className="input"
            value={grams}
            onChange={(e) => setGrams(e.target.value)}
            placeholder="Gramos"
          />
        </div>
        <button
          type="button"
          className="btn-ghost text-sm mt-2"
          onClick={handleAddIngredient}
        >
          Añadir ingrediente
        </button>
      </div>

      {loadErr && <p className="text-xs text-danger">{loadErr}</p>}

      {ingredients.length > 0 && (
        <ul className="space-y-1">
          {ingredients.map((ing, i) => (
            <li
              key={`${ing.food.id}-${i}`}
              className="flex items-center justify-between border border-bg-border rounded-lg px-3 py-2"
            >
              <span className="text-sm text-text-primary">
                {ing.food.name}
                <span className="text-xs text-text-dim"> · {ing.grams} g</span>
              </span>
              <button
                type="button"
                className="text-xs text-danger"
                onClick={() => handleRemove(i)}
              >
                Quitar
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* Estimated aggregate nutrition (client-side), per 100 g. */}
      <div className="border border-bg-border rounded-lg px-3 py-2 space-y-1">
        <p className="text-xs text-text-secondary">Nutrición estimada por 100 g</p>
        <div className="grid grid-cols-2 gap-3 text-xs text-text-dim">
          <span>Kcal: {fmt(nutrition.kcal)}</span>
          <span>Proteína: {fmt(nutrition.protein)} g</span>
          <span>Grasa: {fmt(nutrition.fat)} g</span>
          <span>Carbohidratos: {fmt(nutrition.carbs)} g</span>
          <span>Fibra: {nutrition.fiber == null ? '—' : `${fmt(nutrition.fiber)} g`}</span>
        </div>
      </div>

      {err && <p className="text-xs text-danger">{err}</p>}

      <button type="submit" className="btn-primary w-full text-sm" disabled={disabled}>
        {saving ? 'Creando...' : 'Crear receta'}
      </button>
    </form>
  )
}

export default CreateRecipeForm
