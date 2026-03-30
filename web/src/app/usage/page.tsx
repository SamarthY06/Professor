'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  ArrowLeft, DollarSign, Zap, TrendingUp, TrendingDown,
  Activity, Clock, BarChart3, PieChart, RefreshCw,
  Cpu, MessageSquare, FileText, HelpCircle, Settings,
  ChevronRight, Loader2, AlertCircle, Key, Sparkles
} from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import api from '@/lib/api';

interface DashboardData {
  is_byok: boolean;
  current_month: {
    requests: number;
    input_tokens: number;
    output_tokens: number;
    cached_tokens: number;
    total_tokens: number;
    cost_cents: number;
    cost_usd: number;
    today_requests: number;
    today_cost_cents: number;
    billing_cycle_start: string;
  };
  daily_breakdown: Array<{
    date: string;
    requests: number;
    input_tokens: number;
    output_tokens: number;
    cost_cents: number;
  }>;
  model_usage: Array<{
    model_name: string;
    display_name: string;
    requests: number;
    input_tokens: number;
    output_tokens: number;
    cost_cents: number;
    percentage: number;
  }>;
  recent_activity: Array<{
    id: string;
    type: string;
    model: string;
    input_tokens: number;
    output_tokens: number;
    cost_cents: number;
    book_title: string | null;
    created_at: string;
  }>;
  cost_projections: {
    daily_average_cents: number;
    projected_monthly_cents: number;
    last_month_cents: number;
    month_over_month_change: number;
  };
}

interface RealtimeData {
  is_byok: boolean;
  today: {
    cost_cents: number;
    cost_usd: number;
    requests: number;
  };
  month: {
    cost_cents: number;
    cost_usd: number;
    requests: number;
  };
  last_activity: {
    type: string;
    model: string;
    cost_cents: number;
    created_at: string;
  } | null;
  preferred_model: string | null;
  timestamp: string;
}

function formatCurrency(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

function formatNumber(num: number): string {
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
  return num.toString();
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  });
}

