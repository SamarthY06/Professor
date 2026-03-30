'use client'

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react'
import api from '@/lib/api'

interface User {
  id: string
  email: string
  name: string
  role: string
  has_api_key: boolean
}

interface SignupData {
  email: string
  password: string
  name: string
  phone?: string
  verification_code?: string
}

interface AuthContextType {
  user: User | null
  token: string | null
  isLoading: boolean
  isAuthenticated: boolean
  signup: (data: SignupData) => Promise<void>
  signin: (email: string, password: string) => Promise<void>
  googleLogin: (code: string, redirectUri: string) => Promise<void>
  login: (email: string, name?: string) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

/**
 * Auth tokens are now stored in httpOnly cookies set by the backend.
 * We keep a thin `token` state for any callers that still need it
 * (e.g. explicit Authorization headers), but the primary auth
 * mechanism is the cookie sent automatically by the browser via
 * `credentials: 'include'`.
 */

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const fetchUser = useCallback(async (accessToken?: string) => {
    try {
      const userData = await api.auth.getCurrentUser(accessToken || '')
      setUser(userData)
      return userData
    } catch {
      setToken(null)
      setUser(null)
      return null
    }
  }, [])

  useEffect(() => {
    const initAuth = async () => {
      // Try cookie-based auth first (no token needed)
      await fetchUser()
      setIsLoading(false)
    }
    initAuth()
  }, [fetchUser])

  const signup = async (data: SignupData) => {
    setIsLoading(true)
    try {
      const tokens = await api.auth.signup(data)
      setToken(tokens.access_token)
      await fetchUser(tokens.access_token)
    } finally {
      setIsLoading(false)
    }
  }

  const signin = async (email: string, password: string) => {
    setIsLoading(true)
    try {
      const tokens = await api.auth.signin(email, password)
      setToken(tokens.access_token)
      await fetchUser(tokens.access_token)
    } finally {
      setIsLoading(false)
    }
  }

  const googleLogin = async (code: string, redirectUri: string) => {
    setIsLoading(true)
    try {
      const tokens = await api.auth.googleLogin(code, redirectUri)
      setToken(tokens.access_token)
      await fetchUser(tokens.access_token)
    } finally {
      setIsLoading(false)
    }
  }

  const login = async (email: string, name?: string) => {
    setIsLoading(true)
    try {
      const tokens = await api.auth.devLogin(email, name)
      setToken(tokens.access_token)
      await fetchUser(tokens.access_token)
    } finally {
      setIsLoading(false)
    }
  }

  const logout = async () => {
    try {
      await api.auth.logout()
    } catch {
      // ignore — cookie may already be gone
    }
    setToken(null)
    setUser(null)
  }

  const refreshUser = async () => {
    await fetchUser(token || undefined)
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        isAuthenticated: !!user,
        signup,
        signin,
        googleLogin,
        login,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
