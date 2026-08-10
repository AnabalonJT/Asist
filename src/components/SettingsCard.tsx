import { useEffect, useState } from 'react'
import { settingsApi, UserSettings } from '../lib/api'

export function SettingsCard() {
  const [settings, setSettings] = useState<UserSettings | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    settingsApi.get().then(({ data }) => { setSettings(data); setLoading(false) }).catch(() => setLoading(false))
  }, [])

  const toggleCalories = async () => {
    if (!settings) return
    const newVal = !settings.show_calories
    setSettings({ ...settings, show_calories: newVal })
    await settingsApi.update({ show_calories: newVal })
  }

  if (loading || !settings) return null

  return (
    <div className="card">
      <h2 className="text-sm font-semibold text-text-primary mb-3">⚙️ Configuración</h2>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-text-primary">Mostrar calorías</p>
          <p className="text-xs text-text-dim">Calcular y mostrar calorías en actividades deportivas</p>
        </div>
        <button
          onClick={toggleCalories}
          className={`relative w-11 h-6 rounded-full transition-colors ${
            settings.show_calories ? 'bg-accent' : 'bg-bg-elevated border border-bg-border'
          }`}
        >
          <div
            className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${
              settings.show_calories ? 'translate-x-5' : 'translate-x-0.5'
            }`}
          />
        </button>
      </div>
    </div>
  )
}
