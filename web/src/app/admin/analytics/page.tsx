'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { 
  DollarSign, TrendingUp, Brain, Zap, ChevronDown,
  FileText, MessageSquare, HelpCircle, BookOpen, Loader2, AlertTriangle
} from 'lucide-react';
import AdminLayout, { AdminCard, StatCard, useAdminTheme } from '@/components/admin/AdminLayout';
import { admin } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';

interface CostsBreakdown {
  period_days: number;
  by_model: Array<{
    model: string;
    platform_cost_cents: number;
    user_cost_cents: number;
    requests: number;
  }>;
  by_usage_type: Array<{
    type: string;
    platform_cost_cents: number;
    user_cost_cents: number;
    requests: number;
  }>;
  totals: {
    platform_cost_cents: number;
    platform_cost_usd: number;
    user_cost_cents: number;
    user_cost_usd: number;
  };
}

interface BooksAnalytics {
  total_books: number;
  new_books_period: number;
  status_breakdown: Record<string, number>;
  daily_uploads: Array<{ date: string; count: number }>;
  learning_stats: {
    total_active_learners: number;
    avg_study_time_minutes: number;
  };
}

interface QuizAnalytics {
  total_completed: number;
  completed_in_period: number;
  average_score: number;
  pass_rate: number;
  daily_completions: Array<{
    date: string;
    count: number;
    avg_score: number;
  }>;
}

interface UsageTimelinePoint {
  date: string;
  requests: number;
  tokens: number;
  platform_cost_cents: number;
  active_users: number;
}

export default function AnalyticsPage() {
  const router = useRouter();
  const { token, isAuthenticated, isLoading: authLoading } = useAuth();
  const [costs, setCosts] = useState<CostsBreakdown | null>(null);
  const [books, setBooks] = useState<BooksAnalytics | null>(null);
  const [quizzes, setQuizzes] = useState<QuizAnalytics | null>(null);
  const [timeline, setTimeline] = useState<UsageTimelinePoint[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [selectedPeriod, setSelectedPeriod] = useState(30);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login?redirect=/admin/analytics');
    }
  }, [authLoading, isAuthenticated, router]);

  const fetchData = useCallback(async () => {
    if (!isAuthenticated) return;
    const t = token || '';

    try {
      const [costsData, booksData, quizzesData, timelineData] = await Promise.all([
        admin.getCostsBreakdown(t, selectedPeriod),
        admin.getBooksAnalytics(t, selectedPeriod),
        admin.getQuizAnalytics(t, selectedPeriod),
        admin.getUsageTimeline(t, selectedPeriod),
      ]);

      setCosts(costsData);
      setBooks(booksData);
      setQuizzes(quizzesData);
      setTimeline(timelineData);
      setError(null);
    } catch (err: any) {
      console.error('Failed to fetch analytics:', err);
      setError(err.message || 'Failed to load analytics');
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated, token, selectedPeriod]);

  useEffect(() => {
    if (isAuthenticated) {
      fetchData();
    }
  }, [isAuthenticated, fetchData]);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await fetchData();
    setIsRefreshing(false);
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-12 h-12 text-violet-500 animate-spin" />
          <p className="text-zinc-400 text-sm">Loading analytics...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="text-center max-w-md mx-auto p-8">
          <AlertTriangle className="w-12 h-12 text-red-400 mx-auto mb-4" />
          <p className="text-red-400 mb-4">{error}</p>
          <button
            onClick={handleRefresh}
            className="px-4 py-2 bg-violet-600 text-white rounded-lg hover:bg-violet-700 transition"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const periodSelector = (
    <div className="relative">
      <select
        value={selectedPeriod}
        onChange={(e) => setSelectedPeriod(Number(e.target.value))}
        className="appearance-none bg-zinc-800/50 border border-zinc-700/50 rounded-lg px-4 py-2 pr-10 text-sm text-white focus:outline-none focus:ring-2 focus:ring-violet-500"
      >
        <option value={7}>Last 7 days</option>
        <option value={14}>Last 14 days</option>
        <option value={30}>Last 30 days</option>
        <option value={60}>Last 60 days</option>
        <option value={90}>Last 90 days</option>
      </select>
      <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500 pointer-events-none" />
    </div>
  );

  return (
    <AdminLayout
      title="Analytics & Costs"
      subtitle="Detailed usage and cost breakdown"
      onRefresh={handleRefresh}
      isRefreshing={isRefreshing}
      headerActions={periodSelector}
    >
      <AnalyticsContent
        costs={costs}
        books={books}
        quizzes={quizzes}
        timeline={timeline}
        selectedPeriod={selectedPeriod}
      />
    </AdminLayout>
  );
}

