import { useEffect, useState, FormEvent } from 'react'
import {
  mealsApi,
  Food,
  FoodInput,
  InventoryItem,
  Dietary,
  Targets,
  MealPlan,
} from '../lib/api'
import { useAuth } from '../hooks/useAuth'

function apiError(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0 && detail[0]?.msg) return detail[0].msg
  return fallback
}

const SOURCE_LABELS: Record<string, string> = {
  derived: 'derivadas',
  manual: 'manuales',
}

type TargetsResponse = Targets | { message: string; disclaimer: string }

function isTargets(t: TargetsResponse | null): t is Targets {
  return t != null && 'kcal' in t
}

type NewFoodForm = {
  kcal: string
  protein: string
  fat: string
  carbs: string
  fiber: string
  is_meat: boolean
  is_animal: boolean
  has_gluten: boolean
}

const EMPTY_NEW_FOOD: NewFoodForm = {
  kcal: '',
  protein: '',
  fat: '',
  carbs: '',
  fiber: '',
  is_meat: false,
  is_animal: false,
  has_gluten: false,
}

export function MealsPage() {
  const { user } = useAuth()

  // ── Catálogo ──
  const [foods, setFoods] = useState<Food[]>([])

  // ── Inventario (alta) ──
  const [invFoodName, setInvFoodName] = useState('')
  const [invGrams, setInvGrams] = useState('')
  const [newFood, setNewFood] = useState<NewFoodForm>(EMPTY_NEW_FOOD)
  const [inventory, setInventory] = useState<InventoryItem[]>([])
  const [invErr, setInvErr] = useState('')
  const [invMsg, setInvMsg] = useState('')
  const [savingInv, setSavingInv] = useState(false)

  // ── Catálogo admin ──
  const [catName, setCatName] = useState('')
  const [catFood, setCatFood] = useState<NewFoodForm>(EMPTY_NEW_FOOD)
  const [catErr, setCatErr] = useState('')
  const [catMsg, setCatMsg] = useState('')
  const [savingCat, setSavingCat] = useState(false)

  // ── Preferencias / restricciones ──
  const [dietary, setDietary] = useState<Dietary>({
    vegetarian: false,
    vegan: false,
    gluten_free: false,
    allergens: [],
  })
  const [allergenInput, setAllergenInput] = useState('')
  const [dietErr, setDietErr] = useState('')
  const [dietMsg, setDietMsg] = useState('')
  const [savingDiet, setSavingDiet] = useState(false)

  // ── Metas ──
  const [targets, setTargets] = useState<TargetsResponse | null>(null)
  const [manualKcal, setManualKcal] = useState('')
  const [manualProtein, setManualProtein] = useState('')
  const [manualFat, setManualFat] = useState('')
  const [manualCarbs, setManualCarbs] = useState('')
  const [targetsErr, setTargetsErr] = useState('')
  const [targetsMsg, setTargetsMsg] = useState('')
  const [savingTargets, setSavingTargets] = useState(false)
  const [deriving, setDeriving] = useState(false)

  // ── Plan ──
  const [plan, setPlan] = useState<MealPlan | null>(null)
  const [planMessage, setPlanMessage] = useState('')
  const [planErr, setPlanErr] = useState('')
  const [generating, setGenerating] = useState(false)

  // ── Lista de compras ──
  const [shopping, setShopping] = useState<{ food_name: string; grams: number }[] | null>(null)
  const [shoppingErr, setShoppingErr] = useState('')
  const [loadingShopping, setLoadingShopping] = useState(false)

  // ── Loading inicial ──
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.allSettled([
      loadFoods(),
      loadInventory(),
      loadDietary(),
      loadTargets(),
      loadPlan(),
    ]).finally(() => setLoading(false))
  }, [])

  async function loadFoods() {
    try {
      const { data } = await mealsApi.listFoods()
      setFoods(data)
    } catch {
      setFoods([])
    }
  }

  async function loadInventory() {
    try {
      const { data } = await mealsApi.getInventory()
      setInventory(data)
    } catch {
      setInventory([])
    }
  }

  async function loadDietary() {
    try {
      const { data } = await mealsApi.getDietary()
      setDietary({
        vegetarian: !!data.vegetarian,
        vegan: !!data.vegan,
        gluten_free: !!data.gluten_free,
        allergens: Array.isArray(data.allergens) ? data.allergens : [],
      })
    } catch {
      /* perfil ausente: se dejan los valores por defecto */
    }
  }

  async function loadTargets() {
    try {
      const { data } = await mealsApi.getTargets()
      setTargets(data)
    } catch {
      setTargets(null)
    }
  }

  async function loadPlan() {
    try {
      const { data } = await mealsApi.getPlan()
      if ('structure' in data) {
        setPlan(data)
        setPlanMessage('')
      } else {
        setPlan(null)
        setPlanMessage(data.message)
      }
    } catch {
      setPlan(null)
    }
  }

  const catalogHasFood = (name: string): boolean => {
    const norm = name.trim().toLowerCase()
    return foods.some((f) => f.name.trim().toLowerCase() === norm)
  }

  const invNeedsNewFood = invFoodName.trim().length > 0 && !catalogHasFood(invFoodName)

  function buildFoodInput(name: string, form: NewFoodForm): FoodInput {
    return {
      name: name.trim(),
      kcal: Number(form.kcal),
      protein: Number(form.protein),
      fat: Number(form.fat),
      carbs: Number(form.carbs),
      fiber: form.fiber === '' ? null : Number(form.fiber),
      is_meat: form.is_meat,
      is_animal: form.is_animal,
      has_gluten: form.has_gluten,
    }
  }

  async function addInventory(e: FormEvent) {
    e.preventDefault()
    setSavingInv(true)
    setInvErr('')
    setInvMsg('')
    try {
      const payload: {
        food_name: string
        quantity_grams?: number | null
        new_food?: FoodInput | null
      } = {
        food_name: invFoodName.trim(),
        quantity_grams: invGrams === '' ? null : Number(invGrams),
      }
      if (invNeedsNewFood) {
        payload.new_food = buildFoodInput(invFoodName, newFood)
      }
      await mealsApi.addInventory(payload)
      setInvMsg('✅ Alimento agregado al inventario')
      setInvFoodName('')
      setInvGrams('')
      setNewFood(EMPTY_NEW_FOOD)
      await Promise.all([loadInventory(), loadFoods()])
    } catch (err: any) {
      setInvErr(apiError(err, 'No se pudo agregar al inventario.'))
    } finally {
      setSavingInv(false)
    }
  }

  async function removeInventory(foodId: number) {
    setInvErr('')
    setInvMsg('')
    try {
      await mealsApi.removeInventory(foodId)
      await loadInventory()
    } catch (err: any) {
      setInvErr(apiError(err, 'No se pudo quitar del inventario.'))
    }
  }

  async function createFood(e: FormEvent) {
    e.preventDefault()
    setSavingCat(true)
    setCatErr('')
    setCatMsg('')
    try {
      await mealsApi.createFood(buildFoodInput(catName, catFood))
      setCatMsg('✅ Alimento creado en el catálogo')
      setCatName('')
      setCatFood(EMPTY_NEW_FOOD)
      await loadFoods()
    } catch (err: any) {
      setCatErr(apiError(err, 'No se pudo crear el alimento.'))
    } finally {
      setSavingCat(false)
    }
  }

  async function deleteFood(id: number) {
    setCatErr('')
    setCatMsg('')
    try {
      await mealsApi.deleteFood(id)
      await loadFoods()
    } catch (err: any) {
      setCatErr(apiError(err, 'No se pudo eliminar el alimento.'))
    }
  }

  function addAllergen() {
    const val = allergenInput.trim()
    if (!val) return
    if (dietary.allergens.some((a) => a.toLowerCase() === val.toLowerCase())) {
      setAllergenInput('')
      return
    }
    setDietary((d) => ({ ...d, allergens: [...d.allergens, val] }))
    setAllergenInput('')
  }

  function removeAllergen(a: string) {
    setDietary((d) => ({ ...d, allergens: d.allergens.filter((x) => x !== a) }))
  }

  async function saveDietary(e: FormEvent) {
    e.preventDefault()
    setSavingDiet(true)
    setDietErr('')
    setDietMsg('')
    try {
      const { data } = await mealsApi.putDietary(dietary)
      setDietary({
        vegetarian: !!data.vegetarian,
        vegan: !!data.vegan,
        gluten_free: !!data.gluten_free,
        allergens: Array.isArray(data.allergens) ? data.allergens : [],
      })
      setDietMsg('✅ Preferencias guardadas')
    } catch (err: any) {
      setDietErr(apiError(err, 'No se pudieron guardar las preferencias.'))
    } finally {
      setSavingDiet(false)
    }
  }

  async function deriveTargets() {
    setDeriving(true)
    setTargetsErr('')
    setTargetsMsg('')
    try {
      const { data } = await mealsApi.deriveTargets()
      setTargets(data)
      setTargetsMsg('✅ Metas derivadas del fitness')
    } catch (err: any) {
      setTargetsErr(apiError(err, 'No se pudieron derivar las metas.'))
    } finally {
      setDeriving(false)
    }
  }

  async function saveManualTargets(e: FormEvent) {
    e.preventDefault()
    setSavingTargets(true)
    setTargetsErr('')
    setTargetsMsg('')
    try {
      const { data } = await mealsApi.putTargets({
        kcal: Number(manualKcal),
        protein_g: Number(manualProtein),
        fat_g: Number(manualFat),
        carbs_g: Number(manualCarbs),
      })
      setTargets(data)
      setTargetsMsg('✅ Metas manuales guardadas')
      setManualKcal('')
      setManualProtein('')
      setManualFat('')
      setManualCarbs('')
    } catch (err: any) {
      setTargetsErr(apiError(err, 'No se pudieron guardar las metas.'))
    } finally {
      setSavingTargets(false)
    }
  }

  async function generatePlan() {
    setGenerating(true)
    setPlanErr('')
    try {
      const { data } = await mealsApi.generatePlan()
      setPlan(data)
      setPlanMessage('')
    } catch (err: any) {
      setPlanErr(apiError(err, 'No se pudo generar el plan. Intenta de nuevo.'))
    } finally {
      setGenerating(false)
    }
  }

  async function loadShoppingList() {
    setLoadingShopping(true)
    setShoppingErr('')
    try {
      const { data } = await mealsApi.getShoppingList()
      setShopping(data)
    } catch (err: any) {
      setShopping(null)
      setShoppingErr(apiError(err, 'No se pudo obtener la lista de compras.'))
    } finally {
      setLoadingShopping(false)
    }
  }

  if (loading) {
    return <div className="text-sm text-text-dim py-8 text-center">Cargando...</div>
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-text-primary">🍽️ Comidas</h1>
        <p className="text-xs text-text-dim mt-1">
          Configura tu despensa, restricciones y metas para generar un plan de comidas.
        </p>
      </div>

      {/* ── Inventario / Despensa ── */}
      <div className="card">
        <h2 className="text-sm font-semibold text-text-primary mb-3">🥫 Inventario / Despensa</h2>

        <form onSubmit={addInventory} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-text-secondary">Alimento</label>
              <input
                type="text"
                className="input"
                value={invFoodName}
                onChange={(e) => setInvFoodName(e.target.value)}
                placeholder="Ej. Pollo"
                required
              />
            </div>
            <div>
              <label className="text-xs text-text-secondary">Cantidad (g)</label>
              <input
                type="number"
                step="1"
                className="input"
                value={invGrams}
                onChange={(e) => setInvGrams(e.target.value)}
                placeholder="Opcional"
              />
            </div>
          </div>

          {invNeedsNewFood && (
            <div className="border border-bg-border rounded-lg p-3 space-y-3">
              <p className="text-xs text-text-secondary">
                Este alimento no está en el catálogo. Ingresa sus valores por 100 g:
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-text-secondary">Kcal</label>
                  <input
                    type="number"
                    step="0.1"
                    className="input"
                    value={newFood.kcal}
                    onChange={(e) => setNewFood({ ...newFood, kcal: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label className="text-xs text-text-secondary">Proteína (g)</label>
                  <input
                    type="number"
                    step="0.1"
                    className="input"
                    value={newFood.protein}
                    onChange={(e) => setNewFood({ ...newFood, protein: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label className="text-xs text-text-secondary">Grasa (g)</label>
                  <input
                    type="number"
                    step="0.1"
                    className="input"
                    value={newFood.fat}
                    onChange={(e) => setNewFood({ ...newFood, fat: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label className="text-xs text-text-secondary">Carbohidratos (g)</label>
                  <input
                    type="number"
                    step="0.1"
                    className="input"
                    value={newFood.carbs}
                    onChange={(e) => setNewFood({ ...newFood, carbs: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label className="text-xs text-text-secondary">Fibra (g, opcional)</label>
                  <input
                    type="number"
                    step="0.1"
                    className="input"
                    value={newFood.fiber}
                    onChange={(e) => setNewFood({ ...newFood, fiber: e.target.value })}
                  />
                </div>
              </div>
              <div className="flex flex-wrap gap-4">
                <label className="flex items-center gap-2 text-sm text-text-primary cursor-pointer">
                  <input
                    type="checkbox"
                    checked={newFood.is_meat}
                    onChange={(e) => setNewFood({ ...newFood, is_meat: e.target.checked })}
                  />
                  Es carne
                </label>
                <label className="flex items-center gap-2 text-sm text-text-primary cursor-pointer">
                  <input
                    type="checkbox"
                    checked={newFood.is_animal}
                    onChange={(e) => setNewFood({ ...newFood, is_animal: e.target.checked })}
                  />
                  Origen animal
                </label>
                <label className="flex items-center gap-2 text-sm text-text-primary cursor-pointer">
                  <input
                    type="checkbox"
                    checked={newFood.has_gluten}
                    onChange={(e) => setNewFood({ ...newFood, has_gluten: e.target.checked })}
                  />
                  Contiene gluten
                </label>
              </div>
            </div>
          )}

          {invErr && <p className="text-xs text-danger">{invErr}</p>}
          {invMsg && <p className="text-xs text-success">{invMsg}</p>}

          <button type="submit" className="btn-primary w-full text-sm" disabled={savingInv}>
            {savingInv ? 'Agregando...' : 'Agregar al inventario'}
          </button>
        </form>

        {/* Inventario actual */}
        <div className="mt-4 border-t border-bg-border pt-3">
          <h3 className="text-xs font-semibold text-text-secondary mb-2">Tu inventario</h3>
          {inventory.length === 0 ? (
            <p className="text-sm text-text-dim">Tu inventario está vacío.</p>
          ) : (
            <ul className="space-y-1">
              {inventory.map((item) => (
                <li
                  key={item.food_id}
                  className="flex items-center justify-between text-sm text-text-secondary"
                >
                  <span>
                    <span className="text-text-primary">{item.food_name}</span>
                    {item.grams != null ? ` — ${item.grams} g` : ''}
                  </span>
                  <button
                    onClick={() => removeInventory(item.food_id)}
                    className="btn-ghost text-xs text-danger"
                  >
                    Quitar
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Catálogo (referencia) */}
        <div className="mt-4 border-t border-bg-border pt-3">
          <h3 className="text-xs font-semibold text-text-secondary mb-2">
            Catálogo de alimentos
          </h3>
          {foods.length === 0 ? (
            <p className="text-sm text-text-dim">No hay alimentos en el catálogo.</p>
          ) : (
            <ul className="space-y-1">
              {foods.map((f) => (
                <li
                  key={f.id}
                  className="flex items-center justify-between text-sm text-text-secondary"
                >
                  <span>
                    <span className="text-text-primary">{f.name}</span>
                    {` — ${f.kcal} kcal/100g`}
                  </span>
                  {user?.is_admin && (
                    <button
                      onClick={() => deleteFood(f.id)}
                      className="btn-ghost text-xs text-danger"
                    >
                      Eliminar
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Catálogo admin */}
        {user?.is_admin && (
          <div className="mt-4 border-t border-bg-border pt-3">
            <h3 className="text-xs font-semibold text-text-secondary mb-2">Catálogo (admin)</h3>
            <form onSubmit={createFood} className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-text-secondary">Nombre</label>
                  <input
                    type="text"
                    className="input"
                    value={catName}
                    onChange={(e) => setCatName(e.target.value)}
                    required
                  />
                </div>
                <div>
                  <label className="text-xs text-text-secondary">Kcal/100g</label>
                  <input
                    type="number"
                    step="0.1"
                    className="input"
                    value={catFood.kcal}
                    onChange={(e) => setCatFood({ ...catFood, kcal: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label className="text-xs text-text-secondary">Proteína (g)</label>
                  <input
                    type="number"
                    step="0.1"
                    className="input"
                    value={catFood.protein}
                    onChange={(e) => setCatFood({ ...catFood, protein: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label className="text-xs text-text-secondary">Grasa (g)</label>
                  <input
                    type="number"
                    step="0.1"
                    className="input"
                    value={catFood.fat}
                    onChange={(e) => setCatFood({ ...catFood, fat: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label className="text-xs text-text-secondary">Carbohidratos (g)</label>
                  <input
                    type="number"
                    step="0.1"
                    className="input"
                    value={catFood.carbs}
                    onChange={(e) => setCatFood({ ...catFood, carbs: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label className="text-xs text-text-secondary">Fibra (g, opcional)</label>
                  <input
                    type="number"
                    step="0.1"
                    className="input"
                    value={catFood.fiber}
                    onChange={(e) => setCatFood({ ...catFood, fiber: e.target.value })}
                  />
                </div>
              </div>
              <div className="flex flex-wrap gap-4">
                <label className="flex items-center gap-2 text-sm text-text-primary cursor-pointer">
                  <input
                    type="checkbox"
                    checked={catFood.is_meat}
                    onChange={(e) => setCatFood({ ...catFood, is_meat: e.target.checked })}
                  />
                  Es carne
                </label>
                <label className="flex items-center gap-2 text-sm text-text-primary cursor-pointer">
                  <input
                    type="checkbox"
                    checked={catFood.is_animal}
                    onChange={(e) => setCatFood({ ...catFood, is_animal: e.target.checked })}
                  />
                  Origen animal
                </label>
                <label className="flex items-center gap-2 text-sm text-text-primary cursor-pointer">
                  <input
                    type="checkbox"
                    checked={catFood.has_gluten}
                    onChange={(e) => setCatFood({ ...catFood, has_gluten: e.target.checked })}
                  />
                  Contiene gluten
                </label>
              </div>

              {catErr && <p className="text-xs text-danger">{catErr}</p>}
              {catMsg && <p className="text-xs text-success">{catMsg}</p>}

              <button type="submit" className="btn-primary w-full text-sm" disabled={savingCat}>
                {savingCat ? 'Creando...' : 'Crear alimento'}
              </button>
            </form>
          </div>
        )}
      </div>

      {/* ── Preferencias / Restricciones ── */}
      <div className="card">
        <h2 className="text-sm font-semibold text-text-primary mb-3">
          🥗 Preferencias / Restricciones
        </h2>
        <form onSubmit={saveDietary} className="space-y-3">
          <div className="flex flex-wrap gap-4">
            <label className="flex items-center gap-2 text-sm text-text-primary cursor-pointer">
              <input
                type="checkbox"
                checked={dietary.vegetarian}
                onChange={(e) => setDietary({ ...dietary, vegetarian: e.target.checked })}
              />
              Vegetariano
            </label>
            <label className="flex items-center gap-2 text-sm text-text-primary cursor-pointer">
              <input
                type="checkbox"
                checked={dietary.vegan}
                onChange={(e) => setDietary({ ...dietary, vegan: e.target.checked })}
              />
              Vegano
            </label>
            <label className="flex items-center gap-2 text-sm text-text-primary cursor-pointer">
              <input
                type="checkbox"
                checked={dietary.gluten_free}
                onChange={(e) => setDietary({ ...dietary, gluten_free: e.target.checked })}
              />
              Sin gluten
            </label>
          </div>

          <div>
            <label className="text-xs text-text-secondary">Alérgenos</label>
            <div className="flex gap-2 mt-1">
              <input
                type="text"
                className="input"
                value={allergenInput}
                onChange={(e) => setAllergenInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    addAllergen()
                  }
                }}
                placeholder="Ej. maní"
              />
              <button type="button" onClick={addAllergen} className="btn-ghost text-sm">
                Agregar
              </button>
            </div>
            {dietary.allergens.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-2">
                {dietary.allergens.map((a) => (
                  <span
                    key={a}
                    className="inline-flex items-center gap-1 text-xs text-text-primary bg-bg-surface border border-bg-border rounded-full px-2 py-0.5"
                  >
                    {a}
                    <button
                      type="button"
                      onClick={() => removeAllergen(a)}
                      className="text-text-dim hover:text-danger"
                      aria-label={`Quitar ${a}`}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          {dietErr && <p className="text-xs text-danger">{dietErr}</p>}
          {dietMsg && <p className="text-xs text-success">{dietMsg}</p>}

          <button type="submit" className="btn-primary w-full text-sm" disabled={savingDiet}>
            {savingDiet ? 'Guardando...' : 'Guardar preferencias'}
          </button>
        </form>
      </div>

      {/* ── Metas nutricionales ── */}
      <div className="card">
        <h2 className="text-sm font-semibold text-text-primary mb-3">🎯 Metas nutricionales</h2>

        {isTargets(targets) ? (
          <div className="space-y-1 mb-3">
            <p className="text-sm text-text-primary">
              {targets.kcal} kcal — {targets.protein_g} g proteína, {targets.fat_g} g grasa,{' '}
              {targets.carbs_g} g carbohidratos
            </p>
            <p className="text-xs text-text-secondary">
              Metas {SOURCE_LABELS[targets.source] ?? targets.source}
            </p>
            {targets.disclaimer && (
              <p className="text-xs text-text-dim">{targets.disclaimer}</p>
            )}
          </div>
        ) : targets && 'message' in targets ? (
          <div className="space-y-1 mb-3">
            <p className="text-sm text-text-dim">{targets.message}</p>
            {targets.disclaimer && (
              <p className="text-xs text-text-dim">{targets.disclaimer}</p>
            )}
          </div>
        ) : (
          <p className="text-sm text-text-dim mb-3">Aún no tienes metas configuradas.</p>
        )}

        <button
          type="button"
          onClick={deriveTargets}
          className="btn-ghost text-sm mb-4"
          disabled={deriving}
        >
          {deriving ? 'Derivando...' : 'Derivar del fitness'}
        </button>

        <form onSubmit={saveManualTargets} className="space-y-3">
          <p className="text-xs text-text-secondary">O ingresa metas manuales:</p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-text-secondary">Kcal</label>
              <input
                type="number"
                step="1"
                className="input"
                value={manualKcal}
                onChange={(e) => setManualKcal(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="text-xs text-text-secondary">Proteína (g)</label>
              <input
                type="number"
                step="0.1"
                className="input"
                value={manualProtein}
                onChange={(e) => setManualProtein(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="text-xs text-text-secondary">Grasa (g)</label>
              <input
                type="number"
                step="0.1"
                className="input"
                value={manualFat}
                onChange={(e) => setManualFat(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="text-xs text-text-secondary">Carbohidratos (g)</label>
              <input
                type="number"
                step="0.1"
                className="input"
                value={manualCarbs}
                onChange={(e) => setManualCarbs(e.target.value)}
                required
              />
            </div>
          </div>

          {targetsErr && <p className="text-xs text-danger">{targetsErr}</p>}
          {targetsMsg && <p className="text-xs text-success">{targetsMsg}</p>}

          <button type="submit" className="btn-primary w-full text-sm" disabled={savingTargets}>
            {savingTargets ? 'Guardando...' : 'Guardar metas manuales'}
          </button>
        </form>
      </div>

      {/* ── Plan de comidas ── */}
      <div className="card">
        <h2 className="text-sm font-semibold text-text-primary mb-3">📅 Plan de comidas</h2>
        <button
          onClick={generatePlan}
          className="btn-primary w-full text-sm mb-3"
          disabled={generating}
        >
          {generating ? 'Generando...' : 'Generar plan'}
        </button>

        {planErr && (
          <div className="mb-3">
            <p className="text-xs text-danger">{planErr}</p>
            <button onClick={generatePlan} className="btn-ghost text-xs mt-1" disabled={generating}>
              Reintentar
            </button>
          </div>
        )}

        {planMessage && !plan && <p className="text-sm text-text-dim">{planMessage}</p>}

        {plan && (
          <div className="space-y-4">
            {plan.structure.map((day, di) => (
              <div key={di} className="border border-bg-border rounded-lg p-3">
                <h3 className="text-sm font-semibold text-accent mb-2">{day.day}</h3>
                <div className="space-y-2">
                  {day.meals.map((meal, mi) => (
                    <div key={mi}>
                      <p className="text-xs font-medium text-text-secondary">{meal.type}</p>
                      <ul className="space-y-0.5">
                        {meal.items.map((item, ii) => (
                          <li key={ii} className="text-sm text-text-secondary">
                            <span className="text-text-primary">{item.food_name}</span>
                            {` (${item.grams}g)`}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-text-dim mt-2 border-t border-bg-border pt-2">
                  Total: {day.totals.kcal} kcal — {day.totals.protein_g} g P, {day.totals.fat_g} g
                  G, {day.totals.carbs_g} g C
                </p>
              </div>
            ))}
            {plan.disclaimer && <p className="text-xs text-text-dim">{plan.disclaimer}</p>}
          </div>
        )}
      </div>

      {/* ── Lista de compras ── */}
      <div className="card">
        <h2 className="text-sm font-semibold text-text-primary mb-3">🛒 Lista de compras</h2>
        <button
          onClick={loadShoppingList}
          className="btn-primary w-full text-sm mb-3"
          disabled={loadingShopping}
        >
          {loadingShopping ? 'Cargando...' : 'Ver lista de compras'}
        </button>

        {shoppingErr && <p className="text-xs text-danger">{shoppingErr}</p>}

        {shopping != null && !shoppingErr && (
          shopping.length === 0 ? (
            <p className="text-sm text-text-dim">
              No necesitas comprar nada, tu inventario cubre el plan.
            </p>
          ) : (
            <ul className="space-y-1">
              {shopping.map((item, i) => (
                <li key={i} className="text-sm text-text-secondary">
                  <span className="text-text-primary">{item.food_name}</span>
                  {` — ${item.grams} g`}
                </li>
              ))}
            </ul>
          )
        )}
      </div>
    </div>
  )
}
