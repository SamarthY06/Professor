'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  Brain,
  ArrowLeft,
  Calendar,
  Clock,
  BookOpen,
  CheckCircle,
  Play,
  Loader2,
  AlertCircle,
  GraduationCap,
} from 'lucide-react';
import api from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';

interface DayItem {
  chapter_number: number;
  chapter_title: string;
  topics: string[];
  estimated_minutes: number;
  quiz_after: boolean;
}

interface DaySchedule {
  day: number;
  rest: boolean;
  items: DayItem[];
}

interface PlanData {
  total_days: number;
  overview?: string;
  days: DaySchedule[];
  daily_minutes?: number;
  learning_level?: string;
  quiz_frequency?: string;
}

interface LearningPlan {
  id: string;
  book_id: string;
  summary: string;
  plan_data: PlanData;
  status: string;
  version: number;
  created_at: string;
}

export default function PlanPage() {
  const params = useParams();
  const router = useRouter();
  const bookId = params.id as string;
  const { token, isLoading: authLoading, isAuthenticated } = useAuth();

  const [plan, setPlan] = useState<LearningPlan | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isAccepting, setIsAccepting] = useState(false);
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [regenerateNotes, setRegenerateNotes] = useState('');

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  useEffect(() => {
    if (authLoading || !isAuthenticated) return;

    const t = token || '';
    const loadPlan = async () => {
      try {
        setIsLoading(true);
        const current = await api.planning.current(t, bookId);
        if (current) {
          setPlan(current as unknown as LearningPlan);
        } else {
          const generated = await api.planning.generate(t, { book_id: bookId });
          setPlan(generated as unknown as LearningPlan);
        }
      } catch (err: any) {
        console.error('Failed to load plan:', err);
        setError(err.message || 'Failed to load learning plan');
      } finally {
        setIsLoading(false);
      }
    };

    loadPlan();
  }, [bookId, token, authLoading, isAuthenticated, router]);

  const handleAcceptPlan = async () => {
    if (!plan || !isAuthenticated) return;
    setIsAccepting(true);
    try {
      await api.planning.review(token || '', {
        plan_id: plan.id,
        feedback: '',
        action: 'accept',
      });
      router.push(`/learn/${bookId}`);
    } catch (err: any) {
      console.error('Failed to accept plan:', err);
      setError(err.message || 'Failed to accept plan');
    } finally {
      setIsAccepting(false);
    }
  };

  const handleRegenerate = async () => {
    if (!isAuthenticated) return;
    setIsRegenerating(true);
    try {
      const regenerated = await api.planning.generate(token || '', {
        book_id: bookId,
        additional_instructions: regenerateNotes || undefined,
      });
      setPlan(regenerated as unknown as LearningPlan);
      setRegenerateNotes('');
    } catch (err: any) {
      console.error('Failed to regenerate plan:', err);
      setError(err.message || 'Failed to regenerate plan');
    } finally {
      setIsRegenerating(false);
    }
  };

  const days = plan?.plan_data?.days || [];
  const totalDays = plan?.plan_data?.total_days || days.length;
  const dailyMinutes = plan?.plan_data?.daily_minutes;
  const learningLevel = plan?.plan_data?.learning_level;
  const totalChapters = Array.from(
    new Set(
      days.flatMap((day) => day.items.map((item) => item.chapter_number))
    )
  ).length;

  if (authLoading || isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin text-blue-600 mx-auto mb-4" />
          <p className="text-gray-600 dark:text-gray-300">Loading your learning plan...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <AlertCircle className="h-8 w-8 text-red-600 mx-auto mb-4" />
          <p className="text-gray-900 dark:text-gray-100 font-medium mb-2">Failed to load plan</p>
          <p className="text-gray-600 dark:text-gray-300 mb-4">{error}</p>
          <Link
            href="/dashboard"
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Back to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  if (!plan) return null;

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <header className="bg-white dark:bg-gray-800 border-b dark:border-gray-700">
        <div className="max-w-4xl mx-auto px-6 py-4">
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Dashboard
          </Link>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-8">
        {/* Title Section */}
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-gradient-to-br from-blue-500 to-purple-600 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <Brain className="h-8 w-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2">
            Your Learning Plan
          </h1>
          <p className="text-gray-600 dark:text-gray-300">Plan Version {plan.version}</p>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <div className="bg-white dark:bg-gray-800 rounded-xl border dark:border-gray-700 p-4 text-center">
            <Calendar className="h-6 w-6 text-blue-600 mx-auto mb-2" />
            <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">{totalDays}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">Days</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-xl border dark:border-gray-700 p-4 text-center">
            <BookOpen className="h-6 w-6 text-green-600 mx-auto mb-2" />
            <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">{totalChapters}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">Chapters</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-xl border dark:border-gray-700 p-4 text-center">
            <Clock className="h-6 w-6 text-purple-600 mx-auto mb-2" />
            <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">{dailyMinutes ?? '-'}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">Min/Day</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-xl border dark:border-gray-700 p-4 text-center">
            <GraduationCap className="h-6 w-6 text-orange-600 mx-auto mb-2" />
            <div className="text-2xl font-bold text-gray-900 dark:text-gray-100 capitalize">{learningLevel ?? '-'}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">Level</div>
          </div>
        </div>

        {/* Timeline */}
        <div className="bg-white dark:bg-gray-800 rounded-2xl border dark:border-gray-700 p-6 mb-8">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4 flex items-center gap-2">
            <Calendar className="h-5 w-5 text-blue-600" />
            Day-by-Day Schedule
          </h2>
          
          <div className="space-y-4">
            {days.map((day) => {
              const totalMinutes = day.items.reduce((sum, item) => sum + item.estimated_minutes, 0);
              const hasQuiz = day.items.some(item => item.quiz_after);
              return (
                <div key={day.day} className="border dark:border-gray-700 rounded-xl p-4 hover:border-blue-200 dark:hover:border-blue-700 transition">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-blue-100 dark:bg-blue-900/30 rounded-full flex items-center justify-center">
                        <span className="font-bold text-blue-600 dark:text-blue-400">{day.day}</span>
                      </div>
                      <div>
                        <h3 className="font-medium text-gray-900 dark:text-gray-100">Day {day.day}</h3>
                        <p className="text-sm text-gray-500 dark:text-gray-400">
                          {day.rest ? 'Review or rest' : `${totalMinutes} minutes`}
                        </p>
                      </div>
                    </div>
                    {!day.rest && hasQuiz && (
                      <span className="px-3 py-1 bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-400 rounded-full text-xs font-medium">
                        📝 Quiz
                      </span>
                    )}
                  </div>
                  
                  <div className="pl-13 space-y-2">
                    {day.rest ? (
                      <div className="flex items-center gap-2 text-sm">
                        <CheckCircle className="h-4 w-4 text-gray-300 dark:text-gray-600" />
                        <span className="text-gray-700 dark:text-gray-200">Review, recap, or rest</span>
                      </div>
                    ) : (
                      day.items.map((item, idx) => (
                        <div key={idx} className="flex items-start gap-2 text-sm">
                          <CheckCircle className="h-4 w-4 text-gray-300 dark:text-gray-600 mt-0.5" />
                          <div className="text-gray-700 dark:text-gray-200">
                            <div>{item.chapter_title} ({item.estimated_minutes} min)</div>
                            {item.topics?.length > 0 && (
                              <div className="text-gray-500 dark:text-gray-400">
                                Topics: {item.topics.join(', ')}
                              </div>
                            )}
                            {item.quiz_after && (
                              <div className="text-yellow-600 dark:text-yellow-500">Quiz after this session</div>
                            )}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Accept Button */}
        <div className="text-center">
          <div className="max-w-xl mx-auto mb-4">
            <textarea
              value={regenerateNotes}
              onChange={(e) => setRegenerateNotes(e.target.value)}
              placeholder="Request changes or add preferences for a new plan"
              rows={3}
              className="w-full px-4 py-3 border dark:border-gray-700 rounded-xl focus:ring-2 focus:ring-blue-100 dark:focus:ring-blue-900/50 focus:border-blue-300 dark:focus:border-blue-500 outline-none resize-none dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
            />
            <button
              onClick={handleRegenerate}
              disabled={isRegenerating}
              className="mt-3 px-6 py-3 bg-white dark:bg-gray-800 border border-blue-600 text-blue-600 dark:text-blue-400 rounded-xl font-medium hover:bg-blue-50 dark:hover:bg-gray-700 transition disabled:opacity-50"
            >
              {isRegenerating ? 'Regenerating...' : 'Regenerate Plan'}
            </button>
          </div>
          <button
            onClick={handleAcceptPlan}
            disabled={isAccepting}
            className="px-8 py-4 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition disabled:opacity-50 flex items-center gap-2 mx-auto"
          >
            {isAccepting ? (
              <>
                <Loader2 className="h-5 w-5 animate-spin" />
                Starting...
              </>
            ) : (
              <>
                <Play className="h-5 w-5" />
                Accept Plan & Start Learning
              </>
            )}
          </button>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-3">
            You can adjust the plan at any time during your learning journey
          </p>
        </div>
      </main>
    </div>
  );
}
