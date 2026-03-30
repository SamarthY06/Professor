'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { 
  ArrowLeft, User, Key, Bell, BookOpen, Shield, Phone,
  Check, AlertCircle, Eye, EyeOff, Save, Trash2, Loader2
} from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import api from '@/lib/api';

interface UserProfile {
  id: string;
  email: string;
  name: string;
  phone: string | null;
  role: string;
  is_active: boolean;
  created_at: string;
}

interface UserSettings {
  professor_style: 'strict' | 'balanced' | 'encouraging';
  notification_preferences: {
    email: boolean;
    whatsapp: boolean;
  };
  timezone: string;
  study_schedule: {
    preferred_time: string;
    daily_goal_minutes: number;
  } | null;
}

interface ApiKeyStatus {
  has_key: boolean;
  is_valid: boolean;
  last_validated: string | null;
  masked_key: string | null;
  using_default: boolean;
}

interface UsageSummary {
  tier: string;
  cost_cents: number;
  total_requests: number;
  tokens: { input: number; output: number; total: number };
  preferred_model: string | null;
}

export default function SettingsPage() {
  const router = useRouter();
  const { token, isLoading: authLoading, isAuthenticated, refreshUser } = useAuth();
  const [activeTab, setActiveTab] = useState<'profile' | 'api' | 'notifications' | 'learning' | 'privacy'>('profile');
  const [isLoading, setIsLoading] = useState(true);
  
  // Profile state
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [profileName, setProfileName] = useState('');
  const [profilePhone, setProfilePhone] = useState('');
  
  // API Key state
  const [apiKeyStatus, setApiKeyStatus] = useState<ApiKeyStatus | null>(null);
  const [newApiKey, setNewApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [isValidatingKey, setIsValidatingKey] = useState(false);
  
  // BYOK Usage state
  const [usageSummary, setUsageSummary] = useState<UsageSummary | null>(null);
  
  // Settings state
  const [settings, setSettings] = useState<UserSettings>({
    professor_style: 'balanced',
    notification_preferences: {
      email: true,
      whatsapp: true,
    },
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    study_schedule: {
      preferred_time: 'morning',
      daily_goal_minutes: 30,
    },
  });
  
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Redirect if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  // Fetch data
  useEffect(() => {
    const fetchData = async () => {
      if (!isAuthenticated) return;
      
      setIsLoading(true);
      try {
        const t = token || '';
        const [profileData, settingsData, apiKeyData, usageData] = await Promise.all([
          api.users.getProfile(t),
          api.users.getSettings(t),
          api.users.getApiKeyStatus(t),
          api.usage.getSummary(t).catch(() => null),
        ]);
        
        setProfile(profileData);
        setProfileName(profileData.name);
        setProfilePhone(profileData.phone || '');
        
        setSettings({
          professor_style: settingsData.professor_style as any || 'balanced',
          notification_preferences: settingsData.notification_preferences as any || { email: true, whatsapp: true },
          timezone: settingsData.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone,
          study_schedule: settingsData.study_schedule as any || { preferred_time: 'morning', daily_goal_minutes: 30 },
        });
        
        setApiKeyStatus(apiKeyData);
        
        if (usageData) {
          setUsageSummary({
            tier: usageData.tier,
            cost_cents: usageData.cost_cents,
            total_requests: usageData.total_requests,
            tokens: usageData.tokens,
            preferred_model: usageData.preferred_model,
          });
        }
      } catch (err) {
        console.error('Failed to fetch settings:', err);
      } finally {
        setIsLoading(false);
      }
    };

    if (isAuthenticated) {
      fetchData();
    }
  }, [isAuthenticated, token]);

  const handleSaveProfile = async () => {
    if (!isAuthenticated) return;
    
    setIsSaving(true);
    try {
      await api.users.updateProfile(token || '', {
        name: profileName,
        phone: profilePhone || undefined,
      });
      
      setSaveMessage({ type: 'success', text: 'Profile saved successfully!' });
      refreshUser();
    } catch (err: any) {
      setSaveMessage({ type: 'error', text: err.message || 'Failed to save profile' });
    } finally {
      setIsSaving(false);
      setTimeout(() => setSaveMessage(null), 3000);
    }
  };

  const handleSaveSettings = async () => {
    if (!isAuthenticated) return;
    
    setIsSaving(true);
    try {
      await api.users.updateSettings(token || '', settings as unknown as Record<string, unknown>);
      setSaveMessage({ type: 'success', text: 'Settings saved successfully!' });
    } catch (err: any) {
      setSaveMessage({ type: 'error', text: err.message || 'Failed to save settings' });
    } finally {
      setIsSaving(false);
      setTimeout(() => setSaveMessage(null), 3000);
    }
  };

  const handleValidateApiKey = async () => {
    if (!newApiKey || !isAuthenticated) return;
    
    setIsValidatingKey(true);
    try {
      await api.users.saveApiKey(token || '', newApiKey, true);
      
      // Refresh API key status
      const apiKeyData = await api.users.getApiKeyStatus(token || '');
      setApiKeyStatus(apiKeyData);
      setNewApiKey('');
      setSaveMessage({ type: 'success', text: 'API key validated and saved!' });
    } catch (err: any) {
      setSaveMessage({ type: 'error', text: err.message || 'Invalid API key' });
    } finally {
      setIsValidatingKey(false);
      setTimeout(() => setSaveMessage(null), 3000);
    }
  };

  const handleDeleteApiKey = async () => {
    if (!confirm('Are you sure you want to delete your API key?') || !isAuthenticated) return;
    
    try {
      await api.users.deleteApiKey(token || '');
      
      setApiKeyStatus({
        has_key: false,
        is_valid: false,
        last_validated: null,
        masked_key: null,
        using_default: true,
      });
      
      setSaveMessage({ type: 'success', text: 'API key deleted.' });
    } catch (err: any) {
      setSaveMessage({ type: 'error', text: err.message || 'Failed to delete API key' });
    }
    setTimeout(() => setSaveMessage(null), 3000);
  };

  const tabs = [
    { id: 'profile', label: 'Profile', icon: User },
    { id: 'api', label: 'API Key', icon: Key },
    { id: 'notifications', label: 'Notifications', icon: Bell },
    { id: 'privacy', label: 'Privacy', icon: Shield },
  ] as const;

  if (authLoading || !isAuthenticated) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <div className="bg-white dark:bg-gray-800 border-b dark:border-gray-700">
        <div className="max-w-4xl mx-auto px-4 py-4">
          <div className="flex items-center gap-4">
            <Link 
              href="/dashboard"
              className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg text-gray-900 dark:text-gray-100"
            >
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div>
              <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">Settings</h1>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Manage your account and preferences
              </p>
            </div>
          </div>
        </div>
      </div>
      
      {/* Content */}
      <div className="max-w-4xl mx-auto px-4 py-6">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
          </div>
        ) : (
          <div className="flex gap-6">
            {/* Sidebar */}
            <div className="w-48 flex-shrink-0">
              <nav className="space-y-1">
                {tabs.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-colors ${
                      activeTab === tab.id
                        ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400'
                        : 'hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300'
                    }`}
                  >
                    <tab.icon className="w-4 h-4" />
                    {tab.label}
                  </button>
                ))}
              </nav>
            </div>
            
            {/* Main Content */}
            <div className="flex-1">
              {/* Save Message */}
              {saveMessage && (
                <div className={`mb-4 p-3 rounded-lg flex items-center gap-2 ${
                  saveMessage.type === 'success' 
                    ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-800'
                    : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-800'
                }`}>
                  {saveMessage.type === 'success' ? (
                    <Check className="w-4 h-4" />
                  ) : (
                    <AlertCircle className="w-4 h-4" />
                  )}
                  {saveMessage.text}
                </div>
              )}
              
              {/* Profile Tab */}
              {activeTab === 'profile' && (
                <div className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-xl p-6">
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Profile Information</h2>
                  
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">Name</label>
                      <input
                        type="text"
                        value={profileName}
                        onChange={(e) => setProfileName(e.target.value)}
                        className="w-full px-3 py-2 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-100 dark:focus:ring-blue-900/50 focus:border-blue-300 dark:focus:border-blue-500"
                      />
                    </div>
                    
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">Email</label>
                      <input
                        type="email"
                        value={profile?.email || ''}
                        disabled
                        className="w-full px-3 py-2 border dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-400 cursor-not-allowed"
                      />
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        Email is managed through your account
                      </p>
                    </div>
                    
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                        <span className="flex items-center gap-2">
                          <Phone className="w-4 h-4" />
                          Phone Number (for WhatsApp reminders)
                        </span>
                      </label>
                      <input
                        type="tel"
                        value={profilePhone}
                        onChange={(e) => setProfilePhone(e.target.value)}
                        placeholder="+1 234 567 8900"
                        className="w-full px-3 py-2 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-100 dark:focus:ring-blue-900/50 focus:border-blue-300 dark:focus:border-blue-500"
                      />
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        Used for WhatsApp study reminders. Include country code.
                      </p>
                    </div>
                    
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">Timezone</label>
                      <select
                        value={settings.timezone}
                        onChange={(e) => setSettings({ ...settings, timezone: e.target.value })}
                        className="w-full px-3 py-2 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-100 dark:focus:ring-blue-900/50 focus:border-blue-300 dark:focus:border-blue-500"
                      >
                        <option value="America/New_York">Eastern Time (ET)</option>
                        <option value="America/Chicago">Central Time (CT)</option>
                        <option value="America/Denver">Mountain Time (MT)</option>
                        <option value="America/Los_Angeles">Pacific Time (PT)</option>
                        <option value="UTC">UTC</option>
                        <option value="Europe/London">London (GMT)</option>
                        <option value="Asia/Kolkata">India (IST)</option>
                        <option value="Asia/Tokyo">Tokyo (JST)</option>
                      </select>
                    </div>
                    
                    <div className="pt-4">
                      <button
                        onClick={handleSaveProfile}
                        disabled={isSaving}
                        className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                      >
                        {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                        Save Profile
                      </button>
                    </div>
                  </div>
                </div>
              )}
              
              {/* API Key Tab */}
              {activeTab === 'api' && (
                <div className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-xl p-6">
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">OpenAI API Key</h2>
                  
                  <p className="text-gray-600 dark:text-gray-300 mb-4">
                    Professor uses OpenAI's GPT-4o model for personalized teaching. 
                    You can use your own API key or use the default one.
                  </p>
                  
                  {/* BYOK Usage Summary */}
                  {usageSummary?.tier === 'byok' && (
                    <div className="mb-6 p-4 bg-gradient-to-r from-emerald-50 to-teal-50 dark:from-emerald-900/20 dark:to-teal-900/20 border border-emerald-200 dark:border-emerald-800 rounded-xl">
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                          <div className="p-2 bg-emerald-100 dark:bg-emerald-900/40 rounded-lg">
                            <Key className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                          </div>
                          <span className="font-semibold text-emerald-800 dark:text-emerald-300">BYOK Active</span>
                        </div>
                        <Link
                          href="/usage"
                          className="text-sm text-emerald-600 dark:text-emerald-400 hover:text-emerald-700 dark:hover:text-emerald-300 font-medium flex items-center gap-1"
                        >
                          View Dashboard
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                          </svg>
                        </Link>
                      </div>
                      
                      <div className="grid grid-cols-3 gap-4">
                        <div>
                          <div className="text-2xl font-bold text-emerald-700 dark:text-emerald-400">
                            ${(usageSummary.cost_cents / 100).toFixed(2)}
                          </div>
                          <div className="text-xs text-emerald-600 dark:text-emerald-500">This Month</div>
                        </div>
                        <div>
                          <div className="text-2xl font-bold text-emerald-700 dark:text-emerald-400">
                            {usageSummary.total_requests.toLocaleString()}
                          </div>
                          <div className="text-xs text-emerald-600 dark:text-emerald-500">Requests</div>
                        </div>
                        <div>
                          <div className="text-2xl font-bold text-emerald-700 dark:text-emerald-400">
                            {(usageSummary.tokens.total / 1000).toFixed(1)}K
                          </div>
                          <div className="text-xs text-emerald-600 dark:text-emerald-500">Tokens</div>
                        </div>
                      </div>
                      
                      {usageSummary.preferred_model && (
                        <div className="mt-3 pt-3 border-t border-emerald-200 dark:border-emerald-800">
                          <span className="text-sm text-emerald-600 dark:text-emerald-400">
                            Current Model: <span className="font-medium">{usageSummary.preferred_model}</span>
                          </span>
                        </div>
                      )}
                    </div>
                  )}
                  
                  {/* Current Key Status */}
                  <div className={`p-4 rounded-lg mb-4 ${
                    apiKeyStatus?.has_key
                      ? apiKeyStatus.is_valid
                        ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
                        : 'bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800'
                      : 'bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700'
                  }`}>
                    <div className="flex items-center gap-2">
                      {apiKeyStatus?.has_key ? (
                        apiKeyStatus.is_valid ? (
                          <>
                            <Check className="w-5 h-5 text-green-600 dark:text-green-400" />
                            <span className="font-medium text-green-700 dark:text-green-400">Your API key is active</span>
                          </>
                        ) : (
                          <>
                            <AlertCircle className="w-5 h-5 text-yellow-600 dark:text-yellow-400" />
                            <span className="font-medium text-yellow-700 dark:text-yellow-400">API key needs validation</span>
                          </>
                        )
                      ) : (
                        <>
                          <AlertCircle className="w-5 h-5 text-gray-500 dark:text-gray-400" />
                          <span className="font-medium text-gray-700 dark:text-gray-200">Using default API key</span>
                        </>
                      )}
                    </div>
                    
                    {apiKeyStatus?.masked_key && (
                      <p className="text-sm text-gray-600 dark:text-gray-300 mt-1">
                        Key: {apiKeyStatus.masked_key}
                      </p>
                    )}
                    
                    {apiKeyStatus?.last_validated && (
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        Last validated: {new Date(apiKeyStatus.last_validated).toLocaleString()}
                      </p>
                    )}
                  </div>
                  
                  {/* Add/Update Key */}
                  <div className="space-y-3">
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-200">
                      {apiKeyStatus?.has_key ? 'Update API Key' : 'Add Your Own API Key'}
                    </label>
                    
                    <div className="flex gap-2">
                      <div className="flex-1 relative">
                        <input
                          type={showApiKey ? 'text' : 'password'}
                          value={newApiKey}
                          onChange={(e) => setNewApiKey(e.target.value)}
                          placeholder="sk-..."
                          className="w-full px-3 py-2 pr-10 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-100 dark:focus:ring-blue-900/50 focus:border-blue-300 dark:focus:border-blue-500"
                        />
                        <button
                          onClick={() => setShowApiKey(!showApiKey)}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
                        >
                          {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                        </button>
                      </div>
                      
                      <button
                        onClick={handleValidateApiKey}
                        disabled={!newApiKey || isValidatingKey}
                        className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {isValidatingKey ? 'Validating...' : 'Validate & Save'}
                      </button>
                    </div>
                    
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      Get your API key from{' '}
                      <a 
                        href="https://platform.openai.com/api-keys" 
                        target="_blank" 
                        rel="noopener noreferrer"
                        className="text-blue-600 hover:underline"
                      >
                        OpenAI's dashboard
                      </a>
                    </p>
                  </div>
                  
                  {/* Delete Key */}
                  {apiKeyStatus?.has_key && (
                    <div className="mt-6 pt-6 border-t dark:border-gray-700">
                      <button
                        onClick={handleDeleteApiKey}
                        className="flex items-center gap-2 text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300"
                      >
                        <Trash2 className="w-4 h-4" />
                        Delete API Key (use default)
                      </button>
                    </div>
                  )}
                </div>
              )}
              
              {/* Notifications Tab */}
              {activeTab === 'notifications' && (
                <div className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-xl p-6">
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Notification Preferences</h2>
                  
                  <div className="space-y-4">
                    {[
                      { key: 'email', label: 'Email Notifications', desc: 'Receive updates via email' },
                      { key: 'whatsapp', label: 'WhatsApp Reminders', desc: 'Get study reminders on WhatsApp (requires phone number)' },
                    ].map((item) => (
                      <div key={item.key} className="flex items-center justify-between p-4 border dark:border-gray-700 rounded-lg">
                        <div>
                          <div className="font-medium text-gray-900 dark:text-gray-100">{item.label}</div>
                          <div className="text-sm text-gray-500 dark:text-gray-400">{item.desc}</div>
                        </div>
                        <label className="relative inline-flex items-center cursor-pointer">
                          <input
                            type="checkbox"
                            checked={settings.notification_preferences[item.key as keyof typeof settings.notification_preferences]}
                            onChange={(e) => setSettings({
                              ...settings,
                              notification_preferences: {
                                ...settings.notification_preferences,
                                [item.key]: e.target.checked,
                              },
                            })}
                            className="sr-only peer"
                          />
                          <div className="w-11 h-6 bg-gray-200 dark:bg-gray-600 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-100 dark:peer-focus:ring-blue-900/50 rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white dark:after:bg-gray-300 after:border-gray-300 dark:after:border-gray-600 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                        </label>
                      </div>
                    ))}
                  </div>
                  
                  <div className="mt-6 pt-4">
                    <button
                      onClick={handleSaveSettings}
                      disabled={isSaving}
                      className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                    >
                      {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                      Save Settings
                    </button>
                  </div>
                </div>
              )}
              
              {/* Privacy Tab */}
              {activeTab === 'privacy' && (
                <div className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-xl p-6">
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Privacy & Security</h2>
                  
                  <div className="space-y-6">
                    <div className="p-4 bg-gray-50 dark:bg-gray-900 rounded-lg">
                      <h3 className="font-medium text-gray-900 dark:text-gray-100 mb-2">Data Protection</h3>
                      <ul className="text-sm text-gray-600 dark:text-gray-300 space-y-1">
                        <li>• Your API keys are encrypted using AES-256</li>
                        <li>• Chat history is stored securely in our database</li>
                        <li>• We never share your data with third parties</li>
                        <li>• You can export or delete your data at any time</li>
                      </ul>
                    </div>
                    
                    <div className="space-y-3">
                      <h3 className="font-medium text-gray-900 dark:text-gray-100">Data Management</h3>
                      
                      <button className="w-full p-3 border dark:border-gray-700 rounded-lg text-left hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center justify-between">
                        <div>
                          <div className="font-medium text-gray-900 dark:text-gray-100">Export My Data</div>
                          <div className="text-sm text-gray-500 dark:text-gray-400">Download all your data</div>
                        </div>
                        <span className="text-blue-600">Export</span>
                      </button>
                      
                      <button className="w-full p-3 border border-red-200 dark:border-red-800 rounded-lg text-left hover:bg-red-50 dark:hover:bg-red-900/20 flex items-center justify-between">
                        <div>
                          <div className="font-medium text-red-600 dark:text-red-400">Delete Account</div>
                          <div className="text-sm text-gray-500 dark:text-gray-400">Permanently delete all data</div>
                        </div>
                        <Trash2 className="w-5 h-5 text-red-600 dark:text-red-400" />
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
