import { useState, FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { authApi } from '../lib/api'

export function RegisterPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    if (password !== confirm) {
      setError('Las contraseñas no coinciden')
      return
    }
    if (password.length < 6) {
      setError('La contraseña debe tener al menos 6 caracteres')
      return
    }
    setLoading(true)
    try {
      const { data } = await authApi.register(email, password)
      await login(data.access_token)
      navigate('/dashboard')
    } catch (err: any) {
      setError(err.response?.data?.detail ?? 'No se pudo crear la cuenta')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="h-full flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="mb-8 text-center">
          <div className="inline-flex items-center gap-2 mb-2">
            <span className="text-2xl">🏃</span>
            <span className="text-xl font-semibold text-text-primary">HabitBot</span>
          </div>
          <p className="text-text-secondary text-sm">Seguimiento de hábitos vía Telegram</p>
        </div>

        <div className="card">
          <h1 className="text-lg font-semibold text-text-primary mb-6">Crear cuenta</h1>

          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="block text-xs text-text-secondary mb-1.5">Email</label>
              <input
                type="email"
                className="input"
                placeholder="tu@email.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
              />
            </div>
            <div>
              <label className="block text-xs text-text-secondary mb-1.5">Contraseña</label>
              <input
                type="password"
                className="input"
                placeholder="Mínimo 6 caracteres"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="block text-xs text-text-secondary mb-1.5">Confirmar contraseña</label>
              <input
                type="password"
                className="input"
                placeholder="••••••••"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
              />
            </div>

            {error && (
              <p className="text-danger text-sm bg-danger/10 border border-danger/20 rounded-lg px-3 py-2">
                {error}
              </p>
            )}

            <button type="submit" className="btn-primary w-full" disabled={loading}>
              {loading ? 'Creando cuenta...' : 'Crear cuenta'}
            </button>
          </form>
        </div>

        <p className="text-center text-text-secondary text-sm mt-4">
          ¿Ya tienes cuenta?{' '}
          <Link to="/login" className="text-accent hover:text-blue-400 transition-colors">
            Inicia sesión
          </Link>
        </p>
      </div>
    </div>
  )
}
