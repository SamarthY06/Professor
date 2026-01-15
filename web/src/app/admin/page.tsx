'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { 
  Users, BookOpen, Activity, BarChart3, Shield, Settings,
  TrendingUp, TrendingDown, Clock, CheckCircle, XCircle,
  AlertTriangle, Search, RefreshCw, ChevronRight
} from 'lucide-react';

interface DashboardStats {
  total_users: number;
  active_users_24h: number;
  total_books: number;
  quizzes_completed_today: number;
  average_quiz_score: number;
  api_latency_p95: number;
  error_rate_24h: number;
}

interface RecentUser {
  id: string;
  name: string;
  email: string;
  last_active: string;
  books_count: number;
  status: 'active' | 'inactive';
}

interface SystemHealth {
  postgres: { status: 'healthy' | 'degraded' | 'down'; latency_ms: number };
  redis: { status: 'healthy' | 'degraded' | 'down'; latency_ms: number };
  temporal: { status: 'healthy' | 'degraded' | 'down'; workflows_pending: number };
}

// Mock data
const mockStats: DashboardStats = {
  total_users: 1247,
  active_users_24h: 342,
  total_books: 856,
  quizzes_completed_today: 127,
  average_quiz_score: 0.78,
  api_latency_p95: 234,
  error_rate_24h: 0.02,
};

const mockRecentUsers: RecentUser[] = [
  { id: '1', name: 'Alice Johnson', email: 'alice@example.com', last_active: '2 min ago', books_count: 3, status: 'active' },
  { id: '2', name: 'Bob Smith', email: 'bob@example.com', last_active: '15 min ago', books_count: 1, status: 'active' },
  { id: '3', name: 'Carol Davis', email: 'carol@example.com', last_active: '1 hour ago', books_count: 5, status: 'active' },
  { id: '4', name: 'David Wilson', email: 'david@example.com', last_active: '3 hours ago', books_count: 2, status: 'inactive' },
  { id: '5', name: 'Eve Brown', email: 'eve@example.com', last_active: '5 hours ago', books_count: 4, status: 'inactive' },
];

const mockHealth: SystemHealth = {
  postgres: { status: 'healthy', latency_ms: 12 },
  redis: { status: 'healthy', latency_ms: 3 },
  temporal: { status: 'healthy', workflows_pending: 5 },
};

