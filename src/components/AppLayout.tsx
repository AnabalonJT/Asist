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
            <span className="text-base">🏃</span>
            <span className="font-semibold text-text-primary text-sm">HabitBot</span>
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
