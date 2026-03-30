'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { 
  BookOpen, Search, CheckCircle, XCircle,
  AlertTriangle, Loader2, Clock, TrendingUp, Brain,
  Filter, ChevronDown
} from 'lucide-react';
import AdminLayout, { AdminCard, StatCard, useAdminTheme } from '@/components/admin/AdminLayout';
import { admin } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';

interface Book {
  id: string;
  title: string;
  author: string | null;
  processing_status: string;
  processing_progress: number;
  processing_step: string | null;
  total_chapters: number | null;
  created_at: string;
  user_id: string;
  user_email: string;
  user_name: string;
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

export default function BooksAdminPage() {
  const router = useRouter();
  const { token, isAuthenticated, isLoading: authLoading } = useAuth();
  const [analytics, setAnalytics] = useState<BooksAnalytics | null>(null);
  const [books, setBooks] = useState<Book[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login?redirect=/admin/books');
    }
  }, [authLoading, isAuthenticated, router]);

  const fetchData = useCallback(async () => {
    if (!isAuthenticated) return;
    const t = token || '';

    try {
      const [analyticsData, booksData] = await Promise.all([
        admin.getBooksAnalytics(t, 30),
        admin.listBooks(t, page, undefined, statusFilter || undefined),
      ]);
      setAnalytics(analyticsData);
      setBooks(booksData);
      setError(null);
    } catch (err: any) {
      console.error('Failed to fetch books data:', err);
      setError(err.message || 'Failed to load data');
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated, token, page, statusFilter]);

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

  // Filter books by search query
  const filteredBooks = books.filter(book => 
    searchQuery === '' || 
    book.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    book.user_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    book.user_email.toLowerCase().includes(searchQuery.toLowerCase())
  );

  if (isLoading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-12 h-12 text-violet-500 animate-spin" />
          <p className="text-zinc-400 text-sm">Loading books data...</p>
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

  return (
    <AdminLayout
      title="Books Management"
      subtitle="Monitor uploaded books and learning activity"
      onRefresh={handleRefresh}
      isRefreshing={isRefreshing}
    >
      <BooksContent
        analytics={analytics}
        books={filteredBooks}
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        statusFilter={statusFilter}
        setStatusFilter={setStatusFilter}
        page={page}
        setPage={setPage}
        totalBooks={books.length}
      />
    </AdminLayout>
  );
}

function BooksContent({
  analytics,
  books,
  searchQuery,
  setSearchQuery,
  statusFilter,
  setStatusFilter,
  page,
  setPage,
  totalBooks,
}: {
  analytics: BooksAnalytics | null;
  books: Book[];
  searchQuery: string;
  setSearchQuery: (v: string) => void;
  statusFilter: string;
  setStatusFilter: (v: string) => void;
  page: number;
  setPage: (v: number) => void;
  totalBooks: number;
}) {
  const { isDark } = useAdminTheme();

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return isDark 
        ? 'text-emerald-300 bg-emerald-500/20 border-emerald-500/30' 
        : 'text-green-600 bg-green-100 border-green-200';
      case 'processing': return isDark 
        ? 'text-blue-300 bg-blue-500/20 border-blue-500/30' 
        : 'text-blue-600 bg-blue-100 border-blue-200';
      case 'pending': return isDark 
        ? 'text-amber-300 bg-amber-500/20 border-amber-500/30' 
        : 'text-amber-600 bg-amber-100 border-amber-200';
      case 'failed': return isDark 
        ? 'text-red-300 bg-red-500/20 border-red-500/30' 
        : 'text-red-600 bg-red-100 border-red-200';
      default: return isDark 
        ? 'text-zinc-300 bg-zinc-700 border-zinc-600' 
        : 'text-gray-600 bg-gray-100 border-gray-200';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed': return <CheckCircle className="w-4 h-4" />;
      case 'processing': return <Loader2 className="w-4 h-4 animate-spin" />;
      case 'pending': return <Clock className="w-4 h-4" />;
      case 'failed': return <XCircle className="w-4 h-4" />;
      default: return <BookOpen className="w-4 h-4" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard
          title="Total Books"
          value={analytics?.total_books || 0}
          icon={BookOpen}
          iconColor="text-violet-400"
        />
        <StatCard
          title="New This Month"
          value={analytics?.new_books_period || 0}
          icon={TrendingUp}
          iconColor="text-emerald-400"
        />
        <StatCard
          title="Active Learners"
          value={analytics?.learning_stats?.total_active_learners || 0}
          icon={Brain}
          iconColor="text-blue-400"
        />
        <StatCard
          title="Avg Study Time"
          value={`${analytics?.learning_stats?.avg_study_time_minutes?.toFixed(0) || 0} min`}
          icon={Clock}
          iconColor="text-amber-400"
        />
      </div>

      {/* Status Breakdown */}
      <AdminCard className="p-6">
        <h2 className={`text-lg font-semibold mb-4 ${isDark ? 'text-white' : 'text-gray-900'}`}>
          Processing Status
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Object.entries(analytics?.status_breakdown || {}).map(([status, count]) => (
            <div
              key={status}
              className={`flex items-center gap-3 p-4 rounded-lg border ${getStatusColor(status)}`}
            >
              {getStatusIcon(status)}
              <div>
                <div className="text-2xl font-bold">{count}</div>
                <div className="text-sm capitalize opacity-80">{status}</div>
              </div>
            </div>
          ))}
          {Object.keys(analytics?.status_breakdown || {}).length === 0 && (
            <div className={`col-span-4 text-center py-8 ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>
              No books uploaded yet
            </div>
          )}
        </div>
      </AdminCard>

      {/* Books List */}
      <AdminCard className="overflow-hidden">
        <div className={`p-4 border-b ${isDark ? 'border-zinc-800/50' : 'border-gray-200'}`}>
          <div className="flex flex-wrap items-center gap-4">
            <h2 className={`text-lg font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>
              All Books
            </h2>
            
            <div className="flex-1" />
            
            <div className="relative">
              <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${isDark ? 'text-zinc-500' : 'text-gray-400'}`} />
              <input
                type="text"
                placeholder="Search books or users..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className={`rounded-lg pl-10 pr-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500 w-64 ${
                  isDark 
                    ? 'bg-zinc-800/50 border border-zinc-700/50 text-white placeholder-zinc-500' 
                    : 'bg-white border border-gray-200 text-gray-900 placeholder-gray-400'
                }`}
              />
            </div>
            
            <div className="relative">
              <Filter className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${isDark ? 'text-zinc-500' : 'text-gray-400'}`} />
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className={`appearance-none rounded-lg pl-10 pr-10 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500 ${
                  isDark 
                    ? 'bg-zinc-800/50 border border-zinc-700/50 text-white' 
                    : 'bg-white border border-gray-200 text-gray-900'
                }`}
              >
                <option value="">All Status</option>
                <option value="completed">Completed</option>
                <option value="processing">Processing</option>
                <option value="pending">Pending</option>
                <option value="failed">Failed</option>
              </select>
              <ChevronDown className={`absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 pointer-events-none ${isDark ? 'text-zinc-500' : 'text-gray-400'}`} />
            </div>
          </div>
        </div>
        
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className={isDark ? 'bg-zinc-800/30' : 'bg-gray-50'}>
                <th className={`text-left px-6 py-4 text-xs font-medium uppercase tracking-wider ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>Book</th>
                <th className={`text-left px-6 py-4 text-xs font-medium uppercase tracking-wider ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>User</th>
                <th className={`text-left px-6 py-4 text-xs font-medium uppercase tracking-wider ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>Status</th>
                <th className={`text-left px-6 py-4 text-xs font-medium uppercase tracking-wider ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>Chapters</th>
                <th className={`text-left px-6 py-4 text-xs font-medium uppercase tracking-wider ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>Uploaded</th>
              </tr>
            </thead>
            <tbody className={`divide-y ${isDark ? 'divide-zinc-800/50' : 'divide-gray-100'}`}>
              {books.map((book) => (
                <tr key={book.id} className={`transition ${isDark ? 'hover:bg-zinc-800/20' : 'hover:bg-gray-50'}`}>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                        isDark 
                          ? 'bg-gradient-to-br from-violet-500/20 to-fuchsia-600/20 border border-violet-500/30' 
                          : 'bg-violet-100 border border-violet-200'
                      }`}>
                        <BookOpen className={`w-5 h-5 ${isDark ? 'text-violet-400' : 'text-violet-600'}`} />
                      </div>
                      <div>
                        <p className={`font-medium ${isDark ? 'text-white' : 'text-gray-900'}`}>{book.title}</p>
                        {book.author && (
                          <p className={`text-sm ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>by {book.author}</p>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-2">
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ${
                        isDark 
                          ? 'bg-gradient-to-br from-zinc-600 to-zinc-700 text-white' 
                          : 'bg-gray-200 text-gray-700'
                      }`}>
                        {book.user_name.charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <p className={`text-sm font-medium ${isDark ? 'text-white' : 'text-gray-900'}`}>{book.user_name}</p>
                        <p className={`text-xs ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>{book.user_email}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${getStatusColor(book.processing_status)}`}>
                      {getStatusIcon(book.processing_status)}
                      {book.processing_status}
                    </span>
                    {book.processing_status === 'processing' && (
                      <div className="mt-1">
                        <div className={`w-20 h-1 rounded-full overflow-hidden ${isDark ? 'bg-zinc-800' : 'bg-gray-200'}`}>
                          <div 
                            className="h-full bg-blue-500 rounded-full"
                            style={{ width: `${book.processing_progress}%` }}
                          />
                        </div>
                      </div>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    <span className={`text-sm ${isDark ? 'text-zinc-400' : 'text-gray-600'}`}>
                      {book.total_chapters || '-'}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <span className={`text-sm ${isDark ? 'text-zinc-400' : 'text-gray-600'}`}>
                      {new Date(book.created_at).toLocaleDateString()}
                    </span>
                  </td>
                </tr>
              ))}
              
              {books.length === 0 && (
                <tr>
                  <td colSpan={5} className={`px-6 py-12 text-center ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>
                    No books found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        
        {/* Pagination */}
        <div className={`flex items-center justify-between px-6 py-4 border-t ${isDark ? 'border-zinc-800/50' : 'border-gray-200'}`}>
          <p className={`text-sm ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>
            Showing {books.length} books
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(Math.max(1, page - 1))}
              disabled={page === 1}
              className={`px-3 py-1.5 rounded-lg text-sm transition disabled:opacity-50 ${
                isDark 
                  ? 'bg-zinc-800/50 border border-zinc-700/50 hover:bg-zinc-800' 
                  : 'bg-white border border-gray-200 hover:bg-gray-50'
              }`}
            >
              Previous
            </button>
            <span className={`px-3 py-1.5 text-sm ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>Page {page}</span>
            <button
              onClick={() => setPage(page + 1)}
              disabled={totalBooks < 20}
              className={`px-3 py-1.5 rounded-lg text-sm transition disabled:opacity-50 ${
                isDark 
                  ? 'bg-zinc-800/50 border border-zinc-700/50 hover:bg-zinc-800' 
                  : 'bg-white border border-gray-200 hover:bg-gray-50'
              }`}
            >
              Next
            </button>
          </div>
        </div>
      </AdminCard>

      {/* Daily Uploads Chart */}
      <AdminCard className="p-6">
        <h2 className={`text-lg font-semibold mb-4 ${isDark ? 'text-white' : 'text-gray-900'}`}>
          Daily Uploads (Last 30 Days)
        </h2>
        {analytics?.daily_uploads && analytics.daily_uploads.length > 0 ? (
          <div>
            <div className="h-40 flex items-end gap-1 mb-2">
              {analytics.daily_uploads.map((day, i) => {
                const maxCount = Math.max(...analytics.daily_uploads.map(d => d.count), 1);
                const height = (day.count / maxCount) * 100;
                const date = new Date(day.date);
                return (
                  <div
                    key={i}
                    className="flex-1 flex flex-col items-center"
                  >
                    <div
                      className={`w-full rounded-t min-h-[4px] transition-all cursor-pointer group relative ${
                        isDark 
                          ? 'bg-gradient-to-t from-violet-600 to-violet-400 hover:from-violet-500 hover:to-violet-300' 
                          : 'bg-gradient-to-t from-violet-500 to-violet-400 hover:from-violet-400 hover:to-violet-300'
                      }`}
                      style={{ height: `${Math.max(4, height)}%` }}
                    >
                      <div className={`absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 rounded text-xs opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-10 ${
                        isDark ? 'bg-zinc-800 text-white' : 'bg-gray-900 text-white'
                      }`}>
                        {date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}: {day.count} uploads
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
            {/* Date labels */}
            <div className="flex gap-1">
              {analytics.daily_uploads.map((day, i) => {
                const date = new Date(day.date);
                // Show label every 5 days or first/last
                const showLabel = i === 0 || i === analytics.daily_uploads.length - 1 || i % 5 === 0;
                return (
                  <div key={i} className="flex-1 text-center">
                    {showLabel && (
                      <span className={`text-[10px] ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>
                        {date.getDate()}/{date.getMonth() + 1}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <div className={`h-48 flex items-center justify-center ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>
            No upload data available
          </div>
        )}
      </AdminCard>
    </div>
  );
}
