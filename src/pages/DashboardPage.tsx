import { useEffect, useState } from 'react'
import { useAuth } from '../hooks/useAuth'
import { dashboardApi, DashboardStats } from '../lib/api'
import { TelegramLinkCard } from '../components/TelegramLinkCard'
import { StatCard } from '../components/StatCard'
import { Calendar } from '../components/Calendar'
import { ReminderList } from '../components/ReminderList'

export function DashboardPage() {
  const { user } = useAuth()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [telegramLinked, setTelegramLinked] = useState(user?.telegram_linked ?? false)

  const fetchStats = async () => {
    try {
      const { data } = await dashboardApi.stats()
      setStats(data)
      setTelegramLinked(data.telegram_linked)
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }

  useEffect(() => {
    fetchStats()
    const interval = setInterval(fetchStats, 30000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="space-y-6">
      {/* Greeting */}
      <div>
        <h1 className="text-lg font-semibold text-text-primary">
          Hola{user?.email ? `, ${user.email.split('@')[0]}` : ''} 👋
        </h1>
        <p className="text-text-secondary text-xs mt-0.5">Tu resumen de actividad</p>
      </div>

      {/* Telegram link */}
      <TelegramLinkCard
        linked={telegramLinked}
        onLinked={() => { setTelegramLinked(true); fetchStats() }}
      />

      {/* Stats */}
      {loading ? (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[0, 1, 2, 3].map((i) => <div key={i} className="card h-20 animate-pulse bg-bg-elevated" />)}
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatCard icon="⚡" label="Actividades" value={stats?.total_activities ?? 0} />
          <StatCard icon="🔥" label="Calorías" value={stats ? `${(stats.total_calories / 1000).toFixed(1)}k` : '0'} sub="total" />
          <StatCard icon="📅" label="Racha" value={stats?.current_streak ?? 0} sub="días" />
          <StatCard icon="⏱" label="Tiempo" value={stats ? `${Math.round((stats.total_minutes ?? 0) / 60)}h` : '0'} sub="total" />
        </div>
      )}

      {/* Reminders */}
      <ReminderList />

      {/* Calendar */}
      <Calendar />
    </div>
  )
}
