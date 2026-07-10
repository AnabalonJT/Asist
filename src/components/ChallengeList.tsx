import { useEffect, useState } from 'react'
import { challengesApi, ChallengeItem } from '../lib/api'

export function ChallengeList() {
  const [challenges, setChallenges] = useState<ChallengeItem[]>([])
  const [loading, setLoading] = useState(true)

  const fetch = async () => {
    try {
      const { data } = await challengesApi.list()
      setChallenges(data)
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }

  useEffect(() => {
    fetch()
    const interval = setInterval(fetch, 30000)
    return () => clearInterval(interval)
  }, [])

  const handleDelete = async (id: number) => {
    await challengesApi.delete(id)
    setChallenges((prev) => prev.filter((c) => c.id !== id))
  }

  if (loading) return <div className="card"><div className="h-20 animate-pulse bg-bg-elevated rounded-lg" /></div>

  if (challenges.length === 0) return null // Don't show section if no challenges

  const period = (p: string) => ({ daily: 'hoy', weekly: 'esta semana', monthly: 'este mes' }[p] ?? p)

  return (
    <div className="space-y-4">
      {challenges.map((ch) => {
        const completedGoals = ch.goals.filter((g) => g.completed).length
        const totalGoals = ch.goals.length
        const overallPct = totalGoals > 0 ? (completedGoals / totalGoals) * 100 : 0

        return (
          <div
            key={ch.id}
            className={`card border-2 transition-all ${
              ch.all_completed
                ? 'border-success/50 bg-success/5'
                : 'border-accent/30'
            }`}
          >
            {/* Challenge Header */}
            <div className="flex items-center justify-between mb-3">
              <div>
                <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
                  {ch.all_completed ? '🏆' : '🎯'} {ch.name}
                </h3>
                <p className="text-xs text-text-dim mt-0.5">
                  {ch.ends_at
                    ? `Hasta ${new Date(ch.ends_at + 'T12:00:00').toLocaleDateString('es-CL', { day: 'numeric', month: 'short', year: 'numeric' })}`
                    : 'Sin fecha límite'}
                  {' · '}{completedGoals}/{totalGoals} completadas
                </p>
              </div>
              <button
                onClick={() => handleDelete(ch.id)}
                className="text-xs p-1.5 rounded-lg text-text-dim hover:text-danger hover:bg-danger/10"
                title="Eliminar desafío"
              >
                ✕
              </button>
            </div>

            {/* Overall progress bar */}
            <div className="h-2 rounded-full bg-bg-elevated overflow-hidden mb-4">
              <div
                className={`h-full rounded-full transition-all duration-700 ${
                  ch.all_completed ? 'bg-gradient-to-r from-success to-green-400' : 'bg-gradient-to-r from-accent to-blue-400'
                }`}
                style={{ width: `${overallPct}%` }}
              />
            </div>

            {/* Individual goals */}
            <div className="space-y-2">
              {ch.goals.map((g) => {
                const pct = Math.min((g.current_progress / g.target_count) * 100, 100)

                return (
                  <div
                    key={g.id}
                    className={`flex items-center gap-3 p-2 rounded-lg ${
                      g.completed ? 'bg-success/10' : 'bg-bg-elevated'
                    }`}
                  >
                    {/* Status icon */}
                    <span className="text-lg w-6 text-center">
                      {g.completed ? '✅' : '⬜'}
                    </span>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm ${g.completed ? 'text-success line-through' : 'text-text-primary'}`}>
                        {g.description}
                      </p>
                      <div className="flex items-center gap-2 mt-1">
                        <div className="flex-1 h-1.5 rounded-full bg-bg-border overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all ${
                              g.completed ? 'bg-success' : 'bg-accent'
                            }`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <span className="text-xs font-mono text-text-dim">
                          {g.current_progress}/{g.target_count} {period(g.period)}
                        </span>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Completion message */}
            {ch.all_completed && (
              <div className="mt-3 text-center py-2 rounded-lg bg-success/10 border border-success/20">
                <p className="text-sm font-semibold text-success">
                  🎉 ¡Desafío completado hoy! Sigue así
                </p>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
