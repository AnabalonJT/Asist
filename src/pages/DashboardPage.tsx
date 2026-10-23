import { useEffect, useState } from 'react'
import { useAuth } from '../hooks/useAuth'
import { dashboardApi, DashboardStats } from '../lib/api'
import { TelegramLinkCard } from '../components/TelegramLinkCard'
import { StatCard } from '../components/StatCard'
import { Calendar } from '../components/Calendar'
import { ReminderList } from '../components/ReminderList'
import { GoalList } from '../components/GoalList'
import { ChallengeList } from '../components/ChallengeList'
import { ActivityFeed } from '../components/ActivityFeed'

// Inline Lucide-style icons (no emoji, no new dependency).
function IconZap() {
  return (
    <svg className="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z" />
    </svg>
  )
}
function IconFlame() {
  return (
    <svg className="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M8.5 14.5A2.5 2.5 0 0 0 11 17c1.4 0 2.5-1 2.5-2.6 0-1.3-.8-2.2-1.5-3.1-.9-1.2-1.3-2.3-1.2-3.8-1.6.9-3.3 2.9-3.3 5.5 0 .5.1 1 .2 1.5Z" />
      <path d="M12 2c1 2.5.5 4-1 5.5C9 9.5 7 11 7 14a5 5 0 0 0 10 0c0-2-1-3.8-2.5-5.3" />
    </svg>
  )
}
function IconClock() {
  return (
    <svg className="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  )
}

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

  const streak = stats?.current_streak ?? 0
  const streakActive = streak > 0
  const name = user?.email ? user.email.split('@')[0] : ''

  return (
    <div className="space-y-6">
      {/* Greeting */}
      <div>
        <h1 className="font-display text-2xl font-semibold text-text-primary leading-none">
          Hola{name ? `, ${name}` : ''}
        </h1>
        <p className="text-text-secondary text-sm mt-1">Tu resumen de actividad</p>
      </div>

      {/* Streak hero — the one bold element on the page */}
      {loading ? (
        <div className="card h-28 animate-pulse bg-bg-elevated" />
      ) : (
        <div className="card relative overflow-hidden">
          <div
            aria-hidden="true"
            className={`absolute -right-6 -top-10 w-40 h-40 rounded-full blur-2xl ${
              streakActive ? 'bg-success-glow' : 'bg-bg-elevated'
            }`}
          />
          <div className="relative flex items-end justify-between">
            <div>
              <p className="text-sm text-text-secondary mb-1">Racha actual</p>
              <div className="flex items-baseline gap-2">
                <span
                  className={`display text-6xl ${
                    streakActive ? 'text-success' : 'text-text-dim'
                  }`}
                >
                  {streak}
                </span>
                <span className="font-display text-xl text-text-secondary">
                  {streak === 1 ? 'día' : 'días'}
                </span>
              </div>
              <p className="text-sm text-text-secondary mt-2">
                {streakActive
                  ? '¡Sigue así! No rompas la cadena.'
                  : 'Registra una actividad para empezar tu racha.'}
              </p>
            </div>
            <div
              className={`w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 ${
                streakActive ? 'bg-success/15 text-success' : 'bg-bg-elevated text-text-dim'
              }`}
            >
              <IconFlame />
            </div>
          </div>
        </div>
      )}

      {/* Telegram link */}
      <TelegramLinkCard
        linked={telegramLinked}
        onLinked={() => { setTelegramLinked(true); fetchStats() }}
      />

      {/* Supporting stats — quieter than the hero */}
      {loading ? (
        <div className="grid grid-cols-3 gap-3">
          {[0, 1, 2].map((i) => <div key={i} className="card h-20 animate-pulse bg-bg-elevated" />)}
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-3">
          <StatCard icon={<IconZap />} label="Actividades" value={stats?.total_activities ?? 0} />
          <StatCard icon={<IconFlame />} label="Calorías" value={stats ? `${(stats.total_calories / 1000).toFixed(1)}k` : '0'} sub="total" />
          <StatCard icon={<IconClock />} label="Tiempo" value={stats ? `${Math.round((stats.total_minutes ?? 0) / 60)}h` : '0'} sub="total" />
        </div>
      )}

      {/* Reminders */}
      <ReminderList />

      {/* Challenges */}
      <ChallengeList />

      {/* Goals */}
      <GoalList />

      {/* Calendar */}
      <Calendar />

      {/* Activity feed */}
      <ActivityFeed />
    </div>
  )
}
