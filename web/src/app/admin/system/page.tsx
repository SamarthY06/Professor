'use client';

import { useState, useEffect, useCallback } from 'react';
import { 
  Cpu, HardDrive, Wifi, Monitor, Brain, RefreshCw,
  AlertTriangle, CheckCircle, XCircle, Play, Pause,
  ArrowUp, ArrowDown, Loader2
} from 'lucide-react';
import AdminLayout, { AdminCard, useAdminTheme } from '@/components/admin/AdminLayout';
import { admin } from '@/lib/api';

interface ServerMetrics {
  timestamp: string;
  system_info: {
    hostname: string;
    platform: string;
    platform_release: string;
    platform_version: string;
    architecture: string;
    processor: string;
    python_version: string;
    boot_time: string;
    uptime_seconds: number;
    uptime_formatted: string;
    is_containerized?: boolean;
    container_type?: string | null;
  };
  cpu: {
    usage_percent: number;
    core_count: number;
    logical_count: number;
    frequency_mhz: number | null;
    per_core_usage: number[];
    load_average_1m: number | null;
    load_average_5m: number | null;
    load_average_15m: number | null;
  };
  memory: {
    total_gb: number;
    available_gb: number;
    used_gb: number;
    usage_percent: number;
    swap_total_gb: number;
    swap_used_gb: number;
    swap_percent: number;
  };
  disk: {
    total_gb: number;
    used_gb: number;
    free_gb: number;
    usage_percent: number;
    read_bytes_per_sec: number;
    write_bytes_per_sec: number;
    partitions: Array<{
      device: string;
      mountpoint: string;
      fstype: string;
      total_gb: number;
      used_gb: number;
      percent: number;
    }>;
  };
  network: {
    bytes_sent_per_sec: number;
    bytes_recv_per_sec: number;
    packets_sent_per_sec: number;
    packets_recv_per_sec: number;
    connections_count: number;
    interfaces: Array<{
      name: string;
      is_up: boolean;
      addresses: Array<{ type: string; address: string }>;
    }>;
  };
  processes: {
    total_processes: number;
    running_processes: number;
    sleeping_processes: number;
    top_cpu_processes: Array<{
      pid: number;
      name: string;
      cpu_percent: number;
      memory_percent: number;
    }>;
    top_memory_processes: Array<{
      pid: number;
      name: string;
      cpu_percent: number;
      memory_percent: number;
    }>;
  };
  health_status: string;
  health_issues: string[];
  environment_note?: string | null;
}

interface ModelPricing {
  id: string;
  model_name: string;
  display_name: string;
  input_price_per_million: number;
  output_price_per_million: number;
  cached_input_price_per_million: number | null;
  is_available: boolean;
  supports_batch: boolean;
  available_for_free: boolean;
  available_for_byok: boolean;
  description: string | null;
}

