/**
 * API client for the Professor backend
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface ApiOptions extends RequestInit {
  token?: string
}

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

async function fetchApi<T>(
  endpoint: string,
  options: ApiOptions = {}
): Promise<T> {
  const { token, ...fetchOptions } = options

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }

  // Merge existing headers if any
  if (options.headers) {
    const existingHeaders = options.headers as Record<string, string>
    Object.assign(headers, existingHeaders)
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(`${API_URL}${endpoint}`, {
    ...fetchOptions,
    headers,
    credentials: 'include',
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    let message = 'Request failed'
    if (typeof error.detail === 'string') {
      message = error.detail
    } else if (Array.isArray(error.detail)) {
      message = error.detail.map((d: any) => d.msg || String(d)).join('; ')
    } else if (error.detail) {
      message = String(error.detail)
    }
    throw new ApiError(response.status, message)
  }

  return response.json()
}

// Auth endpoints
export const auth = {
  sendVerification: (email: string) =>
    fetchApi<{ status: string; message: string }>('/api/auth/send-verification', {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),

  verifyEmail: (email: string, code: string) =>
    fetchApi<{ status: string; message: string }>('/api/auth/verify-email', {
      method: 'POST',
      body: JSON.stringify({ email, code }),
    }),

  signup: (data: { email: string; password: string; name: string; phone?: string; verification_code?: string }) =>
    fetchApi<{ access_token: string; refresh_token: string; token_type: string; expires_in: number }>('/api/auth/signup', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  signin: (email: string, password: string) =>
    fetchApi<{ access_token: string; refresh_token: string; token_type: string; expires_in: number }>('/api/auth/signin', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  googleLogin: (code: string, redirectUri: string) =>
    fetchApi<{ access_token: string; refresh_token: string; token_type: string; expires_in: number }>('/api/auth/google', {
      method: 'POST',
      body: JSON.stringify({ code, redirect_uri: redirectUri }),
    }),

  devLogin: (email: string, name?: string) =>
    fetchApi<{ access_token: string; refresh_token: string; token_type: string; expires_in: number }>('/api/auth/dev-login', {
      method: 'POST',
      body: JSON.stringify({ email, name: name || 'Test User' }),
    }),

  refreshToken: (refreshToken: string) =>
    fetchApi<{ access_token: string; refresh_token: string; token_type: string; expires_in: number }>('/api/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken }),
    }),

  getCurrentUser: (token: string) =>
    fetchApi<{
      id: string
      email: string
      name: string
      role: string
      has_api_key: boolean
    }>('/api/auth/me', { token }),

  logout: () =>
    fetchApi<{ status: string }>('/api/auth/logout', { method: 'POST' }),
}

// User endpoints
export const users = {
  getProfile: (token: string) =>
    fetchApi<{
      id: string
      email: string
      name: string
      phone: string | null
      role: string
      is_active: boolean
      created_at: string
    }>('/api/users/profile', { token }),

  updateProfile: (token: string, data: { name?: string; phone?: string }) =>
    fetchApi('/api/users/profile', {
      method: 'PATCH',
      token,
      body: JSON.stringify(data),
    }),

  getSettings: (token: string) =>
    fetchApi<{
      professor_style: string
      notification_preferences: Record<string, boolean>
      study_schedule: Record<string, unknown> | null
      timezone: string
    }>('/api/users/settings', { token }),

  updateSettings: (token: string, settings: Record<string, unknown>) =>
    fetchApi('/api/users/settings', {
      method: 'PATCH',
      token,
      body: JSON.stringify(settings),
    }),

  // API Key Management
  getApiKeyStatus: (token: string) =>
    fetchApi<{
      has_key: boolean
      is_valid: boolean
      last_validated: string | null
      masked_key: string | null
      using_default: boolean
    }>('/api/users/api-key/status', { token }),

  saveApiKey: (token: string, apiKey: string, validateKey: boolean = true) =>
    fetchApi<{ success: boolean; message: string }>('/api/users/api-key', {
      method: 'POST',
      token,
      body: JSON.stringify({ api_key: apiKey, validate_key: validateKey }),
    }),

  deleteApiKey: (token: string) =>
    fetchApi<{ success: boolean; message: string }>('/api/users/api-key', {
      method: 'DELETE',
      token,
    }),

  validateApiKey: (token: string) =>
    fetchApi<{ success: boolean; message: string }>('/api/users/api-key/validate', {
      method: 'POST',
      token,
    }),
}

// Books endpoints
export const books = {
  list: (token: string) =>
    fetchApi<
      Array<{
        id: string
        title: string
        author: string | null
        processing_status: string
        processing_progress: number
        processing_step: string | null
        total_chapters: number | null
        created_at: string
      }>
    >('/api/books', { token }),

  get: (token: string, bookId: string) =>
    fetchApi<{
      id: string
      title: string
      author: string | null
      total_pages: number | null
      total_chapters: number | null
      processing_status: string
      processing_progress: number
      processing_step: string | null
      chapters: Array<{
        id: string
        chapter_number: number
        title: string | null
      }>
    }>(`/api/books/${bookId}`, { token }),

  getStatus: (token: string, bookId: string) =>
    fetchApi<{
      id: string
      processing_status: string
      processing_progress: number
      processing_step: string | null
      processing_error: string | null
      total_pages: number | null
      total_chapters: number | null
    }>(`/api/books/${bookId}/status`, { token }),

  upload: async (token: string, file: File, title?: string, author?: string) => {
    const formData = new FormData()
    formData.append('file', file)
    if (title) formData.append('title', title)
    if (author) formData.append('author', author)

    const response = await fetch(`${API_URL}/api/books/upload`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
      },
      body: formData,
      credentials: 'include',
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Upload failed' }))
      throw new ApiError(response.status, error.detail)
    }

    return response.json()
  },

  uploadWithConfig: async (
    token: string,
    file: File,
    title: string,
    author: string | undefined,
    config: {
      learning_level: string
      total_days: number
      daily_minutes: number
      quiz_frequency: string
    }
  ) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('title', title)
    if (author) formData.append('author', author)
    formData.append('learning_level', config.learning_level)
    formData.append('total_days', config.total_days.toString())
    formData.append('daily_minutes', config.daily_minutes.toString())
    formData.append('quiz_frequency', config.quiz_frequency)

    const response = await fetch(`${API_URL}/api/books/upload-with-config`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
      },
      body: formData,
      credentials: 'include',
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Upload failed' }))
      throw new ApiError(response.status, error.detail)
    }

    return response.json()
  },


  delete: (token: string, bookId: string) =>
    fetchApi(`/api/books/${bookId}`, { method: 'DELETE', token }),

  getChapters: (bookId: string, token: string) =>
    fetchApi<
      Array<{
        id: string
        chapter_number: number
        title: string
        estimated_duration_minutes: number
      }>
    >(`/api/books/${bookId}/chapters`, { token }),

  saveConfig: (bookId: string, config: {
    target_completion_date: string
    daily_study_minutes: number
    learning_level: string
    quiz_frequency: string
    selected_chapters: number[]
  }, token: string) =>
    fetchApi(`/api/books/${bookId}/config`, {
      method: 'POST',
      token,
      body: JSON.stringify(config),
    }),
}

// Goals endpoints
export const goals = {
  list: (token: string) =>
    fetchApi<
      Array<{
        id: string
        title: string
        description: string | null
        duration_days: number
        status: string
        created_at: string
      }>
    >('/api/goals', { token }),

  create: (
    token: string,
    data: {
      title: string
      description?: string
      duration_days: number
      difficulty_level?: string
    }
  ) =>
    fetchApi('/api/goals', {
      method: 'POST',
      token,
      body: JSON.stringify(data),
    }),
}

// Chat endpoints
export const chat = {
  send: (
    token: string,
    data: {
      message: string
      session_id?: string
      book_id?: string
      goal_id?: string
    }
  ) =>
    fetchApi<{
      message: string
      session_id: string
      mode: string
      chapter: number
      quiz_question?: Record<string, unknown>
      latency_ms: number
      agent_name?: string
    }>('/api/chat', {
      method: 'POST',
      token,
      body: JSON.stringify(data),
    }),

  getSessions: (token: string, bookId?: string) =>
    fetchApi<
      Array<{
        id: string
        book_id: string | null
        chapter_context: number | null
        message_count: number
        created_at: string
      }>
    >(`/api/chat/sessions${bookId ? `?book_id=${bookId}` : ''}`, { token }),

  getSession: (token: string, sessionId: string) =>
    fetchApi<{
      id: string
      messages: Array<{
        id: string
        role: string
        content: string
        agent_name?: string
        is_quiz_question: boolean
        quiz_answer_correct?: boolean
        created_at: string
      }>
    }>(`/api/chat/sessions/${sessionId}`, { token }),

  // Initialize or get existing session for a book
  // This returns the professor's greeting and current state
  initSession: (token: string, bookId: string) =>
    fetchApi<{
      session_id: string
      phase: string
      current_chapter: number
      messages: Array<{
        id: string
        role: string
        content: string
        agent_name?: string
        is_quiz_question: boolean
        quiz_answer_correct?: boolean
        created_at: string
      }>
      has_greeting: boolean
      book_title: string
      total_chapters: number
    }>(`/api/chat/init/${bookId}`, { token }),

  // Regenerate professor greeting
  regenerateGreeting: (token: string, bookId: string) =>
    fetchApi<{
      message: string
      session_id: string
    }>(`/api/chat/regenerate-greeting/${bookId}`, {
      method: 'POST',
      token,
    }),

  /**
   * Send a message via Temporal-backed SSE endpoint.
   * Returns a promise that resolves with the complete response.
   * Emits progress events via the optional onProgress callback.
   */
  sendV2Stream: (
    token: string,
    data: { message: string; book_id: string },
    onProgress?: (status: string) => void,
  ): Promise<{
    message: string
    phase: string
    current_chapter: number
    current_day: number
    latency_ms: number
    session_id: string
  }> => {
    return new Promise((resolve, reject) => {
      const controller = new AbortController()
      const timeout = setTimeout(() => {
        controller.abort()
        reject(new ApiError(408, 'Request timed out'))
      }, 180_000)

      fetch(`${API_URL}/api/chat/v2/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(data),
        signal: controller.signal,
        credentials: 'include',
      })
        .then(async (res) => {
          if (!res.ok) {
            clearTimeout(timeout)
            const err = await res.json().catch(() => ({ detail: 'Request failed' }))
            reject(new ApiError(res.status, err.detail || 'Request failed'))
            return
          }
          const reader = res.body?.getReader()
          if (!reader) {
            clearTimeout(timeout)
            reject(new ApiError(500, 'No response body'))
            return
          }
          const decoder = new TextDecoder()
          let buffer = ''
          while (true) {
            const { value, done } = await reader.read()
            if (done) break
            buffer += decoder.decode(value, { stream: true })
            const lines = buffer.split('\n')
            buffer = lines.pop() || ''
            for (const line of lines) {
              if (!line.startsWith('data: ')) continue
              try {
                const payload = JSON.parse(line.slice(6))
                if (payload.status === 'complete') {
                  clearTimeout(timeout)
                  resolve(payload)
                  return
                }
                if (payload.status === 'error') {
                  clearTimeout(timeout)
                  reject(new ApiError(500, payload.error || 'Server error'))
                  return
                }
                onProgress?.(payload.status)
              } catch {
                // ignore non-JSON lines
              }
            }
          }
          clearTimeout(timeout)
          reject(new ApiError(500, 'Stream ended without a complete response'))
        })
        .catch((err) => {
          clearTimeout(timeout)
          if (err.name === 'AbortError') return
          reject(err instanceof ApiError ? err : new ApiError(500, err.message))
        })
    })
  },
}

// Learning endpoints
export const learning = {
  getState: (token: string, bookId: string) =>
    fetchApi<{
      current_day: number
      completed_days: number[]
      current_chapter: number
      completed_chapters: number[]
      motivation_score: number
      attention_score: number
      comprehension_score: number
      total_study_time_minutes: number
    }>(`/api/learning/state/${bookId}`, { token }),

  getProgress: (token: string, bookId: string) =>
    fetchApi<{
      chapter_progress: number
      total_chapters: number
      completion_percentage: number
      total_study_time_minutes: number
      quiz_pass_rate: number
    }>(`/api/learning/progress/${bookId}`, { token }),

  // Detailed progress with chapter->day hierarchy for sidebar
  getDetailedProgress: (token: string, bookId: string) =>
    fetchApi<{
      current_day: number
      current_chapter: number
      completed_days: number[]
      completed_chapters: number[]
      total_days: number
      total_chapters: number
      day_completion_percentage: number
      chapter_completion_percentage: number
      sidebar_chapters: Array<{
        chapter_number: number
        title: string
        is_completed: boolean
        is_current: boolean
        days: Array<{
          day: number
          title: string
          is_completed: boolean
          is_current: boolean
          is_rest: boolean
        }>
      }>
      total_study_time_minutes: number
      quiz_pass_rate: number
      motivation_score: number
      current_phase: string
      plan_data: Record<string, unknown> | null
      scope_completion_percentage?: number
      scope_remaining_topics?: string[]
      scope_total_topics?: number
      scope_covered_topics?: number
    }>(`/api/learning/progress/${bookId}/detailed`, { token }),

  // Reset learning state
  reset: (token: string, bookId: string) =>
    fetchApi(`/api/learning/state/${bookId}/reset`, {
      method: 'POST',
      token,
    }),
}

// Quiz endpoints
export const quiz = {
  start: (token: string, quizId: string) =>
    fetchApi<{
      id: string
      question_text: string
      question_type: string
      options: Record<string, string> | null
    }>(`/api/quiz/start/${quizId}`, { method: 'POST', token }),

  submitAnswer: (token: string, questionId: string, answer: string) =>
    fetchApi<{
      is_correct: boolean
      correct_answer: string
      explanation: string | null
      next_question: Record<string, unknown> | null
      quiz_complete: boolean
      score: number | null
      passed: boolean | null
    }>('/api/quiz/answer', {
      method: 'POST',
      token,
      body: JSON.stringify({ question_id: questionId, answer }),
    }),
}

export const planning = {
  generate: (token: string, data: { book_id: string; additional_instructions?: string }) =>
    fetchApi<{
      id: string
      book_id: string
      summary: string
      plan_data: Record<string, unknown>
      status: string
      version: number
      created_at: string
    }>('/api/planning/generate', {
      method: 'POST',
      token,
      body: JSON.stringify(data),
    }),

  current: (token: string, bookId: string) =>
    fetchApi<{
      id: string
      book_id: string
      summary: string
      plan_data: Record<string, unknown>
      status: string
      version: number
      created_at: string
    } | null>(`/api/planning/${bookId}/current`, { token }),

  review: (token: string, data: { plan_id: string; feedback: string; action: 'accept' | 'request_changes' }) =>
    fetchApi<{
      success: boolean
      message: string
      can_start_learning: boolean
      session_id?: string
    }>('/api/planning/review', {
      method: 'POST',
      token,
      body: JSON.stringify(data),
    }),
}

// Admin endpoints
export const admin = {
  getDashboard: (token: string) =>
    fetchApi<{
      total_users: number
      active_users_24h: number
      active_users_7d: number
      total_books: number
      total_quizzes_completed: number
      avg_quiz_pass_rate: number
      avg_study_time_minutes: number
    }>('/api/admin/dashboard', { token }),

  listUsers: (token: string, page: number = 1, search?: string) =>
    fetchApi<
      Array<{
        id: string
        email: string
        name: string
        role: string
        is_active: boolean
        created_at: string
      }>
    >(`/api/admin/users?page=${page}${search ? `&search=${search}` : ''}`, { token }),

  getUserDetail: (token: string, userId: string) =>
    fetchApi<{
      id: string
      email: string
      name: string
      role: string
      is_active: boolean
      phone: string | null
      created_at: string
      updated_at: string
      books_count: number
      goals_count: number
      total_study_time_minutes: number
    }>(`/api/admin/users/${userId}`, { token }),

  toggleUserStatus: (token: string, userId: string) =>
    fetchApi<{ is_active: boolean }>(`/api/admin/users/${userId}/status`, {
      method: 'PATCH',
      token,
    }),

  getSystemHealth: (token: string) =>
    fetchApi<{
      postgres: string
      redis: string
      temporal: string
      disk_usage_percent: number
      memory_usage_percent: number
    }>('/api/admin/system/health', { token }),

  getDetailedServerMetrics: (token: string) =>
    fetchApi<{
      timestamp: string
      system_info: {
        hostname: string
        platform: string
        platform_release: string
        platform_version: string
        architecture: string
        processor: string
        python_version: string
        boot_time: string
        uptime_seconds: number
        uptime_formatted: string
      }
      cpu: {
        usage_percent: number
        core_count: number
        logical_count: number
        frequency_mhz: number | null
        per_core_usage: number[]
        load_average_1m: number | null
        load_average_5m: number | null
        load_average_15m: number | null
      }
      memory: {
        total_gb: number
        available_gb: number
        used_gb: number
        usage_percent: number
        swap_total_gb: number
        swap_used_gb: number
        swap_percent: number
      }
      disk: {
        total_gb: number
        used_gb: number
        free_gb: number
        usage_percent: number
        read_bytes_per_sec: number
        write_bytes_per_sec: number
        partitions: Array<{
          device: string
          mountpoint: string
          fstype: string
          total_gb: number
          used_gb: number
          percent: number
        }>
      }
      network: {
        bytes_sent_per_sec: number
        bytes_recv_per_sec: number
        packets_sent_per_sec: number
        packets_recv_per_sec: number
        connections_count: number
        interfaces: Array<{
          name: string
          is_up: boolean
          addresses: Array<{ type: string; address: string }>
        }>
      }
      processes: {
        total_processes: number
        running_processes: number
        sleeping_processes: number
        top_cpu_processes: Array<{
          pid: number
          name: string
          cpu_percent: number
          memory_percent: number
        }>
        top_memory_processes: Array<{
          pid: number
          name: string
          cpu_percent: number
          memory_percent: number
        }>
      }
      health_status: string
      health_issues: string[]
    }>('/api/admin/system/metrics', { token }),

  getMetricsHistory: (token: string, hours: number = 24) =>
    fetchApi<{
      period_hours: number
      metrics: Record<string, Array<{ timestamp: string; value: number }>>
    }>(`/api/admin/system/metrics/history?hours=${hours}`, { token }),

  triggerPricingSync: (token: string) =>
    fetchApi<{
      success: boolean
      changes: {
        added: string[]
        updated: string[]
        unchanged: string[]
        errors: Array<{ model: string; error: string }>
      }
    }>('/api/admin/system/pricing/sync', { method: 'POST', token }),

  listFeatureFlags: (token: string) =>
    fetchApi<
      Array<{
        id: string
        flag_name: string
        is_enabled: boolean
        rollout_percentage: number
        conditions: Record<string, unknown> | null
      }>
    >('/api/admin/feature-flags', { token }),

  updateFeatureFlag: (
    token: string,
    flagName: string,
    data: { is_enabled?: boolean; rollout_percentage?: number }
  ) =>
    fetchApi(`/api/admin/feature-flags/${flagName}`, {
      method: 'PATCH',
      token,
      body: JSON.stringify(data),
    }),

  // New comprehensive analytics endpoints
  getPlatformStats: (token: string) =>
    fetchApi<{
      users: {
        total: number
        new_today: number
        new_this_week: number
        active_24h: number
        active_7d: number
        tier_breakdown: Record<string, number>
      }
      usage_today: {
        requests: number
        input_tokens: number
        output_tokens: number
        total_tokens: number
      }
      costs: {
        platform_today_cents: number
        platform_today_usd: number
        platform_month_cents: number
        platform_month_usd: number
      }
      model_breakdown: Array<{
        model: string
        requests: number
        cost_cents: number
        tokens: number
      }>
    }>('/api/admin/analytics/platform-stats', { token }),

  getUsageTimeline: (token: string, days: number = 30) =>
    fetchApi<
      Array<{
        date: string
        requests: number
        tokens: number
        platform_cost_cents: number
        active_users: number
      }>
    >(`/api/admin/analytics/usage-timeline?days=${days}`, { token }),

  getTopUsers: (token: string, limit: number = 20) =>
    fetchApi<
      Array<{
        user_id: string
        email: string
        name: string
        tier: string
        requests: number
        tokens: number
        cost_cents: number
      }>
    >(`/api/admin/analytics/top-users?limit=${limit}`, { token }),

  getUserUsageDetail: (token: string, userId: string) =>
    fetchApi<{
      user: {
        id: string
        email: string
        name: string
        created_at: string
      }
      subscription: {
        tier: string
        preferred_model: string | null
        pdfs_used: number
        messages_used: number
        quizzes_used: number
      } | null
      all_time: {
        requests: number
        tokens: number
        cost_cents: number
      }
      recent_logs: Array<{
        id: string
        type: string
        model: string
        tokens: number
        cost_cents: number
        paid_by: string
        created_at: string
      }>
    }>(`/api/admin/analytics/user/${userId}`, { token }),

  getCostsBreakdown: (token: string, days: number = 30) =>
    fetchApi<{
      period_days: number
      by_model: Array<{
        model: string
        platform_cost_cents: number
        user_cost_cents: number
        requests: number
      }>
      by_usage_type: Array<{
        type: string
        platform_cost_cents: number
        user_cost_cents: number
        requests: number
      }>
      totals: {
        platform_cost_cents: number
        platform_cost_usd: number
        user_cost_cents: number
        user_cost_usd: number
      }
    }>(`/api/admin/analytics/costs-breakdown?days=${days}`, { token }),

  listSubscriptions: (token: string, page: number = 1, tier?: string) =>
    fetchApi<
      Array<{
        id: string
        user_id: string
        email: string
        name: string
        tier: string
        preferred_model: string | null
        usage: { pdfs: number; messages: number; quizzes: number }
        limits: { pdfs: number; messages: number; quizzes: number }
        billing_cycle_start: string
      }>
    >(`/api/admin/subscriptions?page=${page}${tier ? `&tier=${tier}` : ''}`, { token }),

  listUsersWithUsage: (token: string, page: number = 1, search?: string, tier?: string, sortBy?: string) =>
    fetchApi<
      Array<{
        id: string
        email: string
        name: string
        role: string
        is_active: boolean
        created_at: string
        tier: string
        preferred_model: string | null
        books_count: number
        usage: {
          all_time: {
            requests: number
            tokens: number
            platform_cost_cents: number
            user_cost_cents: number
          }
          this_month: {
            requests: number
            tokens: number
            platform_cost_cents: number
            user_cost_cents: number
          }
          subscription: {
            pdfs_used: number
            messages_used: number
            quizzes_used: number
            pdf_limit: number
            message_limit: number
            quiz_limit: number
          } | null
        }
        last_active: string | null
      }>
    >(`/api/admin/users-with-usage?page=${page}${search ? `&search=${encodeURIComponent(search)}` : ''}${tier ? `&tier=${tier}` : ''}${sortBy ? `&sort_by=${sortBy}` : ''}`, { token }),

  updateUserTier: (token: string, userId: string, tier: string) =>
    fetchApi<{ success: boolean; user_id: string; new_tier: string }>(
      `/api/admin/subscriptions/${userId}/tier?tier=${tier}`,
      { method: 'PATCH', token }
    ),

  listFeedback: (token: string, page: number = 1, status?: string, type?: string) =>
    fetchApi<
      Array<{
        id: string
        user_id: string
        user_email: string
        user_name: string
        feedback_type: string
        rating: number | null
        title: string | null
        content: string
        status: string
        created_at: string
      }>
    >(`/api/admin/feedback?page=${page}${status ? `&status_filter=${status}` : ''}${type ? `&feedback_type=${type}` : ''}`, { token }),

  updateFeedback: (token: string, feedbackId: string, data: { status: string; admin_notes?: string }) =>
    fetchApi(`/api/admin/feedback/${feedbackId}`, {
      method: 'PATCH',
      token,
      body: JSON.stringify(data),
    }),

  listModelPricing: (token: string) =>
    fetchApi<
      Array<{
        id: string
        model_name: string
        display_name: string
        input_price_per_million: number
        output_price_per_million: number
        cached_input_price_per_million: number | null
        is_available: boolean
        supports_batch: boolean
        available_for_free: boolean
        available_for_byok: boolean
        description: string | null
      }>
    >('/api/admin/models/pricing', { token }),

  updateModelPricing: (token: string, modelName: string, data: Record<string, unknown>) =>
    fetchApi(`/api/admin/models/pricing/${modelName}`, {
      method: 'PATCH',
      token,
      body: JSON.stringify(data),
    }),

  getBooksAnalytics: (token: string, days: number = 30) =>
    fetchApi<{
      total_books: number
      new_books_period: number
      status_breakdown: Record<string, number>
      daily_uploads: Array<{ date: string; count: number }>
      learning_stats: {
        total_active_learners: number
        avg_study_time_minutes: number
      }
    }>(`/api/admin/analytics/books?days=${days}`, { token }),

  getQuizAnalytics: (token: string, days: number = 30) =>
    fetchApi<{
      total_completed: number
      completed_in_period: number
      average_score: number
      pass_rate: number
      daily_completions: Array<{
        date: string
        count: number
        avg_score: number
      }>
    }>(`/api/admin/analytics/quizzes?days=${days}`, { token }),

  listBooks: (token: string, page: number = 1, userId?: string, status?: string) =>
    fetchApi<
      Array<{
        id: string
        title: string
        author: string | null
        processing_status: string
        processing_progress: number
        processing_step: string | null
        total_chapters: number | null
        created_at: string
        user_id: string
        user_email: string
        user_name: string
      }>
    >(`/api/admin/books?page=${page}${userId ? `&user_id=${userId}` : ''}${status ? `&status=${status}` : ''}`, { token }),

  getBookDetail: (token: string, bookId: string) =>
    fetchApi<{
      id: string
      title: string
      author: string | null
      processing_status: string
      processing_progress: number
      processing_step: string | null
      processing_error: string | null
      total_pages: number | null
      total_chapters: number | null
      created_at: string
      user: {
        id: string
        email: string
        name: string
      }
      learning: {
        current_day: number | null
        current_chapter: number | null
        total_study_time_minutes: number
        last_active_at: string | null
      } | null
      quizzes: {
        total_completed: number
        average_score: number
      }
    }>(`/api/admin/books/${bookId}`, { token }),
}

// Usage endpoints (user-facing)
export const usage = {
  getSummary: (token: string) =>
    fetchApi<{
      tier: string
      billing_cycle_start: string
      usage: {
        pdfs: { used: number; limit: number; unlimited: boolean }
        messages: { used: number; limit: number; unlimited: boolean }
        quizzes: { used: number; limit: number; unlimited: boolean }
      }
      tokens: { input: number; output: number; total: number }
      cost_cents: number
      total_requests: number
      model_breakdown: Record<string, { count: number; cost_cents: number }>
      preferred_model: string | null
      use_batch_api: boolean
    }>('/api/usage/summary', { token }),

  checkLimit: (token: string, feature: 'pdf' | 'message' | 'quiz') =>
    fetchApi<{
      can_use: boolean
      error_message: string | null
      usage_info: {
        tier: string
        unlimited: boolean
        used: number
        limit?: number
        remaining?: number
        percentage_used?: number
      }
    }>(`/api/usage/check/${feature}`, { token }),

  getTier: (token: string) =>
    fetchApi<{
      tier: string
      limits: { pdfs: number; messages: number; quizzes: number }
      usage: { pdfs: number; messages: number; quizzes: number }
      preferred_model: string | null
      use_batch_api: boolean
      billing_cycle_start: string
      is_unlimited: boolean
    }>('/api/usage/tier', { token }),

  getAvailableModels: (token: string) =>
    fetchApi<
      Array<{
        model_name: string
        display_name: string
        description: string | null
        input_price_per_million: number
        output_price_per_million: number
        cached_input_price_per_million: number | null
        supports_batch: boolean
        max_context_tokens: number
        is_selected: boolean
      }>
    >('/api/usage/models', { token }),

  setPreferredModel: (token: string, modelName: string) =>
    fetchApi<{ success: boolean; preferred_model: string; message: string }>('/api/usage/models/select', {
      method: 'POST',
      token,
      body: JSON.stringify({ model_name: modelName }),
    }),

  setBatchMode: (token: string, useBatchApi: boolean) =>
    fetchApi<{ success: boolean; use_batch_api: boolean; message: string }>('/api/usage/batch-mode', {
      method: 'POST',
      token,
      body: JSON.stringify({ use_batch_api: useBatchApi }),
    }),

  submitFeedback: (
    token: string,
    data: {
      feedback_type: string
      rating?: number
      title?: string
      content: string
      book_id?: string
      session_id?: string
      page_url?: string
    }
  ) =>
    fetchApi<{ id: string; feedback_type: string; status: string; created_at: string }>('/api/usage/feedback', {
      method: 'POST',
      token,
      body: JSON.stringify(data),
    }),

  getMyFeedback: (token: string) =>
    fetchApi<
      Array<{
        id: string
        feedback_type: string
        rating: number | null
        title: string | null
        content: string
        status: string
        created_at: string
      }>
    >('/api/usage/feedback/mine', { token }),

  getPricing: () =>
    fetchApi<{
      tiers: Record<
        string,
        {
          name: string
          price: string
          limits: Record<string, number | string>
          features: string[]
        }
      >
      models: Array<{
        model_name: string
        display_name: string
        description: string | null
        pricing: {
          input_per_million: string
          output_per_million: string
          cached_input_per_million: string | null
        }
        available_for_free: boolean
        supports_batch: boolean
      }>
    }>('/api/usage/pricing', {}),

  // BYOK Dashboard endpoints
  getBYOKDashboard: (token: string) =>
    fetchApi<{
      is_byok: boolean
      current_month: {
        requests: number
        input_tokens: number
        output_tokens: number
        cached_tokens: number
        total_tokens: number
        cost_cents: number
        cost_usd: number
        today_requests: number
        today_cost_cents: number
        billing_cycle_start: string
      }
      daily_breakdown: Array<{
        date: string
        requests: number
        input_tokens: number
        output_tokens: number
        cost_cents: number
      }>
      model_usage: Array<{
        model_name: string
        display_name: string
        requests: number
        input_tokens: number
        output_tokens: number
        cost_cents: number
        percentage: number
      }>
      recent_activity: Array<{
        id: string
        type: string
        model: string
        input_tokens: number
        output_tokens: number
        cost_cents: number
        book_title: string | null
        created_at: string
      }>
      cost_projections: {
        daily_average_cents: number
        projected_monthly_cents: number
        last_month_cents: number
        month_over_month_change: number
      }
    }>('/api/usage/byok/dashboard', { token }),

  getBYOKRealtime: (token: string) =>
    fetchApi<{
      is_byok: boolean
      today: {
        cost_cents: number
        cost_usd: number
        requests: number
      }
      month: {
        cost_cents: number
        cost_usd: number
        requests: number
      }
      last_activity: {
        type: string
        model: string
        cost_cents: number
        created_at: string
      } | null
      preferred_model: string | null
      timestamp: string
    }>('/api/usage/byok/realtime', { token }),
}

// Notes endpoints
export const notes = {
  list: (token: string, bookId?: string) =>
    fetchApi<
      Array<{
        id: string
        title: string
        content: string
        book_id: string | null
        chapter_id: string | null
        tags: string[]
        is_pinned: boolean
        created_at: string
        updated_at: string
      }>
    >(`/api/notes${bookId ? `?book_id=${bookId}` : ''}`, { token }),

  create: (
    token: string,
    data: {
      title: string
      content: string
      book_id?: string
      chapter_id?: string
      tags?: string[]
    }
  ) =>
    fetchApi('/api/notes', {
      method: 'POST',
      token,
      body: JSON.stringify(data),
    }),

  update: (token: string, noteId: string, data: { title?: string; content?: string; tags?: string[] }) =>
    fetchApi(`/api/notes/${noteId}`, {
      method: 'PATCH',
      token,
      body: JSON.stringify(data),
    }),

  delete: (token: string, noteId: string) =>
    fetchApi(`/api/notes/${noteId}`, { method: 'DELETE', token }),

  togglePin: (token: string, noteId: string) =>
    fetchApi(`/api/notes/${noteId}/pin`, { method: 'POST', token }),
}

const voice = {
  transcribe: async (token: string, audioBlob: Blob): Promise<{ text: string }> => {
    const formData = new FormData()
    const ext = audioBlob.type.includes('mp4') ? 'mp4' : audioBlob.type.includes('ogg') ? 'ogg' : 'webm'
    formData.append('file', audioBlob, `recording.${ext}`)

    const response = await fetch(`${API_URL}/api/voice/transcribe`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      credentials: 'include',
      body: formData,
    })

    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data.detail || 'Transcription failed')
    }

    return response.json()
  },
}

export default {
  auth,
  users,
  books,
  goals,
  chat,
  learning,
  quiz,
  planning,
  admin,
  notes,
  usage,
  voice,
}
