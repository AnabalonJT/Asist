import { useState, useEffect } from 'react'
import { mealsApi, SearchResult } from '../lib/api'

// Extract the Spanish `detail` from an API error, falling back to a message.
function apiError(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0 && detail[0]?.msg) return detail[0].msg
  return fallback
}

// Search_Debounce: wait this long after the last keystroke before querying.
const SEARCH_DEBOUNCE_MS = 300

// Spanish labels for each Search_Result `kind`.
const KIND_LABELS: Record<SearchResult['kind'], string> = {
  catalog: 'Catálogo',
  inventory: 'Mi inventario',
  recipe: 'Receta',
  off: 'Open Food Facts',
}

interface IncrementalSearchBoxProps {
  onPick: (result: SearchResult) => void
  onCreateNew?: () => void
}

// Incremental_Search box: as the user types, debounce the term by 300 ms and
// query the unified search (catalog + inventory + recipes + Open Food Facts),
// rendering selectable Search_Result rows.
export function IncrementalSearchBox({ onPick, onCreateNew }: IncrementalSearchBoxProps) {
  const [term, setTerm] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [searched, setSearched] = useState(false)
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)

  // Debounce the search: a timeout per term change, cleared on the next
  // keystroke so rapid typing fires only ONE request after the user pauses.
  useEffect(() => {
    const q = term.trim()
    // Do not query for empty/whitespace-only terms — clear the results.
    if (!q) {
      setResults([])
      setSearched(false)
      setErr('')
      setLoading(false)
      return
    }

    let cancelled = false
    setLoading(true)
    setErr('')
    const handle = setTimeout(async () => {
      try {
        const { data } = await mealsApi.search(q)
        // Ignore stale responses from a term that has since changed.
        if (cancelled) return
        setResults(data)
        setSearched(true)
      } catch (e: any) {
        if (cancelled) return
        setResults([])
        setSearched(true)
        setErr(apiError(e, 'No se pudo buscar.'))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }, SEARCH_DEBOUNCE_MS)

    return () => {
      cancelled = true
      clearTimeout(handle)
    }
  }, [term])

  return (
    <div className="space-y-3">
      <input
        type="text"
        className="input"
        value={term}
        onChange={(e) => setTerm(e.target.value)}
        placeholder="Buscar por nombre"
      />

      {loading && <p className="text-xs text-text-dim">Buscando…</p>}

      {err && <p className="text-xs text-danger">{err}</p>}

      {results.length > 0 && (
        <ul className="space-y-1">
          {results.map((r, i) => (
            <li key={`${r.kind}-${r.id ?? ''}-${r.name}-${i}`}>
              <button
                type="button"
                onClick={() => onPick(r)}
                className="w-full text-left border border-bg-border rounded-lg px-3 py-2 hover:border-accent"
              >
                <span className="text-sm text-text-primary">{r.name}</span>
                {r.brand && (
                  <span className="text-xs text-text-secondary"> — {r.brand}</span>
                )}
                <span className="text-xs text-text-secondary"> [{KIND_LABELS[r.kind]}]</span>
                {r.kcal != null && (
                  <span className="text-xs text-text-dim"> · {r.kcal} kcal/100g</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}

      {searched && !loading && !err && results.length === 0 && (
        <div className="space-y-2">
          <p className="text-sm text-text-dim">
            No se encontró '{term.trim()}'. ¿Quieres crear un alimento o una receta nueva?
          </p>
          {onCreateNew && (
            <button type="button" className="btn-primary text-sm" onClick={onCreateNew}>
              Crear nuevo
            </button>
          )}
        </div>
      )}
    </div>
  )
}
