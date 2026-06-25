import { useState } from 'react'
import { authApi } from '../lib/api'

interface Props {
  linked: boolean
  onLinked: () => void
}

export function TelegramLinkCard({ linked, onLinked }: Props) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleConnect = async () => {
    setError('')
    setLoading(true)
    try {
      const { data } = await authApi.linkingToken()
      // Open bot in new tab — if already started, goes straight to chat
      window.open(data.bot_url, '_blank', 'noopener,noreferrer')
      // Poll /me every 2s for up to 60s to detect linking
      let attempts = 0
      const interval = setInterval(async () => {
        attempts++
        try {
          const me = await authApi.me()
          if (me.data.telegram_linked) {
            clearInterval(interval)
            onLinked()
          }
        } catch {
          // ignore
        }
        if (attempts >= 30) clearInterval(interval)
      }, 2000)
    } catch (err: any) {
      setError('No se pudo generar el enlace')
    } finally {
      setLoading(false)
    }
  }

  if (linked) {
    return (
      <div className="card flex items-center gap-4">
        <div className="w-10 h-10 rounded-full bg-tg/10 flex items-center justify-center flex-shrink-0">
          <svg className="w-5 h-5 text-tg" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.562 8.248-2.012 9.479c-.145.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12L6.155 14.36l-2.936-.92c-.638-.203-.65-.638.136-.943l11.45-4.415c.537-.194 1.006.131.757.166z" />
          </svg>
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-text-primary">Telegram conectado</p>
          <p className="text-xs text-text-secondary mt-0.5">Ya puedes registrar actividades desde el bot</p>
        </div>
        <span className="badge bg-success/10 text-success border border-success/20">✓ Activo</span>
      </div>
    )
  }

  return (
    <div className="card">
      <div className="flex items-start gap-4">
        <div className="w-10 h-10 rounded-full bg-bg-elevated flex items-center justify-center flex-shrink-0">
          <svg className="w-5 h-5 text-text-dim" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.562 8.248-2.012 9.479c-.145.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12L6.155 14.36l-2.936-.92c-.638-.203-.65-.638.136-.943l11.45-4.415c.537-.194 1.006.131.757.166z" />
          </svg>
        </div>
        <div className="flex-1">
          <p className="text-sm font-medium text-text-primary">Conectar Telegram</p>
          <p className="text-xs text-text-secondary mt-0.5 mb-4">
            Vincula tu cuenta para registrar actividades en lenguaje natural
          </p>
          {error && (
            <p className="text-danger text-xs mb-3">{error}</p>
          )}
          <button
            onClick={handleConnect}
            disabled={loading}
            className="inline-flex items-center gap-2 bg-tg hover:bg-tg/90 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors disabled:opacity-50"
          >
            {loading ? (
              <span className="w-4 h-4 rounded-full border-2 border-white border-t-transparent animate-spin" />
            ) : (
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.562 8.248-2.012 9.479c-.145.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12L6.155 14.36l-2.936-.92c-.638-.203-.65-.638.136-.943l11.45-4.415c.537-.194 1.006.131.757.166z" />
              </svg>
            )}
            {loading ? 'Esperando vinculación...' : 'Abrir en Telegram'}
          </button>
        </div>
      </div>
    </div>
  )
}
