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
      if (!token) return;
      
      setIsLoading(true);
      try {
        const [profileData, settingsData, apiKeyData] = await Promise.all([
          api.users.getProfile(token),
          api.users.getSettings(token),
          api.users.getApiKeyStatus(token),
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
      } catch (err) {
        console.error('Failed to fetch settings:', err);
      } finally {
        setIsLoading(false);
      }
    };

    if (token) {
      fetchData();
    }
  }, [token]);

  const handleSaveProfile = async () => {
    if (!token) return;
    
    setIsSaving(true);
    try {
      await api.users.updateProfile(token, {
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
    if (!token) return;
    
    setIsSaving(true);
    try {
      await api.users.updateSettings(token, settings as unknown as Record<string, unknown>);
      setSaveMessage({ type: 'success', text: 'Settings saved successfully!' });
    } catch (err: any) {
      setSaveMessage({ type: 'error', text: err.message || 'Failed to save settings' });
    } finally {
      setIsSaving(false);
      setTimeout(() => setSaveMessage(null), 3000);
    }
  };

  const handleValidateApiKey = async () => {
    if (!newApiKey || !token) return;
    
    setIsValidatingKey(true);
    try {
      await api.users.saveApiKey(token, newApiKey, true);
      
      // Refresh API key status
      const apiKeyData = await api.users.getApiKeyStatus(token);
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
    if (!confirm('Are you sure you want to delete your API key?') || !token) return;
    
    try {
      await api.users.deleteApiKey(token);
      
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
    { id: 'learning', label: 'Learning', icon: BookOpen },
    { id: 'privacy', label: 'Privacy', icon: Shield },
  ] as const;

  if (authLoading || !isAuthenticated) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b">
        <div className="max-w-4xl mx-auto px-4 py-4">
          <div className="flex items-center gap-4">
            <Link 
              href="/dashboard"
              className="p-2 hover:bg-gray-100 rounded-lg"
            >
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div>
              <h1 className="text-xl font-bold">Settings</h1>
              <p className="text-sm text-gray-500">
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
                        ? 'bg-blue-50 text-blue-700'
                        : 'hover:bg-gray-100 text-gray-600'
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
                    ? 'bg-green-50 text-green-700 border border-green-200'
                    : 'bg-red-50 text-red-700 border border-red-200'
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
                <div className="bg-white border rounded-xl p-6">
                  <h2 className="text-lg font-semibold mb-4">Profile Information</h2>
                  
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium mb-1">Name</label>
                      <input
                        type="text"
                        value={profileName}
                        onChange={(e) => setProfileName(e.target.value)}
                        className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-300"
                      />
                    </div>
                    
                    <div>
                      <label className="block text-sm font-medium mb-1">Email</label>
                      <input
                        type="email"
                        value={profile?.email || ''}
                        disabled
                        className="w-full px-3 py-2 border rounded-lg bg-gray-50 cursor-not-allowed"
                      />
                      <p className="text-xs text-gray-500 mt-1">
                        Email is managed through your account
                      </p>
                    </div>
                    
                    <div>
                      <label className="block text-sm font-medium mb-1">
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
                        className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-300"
                      />
                      <p className="text-xs text-gray-500 mt-1">
                        Used for WhatsApp study reminders. Include country code.
                      </p>
                    </div>
                    
                    <div>
                      <label className="block text-sm font-medium mb-1">Timezone</label>
                      <select
                        value={settings.timezone}
                        onChange={(e) => setSettings({ ...settings, timezone: e.target.value })}
                        className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-300"
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
                <div className="bg-white border rounded-xl p-6">
                  <h2 className="text-lg font-semibold mb-4">OpenAI API Key</h2>
                  
                  <p className="text-gray-600 mb-4">
                    Professor uses OpenAI's GPT-4o model for personalized teaching. 
                    You can use your own API key or use the default one.
                  </p>
                  
                  {/* Current Key Status */}
                  <div className={`p-4 rounded-lg mb-4 ${
                    apiKeyStatus?.has_key
                      ? apiKeyStatus.is_valid
                        ? 'bg-green-50 border border-green-200'
                        : 'bg-yellow-50 border border-yellow-200'
                      : 'bg-gray-50 border border-gray-200'
                  }`}>
                    <div className="flex items-center gap-2">
                      {apiKeyStatus?.has_key ? (
                        apiKeyStatus.is_valid ? (
                          <>
                            <Check className="w-5 h-5 text-green-600" />
                            <span className="font-medium text-green-700">Your API key is active</span>
                          </>
                        ) : (
                          <>
                            <AlertCircle className="w-5 h-5 text-yellow-600" />
                            <span className="font-medium text-yellow-700">API key needs validation</span>
                          </>
                        )
                      ) : (
                        <>
                          <AlertCircle className="w-5 h-5 text-gray-500" />
                          <span className="font-medium text-gray-700">Using default API key</span>
                        </>
                      )}
                    </div>
                    
                    {apiKeyStatus?.masked_key && (
                      <p className="text-sm text-gray-600 mt-1">
                        Key: {apiKeyStatus.masked_key}
                      </p>
                    )}
                    
                    {apiKeyStatus?.last_validated && (
                      <p className="text-xs text-gray-500 mt-1">
                        Last validated: {new Date(apiKeyStatus.last_validated).toLocaleString()}
                      </p>
                    )}
                  </div>
                  
                  {/* Add/Update Key */}
                  <div className="space-y-3">
                    <label className="block text-sm font-medium">
                      {apiKeyStatus?.has_key ? 'Update API Key' : 'Add Your Own API Key'}
                    </label>
                    
                    <div className="flex gap-2">
                      <div className="flex-1 relative">
                        <input
                          type={showApiKey ? 'text' : 'password'}
                          value={newApiKey}
                          onChange={(e) => setNewApiKey(e.target.value)}
                          placeholder="sk-..."
                          className="w-full px-3 py-2 pr-10 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-300"
                        />
                        <button
                          onClick={() => setShowApiKey(!showApiKey)}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
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
                    
                    <p className="text-xs text-gray-500">
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
                    <div className="mt-6 pt-6 border-t">
                      <button
                        onClick={handleDeleteApiKey}
                        className="flex items-center gap-2 text-red-600 hover:text-red-700"
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
                <div className="bg-white border rounded-xl p-6">
                  <h2 className="text-lg font-semibold mb-4">Notification Preferences</h2>
                  
                  <div className="space-y-4">
                    {[
                      { key: 'email', label: 'Email Notifications', desc: 'Receive updates via email' },
                      { key: 'whatsapp', label: 'WhatsApp Reminders', desc: 'Get study reminders on WhatsApp (requires phone number)' },
                    ].map((item) => (
                      <div key={item.key} className="flex items-center justify-between p-4 border rounded-lg">
                        <div>
                          <div className="font-medium">{item.label}</div>
                          <div className="text-sm text-gray-500">{item.desc}</div>
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
                          <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-100 rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
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
              
              {/* Learning Tab */}
              {activeTab === 'learning' && (
                <div className="bg-white border rounded-xl p-6">
                  <h2 className="text-lg font-semibold mb-4">Learning Preferences</h2>
                  
                  <div className="space-y-6">
                    {/* Professor Style */}
                    <div>
                      <label className="block text-sm font-medium mb-3">Professor Style</label>
                      <div className="grid grid-cols-3 gap-3">
                        {[
                          { value: 'strict', label: 'Strict', desc: 'PhD level - rigorous, detailed' },
                          { value: 'balanced', label: 'Balanced', desc: 'Graduate level - mix of support' },
                          { value: 'encouraging', label: 'Encouraging', desc: 'Undergraduate - supportive' },
                        ].map((style) => (
                          <button
                            key={style.value}
                            onClick={() => setSettings({ ...settings, professor_style: style.value as any })}
                            className={`p-4 border rounded-lg text-left transition-colors ${
                              settings.professor_style === style.value
                                ? 'border-blue-500 bg-blue-50'
                                : 'hover:border-blue-300'
                            }`}
                          >
                            <div className="font-medium">{style.label}</div>
                            <div className="text-xs text-gray-500 mt-1">{style.desc}</div>
                          </button>
                        ))}
                      </div>
                    </div>
                    
                    {/* Preferred Study Time */}
                    <div>
                      <label className="block text-sm font-medium mb-3">Preferred Study Time</label>
                      <div className="grid grid-cols-3 gap-3">
                        {[
                          { value: 'morning', label: '🌅 Morning', desc: '6 AM - 12 PM' },
                          { value: 'afternoon', label: '☀️ Afternoon', desc: '12 PM - 6 PM' },
                          { value: 'evening', label: '🌙 Evening', desc: '6 PM - 12 AM' },
                        ].map((time) => (
                          <button
                            key={time.value}
                            onClick={() => setSettings({
                              ...settings,
                              study_schedule: { ...settings.study_schedule!, preferred_time: time.value },
                            })}
                            className={`p-4 border rounded-lg text-left transition-colors ${
                              settings.study_schedule?.preferred_time === time.value
                                ? 'border-blue-500 bg-blue-50'
                                : 'hover:border-blue-300'
                            }`}
                          >
                            <div className="font-medium">{time.label}</div>
                            <div className="text-xs text-gray-500 mt-1">{time.desc}</div>
                          </button>
                        ))}
                      </div>
                    </div>
                    
                    {/* Daily Goal */}
                    <div>
                      <label className="block text-sm font-medium mb-3">
                        Daily Study Goal: {settings.study_schedule?.daily_goal_minutes || 30} minutes
                      </label>
                      <input
                        type="range"
                        min="15"
                        max="120"
                        step="15"
                        value={settings.study_schedule?.daily_goal_minutes || 30}
                        onChange={(e) => setSettings({
                          ...settings,
                          study_schedule: { ...settings.study_schedule!, daily_goal_minutes: parseInt(e.target.value) },
                        })}
                        className="w-full"
                      />
                      <div className="flex justify-between text-xs text-gray-500 mt-1">
                        <span>15 min</span>
                        <span>2 hours</span>
                      </div>
                    </div>
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
                <div className="bg-white border rounded-xl p-6">
                  <h2 className="text-lg font-semibold mb-4">Privacy & Security</h2>
                  
                  <div className="space-y-6">
                    <div className="p-4 bg-gray-50 rounded-lg">
                      <h3 className="font-medium mb-2">Data Protection</h3>
                      <ul className="text-sm text-gray-600 space-y-1">
                        <li>• Your API keys are encrypted using AES-256</li>
                        <li>• Chat history is stored securely in our database</li>
                        <li>• We never share your data with third parties</li>
                        <li>• You can export or delete your data at any time</li>
                      </ul>
                    </div>
                    
                    <div className="space-y-3">
                      <h3 className="font-medium">Data Management</h3>
                      
                      <button className="w-full p-3 border rounded-lg text-left hover:bg-gray-50 flex items-center justify-between">
                        <div>
                          <div className="font-medium">Export My Data</div>
                          <div className="text-sm text-gray-500">Download all your data</div>
                        </div>
                        <span className="text-blue-600">Export</span>
                      </button>
                      
                      <button className="w-full p-3 border border-red-200 rounded-lg text-left hover:bg-red-50 flex items-center justify-between">
                        <div>
                          <div className="font-medium text-red-600">Delete Account</div>
                          <div className="text-sm text-gray-500">Permanently delete all data</div>
                        </div>
                        <Trash2 className="w-5 h-5 text-red-600" />
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
