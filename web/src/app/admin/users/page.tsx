'use client';

import { useState, useEffect, useCallback } from 'react';
import { 
  Users, BookOpen, Search, ChevronDown, Crown, Key,
  Sparkles, Eye, X, Zap, Brain, Loader2, AlertTriangle
} from 'lucide-react';
import AdminLayout, { AdminCard, StatCard, useAdminTheme } from '@/components/admin/AdminLayout';
import { admin } from '@/lib/api';

interface UserWithUsage {
  id: string;
  email: string;
  name: string;
  role: string;
  is_active: boolean;
  created_at: string;
  tier: string;
  preferred_model: string | null;
  books_count: number;
  usage: {
    all_time: {
      requests: number;
      tokens: number;
      platform_cost_cents: number;
      user_cost_cents: number;
    };
    this_month: {
      requests: number;
      tokens: number;
      platform_cost_cents: number;
      user_cost_cents: number;
    };
    subscription: {
      pdfs_used: number;
      messages_used: number;
      quizzes_used: number;
      pdf_limit: number;
      message_limit: number;
      quiz_limit: number;
    } | null;
  };
  last_active: string | null;
}

interface UserDetail {
  user: {
    id: string;
    email: string;
    name: string;
    created_at: string;
  };
  subscription: {
    tier: string;
    preferred_model: string | null;
    pdfs_used: number;
    messages_used: number;
    quizzes_used: number;
  } | null;
  all_time: {
    requests: number;
    tokens: number;
    cost_cents: number;
  };
  recent_logs: Array<{
    id: string;
    type: string;
    model: string;
    tokens: number;
    cost_cents: number;
    paid_by: string;
    created_at: string;
  }>;
}

export default function UsersPage() {
  const [users, setUsers] = useState<UserWithUsage[]>([]);
  const [selectedUser, setSelectedUser] = useState<UserDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [tierFilter, setTierFilter] = useState<string>('');
  const [sortBy, setSortBy] = useState<string>('created_at');
  const [showUserModal, setShowUserModal] = useState(false);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    const token = localStorage.getItem('professor_access_token');
    if (!token) {
      window.location.href = '/login?redirect=/admin/users';
      return;
    }

    try {
      const usersData = await admin.listUsersWithUsage(
        token, 
        page, 
        searchQuery || undefined, 
        tierFilter || undefined,
        sortBy
      );
      setUsers(usersData);
      setError(null);
    } catch (err: any) {
      console.error('Failed to fetch users:', err);
      setError(err.message || 'Failed to load users');
    } finally {
      setIsLoading(false);
    }
  }, [page, searchQuery, tierFilter, sortBy]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await fetchData();
    setIsRefreshing(false);
  };

  const handleViewUser = async (userId: string) => {
    const token = localStorage.getItem('professor_access_token');
    if (!token) return;

    try {
      const detail = await admin.getUserUsageDetail(token, userId);
      setSelectedUser(detail);
      setShowUserModal(true);
    } catch (err) {
      console.error('Failed to fetch user detail:', err);
    }
  };

  const formatCost = (cents: number) => `$${(cents / 100).toFixed(2)}`;

  const formatTokens = (tokens: number) => {
    if (tokens >= 1000000) return `${(tokens / 1000000).toFixed(1)}M`;
    if (tokens >= 1000) return `${(tokens / 1000).toFixed(1)}K`;
    return tokens.toString();
  };

  // Calculate totals
  const totals = users.reduce((acc, user) => ({
    totalUsers: acc.totalUsers + 1,
    totalRequests: acc.totalRequests + user.usage.all_time.requests,
    platformCost: acc.platformCost + user.usage.all_time.platform_cost_cents,
    userCost: acc.userCost + user.usage.all_time.user_cost_cents,
    byokUsers: acc.byokUsers + (user.tier === 'byok' ? 1 : 0),
    freeUsers: acc.freeUsers + (user.tier === 'free' ? 1 : 0),
  }), { totalUsers: 0, totalRequests: 0, platformCost: 0, userCost: 0, byokUsers: 0, freeUsers: 0 });

  if (isLoading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-12 h-12 text-violet-500 animate-spin" />
          <p className="text-zinc-400 text-sm">Loading users...</p>
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
      title="User Management"
      subtitle="Monitor user activity and usage statistics"
      onRefresh={handleRefresh}
      isRefreshing={isRefreshing}
    >
      <UsersContent
        users={users}
        totals={totals}
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        tierFilter={tierFilter}
        setTierFilter={setTierFilter}
        sortBy={sortBy}
        setSortBy={setSortBy}
        page={page}
        setPage={setPage}
        handleViewUser={handleViewUser}
        formatCost={formatCost}
        formatTokens={formatTokens}
        showUserModal={showUserModal}
        setShowUserModal={setShowUserModal}
        selectedUser={selectedUser}
      />
    </AdminLayout>
  );
}

