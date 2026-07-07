import { useEffect, useState } from 'react'
import { useAuth } from '../hooks/useAuth'
import { dashboardApi, DashboardStats } from '../lib/api'
import { TelegramLinkCard } from '../components/TelegramLinkCard'
import { ActivityRow } from '../components/ActivityRow'
import { StatCard } from '../components/StatCard'
import { Calendar } from '../components/Calendar'
import { ReminderList } from '../components/ReminderList'
import { GoalList } from '../components/GoalList'

export function DashboardPage() {
  const { user, logout } = useAuth()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [telegramLinked, setTelegramLinked] = useState(user?.telegram_linked ?? false)

  const fetchStats = async () => {
    try {
      const { data } = await dashboardApi.stats()
      setStats(data)
      setTelegramLinked(data.telegram_linked)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStats()
    // Auto-refresh every 30s
    const interval = setInterval(fetchStats, 30000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="min-h-full">
      {/* Top nav */}
      <header className="border-b border-bg-border bg-bg-surface/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-2xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-lg">🏃</span>
            <span className="font-semibold text-text-primary">HabitBot</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-text-dim hidden sm:block">{user?.email}</span>
            <button onClick={logout} className="btn-ghost text-sm py-1.5">
              Salir
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-6 space-y-6">
        {/* Greeting */}
        <div>
          <h1 className="text-xl font-semibold text-text-primary">
            Hola{user?.email ? `, ${user.email.split('@')[0]}` : ''} 👋
          </h1>
          <p className="text-text-secondary text-sm mt-0.5">Tu resumen de actividad</p>
        </div>

        {/* Telegram link card */}
        <TelegramLinkCard
          linked={telegramLinked}
          onLinked={() => {
            setTelegramLinked(true)
            fetchStats()
          }}
        />

        {/* Main Stats */}
        {loading ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="card h-20 animate-pulse bg-bg-elevated" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard
              icon="⚡"
              label="Actividades"
              value={stats?.total_activities ?? 0}
            />
            <StatCard
              icon="🔥"
              label="Calorías"
              value={stats ? `${(stats.total_calories / 1000).toFixed(1)}k` : '0'}
              sub="total"
            />
            <StatCard
              icon="📅"
              label="Racha"
              value={stats?.current_streak ?? 0}
              sub="días"
            />
            <StatCard
              icon="⏱"
              label="Tiempo"
              value={stats ? `${Math.round((stats.total_minutes ?? 0) / 60)}h` : '0'}
              sub="total"
            />
          </div>
        )}

        {/* Week comparison */}
        {stats && stats.week_comparison && (
          <div className="card flex items-center justify-between">
            <div>
              <p className="text-xs text-text-secondary">Esta semana</p>
              <p className="text-lg font-semibold text-text-primary">{stats.week_comparison.this_week} actividades</p>
            </div>
            <div className="text-right">
              <p className="text-xs text-text-secondary">vs semana pasada</p>
              <p className={`text-sm font-mono ${stats.week_comparison.change_pct >= 0 ? 'text-success' : 'text-danger'}`}>
                {stats.week_comparison.change_pct >= 0 ? '↑' : '↓'} {Math.abs(stats.week_comparison.change_pct)}%
              </p>
            </div>
          </div>
        )}

        {/* Calendar */}
        <Calendar />

        {/* Goals */}
        <GoalList />

        {/* Reminders */}
        <ReminderList />

        {/* Breakdown by type */}
        {stats && stats.breakdown.length > 0 && (
          <div className="card">
            <h2 className="text-sm font-semibold text-text-primary mb-3">Desglose por actividad</h2>
            <div className="space-y-2">
              {stats.breakdown.map((b) => (
                <div key={b.activity_type} className="flex items-center justify-between py-1.5 border-b border-bg-border last:border-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm capitalize">{b.activity_type}</span>
                    <span className="badge bg-bg-elevated text-text-dim">{b.count}x</span>
                  </div>
                  <div className="text-xs text-text-secondary">
                    {b.total_minutes > 0 && <span>{b.total_minutes} min</span>}
                    {b.total_calories > 0 && <span className="ml-2 text-warning">{b.total_calories} cal</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recent activities */}
        <div className="card">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-semibold text-text-primary">Actividad reciente</h2>
            {stats && stats.recent_activities.length > 0 && (
              <span className="badge bg-bg-elevated text-text-secondary">
                últimas {stats.recent_activities.length}
              </span>
            )}
          </div>

          {loading ? (
            <div className="space-y-3 py-2">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-12 rounded-lg bg-bg-elevated animate-pulse" />
              ))}
            </div>
          ) : stats && stats.recent_activities.length > 0 ? (
            <div>
              {stats.recent_activities.map((a) => (
                <ActivityRow key={a.id} activity={a} />
              ))}
            </div>
          ) : (
            <div className="py-10 text-center">
              <p className="text-2xl mb-2">📭</p>
              <p className="text-sm text-text-secondary">
                {telegramLinked
                  ? 'Manda un mensaje al bot para registrar tu primera actividad'
                  : 'Conecta Telegram para empezar a registrar actividades'}
              </p>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