export default function AdminDashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentUsers, setRecentUsers] = useState<RecentUser[]>([]);
  const [systemHealth, setSystemHealth] = useState<SystemHealth | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  useEffect(() => {
    // TODO: Fetch from API
    setStats(mockStats);
    setRecentUsers(mockRecentUsers);
    setSystemHealth(mockHealth);
  }, []);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await new Promise((resolve) => setTimeout(resolve, 1000));
    setIsRefreshing(false);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy': return 'text-green-600 bg-green-100';
      case 'degraded': return 'text-yellow-600 bg-yellow-100';
      case 'down': return 'text-red-600 bg-red-100';
      default: return 'text-gray-600 bg-gray-100';
    }
  };

  const navItems = [
    { href: '/admin', label: 'Dashboard', icon: BarChart3, active: true },
    { href: '/admin/users', label: 'Users', icon: Users },
    { href: '/admin/books', label: 'Books', icon: BookOpen },
    { href: '/admin/analytics', label: 'Analytics', icon: Activity },
    { href: '/admin/system', label: 'System', icon: Settings },
  ];

  if (!stats || !systemHealth) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Admin Header */}
      <div className="bg-card border-b">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="p-2 bg-primary/10 rounded-lg">
                <Shield className="w-6 h-6 text-primary" />
              </div>
              <div>
                <h1 className="text-xl font-bold">Admin Dashboard</h1>
                <p className="text-sm text-muted-foreground">
                  Professor System Administration
                </p>
              </div>
            </div>
            
            <div className="flex items-center gap-3">
              <button
                onClick={handleRefresh}
                disabled={isRefreshing}
                className="flex items-center gap-2 px-3 py-2 border rounded-lg hover:bg-muted disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
                Refresh
              </button>
              
              <Link
                href="/dashboard"
                className="px-3 py-2 text-sm text-muted-foreground hover:text-foreground"
              >
                Exit Admin
              </Link>
            </div>
          </div>
          
          {/* Admin Nav */}
          <nav className="flex gap-1 mt-4">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-colors ${
                  item.active
                    ? 'bg-primary/10 text-primary font-medium'
                    : 'text-muted-foreground hover:bg-muted'
                }`}
              >
                <item.icon className="w-4 h-4" />
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
      </div>
      
      {/* Content */}
      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <StatCard
            title="Total Users"
            value={stats.total_users.toLocaleString()}
            subValue={`${stats.active_users_24h} active today`}
            icon={Users}
            trend={{ value: 12, positive: true }}
          />
          <StatCard
            title="Total Books"
            value={stats.total_books.toLocaleString()}
            subValue="Uploaded by users"
            icon={BookOpen}
            trend={{ value: 8, positive: true }}
          />
          <StatCard
            title="Quizzes Today"
            value={stats.quizzes_completed_today.toString()}
            subValue={`${Math.round(stats.average_quiz_score * 100)}% avg score`}
            icon={CheckCircle}
            trend={{ value: 5, positive: true }}
          />
          <StatCard
            title="API Latency (p95)"
            value={`${stats.api_latency_p95}ms`}
            subValue={`${stats.error_rate_24h * 100}% error rate`}
            icon={Activity}
            trend={{ value: stats.api_latency_p95 < 300, positive: stats.api_latency_p95 < 300 }}
            trendLabel={stats.api_latency_p95 < 300 ? 'Good' : 'Needs attention'}
          />
        </div>
        
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* System Health */}
          <div className="bg-card border rounded-xl p-6">
            <h2 className="text-lg font-semibold mb-4">System Health</h2>
            
            <div className="space-y-4">
              {[
                { name: 'PostgreSQL', ...systemHealth.postgres, extra: `${systemHealth.postgres.latency_ms}ms latency` },
                { name: 'Redis', ...systemHealth.redis, extra: `${systemHealth.redis.latency_ms}ms latency` },
                { name: 'Temporal', ...systemHealth.temporal, extra: `${systemHealth.temporal.workflows_pending} pending workflows` },
              ].map((service) => (
                <div key={service.name} className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
                  <div className="flex items-center gap-3">
                    <span className={`w-3 h-3 rounded-full ${
                      service.status === 'healthy' ? 'bg-green-500' :
                      service.status === 'degraded' ? 'bg-yellow-500' : 'bg-red-500'
                    }`} />
                    <div>
                      <div className="font-medium">{service.name}</div>
                      <div className="text-xs text-muted-foreground">{service.extra}</div>
                    </div>
                  </div>
                  <span className={`px-2 py-1 text-xs rounded-full ${getStatusColor(service.status)}`}>
                    {service.status}
                  </span>
                </div>
              ))}
            </div>
            
            <Link
              href="/admin/system"
              className="mt-4 flex items-center justify-center gap-2 text-sm text-primary hover:underline"
            >
              View Details
              <ChevronRight className="w-4 h-4" />
            </Link>
          </div>
          
          {/* Recent Users */}
          <div className="lg:col-span-2 bg-card border rounded-xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Recent Users</h2>
              <Link
                href="/admin/users"
                className="text-sm text-primary hover:underline"
              >
                View All
              </Link>
            </div>
            
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b text-left">
                    <th className="pb-3 font-medium text-muted-foreground">User</th>
                    <th className="pb-3 font-medium text-muted-foreground">Last Active</th>
                    <th className="pb-3 font-medium text-muted-foreground">Books</th>
                    <th className="pb-3 font-medium text-muted-foreground">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {recentUsers.map((user) => (
                    <tr key={user.id} className="border-b last:border-0">
                      <td className="py-3">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 bg-primary/10 rounded-full flex items-center justify-center">
                            <span className="text-sm font-medium text-primary">
                              {user.name.charAt(0)}
                            </span>
                          </div>
                          <div>
                            <div className="font-medium">{user.name}</div>
                            <div className="text-xs text-muted-foreground">{user.email}</div>
                          </div>
                        </div>
                      </td>
                      <td className="py-3 text-muted-foreground">{user.last_active}</td>
                      <td className="py-3">{user.books_count}</td>
                      <td className="py-3">
                        <span className={`px-2 py-1 text-xs rounded-full ${
                          user.status === 'active'
                            ? 'bg-green-100 text-green-700'
                            : 'bg-gray-100 text-gray-700'
                        }`}>
                          {user.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
        
        {/* Quick Actions */}
        <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4">
          <Link
            href="/admin/users"
            className="p-4 bg-card border rounded-xl hover:shadow-md transition-shadow flex items-center gap-4"
          >
            <div className="p-3 bg-blue-100 rounded-lg">
              <Users className="w-6 h-6 text-blue-600" />
            </div>
            <div>
              <div className="font-medium">Manage Users</div>
              <div className="text-sm text-muted-foreground">View and manage user accounts</div>
            </div>
          </Link>
          
          <Link
            href="/admin/analytics"
            className="p-4 bg-card border rounded-xl hover:shadow-md transition-shadow flex items-center gap-4"
          >
            <div className="p-3 bg-purple-100 rounded-lg">
              <BarChart3 className="w-6 h-6 text-purple-600" />
            </div>
            <div>
              <div className="font-medium">View Analytics</div>
              <div className="text-sm text-muted-foreground">Learning metrics and trends</div>
            </div>
          </Link>
          
          <Link
            href="/admin/system"
            className="p-4 bg-card border rounded-xl hover:shadow-md transition-shadow flex items-center gap-4"
          >
            <div className="p-3 bg-orange-100 rounded-lg">
              <Settings className="w-6 h-6 text-orange-600" />
            </div>
            <div>
              <div className="font-medium">System Settings</div>
              <div className="text-sm text-muted-foreground">Feature flags and configuration</div>
            </div>
          </Link>
        </div>
      </div>
    </div>
  );
}

// Stat Card Component
interface StatCardProps {
  title: string;
  value: string;
  subValue: string;
  icon: React.ElementType;
  trend?: { value: number | boolean; positive: boolean };
  trendLabel?: string;
}

function StatCard({ title, value, subValue, icon: Icon, trend, trendLabel }: StatCardProps) {
  return (
    <div className="bg-card border rounded-xl p-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-muted-foreground">{title}</p>
          <p className="text-2xl font-bold mt-1">{value}</p>
          <p className="text-xs text-muted-foreground mt-1">{subValue}</p>
        </div>
        <div className="p-2 bg-muted rounded-lg">
          <Icon className="w-5 h-5 text-muted-foreground" />
        </div>
      </div>
      
      {trend && (
        <div className={`mt-3 flex items-center gap-1 text-xs ${
          trend.positive ? 'text-green-600' : 'text-red-600'
        }`}>
          {trend.positive ? (
            <TrendingUp className="w-3 h-3" />
          ) : (
            <TrendingDown className="w-3 h-3" />
          )}
          {trendLabel || (typeof trend.value === 'number' ? `${trend.value}% from last week` : '')}
        </div>
      )}
    </div>
  );
}
