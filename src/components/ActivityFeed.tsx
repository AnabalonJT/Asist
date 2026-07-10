import { useEffect, useState } from 'react'
import api, { Activity } from '../lib/api'
import { ActivityRow } from './ActivityRow'

type SortField = 'timestamp' | 'activity_type' | 'duration_minutes'

export function ActivityFeed() {
  const [activities, setActivities] = useState<Activity[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')
  const [sortBy, setSortBy] = useState<SortField>('timestamp')
  const [limit, setLimit] = useState(20)

  const fetchActivities = async () => {
    try {
      const { data } = await api.get<Activity[]>(`/activities?limit=${limit}`)
      setActivities(data)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchActivities()
    const interval = setInterval(fetchActivities, 30000)
    return () => clearInterval(interval)
  }, [limit])

  // Get unique activity types for filter dropdown
  const types = [...new Set(activities.map((a) => a.activity_type))]

  // Filter and sort
  let filtered = activities
  if (filter) {
    filtered = filtered.filter((a) => a.activity_type === filter)
  }

  filtered = [...filtered].sort((a, b) => {
    if (sortBy === 'timestamp') {
      return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    }
    if (sortBy === 'activity_type') {
      return a.activity_type.localeCompare(b.activity_type)
    }
    if (sortBy === 'duration_minutes') {
      return (b.duration_minutes ?? 0) - (a.duration_minutes ?? 0)
    }
    return 0
  })

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-text-primary">Actividades recientes</h2>
        <span className="badge bg-bg-elevated text-text-dim">{filtered.length}</span>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 mb-3">
        {/* Type filter */}
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="text-xs bg-bg-elevated border border-bg-border rounded-lg px-2 py-1.5 text-text-secondary focus:outline-none focus:border-accent"
        >
          <option value="">Todas</option>
          {types.map((t) => (
            <option key={t} value={t}>
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </option>
          ))}
        </select>

        {/* Sort */}
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as SortField)}
          className="text-xs bg-bg-elevated border border-bg-border rounded-lg px-2 py-1.5 text-text-secondary focus:outline-none focus:border-accent"
        >
          <option value="timestamp">Fecha</option>
          <option value="activity_type">Tipo</option>
          <option value="duration_minutes">Duración</option>
        </select>

        {/* Show more */}
        <select
          value={limit}
          onChange={(e) => setLimit(Number(e.target.value))}
          className="text-xs bg-bg-elevated border border-bg-border rounded-lg px-2 py-1.5 text-text-secondary focus:outline-none focus:border-accent"
        >
          <option value={10}>10</option>
          <option value={20}>20</option>
          <option value={50}>50</option>
          <option value={100}>Todas</option>
        </select>
      </div>

      {/* Activity list */}
      {loading ? (
        <div className="space-y-3 py-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-12 rounded-lg bg-bg-elevated animate-pulse" />
          ))}
        </div>
      ) : filtered.length > 0 ? (
        <div className="max-h-[400px] overflow-y-auto">
          {filtered.map((a) => (
            <ActivityRow key={a.id} activity={a} />
          ))}
        </div>
      ) : (
        <div className="py-8 text-center">
          <p className="text-2xl mb-2">📭</p>
          <p className="text-sm text-text-secondary">
            {filter ? 'No hay actividades de este tipo' : 'Manda un mensaje al bot para registrar tu primera actividad'}
          </p>
        </div>
      )}
    </div>
  )
}
