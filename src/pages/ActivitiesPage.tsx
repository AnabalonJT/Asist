import { ActivityFeed } from '../components/ActivityFeed'

export function ActivitiesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-text-primary">📋 Registros</h1>
        <p className="text-xs text-text-secondary mt-0.5">Historial de todas tus actividades</p>
      </div>

      <ActivityFeed />
    </div>
  )
}
