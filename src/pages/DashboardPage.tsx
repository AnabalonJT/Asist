import { useEffect, useState } from 'react'
import { useAuth } from '../hooks/useAuth'
import { dashboardApi, DashboardStats } from '../lib/api'
import { TelegramLinkCard } from '../components/TelegramLinkCard'
import { StatCard } from '../components/StatCard'
import { Calendar } from '../components/Calendar'
import { ReminderList } from '../components/ReminderList'
import { GoalList } from '../components/GoalList'
import { ActivityFeed } from '../components/ActivityFeed'

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
          onLinked={() => { setTelegramLinked(true); fetchStats() }}
        />

        {/* Stats */}
        {loading ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="card h-20 animate-pulse bg-bg-elevated" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard icon="⚡" label="Actividades" value={stats?.total_activities ?? 0} />
            <StatCard icon="🔥" label="Calorías" value={stats ? `${(stats.total_calories / 1000).toFixed(1)}k` : '0'} sub="total" />
            <StatCard icon="📅" label="Racha" value={stats?.current_streak ?? 0} sub="días" />
            <StatCard icon="⏱" label="Tiempo" value={stats ? `${Math.round((stats.total_minutes ?? 0) / 60)}h` : '0'} sub="total" />
          </div>
        )}

        {/* Goals */}
        <GoalList />

        {/* Calendar */}
        <Calendar />

        {/* Activity Feed with filters */}
        <ActivityFeed />

        {/* Reminders */}
        <ReminderList />
      </main>
    </div>
  )
}
