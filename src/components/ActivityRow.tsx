import { Activity } from '../lib/api'

const ACTIVITY_ICONS: Record<string, string> = {
  running: '🏃',
  walking: '🚶',
  cycling: '🚴',
  gym: '🏋️',
  swimming: '🏊',
  yoga: '🧘',
}

function formatDate(iso: string) {
  const d = new Date(iso)
  return d.toLocaleDateString('es-CL', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

function capitalize(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export function ActivityRow({ activity }: { activity: Activity }) {
  const icon = ACTIVITY_ICONS[activity.activity_type.toLowerCase()] ?? '⚡'

  return (
    <div className="flex items-center gap-3 py-3 border-b border-bg-border last:border-0">
      <span className="text-xl w-8 text-center">{icon}</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-text-primary">{capitalize(activity.activity_type)}</p>
        <p className="text-xs text-text-secondary">
          {[
            activity.duration_minutes && `${activity.duration_minutes} min`,
            activity.distance_km && `${activity.distance_km} km`,
          ]
            .filter(Boolean)
            .join(' · ') || 'Sin detalles'}
        </p>
      </div>
      <div className="text-right flex-shrink-0">
        <p className="text-sm font-mono text-warning">{activity.calories} cal</p>
        <p className="text-xs text-text-dim">{formatDate(activity.timestamp)}</p>
      </div>
    </div>
  )
}
