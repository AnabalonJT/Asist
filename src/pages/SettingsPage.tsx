import { useState, FormEvent } from 'react'
import { useAuth } from '../hooks/useAuth'
import { settingsApi, UserSettings } from '../lib/api'
import { useEffect } from 'react'
import api from '../lib/api'

export function SettingsPage() {
  const { user, logout } = useAuth()
  const [settings, setSettings] = useState<UserSettings | null>(null)
  const [pwOld, setPwOld] = useState('')
  const [pwNew, setPwNew] = useState('')
  const [pwMsg, setPwMsg] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    settingsApi.get().then(({ data }) => setSettings(data)).catch(() => {})
  }, [])

  const toggleCalories = async () => {
    if (!settings) return
    const newVal = !settings.show_calories
    setSettings({ ...settings, show_calories: newVal })
    await settingsApi.update({ show_calories: newVal })
  }

  const changePassword = async (e: FormEvent) => {
    e.preventDefault()
    if (pwNew.length < 6) { setPwMsg('Mínimo 6 caracteres'); return }
    setSaving(true)
    setPwMsg('')
    try {
      await api.put('/auth/change-password', { old_password: pwOld, new_password: pwNew })
      setPwMsg('✅ Contraseña actualizada')
      setPwOld('')
      setPwNew('')
    } catch (err: any) {
      setPwMsg(err.response?.data?.detail ?? '❌ Error al cambiar contraseña')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-text-primary">⚙️ Configuración</h1>
      </div>

      {/* Profile */}
      <div className="card">
        <h2 className="text-sm font-semibold text-text-primary mb-3">👤 Perfil</h2>
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-sm text-text-secondary">Email</span>
            <span className="text-sm text-text-primary">{user?.email}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-sm text-text-secondary">Telegram</span>
            <span className={`text-sm ${user?.telegram_linked ? 'text-success' : 'text-text-dim'}`}>
              {user?.telegram_linked ? '✓ Conectado' : 'No conectado'}
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-sm text-text-secondary">Zona horaria</span>
            <span className="text-sm text-text-primary">{settings?.timezone ?? '...'}</span>
          </div>
        </div>
      </div>

      {/* Preferences */}
      <div className="card">
        <h2 className="text-sm font-semibold text-text-primary mb-3">🔧 Preferencias</h2>
        <div className="space-y-4">
          {/* Calories toggle */}
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-text-primary">Mostrar calorías</p>
              <p className="text-xs text-text-dim">Calcular calorías en deportes</p>
            </div>
            <button
              onClick={toggleCalories}
              className={`relative w-11 h-6 rounded-full transition-colors ${
                settings?.show_calories ? 'bg-accent' : 'bg-bg-elevated border border-bg-border'
              }`}
            >
              <div className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${
                settings?.show_calories ? 'translate-x-5' : 'translate-x-0.5'
              }`} />
            </button>
          </div>
        </div>
      </div>

      {/* Change password */}
      <div className="card">
        <h2 className="text-sm font-semibold text-text-primary mb-3">🔒 Cambiar contraseña</h2>
        <form onSubmit={changePassword} className="space-y-3">
          <input
            type="password"
            className="input"
            placeholder="Contraseña actual"
            value={pwOld}
            onChange={(e) => setPwOld(e.target.value)}
            required
          />
          <input
            type="password"
            className="input"
            placeholder="Nueva contraseña (mín. 6)"
            value={pwNew}
            onChange={(e) => setPwNew(e.target.value)}
            required
          />
          {pwMsg && (
            <p className={`text-xs ${pwMsg.startsWith('✅') ? 'text-success' : 'text-danger'}`}>{pwMsg}</p>
          )}
          <button type="submit" className="btn-primary w-full text-sm" disabled={saving}>
            {saving ? 'Guardando...' : 'Cambiar contraseña'}
          </button>
        </form>
      </div>

      {/* Logout */}
      <button onClick={logout} className="w-full text-center text-sm text-danger py-3 hover:bg-danger/10 rounded-lg transition-colors">
        Cerrar sesión
      </button>
    </div>
  )
}