export default function SystemPage() {
  const [metrics, setMetrics] = useState<ServerMetrics | null>(null);
  const [modelPricing, setModelPricing] = useState<ModelPricing[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [syncingPricing, setSyncingPricing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    const token = localStorage.getItem('professor_access_token');
    if (!token) {
      window.location.href = '/login?redirect=/admin/system';
      return;
    }

    try {
      const [metricsData, pricingData] = await Promise.all([
        admin.getDetailedServerMetrics(token),
        admin.listModelPricing(token),
      ]);

      setMetrics(metricsData);
      setModelPricing(pricingData);
      setError(null);
    } catch (err: any) {
      console.error('Failed to fetch system data:', err);
      setError(err.message || 'Failed to load system data');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Auto-refresh every 5 seconds
  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(() => {
      fetchData();
    }, 5000);

    return () => clearInterval(interval);
  }, [autoRefresh, fetchData]);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await fetchData();
    setIsRefreshing(false);
  };

  const handleSyncPricing = async () => {
    const token = localStorage.getItem('professor_access_token');
    if (!token) return;

    setSyncingPricing(true);
    try {
      const result = await admin.triggerPricingSync(token);
      console.log('Pricing sync result:', result);
      await fetchData();
    } catch (err) {
      console.error('Failed to sync pricing:', err);
    } finally {
      setSyncingPricing(false);
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-12 h-12 text-violet-500 animate-spin" />
          <p className="text-zinc-400 text-sm">Loading system metrics...</p>
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

  const autoRefreshButton = (
    <button
      onClick={() => setAutoRefresh(!autoRefresh)}
      className={`flex items-center gap-2 px-4 py-2 rounded-lg border transition ${
        autoRefresh 
          ? 'bg-emerald-500/20 border-emerald-500/30 text-emerald-300' 
          : 'bg-zinc-800/50 border-zinc-700/50 text-zinc-400'
      }`}
    >
      {autoRefresh ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
      <span className="text-sm">Auto-refresh</span>
    </button>
  );

  return (
    <AdminLayout
      title="System Monitoring"
      subtitle="Real-time server metrics & configuration"
      headerActions={autoRefreshButton}
    >
      <SystemContent
        metrics={metrics}
        modelPricing={modelPricing}
        syncingPricing={syncingPricing}
        handleSyncPricing={handleSyncPricing}
      />
    </AdminLayout>
  );
}

function SystemContent({
  metrics,
  modelPricing,
  syncingPricing,
  handleSyncPricing,
}: {
  metrics: ServerMetrics | null;
  modelPricing: ModelPricing[];
  syncingPricing: boolean;
  handleSyncPricing: () => void;
}) {
  const { isDark } = useAdminTheme();

  const getHealthColor = (status: string) => {
    switch (status) {
      case 'healthy': return isDark 
        ? 'text-emerald-300 bg-emerald-500/20 border-emerald-500/30' 
        : 'text-green-600 bg-green-100 border-green-200';
      case 'warning': return isDark 
        ? 'text-amber-300 bg-amber-500/20 border-amber-500/30' 
        : 'text-amber-600 bg-amber-100 border-amber-200';
      case 'critical': return isDark 
        ? 'text-red-300 bg-red-500/20 border-red-500/30' 
        : 'text-red-600 bg-red-100 border-red-200';
      default: return isDark 
        ? 'text-zinc-300 bg-zinc-700 border-zinc-600' 
        : 'text-gray-600 bg-gray-100 border-gray-200';
    }
  };

  const getUsageColor = (percent: number) => {
    if (percent >= 90) return 'bg-red-500';
    if (percent >= 70) return 'bg-amber-500';
    return 'bg-emerald-500';
  };

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes.toFixed(0)} B/s`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB/s`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB/s`;
  };

  return (
    <div className="space-y-6">
      {/* Health Status Banner */}
      {metrics && (
        <div className={`p-4 rounded-xl border ${getHealthColor(metrics.health_status)}`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {metrics.health_status === 'healthy' ? (
                <CheckCircle className="w-6 h-6" />
              ) : metrics.health_status === 'warning' ? (
                <AlertTriangle className="w-6 h-6" />
              ) : (
                <XCircle className="w-6 h-6" />
              )}
              <div>
                <p className="font-semibold capitalize">{metrics.health_status} Status</p>
                {metrics.health_issues.length > 0 && (
                  <p className="text-sm opacity-80">{metrics.health_issues.join(' • ')}</p>
                )}
              </div>
            </div>
            <div className="text-right">
              <p className="text-sm font-medium">{metrics.system_info.hostname}</p>
              <p className="text-xs opacity-70">Uptime: {metrics.system_info.uptime_formatted}</p>
            </div>
          </div>
        </div>
      )}

      {/* Environment Note Banner */}
      {metrics?.environment_note && (
        <div className={`p-4 rounded-xl border ${isDark ? 'bg-blue-500/10 border-blue-500/30 text-blue-300' : 'bg-blue-50 border-blue-200 text-blue-700'}`}>
          <div className="flex items-start gap-3">
            <Monitor className="w-5 h-5 mt-0.5 flex-shrink-0" />
            <div>
              <p className="font-medium text-sm">
                {metrics.system_info.is_containerized 
                  ? `Running in ${metrics.system_info.container_type || 'Container'}` 
                  : 'Environment Note'}
              </p>
              <p className="text-xs opacity-80 mt-1">{metrics.environment_note}</p>
            </div>
          </div>
        </div>
      )}

      {/* Resource Usage Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* CPU */}
        <AdminCard className="p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Cpu className="w-5 h-5 text-blue-400" />
              <span className={`font-medium ${isDark ? 'text-white' : 'text-gray-900'}`}>CPU</span>
            </div>
            <span className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
              {metrics?.cpu.usage_percent.toFixed(1)}%
            </span>
          </div>
          <div className={`h-2 rounded-full overflow-hidden mb-3 ${isDark ? 'bg-zinc-800' : 'bg-gray-200'}`}>
            <div 
              className={`h-full rounded-full transition-all ${getUsageColor(metrics?.cpu.usage_percent || 0)}`}
              style={{ width: `${metrics?.cpu.usage_percent || 0}%` }}
            />
          </div>
          <div className={`text-xs ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>
            {metrics?.cpu.core_count} cores • {metrics?.cpu.logical_count} threads
          </div>
        </AdminCard>

        {/* Memory */}
        <AdminCard className="p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Monitor className="w-5 h-5 text-violet-400" />
              <span className={`font-medium ${isDark ? 'text-white' : 'text-gray-900'}`}>Memory</span>
            </div>
            <span className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
              {metrics?.memory.usage_percent.toFixed(1)}%
            </span>
          </div>
          <div className={`h-2 rounded-full overflow-hidden mb-3 ${isDark ? 'bg-zinc-800' : 'bg-gray-200'}`}>
            <div 
              className={`h-full rounded-full transition-all ${getUsageColor(metrics?.memory.usage_percent || 0)}`}
              style={{ width: `${metrics?.memory.usage_percent || 0}%` }}
            />
          </div>
          <div className={`text-xs ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>
            {metrics?.memory.used_gb.toFixed(1)} / {metrics?.memory.total_gb.toFixed(1)} GB
          </div>
        </AdminCard>

        {/* Disk */}
        <AdminCard className="p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <HardDrive className="w-5 h-5 text-amber-400" />
              <span className={`font-medium ${isDark ? 'text-white' : 'text-gray-900'}`}>Disk</span>
            </div>
            <span className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
              {metrics?.disk.usage_percent.toFixed(1)}%
            </span>
          </div>
          <div className={`h-2 rounded-full overflow-hidden mb-3 ${isDark ? 'bg-zinc-800' : 'bg-gray-200'}`}>
            <div 
              className={`h-full rounded-full transition-all ${getUsageColor(metrics?.disk.usage_percent || 0)}`}
              style={{ width: `${metrics?.disk.usage_percent || 0}%` }}
            />
          </div>
          <div className={`text-xs ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>
            {metrics?.disk.used_gb.toFixed(1)} / {metrics?.disk.total_gb.toFixed(1)} GB
          </div>
        </AdminCard>

        {/* Network */}
        <AdminCard className="p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Wifi className="w-5 h-5 text-emerald-400" />
              <span className={`font-medium ${isDark ? 'text-white' : 'text-gray-900'}`}>Network</span>
            </div>
            <span className={`text-sm font-medium ${isDark ? 'text-white' : 'text-gray-900'}`}>
              {metrics?.network.connections_count} conn
            </span>
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className={`flex items-center gap-1 ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>
                <ArrowUp className="w-3 h-3" /> Upload
              </span>
              <span className={isDark ? 'text-white' : 'text-gray-900'}>
                {formatBytes(metrics?.network.bytes_sent_per_sec || 0)}
              </span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className={`flex items-center gap-1 ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>
                <ArrowDown className="w-3 h-3" /> Download
              </span>
              <span className={isDark ? 'text-white' : 'text-gray-900'}>
                {formatBytes(metrics?.network.bytes_recv_per_sec || 0)}
              </span>
            </div>
          </div>
        </AdminCard>
      </div>

      {/* Model Pricing */}
      <AdminCard className="p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className={`text-lg font-semibold flex items-center gap-2 ${isDark ? 'text-white' : 'text-gray-900'}`}>
            <Brain className="w-5 h-5 text-violet-400" />
            Model Pricing
          </h2>
          <button
            onClick={handleSyncPricing}
            disabled={syncingPricing}
            className="flex items-center gap-2 px-4 py-2 bg-violet-600 text-white rounded-lg hover:bg-violet-700 disabled:opacity-50 transition"
          >
            <RefreshCw className={`w-4 h-4 ${syncingPricing ? 'animate-spin' : ''}`} />
            Sync with OpenAI
          </button>
        </div>
        
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className={`border-b text-left ${isDark ? 'border-zinc-800' : 'border-gray-200'}`}>
                <th className={`pb-3 font-medium ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>Model</th>
                <th className={`pb-3 font-medium text-right ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>Input $/1M</th>
                <th className={`pb-3 font-medium text-right ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>Output $/1M</th>
                <th className={`pb-3 font-medium text-right ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>Cached $/1M</th>
                <th className={`pb-3 font-medium text-center ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>Batch</th>
                <th className={`pb-3 font-medium text-center ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>Free Tier</th>
                <th className={`pb-3 font-medium text-center ${isDark ? 'text-zinc-400' : 'text-gray-500'}`}>Status</th>
              </tr>
            </thead>
            <tbody className={`divide-y ${isDark ? 'divide-zinc-800/50' : 'divide-gray-100'}`}>
              {modelPricing.map((model) => (
                <tr key={model.id} className={`transition ${isDark ? 'hover:bg-zinc-800/20' : 'hover:bg-gray-50'}`}>
                  <td className="py-3">
                    <div>
                      <p className={`font-medium ${isDark ? 'text-white' : 'text-gray-900'}`}>
                        {model.display_name}
                      </p>
                      <p className={`text-xs ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>
                        {model.model_name}
                      </p>
                    </div>
                  </td>
                  <td className={`py-3 text-right font-mono ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    ${(model.input_price_per_million / 100).toFixed(3)}
                  </td>
                  <td className={`py-3 text-right font-mono ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    ${(model.output_price_per_million / 100).toFixed(3)}
                  </td>
                  <td className={`py-3 text-right font-mono ${isDark ? 'text-zinc-500' : 'text-gray-500'}`}>
                    {model.cached_input_price_per_million 
                      ? `$${(model.cached_input_price_per_million / 100).toFixed(3)}`
                      : '-'
                    }
                  </td>
                  <td className="py-3 text-center">
                    {model.supports_batch ? (
                      <CheckCircle className="w-4 h-4 text-emerald-400 mx-auto" />
                    ) : (
                      <XCircle className={`w-4 h-4 mx-auto ${isDark ? 'text-zinc-600' : 'text-gray-400'}`} />
                    )}
                  </td>
                  <td className="py-3 text-center">
                    {model.available_for_free ? (
                      <CheckCircle className="w-4 h-4 text-emerald-400 mx-auto" />
                    ) : (
                      <XCircle className={`w-4 h-4 mx-auto ${isDark ? 'text-zinc-600' : 'text-gray-400'}`} />
                    )}
                  </td>
                  <td className="py-3 text-center">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                      model.is_available 
                        ? isDark ? 'bg-emerald-500/20 text-emerald-300' : 'bg-green-100 text-green-700'
                        : isDark ? 'bg-red-500/20 text-red-300' : 'bg-red-100 text-red-700'
                    }`}>
                      {model.is_available ? 'Active' : 'Disabled'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </AdminCard>
    </div>
  );
}
