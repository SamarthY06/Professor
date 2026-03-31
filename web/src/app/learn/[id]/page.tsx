'use client';

import { useState, useRef, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  Brain,
  ArrowLeft,
  Send,
  BookOpen,
  Settings,
  BarChart3,
  User,
  Loader2,
  CheckCircle,
  AlertCircle,
  BookmarkPlus,
  StickyNote,
} from 'lucide-react';

import api from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import SelectionToNotes from '@/components/SelectionToNotes';
import { notesStore, NotePage } from '@/lib/notes-store';
import { MarkdownRenderer } from '@/components/chat/MarkdownRenderer';
import VoiceInput from '@/components/chat/VoiceInput';

// Types matching backend models
interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  agent_name?: string;
  is_quiz_question?: boolean;
  quiz_answer_correct?: boolean;
  created_at: string;
}

interface LearningState {
  current_day: number;
  completed_days: number[];
  current_chapter: number;
  completed_chapters: number[];
  motivation_score: number;
  attention_score: number;
  comprehension_score: number;
  total_study_time_minutes: number;
}

interface LearningConfig {
  learning_level: string;
  target_days: number;
  daily_minutes: number;
  quiz_frequency: string;
}

interface DayProgress {
  day: number;
  title: string;
  is_completed: boolean;
  is_current: boolean;
  is_rest: boolean;
}

interface ChapterProgress {
  chapter_number: number;
  title: string;
  is_completed: boolean;
  is_current: boolean;
  days: DayProgress[];
}

interface BookInfo {
  id: string;
  title: string;
  author: string | null;
  chapters: {
    id: string;
    chapter_number: number;
    title: string | null;
  }[];
}

interface ChatSession {
  id: string;
  messages: Message[];
}

