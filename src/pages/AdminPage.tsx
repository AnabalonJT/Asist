import { useEffect, useState } from 'react'
import { adminApi, AdminOverview, AdminUserSummary } from '../lib/api'

const OVERVIEW_CARDS: { key: keyof AdminOverview; label: string; icon: string }[] = [
  { key: 'total_users', label: 'Usuarios totales', icon: '👥' },
  { key: 'telegram_linked_users', label: 'Con Telegram', icon: '✈️' },
  { key: 'total_activities', label: 'Actividades', icon: '⚡' },
  { key: 'total_goals', label: 'Metas', icon: '🎯' },
  { key: 'total_reminders', label: 'Recordatorios', icon: '🔔' },
  { key: 'total_challenges', label: 'Retos', icon: '🏆' },
  { key: 'active_users_7d', label: 'Activos (7 días)', icon: '📈' },
  { key: 'active_users_30d', label: 'Activos (30 días)', icon: '📊' },
]

export function AdminPage() {
  const [overview, setOverview] = useState<AdminOverview | null>(null)
  const [users, setUsers] = useState<AdminUserSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let active = true
    Promise.all([adminApi.overview(), adminApi.users()])
      .then(([overviewRes, usersRes]) => {
        if (!active) return
        setOverview(overviewRes.data)
        setUsers(usersRes.data)
      })
      .catch(() => {
        if (active) setError(true)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center py-16">
        <div className="w-5 h-5 rounded-full border-2 border-accent border-t-transparent animate-spin" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="card text-center">
        <p className="text-sm text-danger">No se pudieron cargar los datos de administración.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-text-primary">🛡️ Administración</h1>
        <p className="text-text-secondary text-xs mt-0.5">Uso general de la aplicación</p>
      </div>

      {/* Overview stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {OVERVIEW_CARDS.map(({ key, label, icon }) => (
          <div key={key} className="card flex items-center gap-4">
            <div className="w-10 h-10 rounded-xl bg-accent-glow flex items-center justify-center text-xl flex-shrink-0">
              {icon}
            </div>
            <div>
              <p className="text-xs text-text-secondary mb-0.5">{label}</p>
              <p className="text-xl font-semibold text-text-primary font-mono">
                {overview ? overview[key] : 0}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* Per-user list */}
      <div className="card">
        <h2 className="text-sm font-semibold text-text-primary mb-3">
          👥 Usuarios ({users.length})
        </h2>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-text-dim border-b border-bg-border">
                <th className="py-2 pr-3 font-medium">Email</th>
                <th className="py-2 px-3 font-medium">Telegram</th>
                <th className="py-2 px-3 font-medium">Registro</th>
                <th className="py-2 px-3 font-medium text-center" title="Actividades">⚡</th>
                <th className="py-2 px-3 font-medium text-center" title="Metas">🎯</th>
                <th className="py-2 px-3 font-medium text-center" title="Recordatorios">🔔</th>
                <th className="py-2 pl-3 font-medium text-center" title="Retos">🏆</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b border-bg-border last:border-0">
                  <td className="py-2 pr-3 text-text-primary">{u.email}</td>
                  <td className="py-2 px-3">
                    <span className={u.telegram_linked ? 'text-success' : 'text-text-dim'}>
                      {u.telegram_linked ? '✓ Conectado' : 'No conectado'}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-text-secondary">
                    {u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}
                  </td>
                  <td className="py-2 px-3 text-center text-text-primary font-mono">{u.activity_count}</td>
                  <td className="py-2 px-3 text-center text-text-primary font-mono">{u.goal_count}</td>
                  <td className="py-2 px-3 text-center text-text-primary font-mono">{u.reminder_count}</td>
                  <td className="py-2 pl-3 text-center text-text-primary font-mono">{u.challenge_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