function AnalyticsContent({
  costs,
  books,
  quizzes,
  timeline,
  selectedPeriod,
}: {
  costs: CostsBreakdown | null;
  books: BooksAnalytics | null;
  quizzes: QuizAnalytics | null;
  timeline: UsageTimelinePoint[];
  selectedPeriod: number;
}) {
  const { isDark } = useAdminTheme();

  const totalPlatformCost = costs?.totals.platform_cost_usd || 0;
  const totalUserCost = costs?.totals.user_cost_usd || 0;
  const maxDailyCost = Math.max(...timeline.map(d => d.platform_cost_cents), 1);

  return (
    <div className="space-y-6">
      {/* Cost Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className={`rounded-xl p-5 ${isDark ? 'bg-red-500/10 border border-red-500/20' : 'bg-red-50 border border-red-200'}`}>
          <div className="flex items-center gap-3 mb-3">
            <div className={`p-2 rounded-lg ${isDark ? 'bg-red-500/20' : 'bg-red-100'}`}>
              <DollarSign className={`w-5 h-5 ${isDark ? 'text-red-400' : 'text-red-600'}`} />
            </div>
            <span className={`text-sm ${isDark ? 'text-red-300' : 'text-red-700'}`}>Platform Cost</span>
          </div>
          <p className={`text-3xl font-bold ${isDark ? 'text-red-400' : 'text-red-600'}`}>
            ${totalPlatformCost.toFixed(2)}
          </p>
          <p className={`text-xs mt-1 ${isDark ? 'text-red-400/70' : 'text-red-600/70'}`}>
            Last {selectedPeriod} days (you pay)
          </p>
        </div>
        
        <div className={`rounded-xl p-5 ${isDark ? 'bg-emerald-500/10 border border-emerald-500/20' : 'bg-green-50 border border-green-200'}`}>
          <div className="flex items-center gap-3 mb-3">
            <div className={`p-2 rounded-lg ${isDark ? 'bg-emerald-500/20' : 'bg-green-100'}`}>
              <DollarSign className={`w-5 h-5 ${isDark ? 'text-emerald-400' : 'text-green-600'}`} />
            </div>
            <span className={`text-sm ${isDark ? 'text-emerald-300' : 'text-green-700'}`}>BYOK User Cost</span>
          </div>
          <p className={`text-3xl font-bold ${isDark ? 'text-emerald-400' : 'text-green-600'}`}>
            ${totalUserCost.toFixed(2)}
          </p>
          <p className={`text-xs mt-1 ${isDark ? 'text-emerald-400/70' : 'text-green-600/70'}`}>
            Last {selectedPeriod} days (users pay)
          </p>
        </div>
        
        <StatCard
          title="Total Requests"
          value={(costs?.by_model.reduce((sum, m) => sum + m.requests, 0) || 0).toLocaleString()}
          subtitle="API calls in period"
          icon={Zap}
          iconColor="text-violet-400"
        />
        
        <StatCard
          title="Avg Daily Cost"
          value={`$${(totalPlatformCost / selectedPeriod).toFixed(2)}`}
          subtitle="Platform average"
          icon={TrendingUp}
          iconColor="text-amber-400"
        />
      </div>

      {/* Cost Timeline Chart */}
      <AdminCard className="p-6">
        <h2 className={`text-lg font-semibold mb-6 ${isDark ? 'text-white' : 'text-gray-900'}`}>
          Daily Platform Cost
        </h2>
        
        <div className="h-48 flex items-end gap-1">
          {timeline.map((point, i) => (
            <div key={i} className="flex-1 flex flex-col items-center gap-1 group">
              <div 
                className={`w-full rounded-t transition cursor-pointer relative ${
                  isDark 
                    ? 'bg-gradient-to-t from-red-500 to-orange-400 opacity-70 hover:opacity-100' 
                    : 'bg-gradient-to-t from-red-500 to-orange-400 opacity-80 hover:opacity-100'
                }`}
                style={{ height: `${Math.max((point.platform_cost_cents / maxDailyCost) * 160, 4)}px` }}
              >
                {/* Tooltip */}
                <div className={`absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 rounded text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10 ${
                  isDark ? 'bg-zinc-800 text-white' : 'bg-gray-900 text-white'
                }`}>
                  ${(point.platform_cost_cents / 100).toFixed(2)}
                </div>
              </div>
              <span className={`text-[10px] ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>
                {new Date(point.date).getDate()}
              </span>
            </div>
          ))}
        </div>
      </AdminCard>

      {/* Cost Breakdown Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* By Model */}
        <AdminCard className="p-6">
          <h2 className={`text-lg font-semibold mb-6 flex items-center gap-2 ${isDark ? 'text-white' : 'text-gray-900'}`}>
            <Brain className="w-5 h-5 text-violet-400" />
            Cost by Model
          </h2>
          
          <div className="space-y-4">
            {costs?.by_model.map((model) => {
              const totalCost = model.platform_cost_cents + model.user_cost_cents;
              const platformPercent = totalCost > 0 ? (model.platform_cost_cents / totalCost) * 100 : 0;
              
              return (
                <div key={model.model} className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className={`font-medium text-sm ${isDark ? 'text-white' : 'text-gray-900'}`}>
                      {model.model}
                    </span>
                    <span className={`text-sm ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>
                      {model.requests.toLocaleString()} requests
                    </span>
                  </div>
                  <div className={`h-3 rounded-full overflow-hidden flex ${isDark ? 'bg-zinc-800' : 'bg-gray-200'}`}>
                    <div 
                      className="h-full bg-gradient-to-r from-red-500 to-orange-500"
                      style={{ width: `${platformPercent}%` }}
                      title={`Platform: $${(model.platform_cost_cents / 100).toFixed(2)}`}
                    />
                    <div 
                      className="h-full bg-gradient-to-r from-emerald-500 to-teal-500"
                      style={{ width: `${100 - platformPercent}%` }}
                      title={`BYOK: $${(model.user_cost_cents / 100).toFixed(2)}`}
                    />
                  </div>
                  <div className={`flex justify-between text-xs ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>
                    <span className="text-red-400">Platform: ${(model.platform_cost_cents / 100).toFixed(2)}</span>
                    <span className="text-emerald-400">BYOK: ${(model.user_cost_cents / 100).toFixed(2)}</span>
                  </div>
                </div>
              );
            })}
            
            {(!costs?.by_model || costs.by_model.length === 0) && (
              <p className={`text-center py-8 ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>
                No model usage data
              </p>
            )}
          </div>
        </AdminCard>

        {/* By Usage Type */}
        <AdminCard className="p-6">
          <h2 className={`text-lg font-semibold mb-6 flex items-center gap-2 ${isDark ? 'text-white' : 'text-gray-900'}`}>
            <Zap className="w-5 h-5 text-violet-400" />
            Cost by Usage Type
          </h2>
          
          <div className="space-y-4">
            {costs?.by_usage_type.map((type) => {
              const totalCost = type.platform_cost_cents + type.user_cost_cents;
              const IconComponent = type.type === 'chat_message' ? MessageSquare :
                          type.type === 'pdf_upload' ? FileText :
                          type.type === 'quiz_generation' ? HelpCircle : Zap;
              
              return (
                <div 
                  key={type.type} 
                  className={`flex items-center gap-4 p-3 rounded-xl ${
                    isDark ? 'bg-zinc-800/30' : 'bg-gray-50'
                  }`}
                >
                  <div className={`p-2 rounded-lg ${isDark ? 'bg-zinc-800' : 'bg-gray-200'}`}>
                    <IconComponent className={`w-4 h-4 ${isDark ? 'text-zinc-400' : 'text-gray-500'}`} />
                  </div>
                  <div className="flex-1">
                    <p className={`font-medium text-sm capitalize ${isDark ? 'text-white' : 'text-gray-900'}`}>
                      {type.type.replace(/_/g, ' ')}
                    </p>
                    <p className={`text-xs ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>
                      {type.requests.toLocaleString()} requests
                    </p>
                  </div>
                  <div className="text-right">
                    <p className={`font-medium ${isDark ? 'text-white' : 'text-gray-900'}`}>
                      ${(totalCost / 100).toFixed(2)}
                    </p>
                    <p className="text-xs text-red-400">
                      ${(type.platform_cost_cents / 100).toFixed(2)} platform
                    </p>
                  </div>
                </div>
              );
            })}
            
            {(!costs?.by_usage_type || costs.by_usage_type.length === 0) && (
              <p className={`text-center py-8 ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>
                No usage type data
              </p>
            )}
          </div>
        </AdminCard>
      </div>

      {/* Books & Quiz Analytics */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Books */}
        <AdminCard className="p-6">
          <h2 className={`text-lg font-semibold mb-6 flex items-center gap-2 ${isDark ? 'text-white' : 'text-gray-900'}`}>
            <BookOpen className="w-5 h-5 text-blue-400" />
            Books Analytics
          </h2>
          
          <div className="grid grid-cols-2 gap-4 mb-6">
            <div className={`rounded-xl p-4 text-center ${isDark ? 'bg-zinc-800/30' : 'bg-gray-50'}`}>
              <p className="text-3xl font-bold text-blue-400">{books?.total_books || 0}</p>
              <p className={`text-xs mt-1 ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>Total Books</p>
            </div>
            <div className={`rounded-xl p-4 text-center ${isDark ? 'bg-zinc-800/30' : 'bg-gray-50'}`}>
              <p className="text-3xl font-bold text-emerald-400">+{books?.new_books_period || 0}</p>
              <p className={`text-xs mt-1 ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>New in Period</p>
            </div>
          </div>
          
          <div className="space-y-3">
            <p className={`text-sm font-medium ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>
              Processing Status
            </p>
            {books?.status_breakdown && Object.entries(books.status_breakdown).map(([status, count]) => (
              <div 
                key={status} 
                className={`flex items-center justify-between p-2 rounded-lg ${
                  isDark ? 'bg-zinc-800/30' : 'bg-gray-50'
                }`}
              >
                <span className={`text-sm capitalize ${isDark ? 'text-white' : 'text-gray-900'}`}>
                  {status.replace(/_/g, ' ')}
                </span>
                <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                  status === 'completed' 
                    ? isDark ? 'bg-emerald-500/20 text-emerald-300' : 'bg-green-100 text-green-700'
                    : status === 'processing' 
                    ? isDark ? 'bg-amber-500/20 text-amber-300' : 'bg-amber-100 text-amber-700'
                    : status === 'failed' 
                    ? isDark ? 'bg-red-500/20 text-red-300' : 'bg-red-100 text-red-700'
                    : isDark ? 'bg-zinc-700 text-zinc-300' : 'bg-gray-100 text-gray-700'
                }`}>
                  {count}
                </span>
              </div>
            ))}
          </div>
          
          <div className={`mt-6 pt-4 border-t ${isDark ? 'border-zinc-800' : 'border-gray-200'}`}>
            <div className="flex items-center justify-between text-sm">
              <span className={isDark ? 'text-zinc-400' : 'text-gray-500'}>Active Learners</span>
              <span className={`font-medium ${isDark ? 'text-white' : 'text-gray-900'}`}>
                {books?.learning_stats.total_active_learners || 0}
              </span>
            </div>
            <div className="flex items-center justify-between text-sm mt-2">
              <span className={isDark ? 'text-zinc-400' : 'text-gray-500'}>Avg Study Time</span>
              <span className={`font-medium ${isDark ? 'text-white' : 'text-gray-900'}`}>
                {books?.learning_stats.avg_study_time_minutes?.toFixed(0) || 0} min
              </span>
            </div>
          </div>
        </AdminCard>

        {/* Quizzes */}
        <AdminCard className="p-6">
          <h2 className={`text-lg font-semibold mb-6 flex items-center gap-2 ${isDark ? 'text-white' : 'text-gray-900'}`}>
            <HelpCircle className="w-5 h-5 text-amber-400" />
            Quiz Analytics
          </h2>
          
          <div className="grid grid-cols-2 gap-4 mb-6">
            <div className={`rounded-xl p-4 text-center ${isDark ? 'bg-zinc-800/30' : 'bg-gray-50'}`}>
              <p className="text-3xl font-bold text-amber-400">{quizzes?.total_completed || 0}</p>
              <p className={`text-xs mt-1 ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>Total Completed</p>
            </div>
            <div className={`rounded-xl p-4 text-center ${isDark ? 'bg-zinc-800/30' : 'bg-gray-50'}`}>
              <p className="text-3xl font-bold text-emerald-400">+{quizzes?.completed_in_period || 0}</p>
              <p className={`text-xs mt-1 ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>In Period</p>
            </div>
          </div>
          
          <div className="space-y-4">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className={`text-sm ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>Average Score</span>
                <span className={`font-medium ${isDark ? 'text-white' : 'text-gray-900'}`}>
                  {quizzes?.average_score?.toFixed(1) || 0}%
                </span>
              </div>
              <div className={`h-2 rounded-full overflow-hidden ${isDark ? 'bg-zinc-800' : 'bg-gray-200'}`}>
                <div 
                  className={`h-full rounded-full ${
                    (quizzes?.average_score || 0) >= 70 ? 'bg-emerald-500' : 'bg-amber-500'
                  }`}
                  style={{ width: `${quizzes?.average_score || 0}%` }}
                />
              </div>
            </div>
            
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className={`text-sm ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>Pass Rate</span>
                <span className={`font-medium ${isDark ? 'text-white' : 'text-gray-900'}`}>
                  {quizzes?.pass_rate?.toFixed(1) || 0}%
                </span>
              </div>
              <div className={`h-2 rounded-full overflow-hidden ${isDark ? 'bg-zinc-800' : 'bg-gray-200'}`}>
                <div 
                  className={`h-full rounded-full ${
                    (quizzes?.pass_rate || 0) >= 70 ? 'bg-emerald-500' : 'bg-amber-500'
                  }`}
                  style={{ width: `${quizzes?.pass_rate || 0}%` }}
                />
              </div>
            </div>
          </div>
          
          {/* Mini chart */}
          <div className={`mt-6 pt-4 border-t ${isDark ? 'border-zinc-800' : 'border-gray-200'}`}>
            <p className={`text-sm mb-3 ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>Daily Completions</p>
            <div className="h-16 flex items-end gap-1">
              {quizzes?.daily_completions?.slice(-14).map((day, i) => (
                <div 
                  key={i}
                  className="flex-1 bg-amber-400 rounded-t hover:bg-amber-500 transition"
                  style={{ height: `${Math.max((day.count / Math.max(...(quizzes?.daily_completions?.map(d => d.count) || [1]))) * 100, 10)}%` }}
                  title={`${day.count} quizzes`}
                />
              ))}
            </div>
          </div>
        </AdminCard>
      </div>
    </div>
  );
}
