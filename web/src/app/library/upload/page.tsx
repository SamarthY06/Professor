'use client'

import { useState, useCallback, useEffect, useRef } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import {
  Brain,
  ArrowLeft,
  Upload,
  FileText,
  Target,
  Check,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Sparkles,
  MessageSquare,
} from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'
import api from '@/lib/api'

export default function UploadPage() {
  const router = useRouter()
  const { token, isLoading: authLoading, isAuthenticated } = useAuth()
  const [activeTab, setActiveTab] = useState<'book' | 'goal'>('book')
  const [file, setFile] = useState<File | null>(null)
  const [bookTitle, setBookTitle] = useState('')
  const [bookAuthor, setBookAuthor] = useState('')
  const [isDragging, setIsDragging] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  // Processing state
  const [uploadedBookId, setUploadedBookId] = useState<string | null>(null)
  const [processingStatus, setProcessingStatus] = useState<string>('')
  const [processingProgress, setProcessingProgress] = useState<number>(0)
  const [processingStep, setProcessingStep] = useState<string>('')
  const pollingRef = useRef<NodeJS.Timeout | null>(null)
  
  // Goal form state
  const [goalTitle, setGoalTitle] = useState('')
  const [goalDescription, setGoalDescription] = useState('')
  const [goalDuration, setGoalDuration] = useState('30')
  const [goalDifficulty, setGoalDifficulty] = useState('intermediate')

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current)
      }
    }
  }, [])

  // Redirect if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login')
    }
  }, [authLoading, isAuthenticated, router])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    setError(null)

    const droppedFile = e.dataTransfer.files[0]
    if (droppedFile?.type === 'application/pdf') {
      setFile(droppedFile)
      setBookTitle(droppedFile.name.replace('.pdf', ''))
    } else {
      setError('Please upload a PDF file')
    }
  }, [])

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0]
    setError(null)
    if (selectedFile) {
      if (selectedFile.type === 'application/pdf') {
        setFile(selectedFile)
        setBookTitle(selectedFile.name.replace('.pdf', ''))
      } else {
        setError('Please upload a PDF file')
      }
    }
  }

  const startPolling = (bookId: string) => {
    pollingRef.current = setInterval(async () => {
      if (!isAuthenticated) return
      
      try {
        const status = await api.books.getStatus(token || '', bookId)
        setProcessingStatus(status.processing_status)
        setProcessingProgress(status.processing_progress)
        setProcessingStep(status.processing_step || '')
        
        if (status.processing_status === 'completed' || 
            status.processing_status === 'failed') {
          if (pollingRef.current) {
            clearInterval(pollingRef.current)
            pollingRef.current = null
          }
          
          if (status.processing_status === 'failed') {
            setError(status.processing_error || 'Processing failed')
            setIsUploading(false)
          } else {
            setTimeout(() => {
              router.push(`/learn/${bookId}`)
            }, 1500)
          }
        }
      } catch (err) {
        console.error('Polling error:', err)
      }
    }, 2000)
  }

  const handleUpload = async () => {
    if (!file || !isAuthenticated) return

    setIsUploading(true)
    setError(null)
    setProcessingProgress(0)
    setProcessingStep('Uploading file...')

    try {
      const result = await api.books.upload(
        token || '',
        file,
        bookTitle || file.name.replace('.pdf', ''),
        bookAuthor || undefined,
      )
      
      setUploadedBookId(result.id)
      setProcessingStatus('pending')
      setProcessingStep('Processing started...')
      
      startPolling(result.id)
      
    } catch (err: any) {
      console.error('Upload failed:', err)
      setError(err.message || 'Failed to upload book. Please try again.')
      setIsUploading(false)
      setProcessingProgress(0)
      setProcessingStep('')
    }
  }

  const handleCreateGoal = async () => {
    if (!goalTitle.trim() || !isAuthenticated) return

    setIsUploading(true)
    setError(null)

    try {
      await api.goals.create(token || '', {
        title: goalTitle,
        description: goalDescription || undefined,
        duration_days: parseInt(goalDuration),
        difficulty_level: goalDifficulty,
      })
      
      router.push('/dashboard')
    } catch (err: any) {
      console.error('Goal creation failed:', err)
      setError(err.message || 'Failed to create goal. Please try again.')
      setIsUploading(false)
    }
  }

  if (authLoading || !isAuthenticated) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50 dark:from-gray-900 dark:via-gray-900 dark:to-gray-900">
      {/* Header */}
      <header className="bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm border-b dark:border-gray-700 sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-6 py-4">
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 transition"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Dashboard
          </Link>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-12">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-2xl mb-4 shadow-lg shadow-blue-500/25">
            <Brain className="h-8 w-8 text-white" />
          </div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-2">
            Start Learning Something New
          </h1>
          <p className="text-gray-600 dark:text-gray-300">
            Upload a book and I'll create a personalized learning plan for you
          </p>
        </div>

        {/* Error Message */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl flex items-center gap-3 text-red-700 dark:text-red-400">
            <AlertCircle className="h-5 w-5 flex-shrink-0" />
            <p>{error}</p>
          </div>
        )}

        {/* Tabs */}
        <div className="flex items-center justify-center gap-4 mb-8">
          <button
            onClick={() => setActiveTab('book')}
            className={`flex items-center gap-2 px-6 py-3 rounded-xl font-medium transition ${
              activeTab === 'book'
                ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/25'
                : 'bg-white dark:bg-gray-800 border dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:border-blue-200 dark:hover:border-blue-700 hover:shadow-md'
            }`}
          >
            <FileText className="h-5 w-5" />
            Upload Book
          </button>
          <button
            onClick={() => setActiveTab('goal')}
            className={`flex items-center gap-2 px-6 py-3 rounded-xl font-medium transition ${
              activeTab === 'goal'
                ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/25'
                : 'bg-white dark:bg-gray-800 border dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:border-blue-200 dark:hover:border-blue-700 hover:shadow-md'
            }`}
          >
            <Target className="h-5 w-5" />
            Learning Goal
          </button>
        </div>

        {/* Content */}
        <div className="bg-white dark:bg-gray-800 rounded-2xl border dark:border-gray-700 shadow-xl dark:shadow-gray-900/50 shadow-gray-200/50 p-8">
          {activeTab === 'book' ? (
            <>
              {!isUploading ? (
                <>
                  {/* File Upload */}
                  <div
                    onDragOver={(e) => {
                      e.preventDefault()
                      setIsDragging(true)
                    }}
                    onDragLeave={() => setIsDragging(false)}
                    onDrop={handleDrop}
                    className={`border-2 border-dashed rounded-2xl p-12 text-center transition-all duration-300 ${
                      isDragging
                        ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20 scale-[1.02]'
                        : file
                        ? 'border-green-500 bg-green-50 dark:bg-green-900/20'
                        : 'border-gray-200 dark:border-gray-700 hover:border-blue-300 dark:hover:border-blue-600 hover:bg-gray-50 dark:hover:bg-gray-700'
                    }`}
                  >
                    {file ? (
                      <div className="flex flex-col items-center">
                        <div className="w-16 h-16 bg-green-100 dark:bg-green-900/30 rounded-2xl flex items-center justify-center mb-4">
                          <Check className="h-8 w-8 text-green-600 dark:text-green-400" />
                        </div>
                        <p className="font-semibold text-gray-900 dark:text-gray-100 mb-1 text-lg">{file.name}</p>
                        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
                          {(file.size / 1024 / 1024).toFixed(2)} MB
                        </p>
                        <button
                          onClick={() => {
                            setFile(null)
                            setBookTitle('')
                          }}
                          className="text-sm text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300 font-medium"
                        >
                          Remove file
                        </button>
                      </div>
                    ) : (
                      <>
                        <div className="w-16 h-16 bg-gray-100 dark:bg-gray-700 rounded-2xl flex items-center justify-center mx-auto mb-4">
                          <Upload className="h-8 w-8 text-gray-400 dark:text-gray-500" />
                        </div>
                        <p className="text-gray-900 dark:text-gray-100 font-medium mb-2 text-lg">
                          Drop your PDF here, or{' '}
                          <label className="text-blue-600 cursor-pointer hover:underline">
                            browse
                            <input
                              type="file"
                              accept=".pdf"
                              onChange={handleFileSelect}
                              className="hidden"
                            />
                          </label>
                        </p>
                        <p className="text-sm text-gray-500 dark:text-gray-400">
                          PDF files only, up to 50MB
                        </p>
                      </>
                    )}
                  </div>

                  {/* Book Details */}
                  {file && (
                    <div className="mt-8 space-y-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-2">
                          Book Title
                        </label>
                        <input
                          type="text"
                          value={bookTitle}
                          onChange={(e) => setBookTitle(e.target.value)}
                          className="w-full px-4 py-3 border dark:border-gray-700 rounded-xl focus:ring-2 focus:ring-blue-100 dark:focus:ring-blue-900/50 focus:border-blue-400 dark:focus:border-blue-500 outline-none transition text-gray-900 dark:text-gray-100 dark:bg-gray-800"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-2">
                          Author (optional)
                        </label>
                        <input
                          type="text"
                          value={bookAuthor}
                          onChange={(e) => setBookAuthor(e.target.value)}
                          placeholder="Enter author name"
                          className="w-full px-4 py-3 border dark:border-gray-700 rounded-xl focus:ring-2 focus:ring-blue-100 dark:focus:ring-blue-900/50 focus:border-blue-400 dark:focus:border-blue-500 outline-none transition dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
                        />
                      </div>
                      
                      {/* What happens next info */}
                      <div className="mt-6 p-4 bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 rounded-xl border border-blue-100 dark:border-blue-800">
                        <div className="flex items-start gap-3">
                          <div className="w-10 h-10 bg-blue-100 dark:bg-blue-900/30 rounded-lg flex items-center justify-center flex-shrink-0">
                            <MessageSquare className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                          </div>
                          <div>
                            <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">What happens next?</h3>
                            <p className="text-sm text-gray-600 dark:text-gray-300">
                              After uploading, Professor will chat with you to understand your learning goals, 
                              available time, and preferences. Then I'll create a personalized day-by-day plan just for you!
                            </p>
                          </div>
                        </div>
                      </div>
                      
                      {/* Upload Button */}
                      <button
                        onClick={handleUpload}
                        disabled={!file}
                        className="w-full mt-4 px-6 py-4 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-xl font-semibold hover:from-blue-700 hover:to-indigo-700 transition shadow-lg shadow-blue-500/25 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                      >
                        <Sparkles className="h-5 w-5" />
                        Upload & Start Learning
                      </button>
                    </div>
                  )}
                </>
              ) : (
                <>
                  {/* Processing State */}
                  <div className="text-center py-8">
                    <div className="w-20 h-20 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-2xl flex items-center justify-center mx-auto mb-6 shadow-lg shadow-blue-500/25">
                      {processingProgress === 100 ? (
                        <CheckCircle2 className="h-10 w-10 text-white" />
                      ) : (
                        <Loader2 className="h-10 w-10 text-white animate-spin" />
                      )}
                    </div>
                    
                    <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-2">
                      {processingProgress === 100 ? 'Processing Complete!' : 'Processing Your Book'}
                    </h2>
                    <p className="text-gray-600 dark:text-gray-300 mb-6">
                      {processingProgress === 100 
                        ? 'Redirecting you to start your learning journey...'
                        : processingStep || 'Analyzing content and structure...'}
                    </p>
                    
                    {/* Progress Bar */}
                    <div className="max-w-md mx-auto">
                      <div className="flex items-center justify-between text-sm mb-2">
                        <span className="text-gray-500 dark:text-gray-400">Progress</span>
                        <span className="font-semibold text-blue-600">{processingProgress}%</span>
                      </div>
                      <div className="w-full bg-gray-100 dark:bg-gray-700 rounded-full h-3 overflow-hidden">
                        <div 
                          className="bg-gradient-to-r from-blue-500 to-indigo-600 h-full rounded-full transition-all duration-500 ease-out"
                          style={{ width: `${processingProgress}%` }}
                        />
                      </div>
                    </div>
                    
                    {processingProgress === 100 && (
                      <div className="mt-6 flex items-center justify-center gap-2 text-green-600 dark:text-green-400">
                        <CheckCircle2 className="h-5 w-5" />
                        <span className="font-medium">Ready! Taking you to Professor...</span>
                      </div>
                    )}
                  </div>
                </>
              )}
            </>
          ) : (
            <>
              {/* Goal Form */}
              <div className="space-y-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-2">
                    What do you want to learn?
                  </label>
                  <input
                    type="text"
                    value={goalTitle}
                    onChange={(e) => setGoalTitle(e.target.value)}
                    placeholder="e.g., Master Python programming, Learn Spanish basics"
                    className="w-full px-4 py-3 border dark:border-gray-700 rounded-xl focus:ring-2 focus:ring-blue-100 dark:focus:ring-blue-900/50 focus:border-blue-400 dark:focus:border-blue-500 outline-none transition dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-2">
                    Description (optional)
                  </label>
                  <textarea
                    value={goalDescription}
                    onChange={(e) => setGoalDescription(e.target.value)}
                    placeholder="Tell us more about what you want to achieve..."
                    rows={3}
                    className="w-full px-4 py-3 border dark:border-gray-700 rounded-xl focus:ring-2 focus:ring-blue-100 dark:focus:ring-blue-900/50 focus:border-blue-400 dark:focus:border-blue-500 outline-none resize-none transition dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-2">
                    Learning Duration
                  </label>
                  <select
                    value={goalDuration}
                    onChange={(e) => setGoalDuration(e.target.value)}
                    className="w-full px-4 py-3 border dark:border-gray-700 rounded-xl focus:ring-2 focus:ring-blue-100 dark:focus:ring-blue-900/50 focus:border-blue-400 dark:focus:border-blue-500 outline-none transition dark:bg-gray-800 dark:text-gray-100"
                  >
                    <option value="7">1 week</option>
                    <option value="14">2 weeks</option>
                    <option value="30">1 month</option>
                    <option value="60">2 months</option>
                    <option value="90">3 months</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-2">
                    Difficulty Level
                  </label>
                  <div className="flex gap-3">
                    {[
                      { value: 'beginner', label: 'Beginner' },
                      { value: 'intermediate', label: 'Intermediate' },
                      { value: 'advanced', label: 'Advanced' },
                    ].map((level) => (
                      <button
                        key={level.value}
                        type="button"
                        onClick={() => setGoalDifficulty(level.value)}
                        className={`flex-1 px-4 py-3 border dark:border-gray-700 rounded-xl transition font-medium ${
                          goalDifficulty === level.value
                            ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-500 text-blue-700 dark:text-blue-400 ring-2 ring-blue-200 dark:ring-blue-800'
                            : 'hover:border-blue-300 dark:hover:border-blue-600 text-gray-700 dark:text-gray-200'
                        }`}
                      >
                        {level.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Create Button */}
              <button
                onClick={handleCreateGoal}
                disabled={!goalTitle.trim() || isUploading}
                className="w-full mt-8 px-6 py-4 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-xl font-semibold hover:from-blue-700 hover:to-indigo-700 transition shadow-lg shadow-blue-500/25 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {isUploading ? (
                  <>
                    <Loader2 className="h-5 w-5 animate-spin" />
                    Creating Goal...
                  </>
                ) : (
                  <>
                    <Target className="h-5 w-5" />
                    Create Learning Goal
                  </>
                )}
              </button>
            </>
          )}
        </div>

        {/* Info */}
        <p className="text-center text-sm text-gray-500 dark:text-gray-400 mt-6">
          Professor uses AI to create personalized learning experiences tailored to your pace and style
        </p>
      </main>
    </div>
  )
}
