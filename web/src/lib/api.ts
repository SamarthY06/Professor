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
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new ApiError(response.status, error.detail || 'Request failed')
  }

  return response.json()
}

// Auth endpoints
export const auth = {
  signup: (data: { email: string; password: string; name: string; phone?: string }) =>
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
}

// Learning endpoints
export const learning = {
  getState: (token: string, bookId: string) =>
    fetchApi<{
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

  // Detailed progress with chapter-by-chapter tracking
  getDetailedProgress: (token: string, bookId: string) =>
    fetchApi<{
      completed_chapters: number[]
      total_chapters: number
      completion_percentage: number
      current_chapter: number
      total_study_time_minutes: number
      avg_time_per_chapter: number
      quiz_pass_rate: number
      avg_attention_score: number
      avg_comprehension_score: number
      motivation_score: number
      chapter_summaries: Array<{
        chapter_number: number
        title: string
        is_completed: boolean
        is_current: boolean
        summary: string | null
        estimated_duration_minutes: number
      }>
      current_phase: string
      plan_data: Record<string, unknown> | null
      estimated_completion_date: string | null
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
}
