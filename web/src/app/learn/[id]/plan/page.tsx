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

  const [plan, setPlan] = useState<LearningPlan | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isAccepting, setIsAccepting] = useState(false);
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [regenerateNotes, setRegenerateNotes] = useState('');

  const getToken = () => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('professor_access_token') || '';
    }
    return '';
  };

  useEffect(() => {
    const loadPlan = async () => {
      const token = getToken();
      if (!token) {
        router.push('/login');
        return;
      }

      try {
        setIsLoading(true);
        const current = await api.planning.current(token, bookId);
        if (current) {
          setPlan(current as unknown as LearningPlan);
        } else {
          const generated = await api.planning.generate(token, { book_id: bookId });
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
  }, [bookId, router]);

  const handleAcceptPlan = async () => {
    if (!plan) return;
    setIsAccepting(true);
    try {
      await api.planning.review(getToken(), {
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
    setIsRegenerating(true);
    try {
      const regenerated = await api.planning.generate(getToken(), {
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

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin text-blue-600 mx-auto mb-4" />
          <p className="text-gray-600">Loading your learning plan...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <AlertCircle className="h-8 w-8 text-red-600 mx-auto mb-4" />
          <p className="text-gray-900 font-medium mb-2">Failed to load plan</p>
          <p className="text-gray-600 mb-4">{error}</p>
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
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b">
        <div className="max-w-4xl mx-auto px-6 py-4">
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 text-gray-600 hover:text-gray-900"
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
          <h1 className="text-2xl font-bold text-gray-900 mb-2">
            Your Learning Plan
          </h1>
          <p className="text-gray-600">Plan Version {plan.version}</p>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <div className="bg-white rounded-xl border p-4 text-center">
            <Calendar className="h-6 w-6 text-blue-600 mx-auto mb-2" />
            <div className="text-2xl font-bold text-gray-900">{totalDays}</div>
            <div className="text-sm text-gray-500">Days</div>
          </div>
          <div className="bg-white rounded-xl border p-4 text-center">
            <BookOpen className="h-6 w-6 text-green-600 mx-auto mb-2" />
            <div className="text-2xl font-bold text-gray-900">{totalChapters}</div>
            <div className="text-sm text-gray-500">Chapters</div>
          </div>
          <div className="bg-white rounded-xl border p-4 text-center">
            <Clock className="h-6 w-6 text-purple-600 mx-auto mb-2" />
            <div className="text-2xl font-bold text-gray-900">{dailyMinutes ?? '-'}</div>
            <div className="text-sm text-gray-500">Min/Day</div>
          </div>
          <div className="bg-white rounded-xl border p-4 text-center">
            <GraduationCap className="h-6 w-6 text-orange-600 mx-auto mb-2" />
            <div className="text-2xl font-bold text-gray-900 capitalize">{learningLevel ?? '-'}</div>
            <div className="text-sm text-gray-500">Level</div>
          </div>
        </div>

        {/* Timeline */}
        <div className="bg-white rounded-2xl border p-6 mb-8">
          <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <Calendar className="h-5 w-5 text-blue-600" />
            Day-by-Day Schedule
          </h2>
          
          <div className="space-y-4">
            {days.map((day) => {
              const totalMinutes = day.items.reduce((sum, item) => sum + item.estimated_minutes, 0);
              const hasQuiz = day.items.some(item => item.quiz_after);
              return (
                <div key={day.day} className="border rounded-xl p-4 hover:border-blue-200 transition">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center">
                        <span className="font-bold text-blue-600">{day.day}</span>
                      </div>
                      <div>
                        <h3 className="font-medium text-gray-900">Day {day.day}</h3>
                        <p className="text-sm text-gray-500">
                          {day.rest ? 'Review or rest' : `${totalMinutes} minutes`}
                        </p>
                      </div>
                    </div>
                    {!day.rest && hasQuiz && (
                      <span className="px-3 py-1 bg-yellow-100 text-yellow-800 rounded-full text-xs font-medium">
                        📝 Quiz
                      </span>
                    )}
                  </div>
                  
                  <div className="pl-13 space-y-2">
                    {day.rest ? (
                      <div className="flex items-center gap-2 text-sm">
                        <CheckCircle className="h-4 w-4 text-gray-300" />
                        <span className="text-gray-700">Review, recap, or rest</span>
                      </div>
                    ) : (
                      day.items.map((item, idx) => (
                        <div key={idx} className="flex items-start gap-2 text-sm">
                          <CheckCircle className="h-4 w-4 text-gray-300 mt-0.5" />
                          <div className="text-gray-700">
                            <div>{item.chapter_title} ({item.estimated_minutes} min)</div>
                            {item.topics?.length > 0 && (
                              <div className="text-gray-500">
                                Topics: {item.topics.join(', ')}
                              </div>
                            )}
                            {item.quiz_after && (
                              <div className="text-yellow-600">Quiz after this session</div>
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
              className="w-full px-4 py-3 border rounded-xl focus:ring-2 focus:ring-blue-100 focus:border-blue-300 outline-none resize-none"
            />
            <button
              onClick={handleRegenerate}
              disabled={isRegenerating}
              className="mt-3 px-6 py-3 bg-white border border-blue-600 text-blue-600 rounded-xl font-medium hover:bg-blue-50 transition disabled:opacity-50"
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
          <p className="text-sm text-gray-500 mt-3">
            You can adjust the plan at any time during your learning journey
          </p>
        </div>
      </main>
    </div>
  );
}
