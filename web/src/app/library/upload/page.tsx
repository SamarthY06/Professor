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
  Clock,
  Calendar,
  GraduationCap,
  BookOpen,
  ChevronRight,
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
  
  // NEW: Configuration state (Goals.md Step 1)
  const [showConfig, setShowConfig] = useState(false)
  const [learningLevel, setLearningLevel] = useState<'beginner' | 'intermediate' | 'advanced'>('intermediate')
  const [totalDays, setTotalDays] = useState('30')
  const [dailyMinutes, setDailyMinutes] = useState('30')
  const [quizFrequency, setQuizFrequency] = useState<'after_each_chapter' | 'after_n_chapters' | 'final_only'>('after_each_chapter')
  
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
      if (!token) return
      
      try {
        const status = await api.books.getStatus(token, bookId)
        setProcessingStatus(status.processing_status)
        setProcessingProgress(status.processing_progress)
        setProcessingStep(status.processing_step || '')
        
        if (status.processing_status === 'completed' || 
            status.processing_status === 'ready_for_planning' ||
            status.processing_status === 'failed') {
          if (pollingRef.current) {
            clearInterval(pollingRef.current)
            pollingRef.current = null
          }
          
          if (status.processing_status === 'failed') {
            setError(status.processing_error || 'Processing failed')
            setIsUploading(false)
          } else {
            // Success! Redirect to plan view page
            setTimeout(() => {
              router.push(`/learn/${bookId}/plan`)
            }, 1500)
          }
        }
      } catch (err) {
        console.error('Polling error:', err)
      }
    }, 2000)
  }

  const handleUpload = async () => {
    if (!file || !token) return

    setIsUploading(true)
    setError(null)
    setProcessingProgress(0)
    setProcessingStep('Uploading file...')

    try {
      // Upload with configuration
      const result = await api.books.uploadWithConfig(
        token,
        file,
        bookTitle || file.name.replace('.pdf', ''),
        bookAuthor || undefined,
        {
          learning_level: learningLevel,
          total_days: parseInt(totalDays),
          daily_minutes: parseInt(dailyMinutes),
          quiz_frequency: quizFrequency,
        }
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
    if (!goalTitle.trim() || !token) return

    setIsUploading(true)
    setError(null)

    try {
      await api.goals.create(token, {
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
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b">
        <div className="max-w-3xl mx-auto px-6 py-4">
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 text-gray-600 hover:text-gray-900"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Dashboard
          </Link>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-12">
        <div className="text-center mb-8">
          <Brain className="h-12 w-12 text-blue-600 mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-gray-900 mb-2">
            Start Learning Something New
          </h1>
          <p className="text-gray-600">
            Upload a book and configure your learning preferences
          </p>
        </div>

        {/* Error Message */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center gap-3 text-red-700">
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
                ? 'bg-blue-600 text-white'
                : 'bg-white border text-gray-600 hover:border-blue-200'
            }`}
          >
            <FileText className="h-5 w-5" />
            Upload Book
          </button>
          <button
            onClick={() => setActiveTab('goal')}
            className={`flex items-center gap-2 px-6 py-3 rounded-xl font-medium transition ${
              activeTab === 'goal'
                ? 'bg-blue-600 text-white'
                : 'bg-white border text-gray-600 hover:border-blue-200'
            }`}
          >
            <Target className="h-5 w-5" />
            Learning Goal
          </button>
        </div>

        {/* Content */}
        <div className="bg-white rounded-2xl border p-8">
          {activeTab === 'book' ? (
            <>
              {!showConfig ? (
                <>
                  {/* File Upload */}
                  <div
                    onDragOver={(e) => {
                      e.preventDefault()
                      setIsDragging(true)
                    }}
                    onDragLeave={() => setIsDragging(false)}
                    onDrop={handleDrop}
                    className={`border-2 border-dashed rounded-xl p-12 text-center transition ${
                      isDragging
                        ? 'border-blue-500 bg-blue-50'
                        : file
                        ? 'border-green-500 bg-green-50'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    {file ? (
                      <div className="flex flex-col items-center">
                        <div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center mb-4">
                          <Check className="h-6 w-6 text-green-600" />
                        </div>
                        <p className="font-medium text-gray-900 mb-1">{file.name}</p>
                        <p className="text-sm text-gray-500 mb-4">
                          {(file.size / 1024 / 1024).toFixed(2)} MB
                        </p>
                        <button
                          onClick={() => {
                            setFile(null)
                            setBookTitle('')
                          }}
                          className="text-sm text-red-600 hover:text-red-700"
                        >
                          Remove file
                        </button>
                      </div>
                    ) : (
                      <>
                        <Upload className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                        <p className="text-gray-900 font-medium mb-2">
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
                        <p className="text-sm text-gray-500">
                          PDF files only, up to 50MB
                        </p>
                      </>
                    )}
                  </div>

                  {/* Book Details */}
                  {file && (
                    <div className="mt-8 space-y-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Book Title
                        </label>
                        <input
                          type="text"
                          value={bookTitle}
                          onChange={(e) => setBookTitle(e.target.value)}
                          className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-100 focus:border-blue-300 outline-none"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Author (optional)
                        </label>
                        <input
                          type="text"
                          value={bookAuthor}
                          onChange={(e) => setBookAuthor(e.target.value)}
                          placeholder="Enter author name"
                          className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-100 focus:border-blue-300 outline-none"
                        />
                      </div>
                      
                      {/* Next: Configure Button */}
                      <button
                        onClick={() => setShowConfig(true)}
                        className="w-full mt-4 px-6 py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition flex items-center justify-center gap-2"
                      >
                        Next: Configure Learning
                        <ChevronRight className="h-5 w-5" />
                      </button>
                    </div>
                  )}
                </>
              ) : (
                <>
                  {/* CONFIGURATION SECTION (Goals.md Step 1) */}
                  <div className="space-y-6">
                    <div className="flex items-center gap-3 mb-6">
                      <button
                        onClick={() => setShowConfig(false)}
                        className="text-gray-500 hover:text-gray-700"
                      >
                        <ArrowLeft className="h-5 w-5" />
                      </button>
                      <div>
                        <h2 className="text-lg font-semibold text-gray-900">Configure Your Learning</h2>
                        <p className="text-sm text-gray-500">Set your preferences for "{bookTitle}"</p>
                      </div>
                    </div>

                    {/* Learning Level */}
                    <div>
                      <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-3">
                        <GraduationCap className="h-4 w-4" />
                        Your Learning Level
                      </label>
                      <div className="grid grid-cols-3 gap-3">
                        {[
                          { value: 'beginner', label: 'Beginner', desc: 'New to this topic' },
                          { value: 'intermediate', label: 'Intermediate', desc: 'Some prior knowledge' },
                          { value: 'advanced', label: 'Advanced', desc: 'Deep understanding' },
                        ].map((level) => (
                          <button
                            key={level.value}
                            type="button"
                            onClick={() => setLearningLevel(level.value as any)}
                            className={`p-4 border rounded-xl text-left transition ${
                              learningLevel === level.value
                                ? 'bg-blue-50 border-blue-500 ring-2 ring-blue-200'
                                : 'hover:border-blue-300'
                            }`}
                          >
                            <span className="font-medium text-gray-900">{level.label}</span>
                            <p className="text-xs text-gray-500 mt-1">{level.desc}</p>
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Timeline */}
                    <div>
                      <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-3">
                        <Calendar className="h-4 w-4" />
                        How many days to complete?
                      </label>
                      <select
                        value={totalDays}
                        onChange={(e) => setTotalDays(e.target.value)}
                        className="w-full px-4 py-3 border rounded-xl focus:ring-2 focus:ring-blue-100 focus:border-blue-300 outline-none"
                      >
                        <option value="7">1 week (7 days)</option>
                        <option value="14">2 weeks (14 days)</option>
                        <option value="21">3 weeks (21 days)</option>
                        <option value="30">1 month (30 days)</option>
                        <option value="45">45 days</option>
                        <option value="60">2 months (60 days)</option>
                        <option value="90">3 months (90 days)</option>
                      </select>
                    </div>

                    {/* Daily Study Time */}
                    <div>
                      <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-3">
                        <Clock className="h-4 w-4" />
                        Daily study time
                      </label>
                      <select
                        value={dailyMinutes}
                        onChange={(e) => setDailyMinutes(e.target.value)}
                        className="w-full px-4 py-3 border rounded-xl focus:ring-2 focus:ring-blue-100 focus:border-blue-300 outline-none"
                      >
                        <option value="15">15 minutes</option>
                        <option value="30">30 minutes</option>
                        <option value="45">45 minutes</option>
                        <option value="60">1 hour</option>
                        <option value="90">1.5 hours</option>
                        <option value="120">2 hours</option>
                      </select>
                    </div>

                    {/* Quiz Frequency */}
                    <div>
                      <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-3">
                        <BookOpen className="h-4 w-4" />
                        Quiz Frequency
                      </label>
                      <div className="space-y-2">
                        {[
                          { value: 'after_each_chapter', label: 'After every chapter', desc: 'Recommended for deep learning' },
                          { value: 'after_n_chapters', label: 'After every 2 chapters', desc: 'Balanced approach' },
                          { value: 'final_only', label: 'Final quiz only', desc: 'Quick completion' },
                        ].map((freq) => (
                          <button
                            key={freq.value}
                            type="button"
                            onClick={() => setQuizFrequency(freq.value as any)}
                            className={`w-full p-4 border rounded-xl text-left transition ${
                              quizFrequency === freq.value
                                ? 'bg-blue-50 border-blue-500 ring-2 ring-blue-200'
                                : 'hover:border-blue-300'
                            }`}
                          >
                            <span className="font-medium text-gray-900">{freq.label}</span>
                            <p className="text-xs text-gray-500">{freq.desc}</p>
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Progress Bar */}
                  {isUploading && (
                    <div className="mt-8 space-y-3">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-gray-600">{processingStep || 'Processing...'}</span>
                        <span className="font-medium text-blue-600">{processingProgress}%</span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
                        <div 
                          className="bg-gradient-to-r from-blue-500 to-blue-600 h-full rounded-full transition-all duration-500 ease-out"
                          style={{ width: `${processingProgress}%` }}
                        />
                      </div>
                      {processingProgress === 100 && (
                        <div className="flex items-center gap-2 text-green-600 justify-center">
                          <CheckCircle2 className="h-5 w-5" />
                          <span className="font-medium">Processing complete! Generating plan...</span>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Upload Button */}
                  {!isUploading && (
                    <button
                      onClick={handleUpload}
                      disabled={!file || isUploading}
                      className="w-full mt-8 px-6 py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                    >
                      <Upload className="h-5 w-5" />
                      Generate Your Learning Plan
                    </button>
                  )}
                </>
              )}
            </>
          ) : (
            <>
              {/* Goal Form */}
              <div className="space-y-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    What do you want to learn?
                  </label>
                  <input
                    type="text"
                    value={goalTitle}
                    onChange={(e) => setGoalTitle(e.target.value)}
                    placeholder="e.g., Master Python programming, Learn Spanish basics"
                    className="w-full px-4 py-3 border rounded-lg focus:ring-2 focus:ring-blue-100 focus:border-blue-300 outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Description (optional)
                  </label>
                  <textarea
                    value={goalDescription}
                    onChange={(e) => setGoalDescription(e.target.value)}
                    placeholder="Tell us more about what you want to achieve..."
                    rows={3}
                    className="w-full px-4 py-3 border rounded-lg focus:ring-2 focus:ring-blue-100 focus:border-blue-300 outline-none resize-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Learning Duration
                  </label>
                  <select
                    value={goalDuration}
                    onChange={(e) => setGoalDuration(e.target.value)}
                    className="w-full px-4 py-3 border rounded-lg focus:ring-2 focus:ring-blue-100 focus:border-blue-300 outline-none"
                  >
                    <option value="7">1 week</option>
                    <option value="14">2 weeks</option>
                    <option value="30">1 month</option>
                    <option value="60">2 months</option>
                    <option value="90">3 months</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Difficulty Level
                  </label>
                  <div className="flex gap-4">
                    {[
                      { value: 'beginner', label: 'Beginner' },
                      { value: 'intermediate', label: 'Intermediate' },
                      { value: 'advanced', label: 'Advanced' },
                    ].map((level) => (
                      <button
                        key={level.value}
                        type="button"
                        onClick={() => setGoalDifficulty(level.value)}
                        className={`flex-1 px-4 py-3 border rounded-lg transition ${
                          goalDifficulty === level.value
                            ? 'bg-blue-50 border-blue-500 text-blue-700'
                            : 'hover:border-blue-300'
                        }`}
                      >
                        <span className="text-sm font-medium">{level.label}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Create Button */}
              <button
                onClick={handleCreateGoal}
                disabled={!goalTitle.trim() || isUploading}
                className="w-full mt-8 px-6 py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
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
        <p className="text-center text-sm text-gray-500 mt-6">
          Professor will create a personalized day-by-day learning plan based on your preferences
        </p>
      </main>
    </div>
  )
}
