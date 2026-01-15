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
}

interface AuthContextType {
  user: User | null
  token: string | null
  isLoading: boolean
  isAuthenticated: boolean
  signup: (data: SignupData) => Promise<void>
  signin: (email: string, password: string) => Promise<void>
  login: (email: string, name?: string) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

const TOKEN_KEY = 'professor_access_token'
const REFRESH_TOKEN_KEY = 'professor_refresh_token'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const fetchUser = useCallback(async (accessToken: string) => {
    try {
      const userData = await api.auth.getCurrentUser(accessToken)
      setUser(userData)
      return userData
    } catch (error) {
      console.error('Failed to fetch user:', error)
      // Token might be expired, try to refresh
      const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY)
      if (refreshToken) {
        try {
          const tokens = await api.auth.refreshToken(refreshToken)
          localStorage.setItem(TOKEN_KEY, tokens.access_token)
          localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token)
          setToken(tokens.access_token)
          const userData = await api.auth.getCurrentUser(tokens.access_token)
          setUser(userData)
          return userData
        } catch {
          // Refresh failed, clear tokens
          localStorage.removeItem(TOKEN_KEY)
          localStorage.removeItem(REFRESH_TOKEN_KEY)
          setToken(null)
          setUser(null)
        }
      }
      return null
    }
  }, [])

  // Initialize auth state from localStorage
  useEffect(() => {
    const initAuth = async () => {
      const storedToken = localStorage.getItem(TOKEN_KEY)
      if (storedToken) {
        setToken(storedToken)
        await fetchUser(storedToken)
      }
      setIsLoading(false)
    }
    initAuth()
  }, [fetchUser])

  const signup = async (data: SignupData) => {
    setIsLoading(true)
    try {
      const tokens = await api.auth.signup(data)
      localStorage.setItem(TOKEN_KEY, tokens.access_token)
      localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token)
      setToken(tokens.access_token)
      await fetchUser(tokens.access_token)
    } catch (error) {
      console.error('Signup failed:', error)
      throw error
    } finally {
      setIsLoading(false)
    }
  }

  const signin = async (email: string, password: string) => {
    setIsLoading(true)
    try {
      const tokens = await api.auth.signin(email, password)
      localStorage.setItem(TOKEN_KEY, tokens.access_token)
      localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token)
      setToken(tokens.access_token)
      await fetchUser(tokens.access_token)
    } catch (error) {
      console.error('Signin failed:', error)
      throw error
    } finally {
      setIsLoading(false)
    }
  }

  const login = async (email: string, name?: string) => {
    setIsLoading(true)
    try {
      const tokens = await api.auth.devLogin(email, name)
      localStorage.setItem(TOKEN_KEY, tokens.access_token)
      localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token)
      setToken(tokens.access_token)
      await fetchUser(tokens.access_token)
    } catch (error) {
      console.error('Login failed:', error)
      throw error
    } finally {
      setIsLoading(false)
    }
  }

  const logout = () => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
    setToken(null)
    setUser(null)
  }

  const refreshUser = async () => {
    if (token) {
      await fetchUser(token)
    }
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        isAuthenticated: !!user && !!token,
        signup,
        signin,
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
