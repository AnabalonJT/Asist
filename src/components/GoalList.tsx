import { useEffect, useState } from 'react'
import { goalsApi, GoalItem } from '../lib/api'

const ACTIVITY_ICONS: Record<string, string> = {
  running: '🏃', walking: '🚶', cycling: '🚴', gym: '🏋️',
  swimming: '🏊', yoga: '🧘', weights: '💪', meditation: '🧘',
  reading: '📚', study: '📖', baño: '🚽', comer: '🍽',
  agua: '💧', dormir: '😴', cocinar: '👨‍🍳',
}

export function GoalList() {
  const [goals, setGoals] = useState<GoalItem[]>([])
  const [loading, setLoading] = useState(true)

  const fetchGoals = async () => {
    try {
      const { data } = await goalsApi.list()
      setGoals(data)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchGoals()
    const interval = setInterval(fetchGoals, 30000)
    return () => clearInterval(interval)
  }, [])

  const handleDelete = async (id: number) => {
    await goalsApi.delete(id)
    setGoals((prev) => prev.filter((g) => g.id !== id))
  }

  if (loading) {
    return (
      <div className="card">
        <div className="h-20 animate-pulse bg-bg-elevated rounded-lg" />
      </div>
    )
  }

  if (goals.length === 0) {
    return (
      <div className="card">
        <h2 className="text-sm font-semibold text-text-primary mb-2">🎯 Metas</h2>
        <div className="py-6 text-center">
          <p className="text-2xl mb-2">🎯</p>
          <p className="text-sm text-text-secondary">No tienes metas activas</p>
          <p className="text-xs text-text-dim mt-1">
            Crea una desde Telegram: <span className="italic">"Quiero correr 3 veces por semana"</span>
          </p>
        </div>
      </div>
    )
  }

  const period = (p: string) =>
    ({ daily: 'hoy', weekly: 'esta semana', monthly: 'este mes' }[p] ?? p)

  const completedCount = goals.filter((g) => g.current_progress >= g.target_count).length

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-text-primary">🎯 Metas</h2>
        {goals.length > 0 && (
          <span className="badge bg-success/10 text-success border border-success/20">
            {completedCount}/{goals.length} cumplidas
          </span>
        )}
      </div>

      <div className="space-y-4">
        {goals.map((g) => {
          const pct = Math.min((g.current_progress / g.target_count) * 100, 100)
          const completed = g.current_progress >= g.target_count
          const icon = ACTIVITY_ICONS[g.activity_type.toLowerCase()] ?? '⚡'

          return (
            <div
              key={g.id}
              className={`p-3 rounded-xl border transition-all ${
                completed
                  ? 'border-success/30 bg-success/5'
                  : 'border-bg-border bg-bg-surface'
              }`}
            >
              {/* Header */}
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-lg">{completed ? '🏆' : icon}</span>
                  <div>
                    <p className="text-sm font-medium text-text-primary">{g.description}</p>
                    <p className="text-xs text-text-dim capitalize">
                      {g.activity_type} · {period(g.period)}
                      {g.ends_at && ` · hasta ${new Date(g.ends_at + 'T12:00:00').toLocaleDateString('es-CL', { day: 'numeric', month: 'short' })}`}
                      {!g.ends_at && ' · sin límite'}
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => handleDelete(g.id)}
                  className="text-xs p-1.5 rounded-lg text-text-dim hover:text-danger hover:bg-danger/10 transition-colors"
                  title="Eliminar meta"
                >
                  ✕
                </button>
              </div>

              {/* Progress bar */}
              <div className="flex items-center gap-3">
                <div className="flex-1 h-3 rounded-full bg-bg-elevated overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ease-out ${
                      completed
                        ? 'bg-gradient-to-r from-success to-green-400'
                        : pct > 60
                        ? 'bg-gradient-to-r from-accent to-blue-400'
                        : pct > 30
                        ? 'bg-gradient-to-r from-warning to-yellow-400'
                        : 'bg-gradient-to-r from-orange-500 to-warning'
                    }`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <span className={`text-sm font-mono font-semibold min-w-[3rem] text-right ${
                  completed ? 'text-success' : 'text-text-secondary'
                }`}>
                  {g.current_progress}/{g.target_count}
                </span>
              </div>

              {/* Completion message */}
              {completed && (
                <p className="text-xs text-success mt-2 font-medium">
                  ✅ ¡Meta cumplida! Sigue así
                </p>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