function UsersContent({
  users,
  totals,
  searchQuery,
  setSearchQuery,
  tierFilter,
  setTierFilter,
  sortBy,
  setSortBy,
  page,
  setPage,
  handleViewUser,
  formatCost,
  formatTokens,
  showUserModal,
  setShowUserModal,
  selectedUser,
}: {
  users: UserWithUsage[];
  totals: any;
  searchQuery: string;
  setSearchQuery: (v: string) => void;
  tierFilter: string;
  setTierFilter: (v: string) => void;
  sortBy: string;
  setSortBy: (v: string) => void;
  page: number;
  setPage: (v: number) => void;
  handleViewUser: (id: string) => void;
  formatCost: (cents: number) => string;
  formatTokens: (tokens: number) => string;
  showUserModal: boolean;
  setShowUserModal: (v: boolean) => void;
  selectedUser: UserDetail | null;
}) {
  const { isDark } = useAdminTheme();

  const getTierColor = (tier: string) => {
    switch (tier) {
      case 'byok': return isDark ? 'text-violet-300 bg-violet-500/20' : 'text-violet-600 bg-violet-100';
      case 'pro': return isDark ? 'text-amber-300 bg-amber-500/20' : 'text-amber-600 bg-amber-100';
      default: return isDark ? 'text-zinc-300 bg-zinc-700' : 'text-gray-600 bg-gray-100';
    }
  };

  const getTierIcon = (tier: string) => {
    switch (tier) {
      case 'byok': return <Key className="w-3 h-3" />;
      case 'pro': return <Crown className="w-3 h-3" />;
      default: return <Sparkles className="w-3 h-3" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
        <StatCard
          title="Total Users"
          value={totals.totalUsers}
          subtitle={`${totals.freeUsers} free • ${totals.byokUsers} BYOK`}
          icon={Users}
          iconColor="text-blue-400"
        />
        <StatCard
          title="Total Requests"
          value={totals.totalRequests.toLocaleString()}
          subtitle="All time"
          icon={Zap}
          iconColor="text-amber-400"
        />
        <StatCard
          title="Platform Cost"
          value={formatCost(totals.platformCost)}
          subtitle="You pay"
          icon={Zap}
          iconColor="text-red-400"
        />
        <StatCard
          title="BYOK Cost"
          value={formatCost(totals.userCost)}
          subtitle="Users pay"
          icon={Zap}
          iconColor="text-emerald-400"
        />
        <StatCard
          title="BYOK Users"
          value={totals.byokUsers}
          subtitle={`${totals.totalUsers > 0 ? Math.round((totals.byokUsers / totals.totalUsers) * 100) : 0}% of users`}
          icon={Key}
          iconColor="text-violet-400"
        />
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-4">
        <div className="relative flex-1 min-w-[200px]">
          <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${isDark ? 'text-zinc-500' : 'text-gray-400'}`} />
          <input
            type="text"
            placeholder="Search users..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className={`w-full pl-10 pr-4 py-2.5 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-violet-500 ${
              isDark 
                ? 'bg-zinc-800/50 border border-zinc-700/50 text-white placeholder-zinc-500' 
                : 'bg-white border border-gray-200 text-gray-900 placeholder-gray-400'
            }`}
          />
        </div>
        
        <div className="relative">
          <select
            value={tierFilter}
            onChange={(e) => setTierFilter(e.target.value)}
            className={`appearance-none rounded-lg pl-4 pr-10 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500 ${
              isDark 
                ? 'bg-zinc-800/50 border border-zinc-700/50 text-white' 
                : 'bg-white border border-gray-200 text-gray-900'
            }`}
          >
            <option value="">All Tiers</option>
            <option value="free">Free</option>
            <option value="byok">BYOK</option>
            <option value="pro">Pro</option>
          </select>
          <ChevronDown className={`absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 pointer-events-none ${isDark ? 'text-zinc-500' : 'text-gray-400'}`} />
        </div>
        
        <div className="relative">
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className={`appearance-none rounded-lg pl-4 pr-10 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500 ${
              isDark 
                ? 'bg-zinc-800/50 border border-zinc-700/50 text-white' 
                : 'bg-white border border-gray-200 text-gray-900'
            }`}
          >
            <option value="created_at">Sort by Join Date</option>
            <option value="total_requests">Sort by Usage</option>
            <option value="total_cost">Sort by Cost</option>
            <option value="last_active">Sort by Last Active</option>
          </select>
          <ChevronDown className={`absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 pointer-events-none ${isDark ? 'text-zinc-500' : 'text-gray-400'}`} />
        </div>
      </div>

      {/* Users Table */}
      <AdminCard className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className={isDark ? 'bg-zinc-800/30' : 'bg-gray-50'}>
                <th className={`text-left px-6 py-4 text-xs font-medium uppercase tracking-wider ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>User</th>
                <th className={`text-left px-6 py-4 text-xs font-medium uppercase tracking-wider ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>Tier</th>
                <th className={`text-left px-6 py-4 text-xs font-medium uppercase tracking-wider ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>This Month</th>
                <th className={`text-left px-6 py-4 text-xs font-medium uppercase tracking-wider ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>All Time</th>
                <th className={`text-left px-6 py-4 text-xs font-medium uppercase tracking-wider ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>Cost</th>
                <th className={`text-left px-6 py-4 text-xs font-medium uppercase tracking-wider ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>Last Active</th>
                <th className={`text-right px-6 py-4 text-xs font-medium uppercase tracking-wider ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>Actions</th>
              </tr>
            </thead>
            <tbody className={`divide-y ${isDark ? 'divide-zinc-800/50' : 'divide-gray-100'}`}>
              {users.map((user) => {
                const totalCost = user.tier === 'byok' 
                  ? user.usage.all_time.user_cost_cents 
                  : user.usage.all_time.platform_cost_cents;
                
                return (
                  <tr key={user.id} className={`transition ${isDark ? 'hover:bg-zinc-800/20' : 'hover:bg-gray-50'}`}>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold ${
                          isDark 
                            ? 'bg-gradient-to-br from-violet-500/20 to-fuchsia-600/20 text-violet-300' 
                            : 'bg-violet-100 text-violet-600'
                        }`}>
                          {user.name.charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <p className={`font-medium ${isDark ? 'text-white' : 'text-gray-900'}`}>{user.name}</p>
                          <p className={`text-sm ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>{user.email}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${getTierColor(user.tier)}`}>
                        {getTierIcon(user.tier)}
                        {user.tier.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <div className="space-y-1">
                        <div className={`flex items-center gap-2 text-sm ${isDark ? 'text-white' : 'text-gray-900'}`}>
                          <Zap className="w-3 h-3 text-amber-500" />
                          <span>{user.usage.this_month.requests} requests</span>
                        </div>
                        <div className={`flex items-center gap-2 text-xs ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>
                          <Brain className="w-3 h-3" />
                          <span>{formatTokens(user.usage.this_month.tokens)} tokens</span>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="space-y-1">
                        <div className={`flex items-center gap-2 text-sm ${isDark ? 'text-white' : 'text-gray-900'}`}>
                          <Zap className="w-3 h-3 text-violet-500" />
                          <span>{user.usage.all_time.requests.toLocaleString()} requests</span>
                        </div>
                        <div className={`flex items-center gap-2 text-xs ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>
                          <BookOpen className="w-3 h-3" />
                          <span>{user.books_count} books</span>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="space-y-1">
                        <div className={`text-sm font-medium ${user.tier === 'byok' ? 'text-emerald-400' : 'text-red-400'}`}>
                          {formatCost(totalCost)}
                        </div>
                        <div className={`text-xs ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>
                          {user.tier === 'byok' ? 'User paid' : 'Platform cost'}
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      {user.last_active ? (
                        <div className={`text-sm ${isDark ? 'text-zinc-400' : 'text-gray-600'}`}>
                          {new Date(user.last_active).toLocaleDateString()}
                        </div>
                      ) : (
                        <span className={`text-sm ${isDark ? 'text-zinc-600' : 'text-gray-400'}`}>Never</span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center justify-end">
                        <button
                          onClick={() => handleViewUser(user.id)}
                          className={`p-2 rounded-lg transition ${isDark ? 'hover:bg-zinc-800' : 'hover:bg-gray-100'}`}
                          title="View Details"
                        >
                          <Eye className={`w-4 h-4 ${isDark ? 'text-zinc-400' : 'text-gray-500'}`} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              
              {users.length === 0 && (
                <tr>
                  <td colSpan={7} className={`px-6 py-12 text-center ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>
                    No users found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        
        {/* Pagination */}
        <div className={`flex items-center justify-between px-6 py-4 border-t ${isDark ? 'border-zinc-800/50' : 'border-gray-100'}`}>
          <p className={`text-sm ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>
            Showing {users.length} users
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
              disabled={users.length < 20}
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

      {/* User Detail Modal */}
      {showUserModal && selectedUser && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className={`rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden ${
            isDark ? 'bg-zinc-900 border border-zinc-800' : 'bg-white border border-gray-200'
          }`}>
            <div className={`flex items-center justify-between p-6 border-b ${isDark ? 'border-zinc-800' : 'border-gray-200'}`}>
              <div className="flex items-center gap-3">
                <div className={`w-12 h-12 rounded-full flex items-center justify-center text-lg font-bold ${
                  isDark 
                    ? 'bg-gradient-to-br from-violet-500/20 to-fuchsia-600/20 text-violet-300' 
                    : 'bg-violet-100 text-violet-600'
                }`}>
                  {selectedUser.user.name.charAt(0).toUpperCase()}
                </div>
                <div>
                  <h2 className={`text-lg font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    {selectedUser.user.name}
                  </h2>
                  <p className={`text-sm ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>
                    {selectedUser.user.email}
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowUserModal(false)}
                className={`p-2 rounded-lg transition ${isDark ? 'hover:bg-zinc-800' : 'hover:bg-gray-100'}`}
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="p-6 overflow-y-auto max-h-[calc(90vh-100px)]">
              {/* Stats */}
              <div className="grid grid-cols-3 gap-4 mb-6">
                <div className={`rounded-xl p-4 text-center ${isDark ? 'bg-zinc-800/50' : 'bg-gray-50'}`}>
                  <p className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    {selectedUser.all_time.requests.toLocaleString()}
                  </p>
                  <p className={`text-xs ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>Total Requests</p>
                </div>
                <div className={`rounded-xl p-4 text-center ${isDark ? 'bg-zinc-800/50' : 'bg-gray-50'}`}>
                  <p className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    {formatTokens(selectedUser.all_time.tokens)}
                  </p>
                  <p className={`text-xs ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>Total Tokens</p>
                </div>
                <div className={`rounded-xl p-4 text-center ${isDark ? 'bg-zinc-800/50' : 'bg-gray-50'}`}>
                  <p className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    {formatCost(selectedUser.all_time.cost_cents)}
                  </p>
                  <p className={`text-xs ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>Total Cost</p>
                </div>
              </div>
              
              {/* Recent Activity */}
              <div>
                <h3 className={`text-sm font-medium mb-3 ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>
                  Recent Activity
                </h3>
                <div className="space-y-2">
                  {selectedUser.recent_logs.map((log) => (
                    <div 
                      key={log.id} 
                      className={`flex items-center justify-between p-3 rounded-lg ${
                        isDark ? 'bg-zinc-800/30' : 'bg-gray-50'
                      }`}
                    >
                      <div>
                        <p className={`text-sm font-medium capitalize ${isDark ? 'text-white' : 'text-gray-900'}`}>
                          {log.type.replace(/_/g, ' ')}
                        </p>
                        <p className={`text-xs ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>{log.model}</p>
                      </div>
                      <div className="text-right">
                        <p className={`text-sm ${isDark ? 'text-white' : 'text-gray-900'}`}>
                          {log.tokens.toLocaleString()} tokens
                        </p>
                        <p className={`text-xs ${log.paid_by === 'platform' ? 'text-red-400' : 'text-emerald-400'}`}>
                          {formatCost(log.cost_cents)} ({log.paid_by})
                        </p>
                      </div>
                    </div>
                  ))}
                  
                  {selectedUser.recent_logs.length === 0 && (
                    <p className={`text-center py-8 ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>
                      No activity yet
                    </p>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
