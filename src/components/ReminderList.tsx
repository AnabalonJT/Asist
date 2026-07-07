import { useEffect, useState } from 'react'
import { remindersApi, ReminderItem } from '../lib/api'

export function ReminderList() {
  const [reminders, setReminders] = useState<ReminderItem[]>([])
  const [loading, setLoading] = useState(true)

  const fetch = async () => {
    try {
      const { data } = await remindersApi.list()
      setReminders(data)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetch()
    const interval = setInterval(fetch, 30000)
    return () => clearInterval(interval)
  }, [])

  const handleToggle = async (id: number, active: boolean) => {
    await remindersApi.toggle(id, !active)
    setReminders((prev) => prev.map((r) => (r.id === id ? { ...r, active: !active } : r)))
  }

  const handleDelete = async (id: number) => {
    await remindersApi.delete(id)
    setReminders((prev) => prev.filter((r) => r.id !== id))
  }

  if (loading) {
    return (
      <div className="card">
        <div className="h-16 animate-pulse bg-bg-elevated rounded-lg" />
      </div>
    )
  }

  if (reminders.length === 0) {
    return (
      <div className="card">
        <h2 className="text-sm font-semibold text-text-primary mb-2">⏰ Recordatorios</h2>
        <p className="text-xs text-text-secondary py-4 text-center">
          No tienes recordatorios. Crea uno desde Telegram:<br />
          <span className="text-text-dim italic">"Recuérdame meditar a las 8:00"</span>
        </p>
      </div>
    )
  }

  const freq = (f: string) =>
    ({ daily: 'Diario', weekly: 'Semanal', weekdays: 'L-V' }[f] ?? f)

  return (
    <div className="card">
      <h2 className="text-sm font-semibold text-text-primary mb-3">⏰ Recordatorios</h2>
      <div className="space-y-2">
        {reminders.map((r) => (
          <div
            key={r.id}
            className={`flex items-center justify-between py-2 px-3 rounded-lg border border-bg-border ${
              r.active ? 'bg-bg-surface' : 'bg-bg-elevated opacity-50'
            }`}
          >
            <div className="flex-1 min-w-0">
              <p className="text-sm text-text-primary truncate">{r.message}</p>
              <p className="text-xs text-text-secondary">
                🕐 {r.schedule} · {freq(r.frequency)}
              </p>
            </div>
            <div className="flex items-center gap-2 ml-2">
              <button
                onClick={() => handleToggle(r.id, r.active)}
                className={`text-xs px-2 py-1 rounded ${
                  r.active
                    ? 'bg-success/10 text-success border border-success/20'
                    : 'bg-bg-elevated text-text-dim border border-bg-border'
                }`}
              >
                {r.active ? '✓' : '⏸'}
              </button>
              <button
                onClick={() => handleDelete(r.id)}
                className="text-xs px-2 py-1 rounded bg-danger/10 text-danger border border-danger/20 hover:bg-danger/20"
              >
                ✕
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