function formatTime(dateStr: string): string {
  return new Date(dateStr).toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

function getActivityIcon(type: string) {
  switch (type) {
    case 'chat':
      return <MessageSquare className="w-4 h-4" />;
    case 'quiz':
      return <HelpCircle className="w-4 h-4" />;
    case 'embedding':
      return <FileText className="w-4 h-4" />;
    default:
      return <Zap className="w-4 h-4" />;
  }
}

function getActivityColor(type: string) {
  switch (type) {
    case 'chat':
      return 'bg-blue-100 text-blue-600';
    case 'quiz':
      return 'bg-purple-100 text-purple-600';
    case 'embedding':
      return 'bg-green-100 text-green-600';
    default:
      return 'bg-gray-100 text-gray-600';
  }
}

// Simple bar chart component
function MiniBarChart({ data, maxValue }: { data: number[]; maxValue: number }) {
  return (
    <div className="flex items-end gap-1 h-16">
      {data.slice(-14).map((value, i) => (
        <div
          key={i}
          className="flex-1 bg-gradient-to-t from-emerald-500 to-emerald-400 rounded-t min-w-[4px]"
          style={{ height: `${Math.max(4, (value / maxValue) * 100)}%` }}
        />
      ))}
    </div>
  );
}

// Donut chart component for model usage
function DonutChart({ data }: { data: Array<{ name: string; value: number; color: string }> }) {
  const total = data.reduce((sum, d) => sum + d.value, 0);
  let currentAngle = 0;

  const colors = ['#10b981', '#3b82f6', '#8b5cf6', '#f59e0b', '#ef4444', '#6366f1'];

  return (
    <div className="relative w-32 h-32">
      <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
        {data.map((item, i) => {
          const percentage = total > 0 ? (item.value / total) * 100 : 0;
          const angle = (percentage / 100) * 360;
          const startAngle = currentAngle;
          currentAngle += angle;

          const x1 = 50 + 40 * Math.cos((startAngle * Math.PI) / 180);
          const y1 = 50 + 40 * Math.sin((startAngle * Math.PI) / 180);
          const x2 = 50 + 40 * Math.cos(((startAngle + angle) * Math.PI) / 180);
          const y2 = 50 + 40 * Math.sin(((startAngle + angle) * Math.PI) / 180);

          const largeArc = angle > 180 ? 1 : 0;

          return (
            <path
              key={i}
              d={`M 50 50 L ${x1} ${y1} A 40 40 0 ${largeArc} 1 ${x2} ${y2} Z`}
              fill={colors[i % colors.length]}
              className="transition-all duration-300 hover:opacity-80"
            />
          );
        })}
        <circle cx="50" cy="50" r="25" fill="white" />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-lg font-bold text-gray-900">{data.length}</span>
      </div>
    </div>
  );
}

export default function UsageDashboardPage() {
  const router = useRouter();
  const { token, isLoading: authLoading, isAuthenticated } = useAuth();
  const [isLoading, setIsLoading] = useState(true);
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [realtimeData, setRealtimeData] = useState<RealtimeData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  // Redirect if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  // Fetch dashboard data
  const fetchDashboard = useCallback(async () => {
    if (!isAuthenticated) return;

    try {
      const data = await api.usage.getBYOKDashboard(token || '');
      setDashboardData(data);
      setError(null);
    } catch (err: any) {
      console.error('Failed to fetch dashboard:', err);
      setError(err.message || 'Failed to load dashboard');
    }
  }, [isAuthenticated, token]);

  // Fetch realtime data
  const fetchRealtime = useCallback(async () => {
    if (!isAuthenticated) return;

    try {
      const data = await api.usage.getBYOKRealtime(token || '');
      setRealtimeData(data);
      setLastUpdated(new Date());
    } catch (err) {
      console.error('Failed to fetch realtime data:', err);
    }
  }, [isAuthenticated, token]);

  // Initial load
  useEffect(() => {
    const loadData = async () => {
      if (!isAuthenticated) return;
      setIsLoading(true);
      await Promise.all([fetchDashboard(), fetchRealtime()]);
      setIsLoading(false);
    };

    loadData();
  }, [isAuthenticated, fetchDashboard, fetchRealtime]);

  // Realtime polling (every 30 seconds)
  useEffect(() => {
    if (!isAuthenticated || !dashboardData?.is_byok) return;

    const interval = setInterval(fetchRealtime, 30000);
    return () => clearInterval(interval);
  }, [isAuthenticated, dashboardData?.is_byok, fetchRealtime]);

  // Manual refresh
  const handleRefresh = async () => {
    setIsRefreshing(true);
    await Promise.all([fetchDashboard(), fetchRealtime()]);
    setIsRefreshing(false);
  };

  if (authLoading || !isAuthenticated) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-12 w-12 animate-spin text-emerald-500 mx-auto mb-4" />
          <p className="text-slate-400">Loading your usage dashboard...</p>
        </div>
      </div>
    );
  }

  // Not BYOK - show upgrade prompt
  if (!dashboardData?.is_byok) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
        <div className="max-w-2xl mx-auto px-4 py-12">
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 text-slate-400 hover:text-white mb-8"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Dashboard
          </Link>

          <div className="bg-slate-800/50 border border-slate-700 rounded-2xl p-8 text-center">
            <div className="w-16 h-16 bg-gradient-to-br from-amber-500 to-orange-600 rounded-2xl flex items-center justify-center mx-auto mb-6">
              <Key className="w-8 h-8 text-white" />
            </div>

            <h1 className="text-2xl font-bold text-white mb-3">
              Unlock Your Usage Dashboard
            </h1>

            <p className="text-slate-400 mb-6 max-w-md mx-auto">
              Add your own OpenAI API key to access detailed usage tracking, 
              real-time expense monitoring, and cost projections.
            </p>

            <div className="bg-slate-900/50 rounded-xl p-6 mb-6">
              <h3 className="text-lg font-semibold text-white mb-4">BYOK Benefits</h3>
              <ul className="text-left space-y-3">
                {[
                  'Unlimited PDFs, messages, and quizzes',
                  'Access to all AI models (GPT-4o, GPT-5, etc.)',
                  'Real-time expense tracking',
                  'Detailed usage analytics',
                  'Cost projections and insights',
                  'Batch API mode (50% cheaper)',
                ].map((benefit, i) => (
                  <li key={i} className="flex items-center gap-3 text-slate-300">
                    <Sparkles className="w-4 h-4 text-emerald-500 flex-shrink-0" />
                    {benefit}
                  </li>
                ))}
              </ul>
            </div>

            <Link
              href="/settings"
              className="inline-flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-emerald-500 to-teal-600 text-white font-semibold rounded-xl hover:from-emerald-600 hover:to-teal-700 transition-all"
            >
              <Key className="w-5 h-5" />
              Add Your API Key
              <ChevronRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const { current_month, daily_breakdown, model_usage, recent_activity, cost_projections } = dashboardData;
  const maxDailyCost = Math.max(...daily_breakdown.map(d => d.cost_cents), 1);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Header */}
      <div className="border-b border-slate-700/50 bg-slate-900/50 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Link
                href="/dashboard"
                className="p-2 hover:bg-slate-800 rounded-lg text-slate-400 hover:text-white transition-colors"
              >
                <ArrowLeft className="w-5 h-5" />
              </Link>
              <div>
                <h1 className="text-xl font-bold text-white">Usage Dashboard</h1>
                <p className="text-sm text-slate-400">
                  Real-time expense tracking for your OpenAI API key
                </p>
              </div>
            </div>

            <div className="flex items-center gap-4">
              {lastUpdated && (
                <span className="text-xs text-slate-500">
                  Updated {formatTime(lastUpdated.toISOString())}
                </span>
              )}
              <button
                onClick={handleRefresh}
                disabled={isRefreshing}
                className="flex items-center gap-2 px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
                Refresh
              </button>
              <Link
                href="/settings"
                className="flex items-center gap-2 px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg transition-colors"
              >
                <Settings className="w-4 h-4" />
                Settings
              </Link>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 py-6">
        {error && (
          <div className="mb-6 p-4 bg-red-500/10 border border-red-500/20 rounded-xl flex items-center gap-3 text-red-400">
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
            {error}
          </div>
        )}

        {/* Top Stats Row */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          {/* Today's Cost */}
          <div className="bg-gradient-to-br from-emerald-500/10 to-teal-500/10 border border-emerald-500/20 rounded-2xl p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-emerald-400 text-sm font-medium">Today's Cost</span>
              <div className="p-2 bg-emerald-500/20 rounded-lg">
                <DollarSign className="w-4 h-4 text-emerald-400" />
              </div>
            </div>
            <div className="text-3xl font-bold text-white mb-1">
              {formatCurrency(realtimeData?.today.cost_cents || current_month.today_cost_cents)}
            </div>
            <div className="text-sm text-slate-400">
              {realtimeData?.today.requests || current_month.today_requests} requests
            </div>
          </div>

          {/* Month to Date */}
          <div className="bg-gradient-to-br from-blue-500/10 to-indigo-500/10 border border-blue-500/20 rounded-2xl p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-blue-400 text-sm font-medium">Month to Date</span>
              <div className="p-2 bg-blue-500/20 rounded-lg">
                <BarChart3 className="w-4 h-4 text-blue-400" />
              </div>
            </div>
            <div className="text-3xl font-bold text-white mb-1">
              {formatCurrency(realtimeData?.month.cost_cents || current_month.cost_cents)}
            </div>
            <div className="text-sm text-slate-400">
              {formatNumber(current_month.total_tokens)} tokens
            </div>
          </div>

          {/* Projected Monthly */}
          <div className="bg-gradient-to-br from-purple-500/10 to-pink-500/10 border border-purple-500/20 rounded-2xl p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-purple-400 text-sm font-medium">Projected Monthly</span>
              <div className="p-2 bg-purple-500/20 rounded-lg">
                <TrendingUp className="w-4 h-4 text-purple-400" />
              </div>
            </div>
            <div className="text-3xl font-bold text-white mb-1">
              {formatCurrency(cost_projections.projected_monthly_cents)}
            </div>
            <div className={`text-sm flex items-center gap-1 ${
              cost_projections.month_over_month_change >= 0 ? 'text-red-400' : 'text-emerald-400'
            }`}>
              {cost_projections.month_over_month_change >= 0 ? (
                <TrendingUp className="w-3 h-3" />
              ) : (
                <TrendingDown className="w-3 h-3" />
              )}
              {Math.abs(cost_projections.month_over_month_change)}% vs last month
            </div>
          </div>

          {/* Daily Average */}
          <div className="bg-gradient-to-br from-amber-500/10 to-orange-500/10 border border-amber-500/20 rounded-2xl p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-amber-400 text-sm font-medium">Daily Average</span>
              <div className="p-2 bg-amber-500/20 rounded-lg">
                <Activity className="w-4 h-4 text-amber-400" />
              </div>
            </div>
            <div className="text-3xl font-bold text-white mb-1">
              {formatCurrency(cost_projections.daily_average_cents)}
            </div>
            <div className="text-sm text-slate-400">
              {current_month.requests} total requests
            </div>
          </div>
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
          {/* Daily Cost Chart */}
          <div className="lg:col-span-2 bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-semibold text-white">Daily Costs (Last 14 Days)</h2>
              <span className="text-sm text-slate-400">
                Total: {formatCurrency(daily_breakdown.reduce((sum, d) => sum + d.cost_cents, 0))}
              </span>
            </div>

            <MiniBarChart
              data={daily_breakdown.map(d => d.cost_cents)}
              maxValue={maxDailyCost}
            />

            <div className="flex justify-between mt-2 text-xs text-slate-500">
              <span>{daily_breakdown.length > 0 ? formatDate(daily_breakdown[Math.max(0, daily_breakdown.length - 14)].date) : ''}</span>
              <span>{daily_breakdown.length > 0 ? formatDate(daily_breakdown[daily_breakdown.length - 1].date) : ''}</span>
            </div>
          </div>

          {/* Model Usage Breakdown */}
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6">
            <h2 className="text-lg font-semibold text-white mb-6">Model Usage</h2>

            {model_usage.length > 0 ? (
              <div className="flex items-center gap-6">
                <DonutChart
                  data={model_usage.map((m, i) => ({
                    name: m.display_name,
                    value: m.cost_cents,
                    color: ['#10b981', '#3b82f6', '#8b5cf6', '#f59e0b'][i % 4],
                  }))}
                />

                <div className="flex-1 space-y-2">
                  {model_usage.slice(0, 4).map((model, i) => (
                    <div key={model.model_name} className="flex items-center gap-2">
                      <div
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: ['#10b981', '#3b82f6', '#8b5cf6', '#f59e0b'][i % 4] }}
                      />
                      <span className="text-sm text-slate-300 flex-1 truncate">{model.display_name}</span>
                      <span className="text-sm text-slate-400">{model.percentage}%</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="text-center py-8 text-slate-500">
                No usage data yet
              </div>
            )}
          </div>
        </div>

        {/* Bottom Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Token Breakdown */}
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6">
            <h2 className="text-lg font-semibold text-white mb-6">Token Breakdown</h2>

            <div className="space-y-4">
              <div className="flex items-center justify-between p-4 bg-slate-900/50 rounded-xl">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-blue-500/20 rounded-lg">
                    <Cpu className="w-4 h-4 text-blue-400" />
                  </div>
                  <div>
                    <div className="text-white font-medium">Input Tokens</div>
                    <div className="text-sm text-slate-400">Prompts & context</div>
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-xl font-bold text-white">{formatNumber(current_month.input_tokens)}</div>
                </div>
              </div>

              <div className="flex items-center justify-between p-4 bg-slate-900/50 rounded-xl">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-emerald-500/20 rounded-lg">
                    <MessageSquare className="w-4 h-4 text-emerald-400" />
                  </div>
                  <div>
                    <div className="text-white font-medium">Output Tokens</div>
                    <div className="text-sm text-slate-400">AI responses</div>
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-xl font-bold text-white">{formatNumber(current_month.output_tokens)}</div>
                </div>
              </div>

              {current_month.cached_tokens > 0 && (
                <div className="flex items-center justify-between p-4 bg-slate-900/50 rounded-xl">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-purple-500/20 rounded-lg">
                      <Zap className="w-4 h-4 text-purple-400" />
                    </div>
                    <div>
                      <div className="text-white font-medium">Cached Tokens</div>
                      <div className="text-sm text-slate-400">Discounted rate</div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-xl font-bold text-white">{formatNumber(current_month.cached_tokens)}</div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Recent Activity */}
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-semibold text-white">Recent Activity</h2>
              <span className="text-sm text-slate-400">{recent_activity.length} items</span>
            </div>

            <div className="space-y-3 max-h-80 overflow-y-auto">
              {recent_activity.length > 0 ? (
                recent_activity.slice(0, 10).map((activity) => (
                  <div
                    key={activity.id}
                    className="flex items-center gap-3 p-3 bg-slate-900/50 rounded-xl"
                  >
                    <div className={`p-2 rounded-lg ${getActivityColor(activity.type)}`}>
                      {getActivityIcon(activity.type)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-white font-medium capitalize">{activity.type}</span>
                        <span className="text-xs text-slate-500">{activity.model}</span>
                      </div>
                      {activity.book_title && (
                        <div className="text-sm text-slate-400 truncate">{activity.book_title}</div>
                      )}
                    </div>
                    <div className="text-right">
                      <div className="text-white font-medium">{formatCurrency(activity.cost_cents)}</div>
                      <div className="text-xs text-slate-500">{formatTime(activity.created_at)}</div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-center py-8 text-slate-500">
                  No activity yet
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Current Model & Billing Info */}
        <div className="mt-6 bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="p-3 bg-gradient-to-br from-emerald-500/20 to-teal-500/20 rounded-xl">
                <Sparkles className="w-6 h-6 text-emerald-400" />
              </div>
              <div>
                <div className="text-white font-medium">Current Model</div>
                <div className="text-lg text-emerald-400 font-semibold">
                  {realtimeData?.preferred_model || 'gpt-4o'}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-6">
              <div className="text-right">
                <div className="text-sm text-slate-400">Billing Cycle Started</div>
                <div className="text-white font-medium">
                  {new Date(current_month.billing_cycle_start).toLocaleDateString('en-US', {
                    month: 'long',
                    day: 'numeric',
                    year: 'numeric',
                  })}
                </div>
              </div>

              <Link
                href="/settings"
                className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors"
              >
                <Settings className="w-4 h-4" />
                Change Model
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
