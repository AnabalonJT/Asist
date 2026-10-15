import { useState, FormEvent } from 'react'
import { mealsApi, FoodCandidate } from '../lib/api'

// Extract the Spanish `detail` from an API error, falling back to a message.
function apiError(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0 && detail[0]?.msg) return detail[0].msg
  return fallback
}

interface FoodConfirmProps {
  candidate: FoodCandidate
  onAdded: () => void
  onCancel: () => void
}

// Confirmation_Step: show the Food_Candidate with editable nutrition values
// (per 100 g) and let the user confirm it into their inventory or cancel.
export function FoodConfirm({ candidate, onAdded, onCancel }: FoodConfirmProps) {
  // Pre-fill the editable number inputs from the candidate's nutrition values.
  const toField = (v: number | null | undefined): string =>
    v === null || v === undefined ? '' : String(v)

  const [kcal, setKcal] = useState<string>(toField(candidate.kcal))
  const [protein, setProtein] = useState<string>(toField(candidate.protein))
  const [fat, setFat] = useState<string>(toField(candidate.fat))
  const [carbs, setCarbs] = useState<string>(toField(candidate.carbs))
  const [fiber, setFiber] = useState<string>(toField(candidate.fiber))
  const [grams, setGrams] = useState<string>('')
  const [err, setErr] = useState('')
  const [saving, setSaving] = useState(false)

  async function handleAdd(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setErr('')
    try {
      await mealsApi.addInventory({
        food_name: candidate.name,
        quantity_grams: grams === '' ? null : Number(grams),
        new_food: {
          name: candidate.name,
          kcal: Number(kcal),
          protein: Number(protein),
          fat: Number(fat),
          carbs: Number(carbs),
          fiber: fiber === '' ? null : Number(fiber),
          barcode: candidate.barcode ?? null,
        },
      })
      onAdded()
    } catch (e: any) {
      // Preserve the form so the user can correct out-of-range values.
      setErr(apiError(e, 'No se pudo agregar el alimento.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="card space-y-3">
      <h2 className="text-sm font-semibold text-text-primary">
        ¿Es este el alimento que quieres agregar?
      </h2>

      <div className="flex items-start gap-3">
        {candidate.image_url && (
          <img
            src={candidate.image_url}
            alt={candidate.name}
            className="w-16 h-16 rounded-lg object-cover border border-bg-border"
          />
        )}
        <div>
          <p className="text-sm font-semibold text-text-primary">{candidate.name}</p>
          {candidate.brand && (
            <p className="text-xs text-text-secondary">{candidate.brand}</p>
          )}
          <p className="text-xs text-text-dim">Valores nutricionales por 100 g</p>
        </div>
      </div>

      <form onSubmit={handleAdd} className="space-y-3">
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

        {err && <p className="text-xs text-danger">{err}</p>}

        <div className="flex gap-2">
          <button type="submit" className="btn-primary flex-1 text-sm" disabled={saving}>
            {saving ? 'Agregando...' : 'Agregar'}
          </button>
          <button
            type="button"
            className="btn-ghost text-sm"
            onClick={onCancel}
            disabled={saving}
          >
            Cancelar
          </button>
        </div>
      </form>
    </div>
  )
}
