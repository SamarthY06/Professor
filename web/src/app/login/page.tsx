'use client'

import { useState, useEffect, useRef, Suspense } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { Brain, ArrowLeft, Loader2, Mail, User, Phone, Lock, Eye, EyeOff, CheckCircle2 } from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'
import api from '@/lib/api'

type AuthMode = 'signin' | 'signup'
type SignupStep = 'email' | 'verify' | 'details'

const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID

function LoginContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { signup, signin, googleLogin, isAuthenticated, isLoading: authLoading } = useAuth()
  const [mode, setMode] = useState<AuthMode>(() => {
    return searchParams.get('mode') === 'signup' ? 'signup' : 'signin'
  })
  const [signupStep, setSignupStep] = useState<SignupStep>('email')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [successMessage, setSuccessMessage] = useState('')
  const [showGoogleFallback, setShowGoogleFallback] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)

  // Form fields
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')

  // Verification
  const [verificationCode, setVerificationCode] = useState(['', '', '', '', '', ''])
  const [resendCooldown, setResendCooldown] = useState(0)
  const codeInputRefs = useRef<(HTMLInputElement | null)[]>([])

  const redirectUrl = searchParams.get('redirect') || '/dashboard'

  // Google OAuth callback — use a ref to ensure we only attempt the exchange once per code
  const googleCodeHandled = useRef<string | null>(null)
  useEffect(() => {
    const code = searchParams.get('code')
    if (!code || googleCodeHandled.current === code) return
    googleCodeHandled.current = code

    const redirectUri = `${window.location.origin}/login`
    setIsLoading(true)
    googleLogin(code, redirectUri)
      .then(() => router.push(redirectUrl))
      .catch((err: any) => {
        setError(err.message || 'Google sign-in failed. Please try again.')
        // Remove the code from the URL to prevent retry loops
        const url = new URL(window.location.href)
        url.searchParams.delete('code')
        url.searchParams.delete('iss')
        url.searchParams.delete('scope')
        url.searchParams.delete('authuser')
        url.searchParams.delete('prompt')
        router.replace(url.pathname + url.search)
      })
      .finally(() => setIsLoading(false))
  }, [searchParams, googleLogin, router, redirectUrl])

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated && !authLoading) {
      router.push(redirectUrl)
    }
  }, [isAuthenticated, authLoading, router, redirectUrl])

  // Resend cooldown timer
  useEffect(() => {
    if (resendCooldown <= 0) return
    const timer = setTimeout(() => setResendCooldown(resendCooldown - 1), 1000)
    return () => clearTimeout(timer)
  }, [resendCooldown])

  const handleSendVerification = async () => {
    setError('')
    if (!email || !email.includes('@')) {
      setError('Please enter a valid email address')
      return
    }

    setIsLoading(true)
    try {
      await api.auth.sendVerification(email)
      setSignupStep('verify')
      setSuccessMessage(`Verification code sent to ${email}`)
      setShowGoogleFallback(false)
      setResendCooldown(60)
    } catch (err: any) {
      const msg = err.message || 'Failed to send verification code.'
      setError(msg)
      if (msg.toLowerCase().includes('limit') || msg.toLowerCase().includes('tomorrow') || err.status === 429) {
        setShowGoogleFallback(true)
      }
    } finally {
      setIsLoading(false)
    }
  }

  const handleCodeChange = (index: number, value: string) => {
    if (value.length > 1) {
      const digits = value.replace(/\D/g, '').slice(0, 6).split('')
      const newCode = [...verificationCode]
      digits.forEach((d, i) => {
        if (index + i < 6) newCode[index + i] = d
      })
      setVerificationCode(newCode)
      const nextIdx = Math.min(index + digits.length, 5)
      codeInputRefs.current[nextIdx]?.focus()
      return
    }

    const digit = value.replace(/\D/g, '')
    const newCode = [...verificationCode]
    newCode[index] = digit
    setVerificationCode(newCode)

    if (digit && index < 5) {
      codeInputRefs.current[index + 1]?.focus()
    }
  }

  const handleCodeKeyDown = (index: number, e: React.KeyboardEvent) => {
    if (e.key === 'Backspace' && !verificationCode[index] && index > 0) {
      codeInputRefs.current[index - 1]?.focus()
    }
  }

  const handleVerifyCode = async () => {
    setError('')
    const code = verificationCode.join('')
    if (code.length !== 6) {
      setError('Please enter the full 6-digit code')
      return
    }

    setIsLoading(true)
    try {
      await api.auth.verifyEmail(email, code)
      setSignupStep('details')
      setSuccessMessage('')
    } catch (err: any) {
      setError(err.message || 'Invalid verification code.')
    } finally {
      setIsLoading(false)
    }
  }

  const handleResendCode = async () => {
    if (resendCooldown > 0) return
    setError('')
    setIsLoading(true)
    try {
      await api.auth.sendVerification(email)
      setResendCooldown(60)
      setSuccessMessage('New verification code sent!')
      setShowGoogleFallback(false)
      setVerificationCode(['', '', '', '', '', ''])
    } catch (err: any) {
      const msg = err.message || 'Failed to resend code.'
      setError(msg)
      if (msg.toLowerCase().includes('limit') || msg.toLowerCase().includes('tomorrow') || err.status === 429) {
        setShowGoogleFallback(true)
      }
    } finally {
      setIsLoading(false)
    }
  }

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (!name.trim()) {
      setError('Please enter your name')
      return
    }
    if (!password || password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }

    setIsLoading(true)
    try {
      await signup({
        email,
        password,
        name,
        phone: phone || undefined,
        verification_code: verificationCode.join(''),
      })
      router.push(redirectUrl)
    } catch (err: any) {
      setError(err.message || 'Failed to create account.')
    } finally {
      setIsLoading(false)
    }
  }

  const handleSignin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (!email || !email.includes('@')) {
      setError('Please enter a valid email address')
      return
    }
    if (!password || password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }

    setIsLoading(true)
    try {
      await signin(email, password)
      router.push(redirectUrl)
    } catch (err: any) {
      setError(err.message || 'Authentication failed. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }

  const handleGoogleLogin = () => {
    if (!GOOGLE_CLIENT_ID) {
      setError('Google login is not configured. Please set NEXT_PUBLIC_GOOGLE_CLIENT_ID.')
      return
    }

    const redirectUri = `${window.location.origin}/login`
    const scope = 'openid email profile'
    const params = new URLSearchParams({
      client_id: GOOGLE_CLIENT_ID,
      redirect_uri: redirectUri,
      response_type: 'code',
      scope,
      access_type: 'offline',
      prompt: 'consent',
    })

    window.location.href = `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`
  }

  const switchToSignup = () => {
    setMode('signup')
    setSignupStep('email')
    setError('')
    setSuccessMessage('')
    setVerificationCode(['', '', '', '', '', ''])
  }

  const switchToSignin = () => {
    setMode('signin')
    setSignupStep('email')
    setError('')
    setSuccessMessage('')
  }

  if (authLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-blue-50 to-white dark:from-gray-900 dark:to-gray-900 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-blue-50 to-white dark:from-gray-900 dark:to-gray-900 flex flex-col">
      {/* Back link */}
      <div className="p-6">
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 transition"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to home
        </Link>
      </div>

      {/* Auth Card */}
      <div className="flex-1 flex items-center justify-center px-6 pb-20">
        <div className="w-full max-w-md">
          <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-lg dark:shadow-gray-900/50 border dark:border-gray-700 p-8">
            {/* Logo */}
            <div className="flex items-center justify-center gap-2 mb-8">
              <Brain className="h-10 w-10 text-blue-600" />
              <span className="text-2xl font-bold text-gray-900 dark:text-gray-100">Professor</span>
            </div>

            {/* Tabs */}
            <div className="flex bg-gray-100 dark:bg-gray-700 rounded-lg p-1 mb-6">
              <button
                onClick={switchToSignin}
                className={`flex-1 py-2.5 text-sm font-medium rounded-md transition ${
                  mode === 'signin'
                    ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 shadow-sm'
                    : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100'
                }`}
              >
                Sign In
              </button>
              <button
                onClick={switchToSignup}
                className={`flex-1 py-2.5 text-sm font-medium rounded-md transition ${
                  mode === 'signup'
                    ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 shadow-sm'
                    : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100'
                }`}
              >
                Sign Up
              </button>
            </div>

            {/* Welcome text */}
            <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100 text-center mb-2">
              {mode === 'signin'
                ? 'Welcome back'
                : signupStep === 'email'
                  ? 'Create your account'
                  : signupStep === 'verify'
                    ? 'Check your email'
                    : 'Complete your profile'}
            </h1>
            <p className="text-gray-600 dark:text-gray-300 text-center text-sm mb-6">
              {mode === 'signin'
                ? 'Sign in to continue learning with Professor'
                : signupStep === 'email'
                  ? 'Start your AI-powered learning journey'
                  : signupStep === 'verify'
                    ? `We sent a 6-digit code to ${email}`
                    : 'Just a few more details to get started'}
            </p>

            {/* Step indicator for signup */}
            {mode === 'signup' && (
              <div className="flex items-center justify-center gap-2 mb-6">
                {(['email', 'verify', 'details'] as SignupStep[]).map((step, i) => (
                  <div key={step} className="flex items-center gap-2">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition ${
                      signupStep === step
                        ? 'bg-blue-600 text-white'
                        : i < ['email', 'verify', 'details'].indexOf(signupStep)
                          ? 'bg-blue-100 text-blue-600'
                          : 'bg-gray-100 dark:bg-gray-700 text-gray-400 dark:text-gray-500'
                    }`}>
                      {i < ['email', 'verify', 'details'].indexOf(signupStep) ? (
                        <CheckCircle2 className="h-5 w-5" />
                      ) : (
                        i + 1
                      )}
                    </div>
                    {i < 2 && (
                      <div className={`w-8 h-0.5 ${
                        i < ['email', 'verify', 'details'].indexOf(signupStep) ? 'bg-blue-300' : 'bg-gray-200 dark:bg-gray-700'
                      }`} />
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Error / Success messages */}
            {error && (
              <div className="mb-4">
                <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-400 text-sm">
                  {error}
                </div>
                {showGoogleFallback && (
                  <button
                    onClick={handleGoogleLogin}
                    className="mt-3 w-full flex items-center justify-center gap-3 px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition font-medium"
                  >
                    <GoogleIcon />
                    Sign up with Google instead
                  </button>
                )}
              </div>
            )}
            {successMessage && (
              <div className="mb-4 p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg text-green-700 dark:text-green-400 text-sm">
                {successMessage}
              </div>
            )}

            {/* =================== SIGN IN =================== */}
            {mode === 'signin' && (
              <>
                <button
                  onClick={handleGoogleLogin}
                  disabled={isLoading}
                  className="w-full flex items-center justify-center gap-3 px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition disabled:opacity-50 disabled:cursor-not-allowed font-medium text-gray-700 dark:text-gray-200"
                >
                  <GoogleIcon />
                  Continue with Google
                </button>

                <div className="flex items-center gap-4 my-6">
                  <div className="flex-1 h-px bg-gray-200 dark:bg-gray-700" />
                  <span className="text-sm text-gray-500 dark:text-gray-400">or</span>
                  <div className="flex-1 h-px bg-gray-200 dark:bg-gray-700" />
                </div>

                <form onSubmit={handleSignin} className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1.5">
                      Email Address
                    </label>
                    <div className="relative">
                      <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400 dark:text-gray-500" />
                      <input
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="john@example.com"
                        className="w-full pl-10 pr-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:ring-2 focus:ring-blue-100 dark:focus:ring-blue-900/50 focus:border-blue-500 outline-none transition"
                        required
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1.5">
                      Password
                    </label>
                    <div className="relative">
                      <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400 dark:text-gray-500" />
                      <input
                        type={showPassword ? 'text' : 'password'}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="••••••••"
                        className="w-full pl-10 pr-12 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:ring-2 focus:ring-blue-100 dark:focus:ring-blue-900/50 focus:border-blue-500 outline-none transition"
                        required
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword(!showPassword)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
                      >
                        {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                      </button>
                    </div>
                  </div>

                  <button
                    type="submit"
                    disabled={isLoading}
                    className="w-full px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                  >
                    {isLoading ? (
                      <><Loader2 className="h-5 w-5 animate-spin" /> Signing in...</>
                    ) : 'Sign In'}
                  </button>
                </form>
              </>
            )}

            {/* =================== SIGN UP: Step 1 – Email =================== */}
            {mode === 'signup' && signupStep === 'email' && (
              <>
                <button
                  onClick={handleGoogleLogin}
                  disabled={isLoading}
                  className="w-full flex items-center justify-center gap-3 px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition disabled:opacity-50 disabled:cursor-not-allowed font-medium text-gray-700 dark:text-gray-200"
                >
                  <GoogleIcon />
                  Continue with Google
                </button>

                <div className="flex items-center gap-4 my-6">
                  <div className="flex-1 h-px bg-gray-200 dark:bg-gray-700" />
                  <span className="text-sm text-gray-500 dark:text-gray-400">or</span>
                  <div className="flex-1 h-px bg-gray-200 dark:bg-gray-700" />
                </div>

                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1.5">
                      Email Address
                    </label>
                    <div className="relative">
                      <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400 dark:text-gray-500" />
                      <input
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="john@example.com"
                        className="w-full pl-10 pr-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:ring-2 focus:ring-blue-100 dark:focus:ring-blue-900/50 focus:border-blue-500 outline-none transition"
                        onKeyDown={(e) => e.key === 'Enter' && handleSendVerification()}
                      />
                    </div>
                  </div>

                  <button
                    onClick={handleSendVerification}
                    disabled={isLoading}
                    className="w-full px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                  >
                    {isLoading ? (
                      <><Loader2 className="h-5 w-5 animate-spin" /> Sending code...</>
                    ) : 'Send Verification Code'}
                  </button>
                </div>
              </>
            )}

            {/* =================== SIGN UP: Step 2 – Verify Code =================== */}
            {mode === 'signup' && signupStep === 'verify' && (
              <div className="space-y-6">
                <div className="flex justify-center gap-2">
                  {verificationCode.map((digit, i) => (
                    <input
                      key={i}
                      ref={(el) => { codeInputRefs.current[i] = el }}
                      type="text"
                      inputMode="numeric"
                      maxLength={6}
                      value={digit}
                      onChange={(e) => handleCodeChange(i, e.target.value)}
                      onKeyDown={(e) => handleCodeKeyDown(i, e)}
                      className="w-12 h-14 text-center text-2xl font-bold border-2 border-gray-300 dark:border-gray-600 rounded-xl bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 dark:focus:ring-blue-900/50 outline-none transition"
                    />
                  ))}
                </div>

                <button
                  onClick={handleVerifyCode}
                  disabled={isLoading || verificationCode.join('').length !== 6}
                  className="w-full px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {isLoading ? (
                    <><Loader2 className="h-5 w-5 animate-spin" /> Verifying...</>
                  ) : 'Verify Code'}
                </button>

                <div className="text-center">
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    Didn&apos;t receive the code?{' '}
                    <button
                      onClick={handleResendCode}
                      disabled={resendCooldown > 0 || isLoading}
                      className="text-blue-600 hover:underline font-medium disabled:text-gray-400 dark:disabled:text-gray-500 disabled:no-underline"
                    >
                      {resendCooldown > 0 ? `Resend in ${resendCooldown}s` : 'Resend code'}
                    </button>
                  </p>
                  <button
                    onClick={() => { setSignupStep('email'); setError(''); setSuccessMessage('') }}
                    className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 mt-2"
                  >
                    Change email address
                  </button>
                </div>
              </div>
            )}

            {/* =================== SIGN UP: Step 3 – Profile Details =================== */}
            {mode === 'signup' && signupStep === 'details' && (
              <form onSubmit={handleSignup} className="space-y-4">
                <div className="p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg flex items-center gap-2 text-green-700 dark:text-green-400 text-sm">
                  <CheckCircle2 className="h-4 w-4 flex-shrink-0" />
                  Email verified: {email}
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1.5">
                    Full Name
                  </label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400 dark:text-gray-500" />
                    <input
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="John Doe"
                      className="w-full pl-10 pr-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:ring-2 focus:ring-blue-100 dark:focus:ring-blue-900/50 focus:border-blue-500 outline-none transition"
                      required
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1.5">
                    Password
                  </label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400 dark:text-gray-500" />
                    <input
                      type={showPassword ? 'text' : 'password'}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="••••••••"
                      className="w-full pl-10 pr-12 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:ring-2 focus:ring-blue-100 dark:focus:ring-blue-900/50 focus:border-blue-500 outline-none transition"
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
                    >
                      {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                    </button>
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Must be at least 8 characters</p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1.5">
                    Confirm Password
                  </label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400 dark:text-gray-500" />
                    <input
                      type={showConfirmPassword ? 'text' : 'password'}
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="••••••••"
                      className="w-full pl-10 pr-12 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:ring-2 focus:ring-blue-100 dark:focus:ring-blue-900/50 focus:border-blue-500 outline-none transition"
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
                    >
                      {showConfirmPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1.5">
                    Phone <span className="text-gray-400 dark:text-gray-500">(optional, for WhatsApp reminders)</span>
                  </label>
                  <div className="relative">
                    <Phone className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400 dark:text-gray-500" />
                    <input
                      type="tel"
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      placeholder="+91 98765 43210"
                      className="w-full pl-10 pr-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:ring-2 focus:ring-blue-100 dark:focus:ring-blue-900/50 focus:border-blue-500 outline-none transition"
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={isLoading}
                  className="w-full px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {isLoading ? (
                    <><Loader2 className="h-5 w-5 animate-spin" /> Creating account...</>
                  ) : 'Create Account'}
                </button>
              </form>
            )}

            {/* Switch mode hint */}
            <p className="text-sm text-gray-600 dark:text-gray-300 text-center mt-6">
              {mode === 'signin' ? (
                <>
                  Don&apos;t have an account?{' '}
                  <button onClick={switchToSignup} className="text-blue-600 hover:underline font-medium">
                    Sign up
                  </button>
                </>
              ) : (
                <>
                  Already have an account?{' '}
                  <button onClick={switchToSignin} className="text-blue-600 hover:underline font-medium">
                    Sign in
                  </button>
                </>
              )}
            </p>
          </div>

          {/* Terms */}
          <p className="text-xs text-gray-500 dark:text-gray-400 text-center mt-4">
            By continuing, you agree to our{' '}
            <a href="#" className="text-blue-600 hover:underline">Terms</a>
            {' '}and{' '}
            <a href="#" className="text-blue-600 hover:underline">Privacy Policy</a>
          </p>
        </div>
      </div>
    </div>
  )
}

function GoogleIcon() {
  return (
    <svg className="h-5 w-5" viewBox="0 0 24 24">
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
      />
    </svg>
  )
}

function LoginFallback() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-blue-50 to-white dark:from-gray-900 dark:to-gray-900 flex items-center justify-center">
      <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
    </div>
  )
}

export default function LoginPage() {
  return (
    <Suspense fallback={<LoginFallback />}>
      <LoginContent />
    </Suspense>
  )
}
