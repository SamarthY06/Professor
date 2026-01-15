'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import {
  Brain,
  BookOpen,
  Target,
  Plus,
  Settings,
  LogOut,
  ChevronRight,
  Clock,
  Trophy,
  TrendingUp,
  Loader2,
  StickyNote,
  AlertCircle,
  Trash2,
  MoreVertical,
  RefreshCw,
} from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'
import api from '@/lib/api'

interface Book {
  id: string
  title: string
  author: string | null
  processing_status: string
  processing_progress: number
  processing_step: string | null
  total_chapters: number | null
  created_at: string
}

interface Goal {
  id: string
  title: string
  description: string | null
  duration_days: number
  status: string
  created_at: string
}

export default function DashboardPage() {
  const router = useRouter()
  const { user, token, isLoading: authLoading, isAuthenticated, logout } = useAuth()
  const [activeTab, setActiveTab] = useState<'books' | 'goals'>('books')
  const [books, setBooks] = useState<Book[]>([])
  const [goals, setGoals] = useState<Goal[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Redirect if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login')
    }
  }, [authLoading, isAuthenticated, router])

  // Fetch data when authenticated
  useEffect(() => {
    const fetchData = async () => {
      if (!token) return
      
      setIsLoading(true)
      setError(null)
      
      try {
        const [booksData, goalsData] = await Promise.all([
          api.books.list(token),
          api.goals.list(token),
        ])
        setBooks(booksData)
        setGoals(goalsData)
      } catch (err: any) {
        console.error('Failed to fetch data:', err)
        setError(err.message || 'Failed to load data')
      } finally {
        setIsLoading(false)
      }
    }

    if (token) {
      fetchData()
    }
  }, [token])

  // Auto-refresh for processing books
  useEffect(() => {
    const hasProcessingBooks = books.some(
      b => b.processing_status === 'processing' || b.processing_status === 'pending'
    )
    
    if (!hasProcessingBooks || !token) return
    
    const interval = setInterval(async () => {
      try {
        const booksData = await api.books.list(token)
        setBooks(booksData)
      } catch (err) {
        console.error('Failed to refresh books:', err)
      }
    }, 3000) // Refresh every 3 seconds
    
    return () => clearInterval(interval)
  }, [books, token])

  const handleLogout = () => {
    logout()
    router.push('/login')
  }

  const handleDeleteBook = async (bookId: string) => {
    if (!token) return
    try {
      await api.books.delete(token, bookId)
      setBooks(prev => prev.filter(b => b.id !== bookId))
    } catch (err: any) {
      console.error('Failed to delete book:', err)
      setError(err.message || 'Failed to delete book')
    }
  }

  const handleReprocessBook = async (bookId: string) => {
    if (!token) return
    try {
      // Call reprocess endpoint - triggers background processing
      await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/books/${bookId}/reprocess`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      // Refresh books list
      const booksData = await api.books.list(token)
      setBooks(booksData)
    } catch (err: any) {
      console.error('Failed to reprocess book:', err)
      setError(err.message || 'Failed to reprocess book')
    }
  }

  if (authLoading || !isAuthenticated) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Brain className="h-8 w-8 text-blue-600" />
            <span className="text-xl font-bold">Professor</span>
          </div>
          <div className="flex items-center gap-4">
            <Link
              href="/notes"
              className="p-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition"
              title="Notes"
            >
              <StickyNote className="h-5 w-5" />
            </Link>
            <Link
              href="/settings"
              className="p-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition"
              title="Settings"
            >
              <Settings className="h-5 w-5" />
            </Link>
            <button 
              onClick={handleLogout}
              className="p-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition"
              title="Logout"
            >
              <LogOut className="h-5 w-5" />
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Welcome Section */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            Welcome back, {user?.name || 'Learner'}! 👋
          </h1>
          <p className="text-gray-600">
            Continue your learning journey or start something new.
          </p>
        </div>

        {/* Error Message */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center gap-3 text-red-700">
            <AlertCircle className="h-5 w-5 flex-shrink-0" />
            <p>{error}</p>
          </div>
        )}

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <StatCard
            icon={<Clock className="h-5 w-5" />}
            label="Books"
            value={books.length.toString()}
            subtitle="Uploaded"
            color="blue"
          />
          <StatCard
            icon={<Trophy className="h-5 w-5" />}
            label="Goals"
            value={goals.length.toString()}
            subtitle="Created"
            color="green"
          />
          <StatCard
            icon={<TrendingUp className="h-5 w-5" />}
            label="Processing"
            value={books.filter(b => b.processing_status === 'processing').length.toString()}
            subtitle="In progress"
            color="purple"
          />
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-4 mb-6">
          <button
            onClick={() => setActiveTab('books')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition ${
              activeTab === 'books'
                ? 'bg-blue-100 text-blue-700'
                : 'text-gray-600 hover:bg-gray-100'
            }`}
          >
            <BookOpen className="h-4 w-4" />
            My Books ({books.length})
          </button>
          <button
            onClick={() => setActiveTab('goals')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition ${
              activeTab === 'goals'
                ? 'bg-blue-100 text-blue-700'
                : 'text-gray-600 hover:bg-gray-100'
            }`}
          >
            <Target className="h-4 w-4" />
            Learning Goals ({goals.length})
          </button>
          <div className="flex-1" />
          <Link
            href="/library/upload"
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition font-medium"
          >
            <Plus className="h-4 w-4" />
            Add New
          </Link>
        </div>

        {/* Content */}
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
          </div>
        ) : activeTab === 'books' ? (
          <div className="grid gap-4">
            {books.map((book) => (
              <BookCard 
                key={book.id} 
                book={book} 
                onDelete={handleDeleteBook}
                onReprocess={handleReprocessBook}
              />
            ))}
            {books.length === 0 && (
              <EmptyState
                title="No books yet"
                description="Upload a PDF to start learning with Professor"
              />
            )}
          </div>
        ) : (
          <div className="grid gap-4">
            {goals.map((goal) => (
              <GoalCard key={goal.id} goal={goal} />
            ))}
            {goals.length === 0 && (
              <EmptyState
                title="No goals yet"
                description="Create a learning goal to get started"
              />
            )}
          </div>
        )}
      </main>
    </div>
  )
}

function StatCard({
  icon,
  label,
  value,
  subtitle,
  color,
}: {
  icon: React.ReactNode
  label: string
  value: string
  subtitle: string
  color: 'blue' | 'green' | 'purple'
}) {
  const colors = {
    blue: 'bg-blue-50 text-blue-600',
    green: 'bg-green-50 text-green-600',
    purple: 'bg-purple-50 text-purple-600',
  }

  return (
    <div className="bg-white rounded-xl p-6 border">
      <div className="flex items-center gap-3 mb-3">
        <div className={`p-2 rounded-lg ${colors[color]}`}>{icon}</div>
        <span className="text-gray-600">{label}</span>
      </div>
      <div className="text-3xl font-bold text-gray-900 mb-1">{value}</div>
      <div className="text-sm text-gray-500">{subtitle}</div>
    </div>
  )
}

function BookCard({ book, onDelete, onReprocess }: { book: Book; onDelete: (id: string) => void; onReprocess: (id: string) => void }) {
  const [showMenu, setShowMenu] = useState(false)
  const [deleting, setDeleting] = useState(false)
  
  const isReady = book.processing_status === 'completed' || book.processing_status === 'ready_for_planning'
  const isProcessing = book.processing_status === 'processing' || book.processing_status === 'pending'
  const isFailed = book.processing_status === 'failed'

  // When book is ready, go directly to learn page where professor's greeting will be shown
  // The greeting is already generated by GreetingAgent during processing
  const href = isReady ? `/learn/${book.id}` : '#'

  const handleDelete = async (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    
    if (!confirm(`Delete "${book.title}"? This cannot be undone.`)) return
    
    setDeleting(true)
    setShowMenu(false)
    onDelete(book.id)
  }

  const handleReprocess = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setShowMenu(false)
    onReprocess(book.id)
  }

  return (
    <div className="relative">
      <Link
        href={href}
        className={`block bg-white rounded-xl p-6 border hover:border-blue-200 hover:shadow-md transition group ${
          !isReady ? 'cursor-not-allowed' : ''
        } ${deleting ? 'opacity-50' : ''}`}
        onClick={(e) => !isReady && e.preventDefault()}
      >
        <div className="flex items-start justify-between">
          <div className="flex-1 pr-8">
            <div className="flex items-center gap-3 mb-1">
              <h3 className={`text-lg font-semibold transition ${isReady ? 'text-gray-900 group-hover:text-blue-600' : 'text-gray-600'}`}>
                {book.title}
              </h3>
              {isProcessing && (
                <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs font-medium rounded-full flex items-center gap-1">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  {book.processing_progress || 0}%
                </span>
              )}
              {isFailed && (
                <span className="px-2 py-0.5 bg-red-100 text-red-700 text-xs font-medium rounded-full">
                  Failed
                </span>
              )}
              {isReady && (
                <span className="px-2 py-0.5 bg-green-100 text-green-700 text-xs font-medium rounded-full">
                  Ready
                </span>
              )}
            </div>
            {book.author && <p className="text-gray-600 text-sm mb-2">{book.author}</p>}
            
            {/* Progress bar for processing books */}
            {isProcessing && (
              <div className="mt-3 mb-2">
                <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
                  <span>{book.processing_step || 'Processing...'}</span>
                  <span>{book.processing_progress || 0}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
                  <div 
                    className="bg-blue-500 h-full rounded-full transition-all duration-500"
                    style={{ width: `${book.processing_progress || 0}%` }}
                  />
                </div>
              </div>
            )}
            
            <div className="flex items-center gap-4 text-sm text-gray-500">
              {book.total_chapters && <span>{book.total_chapters} chapters</span>}
              <span>Added {new Date(book.created_at).toLocaleDateString()}</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isReady && (
              <ChevronRight className="h-5 w-5 text-gray-400 group-hover:text-blue-600 transition" />
            )}
          </div>
        </div>
      </Link>
      
      {/* Actions Menu Button */}
      <div className="absolute top-4 right-4">
        <button
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
            setShowMenu(!showMenu)
          }}
          className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition"
        >
          <MoreVertical className="h-4 w-4" />
        </button>
        
        {/* Dropdown Menu */}
        {showMenu && (
          <>
            <div 
              className="fixed inset-0 z-10" 
              onClick={() => setShowMenu(false)}
            />
            <div className="absolute right-0 top-10 bg-white border rounded-lg shadow-lg z-20 py-1 min-w-[140px]">
              {isFailed && (
                <button
                  onClick={handleReprocess}
                  className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                >
                  <RefreshCw className="h-4 w-4" />
                  Reprocess
                </button>
              )}
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="w-full px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50 flex items-center gap-2 disabled:opacity-50"
              >
                <Trash2 className="h-4 w-4" />
                {deleting ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function GoalCard({ goal }: { goal: Goal }) {
  return (
    <Link
      href={`/learn/goal-${goal.id}`}
      className="bg-white rounded-xl p-6 border hover:border-blue-200 hover:shadow-md transition group"
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <Target className="h-5 w-5 text-blue-600" />
            <span className="text-sm font-medium text-blue-600">Goal</span>
            <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${
              goal.status === 'active' ? 'bg-green-100 text-green-700' :
              goal.status === 'completed' ? 'bg-blue-100 text-blue-700' :
              'bg-gray-100 text-gray-700'
            }`}>
              {goal.status}
            </span>
          </div>
          <h3 className="text-lg font-semibold text-gray-900 group-hover:text-blue-600 transition">
            {goal.title}
          </h3>
          {goal.description && (
            <p className="text-gray-600 text-sm mt-1">{goal.description}</p>
          )}
          <div className="flex items-center gap-4 text-sm text-gray-500 mt-2">
            <span>{goal.duration_days} day plan</span>
            <span>Created {new Date(goal.created_at).toLocaleDateString()}</span>
          </div>
        </div>
        <ChevronRight className="h-5 w-5 text-gray-400 group-hover:text-blue-600 transition" />
      </div>
    </Link>
  )
}

function EmptyState({
  title,
  description,
}: {
  title: string
  description: string
}) {
  return (
    <div className="bg-white rounded-xl p-12 border text-center">
      <div className="max-w-sm mx-auto">
        <BookOpen className="h-12 w-12 text-gray-300 mx-auto mb-4" />
        <h3 className="text-lg font-semibold text-gray-900 mb-2">{title}</h3>
        <p className="text-gray-600">{description}</p>
        <p className="text-sm text-gray-500 mt-4">
          Click <span className="font-medium text-blue-600">"Add New"</span> above to get started
        </p>
      </div>
    </div>
  )
}
