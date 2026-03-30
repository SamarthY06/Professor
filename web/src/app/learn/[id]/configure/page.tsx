'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeft,
  Calendar,
  Clock,
  GraduationCap,
  ListChecks,
  BookOpen,
  Loader2,
  CheckCircle,
} from 'lucide-react';

import api from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';

interface BookDetails {
  id: string;
  title: string;
  author: string | null;
  total_pages: number | null;
  total_chapters: number | null;
  processing_status: string;
  processing_progress: number;
  processing_step: string | null;
  chapters: Array<{ id: string; chapter_number: number; title: string | null }>;
}

interface Chapter {
  id: string;
  chapter_number: number;
  title: string;
  estimated_duration_minutes: number;
}

export default function ConfigureLearningPage() {
  const params = useParams();
  const router = useRouter();
  const bookId = params.id as string;
  const { token, isLoading: authLoading, isAuthenticated } = useAuth();

  const [book, setBook] = useState<BookDetails | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Configuration state
  const [targetDate, setTargetDate] = useState('');
  const [dailyMinutes, setDailyMinutes] = useState(60);
  const [learningLevel, setLearningLevel] = useState<'beginner' | 'intermediate' | 'advanced'>('intermediate');
  const [quizFrequency, setQuizFrequency] = useState<'after_each_chapter' | 'after_n_chapters' | 'final_only'>('after_each_chapter');
  const [selectedChapters, setSelectedChapters] = useState<number[]>([]);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  useEffect(() => {
    if (authLoading || !isAuthenticated) return;

    const t = token || '';
    const fetchBook = async () => {
      try {
        const bookData = await api.books.get(t, bookId);
        setBook(bookData);

        const chaptersData = await api.books.getChapters(bookId, t);
        setChapters(chaptersData);
        
        setSelectedChapters(chaptersData.map((c: Chapter) => c.chapter_number));

        const defaultDate = new Date();
        defaultDate.setDate(defaultDate.getDate() + 14);
        setTargetDate(defaultDate.toISOString().split('T')[0]);

      } catch (err) {
        setError('Failed to load book details');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchBook();
  }, [bookId, token, authLoading, isAuthenticated, router]);

  const handleSaveConfig = async () => {
    if (!isAuthenticated) return;
    setSaving(true);
    setError(null);

    try {
      await api.books.saveConfig(bookId, {
        target_completion_date: targetDate,
        daily_study_minutes: dailyMinutes,
        learning_level: learningLevel,
        quiz_frequency: quizFrequency,
        selected_chapters: selectedChapters,
      }, token || '');

      router.push(`/learn/${bookId}`);
    } catch (err) {
      setError('Failed to save configuration');
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  const toggleChapter = (chapterNum: number) => {
    setSelectedChapters(prev =>
      prev.includes(chapterNum)
        ? prev.filter(c => c !== chapterNum)
        : [...prev, chapterNum].sort((a, b) => a - b)
    );
  };

  const estimatedDays = () => {
    const totalMinutes = chapters
      .filter(c => selectedChapters.includes(c.chapter_number))
      .reduce((sum, c) => sum + (c.estimated_duration_minutes || 45), 0);
    return Math.max(1, Math.ceil(totalMinutes / dailyMinutes));
  };

  if (authLoading || loading) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-blue-50 to-white dark:from-gray-900 dark:to-gray-900 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    );
  }

  if (!book) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-blue-50 to-white dark:from-gray-900 dark:to-gray-900 flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2">Book not found</h1>
          <Link href="/dashboard" className="text-blue-600 hover:underline">
            Back to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-blue-50 to-white dark:from-gray-900 dark:to-gray-900">
      {/* Header */}
      <header className="bg-white dark:bg-gray-800 border-b dark:border-gray-700 sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center gap-4">
          <Link href="/dashboard" className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition">
            <ArrowLeft className="h-5 w-5 text-gray-600 dark:text-gray-300" />
          </Link>
          <div>
            <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Configure Learning</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">{book.title}</p>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8">
        <div className="bg-white dark:bg-gray-800 rounded-xl border dark:border-gray-700 shadow-sm p-6 mb-6">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-12 h-12 bg-blue-100 dark:bg-blue-900/30 rounded-xl flex items-center justify-center">
              <BookOpen className="h-6 w-6 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">Let's Plan Your Journey</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Tell me how you'd like to learn "{book.title}" - I'll create a plan that works for you
              </p>
            </div>
          </div>

          {error && (
            <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-400 text-sm">
              {error}
            </div>
          )}

          {/* Target Date */}
          <div className="mb-6">
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-200 mb-2">
              <Calendar className="h-4 w-4" />
              Target Completion Date
            </label>
            <input
              type="date"
              value={targetDate}
              onChange={(e) => setTargetDate(e.target.value)}
              min={new Date().toISOString().split('T')[0]}
              className="w-full px-4 py-3 border dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-800 dark:text-gray-100"
            />
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Estimated {estimatedDays()} days based on your schedule
            </p>
          </div>

          {/* Daily Study Time */}
          <div className="mb-6">
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-200 mb-2">
              <Clock className="h-4 w-4" />
              Daily Study Time
            </label>
            <div className="flex gap-2">
              {[30, 45, 60, 90, 120].map((mins) => (
                <button
                  key={mins}
                  onClick={() => setDailyMinutes(mins)}
                  className={`flex-1 py-3 px-4 rounded-lg border transition ${
                    dailyMinutes === mins
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 border-gray-200 dark:border-gray-700 hover:border-blue-300 dark:hover:border-blue-600'
                  }`}
                >
                  {mins} min
                </button>
              ))}
            </div>
          </div>

          {/* Learning Level */}
          <div className="mb-6">
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-200 mb-2">
              <GraduationCap className="h-4 w-4" />
              How would you like me to teach?
            </label>
            <div className="grid grid-cols-3 gap-3">
              {(['beginner', 'intermediate', 'advanced'] as const).map((level) => (
                <button
                  key={level}
                  onClick={() => setLearningLevel(level)}
                  className={`py-3 px-4 rounded-lg border transition ${
                    learningLevel === level
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 border-gray-200 dark:border-gray-700 hover:border-blue-300 dark:hover:border-blue-600'
                  }`}
                >
                  <span className="capitalize">{level === 'beginner' ? 'Friendly' : level === 'intermediate' ? 'Balanced' : 'Deep Dive'}</span>
                  <p className="text-xs mt-1 opacity-80">
                    {level === 'beginner' && 'Easy-going, lots of examples'}
                    {level === 'intermediate' && 'Clear but thorough'}
                    {level === 'advanced' && 'Full technical depth'}
                  </p>
                </button>
              ))}
            </div>
          </div>

          {/* Quiz Frequency */}
          <div className="mb-6">
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-200 mb-2">
              <ListChecks className="h-4 w-4" />
              How often should I check your understanding?
            </label>
            <div className="space-y-2">
              {[
                { value: 'after_each_chapter', label: 'After each chapter', desc: 'Quick check after every chapter - keeps things fresh!' },
                { value: 'after_n_chapters', label: 'Every couple chapters', desc: 'A bit more breathing room between quizzes' },
                { value: 'final_only', label: 'Just at the end', desc: 'One comprehensive review when you finish' },
              ].map((option) => (
                <button
                  key={option.value}
                  onClick={() => setQuizFrequency(option.value as typeof quizFrequency)}
                  className={`w-full text-left py-3 px-4 rounded-lg border transition flex items-center gap-3 ${
                    quizFrequency === option.value
                      ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-300 dark:border-blue-800'
                      : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:border-blue-200 dark:hover:border-blue-700'
                  }`}
                >
                  <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                    quizFrequency === option.value ? 'border-blue-600' : 'border-gray-300 dark:border-gray-600'
                  }`}>
                    {quizFrequency === option.value && (
                      <div className="w-3 h-3 rounded-full bg-blue-600" />
                    )}
                  </div>
                  <div>
                    <p className="font-medium text-gray-900 dark:text-gray-100">{option.label}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">{option.desc}</p>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Chapter Selection */}
          <div className="mb-6">
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-200 mb-2">
              <BookOpen className="h-4 w-4" />
              Select Chapters to Study ({selectedChapters.length} of {chapters.length})
            </label>
            <div className="border dark:border-gray-700 rounded-lg divide-y dark:divide-gray-700 max-h-64 overflow-y-auto">
              {chapters.map((chapter) => (
                <button
                  key={chapter.id}
                  onClick={() => toggleChapter(chapter.chapter_number)}
                  className="w-full text-left py-3 px-4 flex items-center gap-3 hover:bg-gray-50 dark:hover:bg-gray-700 transition"
                >
                  <div className={`w-5 h-5 rounded border flex items-center justify-center ${
                    selectedChapters.includes(chapter.chapter_number)
                      ? 'bg-blue-600 border-blue-600'
                      : 'border-gray-300 dark:border-gray-600'
                  }`}>
                    {selectedChapters.includes(chapter.chapter_number) && (
                      <CheckCircle className="h-3 w-3 text-white" />
                    )}
                  </div>
                  <div className="flex-1">
                    <p className="font-medium text-gray-900 dark:text-gray-100">
                      Chapter {chapter.chapter_number}: {chapter.title}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      ~{chapter.estimated_duration_minutes || 45} min
                    </p>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Summary */}
          <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4 mb-6">
            <h3 className="font-medium text-blue-900 dark:text-blue-300 mb-2">Here's what we're planning</h3>
            <ul className="text-sm text-blue-800 dark:text-blue-300 space-y-1">
              <li>📚 {selectedChapters.length} chapters to explore together</li>
              <li>⏰ {dailyMinutes} minutes each day</li>
              <li>📅 About {estimatedDays()} days to complete</li>
              <li>🎓 {learningLevel === 'beginner' ? 'Friendly & approachable' : learningLevel === 'intermediate' ? 'Balanced & thorough' : 'Deep & technical'} teaching style</li>
            </ul>
          </div>

          {/* Actions */}
          <div className="flex gap-3">
            <Link
              href="/dashboard"
              className="flex-1 py-3 px-4 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-700 dark:text-gray-200 font-medium hover:bg-gray-50 dark:hover:bg-gray-700 transition text-center"
            >
              Cancel
            </Link>
            <button
              onClick={handleSaveConfig}
              disabled={saving || selectedChapters.length === 0}
              className="flex-1 py-3 px-4 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {saving ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  Start Learning
                </>
              )}
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
