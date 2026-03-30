'use client';

import { useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';

/**
 * Quiz Page - Redirects to Learn Page
 * 
 * Per Goals.md, quizzes are professor-driven and happen through the chat interface,
 * not through a separate quiz page. The professor:
 * 1. Teaches the chapter
 * 2. Asks if there are doubts
 * 3. Triggers quiz when appropriate (based on user preferences)
 * 4. Asks one question at a time through chat
 * 5. Validates answers and provides feedback
 */
export default function QuizPage() {
  const params = useParams();
  const router = useRouter();
  const bookId = params.id as string;

  useEffect(() => {
    // Redirect to the learn page - quizzes happen through chat
    router.replace(`/learn/${bookId}`);
  }, [bookId, router]);

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4" />
        <p className="text-gray-600 dark:text-gray-300">Taking you back to your session...</p>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
          I'll quiz you right in our conversation - it's more natural that way! 📝
        </p>
      </div>
    </div>
  );
}
