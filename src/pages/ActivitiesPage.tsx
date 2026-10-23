import { ActivityFeed } from '../components/ActivityFeed'

export function ActivitiesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold text-text-primary leading-none">Registros</h1>
        <p className="text-sm text-text-secondary mt-1">Historial de todas tus actividades</p>
      </div>

      <ActivityFeed />
    </div>
  )
}
