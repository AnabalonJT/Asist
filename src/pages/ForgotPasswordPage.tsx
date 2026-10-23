import { useState, FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authApi } from '../lib/api'

export function ForgotPasswordPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState<'request' | 'reset'>('request')
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)

  const submitRequest = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccess('')
    setLoading(true)
    try {
      await authApi.forgotPassword(email)
      setStep('reset')
    } catch (err: any) {
      setError(err.response?.data?.detail ?? 'No se pudo procesar la solicitud. Inténtalo de nuevo.')
    } finally {
      setLoading(false)
    }
  }

  const submitReset = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccess('')
    setLoading(true)
    try {
      await authApi.resetPassword(email, code, newPassword)
      setSuccess('Contraseña actualizada. Redirigiendo…')
      setTimeout(() => navigate('/login'), 1500)
    } catch (err: any) {
      setError(err.response?.data?.detail ?? 'No se pudo restablecer la contraseña. Inténtalo de nuevo.')
      // Preserve entered fields except clear the password field
      setNewPassword('')
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
          <h1 className="text-lg font-semibold text-text-primary mb-6">Recuperar contraseña</h1>

          {step === 'request' ? (
            <form onSubmit={submitRequest} className="space-y-4">
              <p className="text-text-secondary text-sm">
                Ingresa tu email y te enviaremos un código de recuperación por Telegram.
              </p>
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

              {error && (
                <p className="text-danger text-sm bg-danger/10 border border-danger/20 rounded-lg px-3 py-2">
                  {error}
                </p>
              )}

              <button type="submit" className="btn-primary w-full" disabled={loading}>
                {loading ? 'Enviando...' : 'Enviar código'}
              </button>
            </form>
          ) : (
            <form onSubmit={submitReset} className="space-y-4">
              <p className="text-text-secondary text-sm">
                Revisa el bot de Telegram: te enviamos un código de recuperación. Ingrésalo junto con
                tu nueva contraseña.
              </p>
              <div>
                <label className="block text-xs text-text-secondary mb-1.5">Código de recuperación</label>
                <input
                  type="text"
                  inputMode="numeric"
                  className="input"
                  placeholder="123456"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  required
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-xs text-text-secondary mb-1.5">Nueva contraseña</label>
                <input
                  type="password"
                  className="input"
                  placeholder="••••••••"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  required
                />
              </div>

              {error && (
                <p className="text-danger text-sm bg-danger/10 border border-danger/20 rounded-lg px-3 py-2">
                  {error}
                </p>
              )}

              {success && (
                <p className="text-accent text-sm bg-accent/10 border border-accent/20 rounded-lg px-3 py-2">
                  {success}
                </p>
              )}

              <button type="submit" className="btn-primary w-full" disabled={loading}>
                {loading ? 'Restableciendo...' : 'Restablecer contraseña'}
              </button>
            </form>
          )}
        </div>

        <p className="text-center text-text-secondary text-sm mt-4">
          <Link to="/login" className="text-accent hover:text-blue-400 transition-colors">
            Volver a iniciar sesión
          </Link>
        </p>
      </div>
    </div>
  )
}
