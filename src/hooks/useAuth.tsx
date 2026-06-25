import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { authApi, UserMe } from '../lib/api'

interface AuthCtx {
  user: UserMe | null
  loading: boolean
  login: (token: string) => Promise<void>
  logout: () => void
}

const Ctx = createContext<AuthCtx | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserMe | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) { setLoading(false); return }

    authApi.me()
      .then((r) => setUser(r.data))
      .catch(() => localStorage.removeItem('token'))
      .finally(() => setLoading(false))
  }, [])

  const login = async (token: string) => {
    localStorage.setItem('token', token)
    const r = await authApi.me()
    setUser(r.data)
  }

  const logout = () => {
    localStorage.removeItem('token')
    setUser(null)
  }

  return <Ctx.Provider value={{ user, loading, login, logout }}>{children}</Ctx.Provider>
}

export const useAuth = () => {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useAuth must be inside AuthProvider')
  return ctx
}
