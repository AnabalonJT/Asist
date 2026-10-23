import { Outlet } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { Navbar } from './Navbar'

export function AppLayout() {
  const { user, logout } = useAuth()

  return (
    <div className="min-h-full pb-20">
      {/* Top header */}
      <header className="border-b border-bg-border bg-bg-surface/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-2xl mx-auto px-4 h-12 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-6 h-6 rounded-md bg-accent/15 text-accent flex items-center justify-center flex-shrink-0" aria-hidden="true">
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z" />
              </svg>
            </span>
            <span className="font-display text-base font-semibold tracking-tight text-text-primary">HabitTrack</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-text-dim hidden sm:block">{user?.email}</span>
            <button onClick={logout} className="text-xs text-text-dim hover:text-text-primary px-2 py-1">
              Salir
            </button>
          </div>
        </div>
      </header>

      {/* Page content */}
      <main className="max-w-2xl mx-auto px-4 py-4">
        <Outlet />
      </main>

      {/* Bottom nav */}
      <Navbar />
    </div>
  )
}
