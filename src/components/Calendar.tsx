import { useEffect, useState } from 'react'
import { Activity } from '../lib/api'
import api from '../lib/api'

const ACTIVITY_ICONS: Record<string, string> = {
  running: '🏃', walking: '🚶', cycling: '🚴', gym: '🏋️',
  swimming: '🏊', yoga: '🧘', weights: '💪', meditation: '🧘',
  reading: '📚', study: '📖', baño: '🚽', comer: '🍽',
  agua: '💧', dormir: '😴', cama: '🛏️',
}

export function Calendar() {
  const [activities, setActivities] = useState<Activity[]>([])
  const [currentMonth, setCurrentMonth] = useState(new Date())
  const [loading, setLoading] = useState(true)
  const [selectedDay, setSelectedDay] = useState<number | null>(null)

  useEffect(() => { fetchMonth() }, [currentMonth])

  const fetchMonth = async () => {
    setLoading(true)
    const year = currentMonth.getFullYear()
    const month = currentMonth.getMonth()
    const start = new Date(year, month, 1).toISOString().split('T')[0]
    const end = new Date(year, month + 1, 0).toISOString().split('T')[0]
    try {
      const { data } = await api.get<Activity[]>(`/activities?start_date=${start}&end_date=${end}&limit=200`)
      setActivities(data)
    } catch { setActivities([]) }
    finally { setLoading(false) }
  }

  const year = currentMonth.getFullYear()
  const month = currentMonth.getMonth()
  const firstDay = new Date(year, month, 1).getDay()
  const daysInMonth = new Date(year, month + 1, 0).getDate()

  const activityDays = new Map<number, Activity[]>()
  activities.forEach((a) => {
    const day = new Date(a.timestamp).getDate()
    if (!activityDays.has(day)) activityDays.set(day, [])
    activityDays.get(day)!.push(a)
  })

  const prevMonth = () => { setCurrentMonth(new Date(year, month - 1, 1)); setSelectedDay(null) }
  const nextMonth = () => { setCurrentMonth(new Date(year, month + 1, 1)); setSelectedDay(null) }

  const monthName = currentMonth.toLocaleDateString('es-CL', { month: 'long', year: 'numeric' })
  const today = new Date()
  const isToday = (day: number) => today.getFullYear() === year && today.getMonth() === month && today.getDate() === day

  const selectedActivities = selectedDay ? activityDays.get(selectedDay) ?? [] : []

  return (
    <div className="card">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <button onClick={prevMonth} className="btn-ghost py-1 px-2 text-lg">‹</button>
        <h2 className="text-sm font-semibold text-text-primary capitalize">{monthName}</h2>
        <button onClick={nextMonth} className="btn-ghost py-1 px-2 text-lg">›</button>
      </div>

      {/* Day headers */}
      <div className="grid grid-cols-7 gap-1 mb-1">
        {['Lu', 'Ma', 'Mi', 'Ju', 'Vi', 'Sa', 'Do'].map((d) => (
          <div key={d} className="text-center text-xs text-text-dim font-medium py-1">{d}</div>
        ))}
      </div>

      {/* Days grid */}
      <div className="grid grid-cols-7 gap-1">
        {Array.from({ length: (firstDay + 6) % 7 }).map((_, i) => (
          <div key={`empty-${i}`} className="h-9" />
        ))}
        {Array.from({ length: daysInMonth }).map((_, i) => {
          const day = i + 1
          const dayActivities = activityDays.get(day)
          const hasActivity = !!dayActivities && dayActivities.length > 0
          const isSelected = selectedDay === day

          return (
            <button
              key={day}
              onClick={() => setSelectedDay(isSelected ? null : day)}
              className={`h-9 rounded-lg flex flex-col items-center justify-center text-xs relative transition-all
                ${isToday(day) ? 'ring-1 ring-accent' : ''}
                ${isSelected ? 'bg-accent/30 ring-2 ring-accent' : ''}
                ${hasActivity && !isSelected ? 'bg-accent/15 text-accent font-semibold' : 'text-text-secondary'}
                ${hasActivity ? 'cursor-pointer hover:bg-accent/25' : 'cursor-default'}
              `}
            >
              <span>{day}</span>
              {hasActivity && (
                <div className="flex gap-0.5 mt-0.5">
                  {dayActivities!.length <= 3
                    ? dayActivities!.map((_, idx) => <div key={idx} className="w-1 h-1 rounded-full bg-accent" />)
                    : <div className="w-1.5 h-1.5 rounded-full bg-accent" />
                  }
                </div>
              )}
            </button>
          )
        })}
      </div>

      {loading && <div className="text-center text-xs text-text-dim mt-2">Cargando...</div>}

      {/* Day Detail Modal */}
      {selectedDay !== null && selectedActivities.length > 0 && (
        <div className="mt-4 p-3 rounded-xl bg-bg-elevated border border-bg-border">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-text-primary">
              {selectedDay} {currentMonth.toLocaleDateString('es-CL', { month: 'short' })} — {selectedActivities.length} actividad{selectedActivities.length > 1 ? 'es' : ''}
            </h3>
            <button onClick={() => setSelectedDay(null)} className="text-text-dim hover:text-text-primary text-lg">×</button>
          </div>
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {selectedActivities.map((a) => {
              const icon = ACTIVITY_ICONS[a.activity_type.toLowerCase()] ?? '⚡'
              const time = new Date(a.timestamp).toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' })
              return (
                <div key={a.id} className="flex items-center gap-2 py-1.5 border-b border-bg-border last:border-0">
                  <span className="text-lg">{icon}</span>
                  <div className="flex-1">
                    <p className="text-sm text-text-primary capitalize">{a.activity_type}</p>
                    <p className="text-xs text-text-dim">
                      {time}
                      {a.duration_minutes && ` · ${a.duration_minutes} min`}
                      {a.distance_km && ` · ${a.distance_km} km`}
                    </p>
                  </div>
                  {a.calories > 0 && (
                    <span className="text-xs font-mono text-warning">{a.calories} cal</span>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {selectedDay !== null && selectedActivities.length === 0 && (
        <div className="mt-4 p-3 rounded-xl bg-bg-elevated border border-bg-border text-center">
          <p className="text-sm text-text-secondary">Sin actividades el {selectedDay} {currentMonth.toLocaleDateString('es-CL', { month: 'short' })}</p>
        </div>
      )}
    </div>
  )
}
