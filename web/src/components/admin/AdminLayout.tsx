'use client';

import { useState, useEffect, createContext, useContext, ReactNode } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { 
  Shield, BarChart3, Users, BookOpen, Activity, Settings,
  RefreshCw, Sun, Moon, LogOut
} from 'lucide-react';

// Theme context
interface ThemeContextType {
  isDark: boolean;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextType>({ isDark: true, toggleTheme: () => {} });

export const useAdminTheme = () => useContext(ThemeContext);

const navItems = [
  { href: '/admin', label: 'Dashboard', icon: BarChart3 },
  { href: '/admin/users', label: 'Users', icon: Users },
  { href: '/admin/books', label: 'Books', icon: BookOpen },
  { href: '/admin/analytics', label: 'Analytics', icon: Activity },
  { href: '/admin/system', label: 'System', icon: Settings },
];

interface AdminLayoutProps {
  children: ReactNode;
  title: string;
  subtitle: string;
  onRefresh?: () => void;
  isRefreshing?: boolean;
  headerActions?: ReactNode;
}

export default function AdminLayout({
  children,
  title,
  subtitle,
  onRefresh,
  isRefreshing = false,
  headerActions,
}: AdminLayoutProps) {
  const pathname = usePathname();
  const [isDark, setIsDark] = useState(true);

  useEffect(() => {
    // Load theme preference from localStorage
    const savedTheme = localStorage.getItem('admin_theme');
    if (savedTheme) {
      setIsDark(savedTheme === 'dark');
    }
  }, []);

  const toggleTheme = () => {
    const newTheme = !isDark;
    setIsDark(newTheme);
    localStorage.setItem('admin_theme', newTheme ? 'dark' : 'light');
  };

  return (
    <ThemeContext.Provider value={{ isDark, toggleTheme }}>
      <div className={`min-h-screen ${isDark ? 'bg-zinc-950 text-zinc-100' : 'bg-gray-50 text-gray-900'}`}>
        {/* Header */}
        <div className={`${isDark ? 'bg-zinc-900/50 border-zinc-800/50' : 'bg-white border-gray-200'} border-b backdrop-blur-xl sticky top-0 z-50`}>
          <div className="max-w-[1600px] mx-auto px-6 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="p-2.5 bg-gradient-to-br from-violet-500 to-fuchsia-600 rounded-xl shadow-lg shadow-violet-500/25">
                  <Shield className="w-6 h-6 text-white" />
                </div>
                <div>
                  <h1 className={`text-xl font-bold ${isDark ? 'bg-gradient-to-r from-white to-zinc-400 bg-clip-text text-transparent' : 'text-gray-900'}`}>
                    {title}
                  </h1>
                  <p className={`text-sm ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>
                    {subtitle}
                  </p>
                </div>
              </div>
              
              <div className="flex items-center gap-3">
                {/* Theme Toggle */}
                <button
                  onClick={toggleTheme}
                  className={`p-2.5 rounded-lg transition ${
                    isDark 
                      ? 'bg-zinc-800/50 border border-zinc-700/50 hover:bg-zinc-800 text-zinc-400 hover:text-white' 
                      : 'bg-gray-100 border border-gray-200 hover:bg-gray-200 text-gray-600 hover:text-gray-900'
                  }`}
                  title={isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
                >
                  {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
                </button>

                {headerActions}
                
                {onRefresh && (
                  <button
                    onClick={onRefresh}
                    disabled={isRefreshing}
                    className={`flex items-center gap-2 px-4 py-2 rounded-lg transition disabled:opacity-50 ${
                      isDark 
                        ? 'bg-zinc-800/50 border border-zinc-700/50 hover:bg-zinc-800' 
                        : 'bg-white border border-gray-200 hover:bg-gray-50'
                    }`}
                  >
                    <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
                    <span className="text-sm">Refresh</span>
                  </button>
                )}
                
                <Link
                  href="/dashboard"
                  className={`flex items-center gap-2 px-4 py-2 text-sm transition ${
                    isDark ? 'text-zinc-400 hover:text-white' : 'text-gray-500 hover:text-gray-900'
                  }`}
                >
                  <LogOut className="w-4 h-4" />
                  Exit Admin
                </Link>
              </div>
            </div>
          </div>
        </div>

        <div className="max-w-[1600px] mx-auto px-6 py-6">
          <div className="flex gap-6">
            {/* Sidebar Navigation */}
            <div className="w-56 flex-shrink-0">
              <nav className="space-y-1 sticky top-24">
                {navItems.map((item) => {
                  const isActive = pathname === item.href;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={`flex items-center gap-3 px-4 py-2.5 rounded-lg transition-all ${
                        isActive
                          ? 'bg-violet-500/20 text-violet-300 border border-violet-500/30'
                          : isDark 
                            ? 'text-zinc-400 hover:text-white hover:bg-zinc-800/50'
                            : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                      }`}
                    >
                      <item.icon className="w-4 h-4" />
                      <span className="text-sm font-medium">{item.label}</span>
                    </Link>
                  );
                })}
              </nav>
            </div>

            {/* Main Content */}
            <div className="flex-1">
              {children}
            </div>
          </div>
        </div>
      </div>
    </ThemeContext.Provider>
  );
}

// Reusable card component for admin pages
interface AdminCardProps {
  children: ReactNode;
  className?: string;
}

export function AdminCard({ children, className = '' }: AdminCardProps) {
  const { isDark } = useAdminTheme();
  return (
    <div className={`${isDark ? 'bg-zinc-900/50 border-zinc-800/50' : 'bg-white border-gray-200'} border rounded-xl ${className}`}>
      {children}
    </div>
  );
}

// Stat card component
interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ElementType;
  iconColor?: string;
  trend?: { value: number; positive: boolean };
}

export function StatCard({ title, value, subtitle, icon: Icon, iconColor = 'text-violet-400', trend }: StatCardProps) {
  const { isDark } = useAdminTheme();
  return (
    <div className={`${isDark ? 'bg-zinc-900/50 border-zinc-800/50' : 'bg-white border-gray-200'} border rounded-xl p-5`}>
      <div className="flex items-center justify-between mb-3">
        <span className={`text-sm ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>{title}</span>
        <Icon className={`w-5 h-5 ${iconColor}`} />
      </div>
      <div className={`text-3xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{value}</div>
      {subtitle && (
        <div className={`text-xs mt-1 ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>{subtitle}</div>
      )}
      {trend && (
        <div className={`text-xs mt-2 ${trend.positive ? 'text-emerald-400' : 'text-red-400'}`}>
          {trend.positive ? '↑' : '↓'} {trend.value}% from last week
        </div>
      )}
    </div>
  );
}