export default function LearnPage() {
  const params = useParams();
  const router = useRouter();
  const bookId = params.id as string;
  const { token, isLoading: authLoading, isAuthenticated } = useAuth();

  // State
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isFetching, setIsFetching] = useState(true);
  const [showSidebar, setShowSidebar] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Learning state from backend
  const [learningState, setLearningState] = useState<LearningState | null>(null);
  const [bookInfo, setBookInfo] = useState<BookInfo | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [mode, setMode] = useState<'greeting' | 'config_gathering' | 'planning' | 'teaching' | 'quiz' | 'attention_check' | 'error'>('config_gathering');
  const [sidebarChapters, setSidebarChapters] = useState<ChapterProgress[]>([]);
  const [totalDays, setTotalDays] = useState(1);
  const [learningConfig, setLearningConfig] = useState<LearningConfig | null>(null);
  const [scopeProgress, setScopeProgress] = useState<{
    completion_percentage: number;
    remaining_topics: string[];
    total_topics: number;
    covered_topics: number;
  } | null>(null);

  const [lastFailedMessage, setLastFailedMessage] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);

  // Handle note saved — uses global toast
  const handleNoteSaved = (note: NotePage) => {
    if (typeof window !== 'undefined') {
      const event = new CustomEvent('professor-toast', {
        detail: { description: `Note saved: "${note.title}"`, variant: 'success' },
      })
      window.dispatchEvent(event)
    }
  };

  // Redirect if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Load initial data from backend
  useEffect(() => {
    if (authLoading || !isAuthenticated) return;

    const t = token || '';
    const loadData = async () => {
      try {
        setIsFetching(true);
        setError(null);

        const [book, state, sessionData, detailedProgress] = await Promise.all([
          api.books.get(t, bookId),
          api.learning.getState(t, bookId).catch((err) => {
            console.warn('Learning state not ready yet:', err);
            return null;
          }),
          api.chat.initSession(t, bookId).catch((err) => {
            console.warn('No session found, will create on first message:', err);
            return null;
          }),
          api.learning.getDetailedProgress(t, bookId).catch((err) => {
            console.warn('Could not fetch detailed progress:', err);
            return null;
          }),
        ]);

        setBookInfo(book);
        if (state) setLearningState(state);
        
        // Set sidebar chapters from detailed progress
        if (detailedProgress && detailedProgress.sidebar_chapters) {
          setSidebarChapters(detailedProgress.sidebar_chapters);
          setTotalDays(detailedProgress.total_days || 1);
          
          if ((detailedProgress.scope_total_topics ?? 0) > 0) {
            setScopeProgress({
              completion_percentage: detailedProgress.scope_completion_percentage || 0,
              remaining_topics: detailedProgress.scope_remaining_topics || [],
              total_topics: detailedProgress.scope_total_topics || 0,
              covered_topics: detailedProgress.scope_covered_topics || 0,
            });
          }
          
          // Extract config from plan data if available
          const planData = detailedProgress.plan_data as any;
          if (planData) {
            setLearningConfig({
              learning_level: planData.learning_level || 'intermediate',
              target_days: planData.total_days || detailedProgress.total_days || 30,
              daily_minutes: planData.daily_minutes || 30,
              quiz_frequency: planData.quiz_frequency || 'after_each_chapter',
            });
          }
        }

        // If the backend says we're in the planning phase, redirect to the
        // plan review page so the user sees a visual schedule instead of chat.
        if (sessionData?.phase === 'planning') {
          router.push(`/learn/${bookId}/plan`);
          return;
        }

        if (sessionData && sessionData.messages.length > 0) {
          // Session exists with professor's greeting - load it
          setSessionId(sessionData.session_id);
          setMode(sessionData.phase as any);
          
          // Load messages from the session (includes professor's greeting)
          setMessages(sessionData.messages.map((m: any) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            agent_name: m.agent_name,
            is_quiz_question: m.is_quiz_question,
            quiz_answer_correct: m.quiz_answer_correct,
            created_at: m.created_at,
          })));
        } else {
          // No session yet - this shouldn't happen normally since greeting is auto-generated
          // But we handle it by triggering greeting regeneration
          try {
            const greetingResponse = await api.chat.regenerateGreeting(t, bookId);
            setSessionId(greetingResponse.session_id);
            setMessages([{
              id: `greeting-${Date.now()}`,
              role: 'assistant',
              content: greetingResponse.message,
              agent_name: 'GreetingAgent',
              created_at: new Date().toISOString(),
            }]);
          } catch (greetingErr: any) {
            console.error('Failed to generate greeting:', greetingErr);
            // Fallback: Let user send first message to trigger greeting
            setMessages([]);
          }
        }
      } catch (err: any) {
        console.error('Failed to load learning data:', err);
        setError(err.message || 'Failed to load learning data');
      } finally {
        setIsFetching(false);
      }
    };

    loadData();
  }, [bookId, token, authLoading, isAuthenticated, router]);

  const handleSend = async () => {
    if (!input.trim() || isLoading || !isAuthenticated) return;

    const userMessage: Message = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: input,
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);
    setError(null);

    try {
      // Use Temporal-backed SSE endpoint for durable, non-blocking chat
      const response = await api.chat.sendV2Stream(
        token || '',
        { message: input, book_id: bookId },
      );

      if (!sessionId && response.session_id) {
        setSessionId(response.session_id);
      }

      const assistantMessage: Message = {
        id: `resp-${Date.now()}`,
        role: 'assistant',
        content: response.message,
        created_at: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, assistantMessage]);

      // When config gathering completes and transitions to planning,
      // redirect to the dedicated plan review page instead of staying
      // in the chat.  The plan page shows a visual day-by-day schedule
      // with accept/regenerate buttons.
      if (response.phase === 'planning') {
        router.push(`/learn/${bookId}/plan`);
        return;
      }

      // Update mode from the response phase so the UI reflects the
      // current agent (e.g. config_gathering → planning → teaching)
      if (response.phase) {
        setMode(response.phase as any);
      }

      const updatedState = await api.learning.getState(token || '', bookId);
      setLearningState(updatedState);

    } catch (err: any) {
      console.error('Chat error:', err);
      setError(err.message || 'Failed to send message');
      setLastFailedMessage(input);
      
      setMessages((prev) => [...prev, {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: `Oops, I stumbled a bit there! ${err.message ? `(${err.message})` : 'Please try again.'}`,
        created_at: new Date().toISOString(),
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRetry = () => {
    if (lastFailedMessage) {
      setInput(lastFailedMessage);
      setLastFailedMessage(null);
      setError(null);
      setMessages((prev) => prev.filter((m) => !m.id.startsWith('error-')));
    }
  };

  // Calculate progress percentage
  const progress = learningState && bookInfo?.chapters.length
    ? Math.round((learningState.completed_chapters.length / bookInfo.chapters.length) * 100)
    : 0;

  if (authLoading || isFetching) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin text-primary mx-auto mb-4" />
          <p className="text-muted-foreground">Getting everything ready for you...</p>
          <p className="text-sm text-muted-foreground/60 mt-1">Just a moment!</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error && !bookInfo) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="text-center max-w-md">
          <AlertCircle className="h-8 w-8 text-amber-500 mx-auto mb-4" />
          <p className="text-gray-900 dark:text-gray-100 font-medium mb-2">Hmm, something went wrong</p>
          <p className="text-gray-600 dark:text-gray-300 mb-4">
            I couldn't load your learning session. This might be a temporary hiccup - 
            want to try again?
          </p>
          <p className="text-sm text-gray-400 dark:text-gray-500 mb-4">{error}</p>
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

  return (
    <div className="min-h-screen bg-background text-foreground flex">
      {/* Sidebar */}
      {showSidebar && (
        <aside className="w-80 bg-card border-r border-border flex flex-col">
          {/* Book Info */}
          <div className="p-4 border-b dark:border-gray-700">
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 mb-4"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Dashboard
            </Link>
            <h2 className="font-semibold text-foreground mb-1">
              {bookInfo?.title || 'Loading...'}
            </h2>
            {bookInfo?.author && (
              <p className="text-sm text-muted-foreground">by {bookInfo.author}</p>
            )}
          </div>

          {/* Progress */}
          <div className="p-4 border-b dark:border-gray-700">
            <div className="flex items-center justify-between text-sm mb-2">
              <span className="text-gray-600 dark:text-gray-300">Overall Progress</span>
              <span className="font-medium">{progress}%</span>
            </div>
            <div className="h-2 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-600 rounded-full transition-all duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>
            
            {/* Learning Metrics */}
            {learningState && (
              <div className="mt-4 grid grid-cols-3 gap-2 text-center">
                <div className="p-2 bg-green-50 dark:bg-green-900/20 rounded-lg">
                  <div className="text-lg font-semibold text-green-700 dark:text-green-400">
                    {Math.round(learningState.comprehension_score * 100)}%
                  </div>
                  <div className="text-xs text-green-600 dark:text-green-400">Comprehension</div>
                </div>
                <div className="p-2 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                  <div className="text-lg font-semibold text-blue-700 dark:text-blue-400">
                    {Math.round(learningState.attention_score * 100)}%
                  </div>
                  <div className="text-xs text-blue-600 dark:text-blue-400">Attention</div>
                </div>
                <div className="p-2 bg-purple-50 dark:bg-purple-900/20 rounded-lg">
                  <div className="text-lg font-semibold text-purple-700 dark:text-purple-400">
                    {learningState.total_study_time_minutes}m
                  </div>
                  <div className="text-xs text-purple-600 dark:text-purple-400">Study Time</div>
                </div>
              </div>
            )}
          </div>

          {/* Config Gathering / Greeting State - Show setup steps */}
          {(mode === 'config_gathering' || mode === 'greeting') && (
            <div className="flex-1 p-4">
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-4">Getting to Know You</h3>
              <div className="space-y-3">
                {[
                  { step: 1, label: 'Your Background', desc: 'What you already know' },
                  { step: 2, label: 'Teaching Style', desc: 'How you like to learn' },
                  { step: 3, label: 'Your Timeline', desc: 'When you want to finish' },
                  { step: 4, label: 'Daily Rhythm', desc: 'Time you can dedicate' },
                ].map((item) => (
                  <div key={item.step} className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-900 rounded-lg">
                    <div className="w-8 h-8 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-600 flex items-center justify-center text-sm font-semibold">
                      {item.step}
                    </div>
                    <div>
                      <div className="font-medium text-gray-800 dark:text-gray-200 text-sm">{item.label}</div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">{item.desc}</div>
                    </div>
                  </div>
                ))}
              </div>
              <p className="mt-4 text-xs text-gray-500 dark:text-gray-400 text-center">
                Just chat naturally - I'll learn what I need to know! 💬
              </p>
            </div>
          )}

          {/* Planning State - Show plan creation steps */}
          {mode === 'planning' && (
            <div className="flex-1 p-4">
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-4">Building Your Plan</h3>
              <div className="space-y-3">
                {[
                  { step: 1, label: 'Day-by-day schedule', desc: 'Chapters mapped to days' },
                  { step: 2, label: 'Time estimates', desc: 'Realistic daily workload' },
                  { step: 3, label: 'Quiz checkpoints', desc: 'Knowledge reinforcement' },
                  { step: 4, label: 'Your approval', desc: 'Review and customize' },
                ].map((item) => (
                  <div key={item.step} className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-900 rounded-lg">
                    <div className="w-8 h-8 rounded-full bg-indigo-100 dark:bg-indigo-900/30 text-indigo-600 flex items-center justify-center text-sm font-semibold">
                      {item.step}
                    </div>
                    <div>
                      <div className="font-medium text-gray-800 dark:text-gray-200 text-sm">{item.label}</div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">{item.desc}</div>
                    </div>
                  </div>
                ))}
              </div>
              <p className="mt-4 text-xs text-gray-500 dark:text-gray-400 text-center">
                Say &quot;yes&quot; to start or request changes 📝
              </p>
            </div>
          )}

          {/* Learning Config (if set) */}
          {learningConfig && mode !== 'config_gathering' && mode !== 'greeting' && (
            <div className="p-4 border-b dark:border-gray-700 bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-gray-900 dark:to-gray-900">
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-2 flex items-center gap-2">
                <Settings className="h-4 w-4" />
                Your Plan
              </h3>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-white/70 dark:bg-gray-800/70 rounded-lg p-2">
                  <div className="text-gray-500 dark:text-gray-400">Level</div>
                  <div className="font-medium text-gray-800 dark:text-gray-200 capitalize">{learningConfig.learning_level}</div>
                </div>
                <div className="bg-white/70 dark:bg-gray-800/70 rounded-lg p-2">
                  <div className="text-gray-500 dark:text-gray-400">Duration</div>
                  <div className="font-medium text-gray-800 dark:text-gray-200">{learningConfig.target_days} days</div>
                </div>
                <div className="bg-white/70 dark:bg-gray-800/70 rounded-lg p-2">
                  <div className="text-gray-500 dark:text-gray-400">Daily Time</div>
                  <div className="font-medium text-gray-800 dark:text-gray-200">{learningConfig.daily_minutes} min</div>
                </div>
                <div className="bg-white/70 dark:bg-gray-800/70 rounded-lg p-2">
                  <div className="text-gray-500 dark:text-gray-400">Quizzes</div>
                  <div className="font-medium text-gray-800 dark:text-gray-200 text-[10px]">
                    {learningConfig.quiz_frequency === 'after_each_chapter' ? 'Each chapter' :
                     learningConfig.quiz_frequency === 'after_2_chapters' ? 'Every 2 ch.' : 'Final only'}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Progress: Chapters with nested Days (only show when actively learning) */}
          {mode !== 'config_gathering' && mode !== 'greeting' && mode !== 'planning' && (
            <div className="flex-1 overflow-y-auto">
              <div className="p-4">
                <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3">
                  Progress ({totalDays} days)
                </h3>
                {scopeProgress && scopeProgress.total_topics > 0 && (
                  <div className="mb-4 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                    <div className="flex items-center justify-between text-xs text-blue-700 dark:text-blue-400 mb-1">
                      <span>Today&apos;s Topics</span>
                      <span>{scopeProgress.covered_topics}/{scopeProgress.total_topics} ({Math.round(scopeProgress.completion_percentage)}%)</span>
                    </div>
                    <div className="w-full bg-blue-200 dark:bg-blue-800 rounded-full h-2">
                      <div
                        className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                        style={{ width: `${scopeProgress.completion_percentage}%` }}
                      />
                    </div>
                    {scopeProgress.remaining_topics.length > 0 && (
                      <div className="mt-2 text-xs text-blue-600 dark:text-blue-400">
                        Remaining: {scopeProgress.remaining_topics.slice(0, 3).join(', ')}
                        {scopeProgress.remaining_topics.length > 3 && ` +${scopeProgress.remaining_topics.length - 3} more`}
                      </div>
                    )}
                  </div>
                )}
                <div className="space-y-3">
                  {sidebarChapters.length > 0 ? (
                    sidebarChapters.map((chapter) => (
                      <ChapterWithDays
                        key={chapter.chapter_number}
                        chapter={chapter}
                        currentDay={learningState?.current_day || 1}
                      />
                    ))
                  ) : (
                    bookInfo?.chapters.map((chapter) => (
                      <ChapterItem
                        key={chapter.id}
                        number={chapter.chapter_number}
                        title={chapter.title || `Chapter ${chapter.chapter_number}`}
                        isCurrent={chapter.chapter_number === learningState?.current_chapter}
                        isCompleted={learningState?.completed_chapters.includes(chapter.chapter_number) || false}
                        isLocked={chapter.chapter_number > (learningState?.current_chapter || 1)}
                      />
                    ))
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Settings */}
          <div className="p-4 border-t dark:border-gray-700">
            <Link 
              href="/settings"
              className="w-full flex items-center gap-2 px-3 py-2 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition"
            >
              <Settings className="h-4 w-4" />
              <span className="text-sm">Learning Settings</span>
            </Link>
          </div>
        </aside>
      )}

      {/* Main Chat Area */}
      <main className="flex-1 flex flex-col">
        {/* Header */}
        <header className="bg-card border-b border-border px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setShowSidebar(!showSidebar)}
              className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition"
            >
              <BookOpen className="h-5 w-5 text-gray-600 dark:text-gray-300" />
            </button>
            <div>
              <h1 className="font-semibold text-foreground">
                {(mode === 'config_gathering' || mode === 'greeting') ? (
                  '👋 Welcome to Professor'
                ) : mode === 'planning' ? (
                  '📋 Your Learning Plan'
                ) : (
                  <>
                    Chapter {learningState?.current_chapter || 1}
                    {sidebarChapters.find(c => c.is_current)?.title && 
                      `: ${sidebarChapters.find(c => c.is_current)?.title}`
                    }
                  </>
                )}
              </h1>
              <p className="text-sm text-gray-600 dark:text-gray-300">
                {(mode === 'config_gathering' || mode === 'greeting') && "Let's set up your personalized learning plan"}
                {mode === 'planning' && 'Review your plan and tell me if you want any changes'}
                {mode === 'quiz' && '📝 Quiz Mode • '}
                {mode === 'attention_check' && '🧠 Quick Check • '}
                {mode !== 'config_gathering' && mode !== 'greeting' && mode !== 'planning' && mode !== 'quiz' && mode !== 'attention_check' && 
                  `Day ${learningState?.current_day || 1} of ${totalDays}`
                }
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition" title="Progress">
              <BarChart3 className="h-5 w-5 text-gray-600 dark:text-gray-300" />
            </button>
          </div>
        </header>

        {/* Error Banner */}
        {error && (
          <div className="bg-red-50 dark:bg-red-900/20 border-b border-red-200 dark:border-red-800 px-6 py-3 flex items-center gap-2 text-red-700 dark:text-red-400">
            <AlertCircle className="h-4 w-4" />
            <span className="text-sm">{error}</span>
            {lastFailedMessage && (
              <button
                onClick={handleRetry}
                className="ml-2 text-sm text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-300 underline"
              >
                Retry
              </button>
            )}
            <button 
              onClick={() => { setError(null); setLastFailedMessage(null); }}
              className="ml-auto text-red-500 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300"
            >
              ✕
            </button>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6" ref={messagesContainerRef}>
          <div className="max-w-3xl mx-auto space-y-6">
            {messages.map((message) => (
              <MessageBubble 
                key={message.id} 
                message={message} 
                bookInfo={bookInfo}
                learningState={learningState}
                onSaveToNotes={handleNoteSaved}
              />
            ))}
            {isLoading && <TypingIndicator />}
            <div ref={messagesEndRef} />
          </div>
          
          {/* Selection to Notes - appears when text is selected */}
          <SelectionToNotes
            containerRef={messagesContainerRef}
            context={{
              bookId: bookInfo?.id,
              bookTitle: bookInfo?.title,
              chapterNumber: learningState?.current_chapter,
              chapterTitle: bookInfo?.chapters.find(c => c.chapter_number === learningState?.current_chapter)?.title || undefined,
            }}
            onNoteSaved={handleNoteSaved}
          />
        </div>
        
        {/* Toast notifications handled by global Radix ToastProvider */}

        {/* Input Area */}
        <div className="bg-card border-t border-border p-4">
          <div className="max-w-3xl mx-auto">
            <div className="flex items-end gap-4">
              <div className="flex-1 bg-gray-50 dark:bg-gray-900 rounded-xl border dark:border-gray-700 focus-within:border-blue-300 dark:focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-100 dark:focus-within:ring-blue-900/50">
                <div className="flex items-end">
                  <textarea
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        handleSend();
                      }
                    }}
                    placeholder={
                      mode === 'config_gathering' || mode === 'greeting'
                        ? "Share your thoughts..."
                        : mode === 'planning'
                        ? "Say 'yes' to start, or tell me what to change..."
                        : mode === 'quiz' 
                        ? "What's your answer?" 
                        : "Ask me anything, or say 'continue' to keep going..."
                    }
                    className="flex-1 px-4 py-3 bg-transparent resize-none outline-none min-h-[48px] max-h-[200px] text-foreground"
                    rows={1}
                    disabled={isLoading}
                    aria-label="Type your message"
                  />
                  <div className="pr-2 pb-2">
                    <VoiceInput
                      onTranscription={(text) => setInput((prev) => prev ? `${prev} ${text}` : text)}
                      disabled={isLoading}
                      token={token || ''}
                    />
                  </div>
                </div>
              </div>
              <button
                onClick={handleSend}
                disabled={!input.trim() || isLoading}
                className="p-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
                aria-label={isLoading ? 'Sending message' : 'Send message'}
              >
                {isLoading ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                  <Send className="h-5 w-5" />
                )}
              </button>
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-2 text-center">
              {(mode === 'config_gathering' || mode === 'greeting')
                ? "Let's create your personalized learning journey ✨"
                : mode === 'planning'
                ? "Review your plan and approve to start learning 📋"
                : `Chapter ${learningState?.current_chapter || 1} • Day ${learningState?.current_day || 1} of ${totalDays}`
              }
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}

// Chapter Item Component
function ChapterItem({
  number,
  title,
  isCurrent,
  isCompleted,
  isLocked,
}: {
  number: number;
  title: string;
  isCurrent: boolean;
  isCompleted: boolean;
  isLocked: boolean;
}) {
  return (
    <button
      disabled={isLocked}
      className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition ${
        isCurrent
          ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400'
          : isCompleted
          ? 'hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100'
          : 'text-gray-400 dark:text-gray-500 cursor-not-allowed'
      }`}
    >
      <div
        className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
          isCurrent
            ? 'bg-blue-600 text-white'
            : isCompleted
            ? 'bg-green-500 text-white'
            : 'bg-gray-200 dark:bg-gray-600 text-gray-500 dark:text-gray-400'
        }`}
      >
        {isCompleted ? <CheckCircle className="h-4 w-4" /> : number}
      </div>
      <span className="text-sm truncate flex-1">{title}</span>
      {isLocked && <span className="text-xs">🔒</span>}
    </button>
  );
}

// Chapter with nested Days component
function ChapterWithDays({
  chapter,
  currentDay,
}: {
  chapter: ChapterProgress;
  currentDay: number;
}) {
  const [isExpanded, setIsExpanded] = useState(chapter.is_current || chapter.days.some(d => d.is_current));
  
  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
      {/* Chapter Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className={`w-full flex items-center gap-3 px-3 py-2.5 text-left transition ${
          chapter.is_current
            ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-800 dark:text-blue-300'
            : chapter.is_completed
            ? 'bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-300'
            : 'bg-gray-50 dark:bg-gray-900 text-gray-600 dark:text-gray-300'
        }`}
      >
        <div
          className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
            chapter.is_completed
              ? 'bg-green-500 text-white'
              : chapter.is_current
              ? 'bg-blue-600 text-white'
              : 'bg-gray-300 dark:bg-gray-500 text-gray-600 dark:text-gray-300'
          }`}
        >
          {chapter.is_completed ? <CheckCircle className="h-4 w-4" /> : chapter.chapter_number}
        </div>
        <div className="flex-1 min-w-0">
          <span className="text-sm font-semibold block truncate">
            Chapter {chapter.chapter_number}
          </span>
          <span className="text-xs opacity-75 block truncate">{chapter.title}</span>
        </div>
        <span className={`text-xs transition-transform ${isExpanded ? 'rotate-90' : ''}`}>▶</span>
      </button>
      
      {/* Nested Days */}
      {isExpanded && chapter.days.length > 0 && (
        <div className="bg-white dark:bg-gray-800 border-t border-gray-100 dark:border-gray-800">
          {chapter.days.map((day) => (
            <div
              key={day.day}
              className={`flex items-center gap-2 px-4 py-2 text-sm border-l-2 ${
                day.is_current
                  ? 'border-l-blue-500 bg-blue-50/50 dark:bg-blue-900/20'
                  : day.is_completed
                  ? 'border-l-green-500'
                  : 'border-l-gray-200 dark:border-l-gray-600'
              }`}
            >
              <div
                className={`w-5 h-5 rounded-full flex items-center justify-center text-xs ${
                  day.is_completed
                    ? 'bg-green-500 text-white'
                    : day.is_current
                    ? 'bg-blue-500 text-white'
                    : day.is_rest
                    ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-600'
                    : 'bg-gray-200 dark:bg-gray-600 text-gray-500 dark:text-gray-400'
                }`}
              >
                {day.is_completed ? '✓' : day.is_rest ? '☕' : day.day}
              </div>
              <span className={`flex-1 truncate ${day.is_current ? 'font-medium text-blue-700 dark:text-blue-400' : 'text-gray-600 dark:text-gray-300'}`}>
                {day.is_rest ? 'Rest Day' : `Day ${day.day}`}
              </span>
              {day.is_current && <span className="text-blue-500 text-xs">●</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Message Bubble Component  
function MessageBubble({ 
  message,
  bookInfo,
  learningState,
  onSaveToNotes,
}: { 
  message: Message;
  bookInfo: BookInfo | null;
  learningState: LearningState | null;
  onSaveToNotes: (note: NotePage) => void;
}) {
  const isUser = message.role === 'user';
  const [showSaveButton, setShowSaveButton] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const handleSaveFullMessage = async () => {
    if (isSaving) return;
    setIsSaving(true);

    try {
      const note = await notesStore.createFromSelection({
        selectedText: message.content,
        messageContent: message.content,
        messageId: message.id,
        agentName: message.agent_name,
        bookId: bookInfo?.id,
        bookTitle: bookInfo?.title,
        chapterNumber: learningState?.current_chapter,
        chapterTitle: bookInfo?.chapters.find(c => c.chapter_number === learningState?.current_chapter)?.title || undefined,
      });
      onSaveToNotes(note);
    } catch (error) {
      console.error('Failed to save note:', error);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div
      className={`flex gap-3 animate-fadeIn group ${
        isUser ? 'flex-row-reverse' : ''
      }`}
      onMouseEnter={() => !isUser && setShowSaveButton(true)}
      onMouseLeave={() => setShowSaveButton(false)}
    >
      <div
        className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
          isUser ? 'bg-blue-600' : 'bg-gradient-to-br from-blue-500 to-purple-600'
        }`}
      >
        {isUser ? (
          <User className="h-4 w-4 text-white" />
        ) : (
          <Brain className="h-4 w-4 text-white" />
        )}
      </div>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 relative ${
          isUser
            ? 'bg-blue-600 text-white'
            : message.is_quiz_question
            ? 'bg-yellow-50 dark:bg-yellow-900/20 border-2 border-yellow-200 dark:border-yellow-700/50'
            : 'bg-white dark:bg-gray-800 border dark:border-gray-700 shadow-sm'
        }`}
        data-message-id={message.id}
        data-agent-name={message.agent_name || ''}
      >
        <div className={`${isUser ? 'text-white' : 'text-gray-900 dark:text-gray-100'}`}>
          {isUser ? (
            // User messages - plain text
            <p className="mb-0">{message.content}</p>
          ) : (
            // Assistant messages - rendered with KaTeX, code highlighting, and GFM
            <MarkdownRenderer content={message.content} />
          )}
        </div>
        
        {/* Footer with agent name and save button */}
        {!isUser && (
          <div className="mt-2 flex items-center justify-between">
            {message.agent_name && (
              <span className="text-xs text-gray-500 dark:text-gray-400">
                via {message.agent_name}
              </span>
            )}
            
            {/* Save to Notes button - visible on hover */}
            {showSaveButton && (
              <button
                onClick={handleSaveFullMessage}
                disabled={isSaving}
                className="flex items-center gap-1 text-xs text-gray-400 dark:text-gray-500 hover:text-blue-600 dark:hover:text-blue-400 transition-colors ml-auto"
                title="Save entire message to notes"
              >
                {isSaving ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <BookmarkPlus className="h-3 w-3" />
                )}
                <span>Save to Notes</span>
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// Typing Indicator Component
function TypingIndicator() {
  return (
    <div className="flex gap-3 animate-fadeIn">
      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
        <Brain className="h-4 w-4 text-white" />
      </div>
      <div className="bg-white dark:bg-gray-800 border dark:border-gray-700 shadow-sm rounded-2xl px-4 py-3 flex items-center gap-1">
        <div className="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
        <div className="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
        <div className="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
      </div>
    </div>
  );
}
