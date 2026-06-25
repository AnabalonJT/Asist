import { useEffect, useState } from 'react'
import { Activity } from '../lib/api'
import api from '../lib/api'

interface Props {
  userId?: number
}

export function Calendar({ userId }: Props) {
  const [activities, setActivities] = useState<Activity[]>([])
  const [currentMonth, setCurrentMonth] = useState(new Date())
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchMonth()
  }, [currentMonth])

  const fetchMonth = async () => {
    setLoading(true)
    const year = currentMonth.getFullYear()
    const month = currentMonth.getMonth()
    const start = new Date(year, month, 1).toISOString().split('T')[0]
    const end = new Date(year, month + 1, 0).toISOString().split('T')[0]

    try {
      const { data } = await api.get<Activity[]>(`/activities?start_date=${start}&end_date=${end}`)
      setActivities(data)
    } catch {
      setActivities([])
    } finally {
      setLoading(false)
    }
  }

  const year = currentMonth.getFullYear()
  const month = currentMonth.getMonth()
  const firstDay = new Date(year, month, 1).getDay()
  const daysInMonth = new Date(year, month + 1, 0).getDate()

  // Group activities by day
  const activityDays = new Map<number, Activity[]>()
  activities.forEach((a) => {
    const day = new Date(a.timestamp).getDate()
    if (!activityDays.has(day)) activityDays.set(day, [])
    activityDays.get(day)!.push(a)
  })

  const prevMonth = () => setCurrentMonth(new Date(year, month - 1, 1))
  const nextMonth = () => setCurrentMonth(new Date(year, month + 1, 1))

  const monthName = currentMonth.toLocaleDateString('es-CL', { month: 'long', year: 'numeric' })

  const today = new Date()
  const isToday = (day: number) =>
    today.getFullYear() === year && today.getMonth() === month && today.getDate() === day

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
          <div key={d} className="text-center text-xs text-text-dim font-medium py-1">
            {d}
          </div>
        ))}
      </div>

      {/* Days grid */}
      <div className="grid grid-cols-7 gap-1">
        {/* Empty cells for offset (adjust Sunday=0 to Monday=0) */}
        {Array.from({ length: (firstDay + 6) % 7 }).map((_, i) => (
          <div key={`empty-${i}`} className="h-9" />
        ))}

        {/* Day cells */}
        {Array.from({ length: daysInMonth }).map((_, i) => {
          const day = i + 1
          const dayActivities = activityDays.get(day)
          const hasActivity = !!dayActivities && dayActivities.length > 0
          const totalCal = dayActivities?.reduce((s, a) => s + a.calories, 0) ?? 0

          return (
            <div
              key={day}
              className={`h-9 rounded-lg flex flex-col items-center justify-center text-xs relative
                ${isToday(day) ? 'ring-1 ring-accent' : ''}
                ${hasActivity ? 'bg-accent/15 text-accent font-semibold' : 'text-text-secondary'}
              `}
              title={hasActivity ? `${dayActivities!.length} actividades, ${totalCal} cal` : undefined}
            >
              <span>{day}</span>
              {hasActivity && (
                <div className="flex gap-0.5 mt-0.5">
                  {dayActivities!.length <= 3
                    ? dayActivities!.map((_, idx) => (
                        <div key={idx} className="w-1 h-1 rounded-full bg-accent" />
                      ))
                    : <div className="w-1.5 h-1.5 rounded-full bg-accent" />
                  }
                </div>
              )}
            </div>
          )
        })}
      </div>

      {loading && (
        <div className="text-center text-xs text-text-dim mt-2">Cargando...</div>
      )}
    </div>
  )
}
