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

/** A strength activity has at least one logged set (reps/weight). */
export function isStrength(activity: Activity): boolean {
  return Array.isArray(activity.sets) && activity.sets.length > 0
}

/** "10×40kg · 10×50kg · 8×60kg" — skips weight when missing. */
export function formatSets(activity: Activity): string {
  const sets = activity.sets ?? []
  return sets
    .map((s) => {
      const reps = s.reps ?? 0
      return s.weight_kg != null ? `${reps}×${s.weight_kg}kg` : `${reps} reps`
    })
    .join(' · ')
}

/** "1.380 kg" — volume formatted with the es-CL thousands separator. */
export function formatVolume(volume: number): string {
  return `${Math.round(volume).toLocaleString('es-CL')} kg`
}

export function ActivityRow({ activity }: { activity: Activity }) {
  const strength = isStrength(activity)
  const title = activity.exercise_name || capitalize(activity.activity_type)
  const icon = strength ? '🏋️' : ACTIVITY_ICONS[activity.activity_type.toLowerCase()] ?? '⚡'

  return (
    <div className="flex items-center gap-3 py-3 border-b border-bg-border last:border-0">
      <span className="text-xl w-8 text-center">{icon}</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-text-primary truncate">{title}</p>
        <p className="text-xs text-text-secondary">
          {strength
            ? `${activity.sets!.length} ${activity.sets!.length === 1 ? 'serie' : 'series'} · ${formatSets(activity)}`
            : [
                activity.duration_minutes && `${activity.duration_minutes} min`,
                activity.distance_km && `${activity.distance_km} km`,
              ]
                .filter(Boolean)
                .join(' · ') || 'Sin detalles'}
        </p>
      </div>
      <div className="text-right flex-shrink-0">
        {strength ? (
          <p className="text-sm font-mono text-accent">{formatVolume(activity.total_volume ?? 0)}</p>
        ) : (
          <p className="text-sm font-mono text-warning">{activity.calories} cal</p>
        )}
        <p className="text-xs text-text-dim">{formatDate(activity.timestamp)}</p>
      </div>
    </div>
  )
}
