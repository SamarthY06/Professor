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
    const fetchBook = async () => {
      try {
        const token = localStorage.getItem('token');
        if (!token) {
          router.push('/login');
          return;
        }

        const bookData = await api.books.get(token, bookId);
        setBook(bookData);

        const chaptersData = await api.books.getChapters(bookId, token);
        setChapters(chaptersData);
        
        // Select all chapters by default
        setSelectedChapters(chaptersData.map((c: Chapter) => c.chapter_number));

        // Set default target date (2 weeks from now)
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
  }, [bookId, router]);

  const handleSaveConfig = async () => {
    setSaving(true);
    setError(null);

    try {
      const token = localStorage.getItem('token');
      if (!token) {
        router.push('/login');
        return;
      }

      await api.books.saveConfig(bookId, {
        target_completion_date: targetDate,
        daily_study_minutes: dailyMinutes,
        learning_level: learningLevel,
        quiz_frequency: quizFrequency,
        selected_chapters: selectedChapters,
      }, token);

      // Navigate to learn page
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

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-blue-50 to-white flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    );
  }

  if (!book) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-blue-50 to-white flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Book not found</h1>
          <Link href="/dashboard" className="text-blue-600 hover:underline">
            Back to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-blue-50 to-white">
      {/* Header */}
      <header className="bg-white border-b sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center gap-4">
          <Link href="/dashboard" className="p-2 hover:bg-gray-100 rounded-lg transition">
            <ArrowLeft className="h-5 w-5 text-gray-600" />
          </Link>
          <div>
            <h1 className="text-lg font-semibold text-gray-900">Configure Learning</h1>
            <p className="text-sm text-gray-500">{book.title}</p>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8">
        <div className="bg-white rounded-xl border shadow-sm p-6 mb-6">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-12 h-12 bg-blue-100 rounded-xl flex items-center justify-center">
              <BookOpen className="h-6 w-6 text-blue-600" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-gray-900">Set Your Learning Goals</h2>
              <p className="text-sm text-gray-500">
                Configure how Professor will guide you through "{book.title}"
              </p>
            </div>
          </div>

          {error && (
            <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
              {error}
            </div>
          )}

          {/* Target Date */}
          <div className="mb-6">
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2">
              <Calendar className="h-4 w-4" />
              Target Completion Date
            </label>
            <input
              type="date"
              value={targetDate}
              onChange={(e) => setTargetDate(e.target.value)}
              min={new Date().toISOString().split('T')[0]}
              className="w-full px-4 py-3 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
            <p className="text-xs text-gray-500 mt-1">
              Estimated {estimatedDays()} days based on your schedule
            </p>
          </div>

          {/* Daily Study Time */}
          <div className="mb-6">
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2">
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
                      : 'bg-white text-gray-700 border-gray-200 hover:border-blue-300'
                  }`}
                >
                  {mins} min
                </button>
              ))}
            </div>
          </div>

          {/* Learning Level */}
          <div className="mb-6">
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2">
              <GraduationCap className="h-4 w-4" />
              Professor Level
            </label>
            <div className="grid grid-cols-3 gap-3">
              {(['beginner', 'intermediate', 'advanced'] as const).map((level) => (
                <button
                  key={level}
                  onClick={() => setLearningLevel(level)}
                  className={`py-3 px-4 rounded-lg border transition ${
                    learningLevel === level
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white text-gray-700 border-gray-200 hover:border-blue-300'
                  }`}
                >
                  <span className="capitalize">{level}</span>
                  <p className="text-xs mt-1 opacity-80">
                    {level === 'beginner' && 'Simple explanations'}
                    {level === 'intermediate' && 'Balanced depth'}
                    {level === 'advanced' && 'Deep technical'}
                  </p>
                </button>
              ))}
            </div>
          </div>

          {/* Quiz Frequency */}
          <div className="mb-6">
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2">
              <ListChecks className="h-4 w-4" />
              Quiz Frequency
            </label>
            <div className="space-y-2">
              {[
                { value: 'after_each_chapter', label: 'After each chapter', desc: 'Quiz after completing every chapter' },
                { value: 'after_n_chapters', label: 'After every 2 chapters', desc: 'Quiz after completing 2 chapters' },
                { value: 'final_only', label: 'Final only', desc: 'One comprehensive quiz at the end' },
              ].map((option) => (
                <button
                  key={option.value}
                  onClick={() => setQuizFrequency(option.value as typeof quizFrequency)}
                  className={`w-full text-left py-3 px-4 rounded-lg border transition flex items-center gap-3 ${
                    quizFrequency === option.value
                      ? 'bg-blue-50 border-blue-300'
                      : 'bg-white border-gray-200 hover:border-blue-200'
                  }`}
                >
                  <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                    quizFrequency === option.value ? 'border-blue-600' : 'border-gray-300'
                  }`}>
                    {quizFrequency === option.value && (
                      <div className="w-3 h-3 rounded-full bg-blue-600" />
                    )}
                  </div>
                  <div>
                    <p className="font-medium text-gray-900">{option.label}</p>
                    <p className="text-xs text-gray-500">{option.desc}</p>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Chapter Selection */}
          <div className="mb-6">
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2">
              <BookOpen className="h-4 w-4" />
              Select Chapters to Study ({selectedChapters.length} of {chapters.length})
            </label>
            <div className="border rounded-lg divide-y max-h-64 overflow-y-auto">
              {chapters.map((chapter) => (
                <button
                  key={chapter.id}
                  onClick={() => toggleChapter(chapter.chapter_number)}
                  className="w-full text-left py-3 px-4 flex items-center gap-3 hover:bg-gray-50 transition"
                >
                  <div className={`w-5 h-5 rounded border flex items-center justify-center ${
                    selectedChapters.includes(chapter.chapter_number)
                      ? 'bg-blue-600 border-blue-600'
                      : 'border-gray-300'
                  }`}>
                    {selectedChapters.includes(chapter.chapter_number) && (
                      <CheckCircle className="h-3 w-3 text-white" />
                    )}
                  </div>
                  <div className="flex-1">
                    <p className="font-medium text-gray-900">
                      Chapter {chapter.chapter_number}: {chapter.title}
                    </p>
                    <p className="text-xs text-gray-500">
                      ~{chapter.estimated_duration_minutes || 45} min
                    </p>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Summary */}
          <div className="bg-blue-50 rounded-lg p-4 mb-6">
            <h3 className="font-medium text-blue-900 mb-2">Your Learning Plan</h3>
            <ul className="text-sm text-blue-800 space-y-1">
              <li>• {selectedChapters.length} chapters to complete</li>
              <li>• {dailyMinutes} minutes per day</li>
              <li>• Estimated completion: {estimatedDays()} days</li>
              <li>• Professor style: {learningLevel}</li>
            </ul>
          </div>

          {/* Actions */}
          <div className="flex gap-3">
            <Link
              href="/dashboard"
              className="flex-1 py-3 px-4 border border-gray-200 rounded-lg text-gray-700 font-medium hover:bg-gray-50 transition text-center"
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
