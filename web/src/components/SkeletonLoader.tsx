'use client';

export function ChatSkeleton() {
  return (
    <div className="animate-pulse space-y-4 p-6" role="status" aria-label="Loading chat messages">
      {[1, 2, 3].map((i) => (
        <div key={i} className={`flex ${i % 2 === 0 ? 'justify-end' : 'justify-start'}`}>
          <div
            className={`rounded-2xl p-4 ${
              i % 2 === 0 ? 'bg-blue-100 dark:bg-blue-900/30 max-w-[60%]' : 'bg-gray-100 dark:bg-gray-700 max-w-[75%]'
            }`}
          >
            <div className="h-3 bg-gray-200 dark:bg-gray-600 rounded w-48 mb-2" />
            <div className="h-3 bg-gray-200 dark:bg-gray-600 rounded w-64 mb-2" />
            {i % 2 !== 0 && <div className="h-3 bg-gray-200 dark:bg-gray-600 rounded w-36" />}
          </div>
        </div>
      ))}
      <span className="sr-only">Loading...</span>
    </div>
  );
}

export function SidebarSkeleton() {
  return (
    <div className="animate-pulse p-4 space-y-3" role="status" aria-label="Loading sidebar">
      <div className="h-4 bg-gray-200 dark:bg-gray-600 rounded w-32 mb-4" />
      {[1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="space-y-2">
          <div className="h-4 bg-gray-200 dark:bg-gray-600 rounded w-40" />
          <div className="ml-4 space-y-1">
            <div className="h-3 bg-gray-100 dark:bg-gray-700 rounded w-32" />
            <div className="h-3 bg-gray-100 dark:bg-gray-700 rounded w-28" />
          </div>
        </div>
      ))}
      <span className="sr-only">Loading...</span>
    </div>
  );
}

export function DashboardCardSkeleton() {
  return (
    <div className="animate-pulse bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm" role="status" aria-label="Loading">
      <div className="h-40 bg-gray-200 dark:bg-gray-600 rounded-lg mb-4" />
      <div className="h-5 bg-gray-200 dark:bg-gray-600 rounded w-3/4 mb-2" />
      <div className="h-4 bg-gray-100 dark:bg-gray-700 rounded w-1/2" />
      <span className="sr-only">Loading...</span>
    </div>
  );
}
