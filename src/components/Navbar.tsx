import { NavLink } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

export function Navbar() {
  const { user } = useAuth()

  const links = [
    { to: '/dashboard', icon: '🏠', label: 'Inicio' },
    { to: '/goals', icon: '🎯', label: 'Metas' },
    { to: '/activities', icon: '📋', label: 'Registros' },
    { to: '/fitness', icon: '🏋️', label: 'Fitness' },
    { to: '/settings', icon: '⚙️', label: 'Config' },
    ...(user?.is_admin ? [{ to: '/admin', icon: '🛡️', label: 'Admin' }] : []),
  ]

  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-bg-surface/95 backdrop-blur-sm border-t border-bg-border z-50 safe-bottom">
      <div className="max-w-2xl mx-auto flex justify-around py-2">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) =>
              `flex flex-col items-center gap-0.5 px-3 py-1 rounded-lg transition-colors ${
                isActive ? 'text-accent' : 'text-text-dim hover:text-text-secondary'
              }`
            }
          >
            <span className="text-lg">{link.icon}</span>
            <span className="text-[10px] font-medium">{link.label}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
