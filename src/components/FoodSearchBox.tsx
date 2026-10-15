import { useState, FormEvent } from 'react'
import { mealsApi, FoodCandidate } from '../lib/api'

// Extract the Spanish `detail` from an API error, falling back to a message.
function apiError(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0 && detail[0]?.msg) return detail[0].msg
  return fallback
}

interface FoodSearchBoxProps {
  onPick: (candidate: FoodCandidate) => void
}

// Name search box: query foods by name and render selectable candidate rows.
export function FoodSearchBox({ onPick }: FoodSearchBoxProps) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<FoodCandidate[]>([])
  const [searched, setSearched] = useState(false)
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSearch(e: FormEvent) {
    e.preventDefault()
    const term = q.trim()
    // Ignore empty terms locally.
    if (!term) return
    setLoading(true)
    setErr('')
    try {
      const { data } = await mealsApi.searchFood(term)
      setResults(data)
      setSearched(true)
    } catch (e: any) {
      setResults([])
      setSearched(true)
      setErr(apiError(e, 'No se pudo buscar el alimento.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-3">
      <form onSubmit={handleSearch} className="flex gap-2">
        <input
          type="text"
          className="input"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Buscar por nombre"
        />
        <button type="submit" className="btn-primary text-sm" disabled={loading}>
          {loading ? 'Buscando...' : 'Buscar'}
        </button>
      </form>

      {err && <p className="text-xs text-danger">{err}</p>}

      {searched && !err && results.length === 0 && (
        <p className="text-sm text-text-dim">Sin resultados</p>
      )}

      {results.length > 0 && (
        <ul className="space-y-1">
          {results.map((c, i) => (
            <li key={`${c.name}-${c.barcode ?? ''}-${i}`}>
              <button
                type="button"
                onClick={() => onPick(c)}
                className="w-full text-left border border-bg-border rounded-lg px-3 py-2 hover:border-accent"
              >
                <span className="text-sm text-text-primary">{c.name}</span>
                {c.brand && (
                  <span className="text-xs text-text-secondary"> — {c.brand}</span>
                )}
                {c.kcal != null && (
                  <span className="text-xs text-text-dim"> · {c.kcal} kcal/100g</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
