import { useState, FormEvent } from 'react'
import { mealsApi } from '../lib/api'

// Extract the Spanish `detail` from an API error, falling back to a message.
function apiError(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0 && detail[0]?.msg) return detail[0].msg
  return fallback
}

interface CreateFoodFormProps {
  onAdded?: () => void
}

// Create_Food_Form: create or add a new Food to the user's own inventory with
// its per-100 g nutrition, an optional Brand and the dietary flags. A non-admin
// user adds an unknown food to their inventory via `addInventory` with a
// `new_food` payload (mirrors MealsPage / FoodConfirm), which creates the Food
// row in the catalog when its name does not exist. Spanish UI copy.
//
// Default export so AddFoodPanel can lazy-load it with React.lazy.
function CreateFoodForm({ onAdded }: CreateFoodFormProps) {
  const [name, setName] = useState('')
  const [brand, setBrand] = useState('')
  const [kcal, setKcal] = useState('')
  const [protein, setProtein] = useState('')
  const [fat, setFat] = useState('')
  const [carbs, setCarbs] = useState('')
  const [fiber, setFiber] = useState('')
  const [grams, setGrams] = useState('')
  const [isMeat, setIsMeat] = useState(false)
  const [isAnimal, setIsAnimal] = useState(false)
  const [hasGluten, setHasGluten] = useState(false)
  const [err, setErr] = useState('')
  const [saving, setSaving] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!name.trim()) {
      setErr('El nombre no puede estar vacío.')
      return
    }
    setSaving(true)
    setErr('')
    try {
      await mealsApi.addInventory({
        food_name: name.trim(),
        quantity_grams: grams === '' ? null : Number(grams),
        new_food: {
          name: name.trim(),
          brand: brand.trim() === '' ? null : brand.trim(),
          kcal: Number(kcal),
          protein: Number(protein),
          fat: Number(fat),
          carbs: Number(carbs),
          fiber: fiber === '' ? null : Number(fiber),
          is_meat: isMeat,
          is_animal: isAnimal,
          has_gluten: hasGluten,
        },
      })
      // Reset the form for the next food.
      setName('')
      setBrand('')
      setKcal('')
      setProtein('')
      setFat('')
      setCarbs('')
      setFiber('')
      setGrams('')
      setIsMeat(false)
      setIsAnimal(false)
      setHasGluten(false)
      onAdded?.()
    } catch (e: any) {
      // Preserve the form so the user can correct values / name / brand.
      setErr(apiError(e, 'No se pudo agregar el alimento.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="card space-y-3">
      <h2 className="text-sm font-semibold text-text-primary">Crear alimento</h2>
      <p className="text-xs text-text-dim">
        Se agregará a tu inventario. Los valores nutricionales son por 100 g.
      </p>

      <div>
        <label className="text-xs text-text-secondary">Nombre</label>
        <input
          type="text"
          className="input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={100}
          placeholder="Ej. Pechuga de pollo"
          required
        />
      </div>

      <div>
        <label className="text-xs text-text-secondary">Marca (opcional)</label>
        <input
          type="text"
          className="input"
          value={brand}
          onChange={(e) => setBrand(e.target.value)}
          maxLength={100}
          placeholder="Ej. Marca Fresca"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-text-secondary">Kcal</label>
          <input
            type="number"
            step="0.1"
            className="input"
            value={kcal}
            onChange={(e) => setKcal(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="text-xs text-text-secondary">Proteína (g)</label>
          <input
            type="number"
            step="0.1"
            className="input"
            value={protein}
            onChange={(e) => setProtein(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="text-xs text-text-secondary">Grasa (g)</label>
          <input
            type="number"
            step="0.1"
            className="input"
            value={fat}
            onChange={(e) => setFat(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="text-xs text-text-secondary">Carbohidratos (g)</label>
          <input
            type="number"
            step="0.1"
            className="input"
            value={carbs}
            onChange={(e) => setCarbs(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="text-xs text-text-secondary">Fibra (g, opcional)</label>
          <input
            type="number"
            step="0.1"
            className="input"
            value={fiber}
            onChange={(e) => setFiber(e.target.value)}
          />
        </div>
        <div>
          <label className="text-xs text-text-secondary">Cantidad (g)</label>
          <input
            type="number"
            step="1"
            className="input"
            value={grams}
            onChange={(e) => setGrams(e.target.value)}
            placeholder="Opcional"
          />
        </div>
      </div>

      {/* Dietary flags — kept because meal-planner uses them (default false). */}
      <div className="space-y-2">
        <p className="text-xs text-text-secondary">Banderas dietéticas</p>
        <label className="flex items-center gap-2 text-sm text-text-primary">
          <input
            type="checkbox"
            checked={isMeat}
            onChange={(e) => setIsMeat(e.target.checked)}
          />
          Es carne
        </label>
        <label className="flex items-center gap-2 text-sm text-text-primary">
          <input
            type="checkbox"
            checked={isAnimal}
            onChange={(e) => setIsAnimal(e.target.checked)}
          />
          Es de origen animal
        </label>
        <label className="flex items-center gap-2 text-sm text-text-primary">
          <input
            type="checkbox"
            checked={hasGluten}
            onChange={(e) => setHasGluten(e.target.checked)}
          />
          Contiene gluten
        </label>
      </div>

      {err && <p className="text-xs text-danger">{err}</p>}

      <button type="submit" className="btn-primary w-full text-sm" disabled={saving}>
        {saving ? 'Agregando...' : 'Agregar alimento'}
      </button>
    </form>
  )
}

export default CreateFoodForm
