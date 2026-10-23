import { Fragment, useEffect, useState } from 'react'
import { adminApi, AdminOverview, AdminUserDetail, AdminUserSummary } from '../lib/api'

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

// Number of columns in the user table — used for the expandable detail row colspan.
const USER_TABLE_COLSPAN = 7

export function AdminPage() {
  const [overview, setOverview] = useState<AdminOverview | null>(null)
  const [users, setUsers] = useState<AdminUserSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  // Per-user detail drill-down state.
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<AdminUserDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState(false)

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

  const toggleUser = (id: number) => {
    // Collapse if the same row is clicked again.
    if (expandedId === id) {
      setExpandedId(null)
      setDetail(null)
      setDetailError(false)
      return
    }

    setExpandedId(id)
    setDetail(null)
    setDetailError(false)
    setDetailLoading(true)

    adminApi
      .userDetail(id)
      .then((res) => {
        // Ignore if the user collapsed or switched rows while loading.
        setDetail(res.data)
      })
      .catch(() => {
        setDetailError(true)
      })
      .finally(() => {
        setDetailLoading(false)
      })
  }

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
        <h1 className="font-display text-2xl font-semibold text-text-primary leading-none">Administración</h1>
        <p className="text-text-secondary text-sm mt-1">Uso general de la aplicación</p>
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
              <p className="display text-2xl text-text-primary">
                {overview ? overview[key] : 0}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* Per-user list */}
      <div className="card">
        <h2 className="font-display text-lg font-semibold text-text-primary mb-3">
          Usuarios ({users.length})
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
              {users.map((u) => {
                const isExpanded = expandedId === u.id
                return (
                  <Fragment key={u.id}>
                    <tr
                      className={`border-b border-bg-border last:border-0 cursor-pointer transition-colors hover:bg-bg-border/40 ${
                        isExpanded ? 'bg-bg-border/40' : ''
                      }`}
                      onClick={() => toggleUser(u.id)}
                    >
                      <td className="py-2 pr-3 text-text-primary">
                        <button
                          type="button"
                          className="flex items-center gap-2 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded"
                          aria-expanded={isExpanded}
                          aria-label={`Ver detalle de ${u.email}`}
                          onClick={(e) => {
                            e.stopPropagation()
                            toggleUser(u.id)
                          }}
                        >
                          <span
                            className={`text-text-dim transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                            aria-hidden="true"
                          >
                            ▸
                          </span>
                          <span>{u.email}</span>
                        </button>
                      </td>
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

                    {isExpanded && (
                      <tr className="border-b border-bg-border last:border-0 bg-bg-border/20">
                        <td colSpan={USER_TABLE_COLSPAN} className="py-3 px-3">
                          {detailLoading && (
                            <div className="flex items-center gap-2 text-text-secondary text-xs">
                              <div className="w-4 h-4 rounded-full border-2 border-accent border-t-transparent animate-spin" />
                              <span>Cargando detalle…</span>
                            </div>
                          )}

                          {!detailLoading && detailError && (
                            <p className="text-xs text-danger">
                              No se pudo cargar el detalle del usuario.
                            </p>
                          )}

                          {!detailLoading && !detailError && detail && (
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                              <div className="rounded-xl bg-bg-surface px-3 py-2">
                                <p className="text-xs text-text-secondary mb-0.5">Actividades (7 días)</p>
                                <p className="text-lg font-mono text-text-primary">{detail.activities_7d}</p>
                              </div>
                              <div className="rounded-xl bg-bg-surface px-3 py-2">
                                <p className="text-xs text-text-secondary mb-0.5">Actividades (30 días)</p>
                                <p className="text-lg font-mono text-text-primary">{detail.activities_30d}</p>
                              </div>
                              <div className="rounded-xl bg-bg-surface px-3 py-2">
                                <p className="text-xs text-text-secondary mb-0.5">Última actividad</p>
                                <p className="text-sm text-text-primary">
                                  {detail.last_activity_at
                                    ? new Date(detail.last_activity_at).toLocaleDateString()
                                    : 'Sin actividad'}
                                </p>
                              </div>
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
