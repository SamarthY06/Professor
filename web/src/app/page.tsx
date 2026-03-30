'use client'

import Link from 'next/link'
import { BookOpen, Brain, Target, Trophy, ArrowRight, Zap, MessageCircle, BarChart3, Clock, Sparkles } from 'lucide-react'

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-blue-50 to-white dark:from-gray-900 dark:to-gray-900">
      {/* Navigation */}
      <nav className="flex items-center justify-between p-6 max-w-7xl mx-auto">
        <div className="flex items-center gap-2">
          <Brain className="h-8 w-8 text-blue-600" />
          <span className="text-xl font-bold text-gray-900 dark:text-gray-100">Professor</span>
        </div>
        <Link
          href="/login"
          className="px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition font-medium"
        >
          Get Started
        </Link>
      </nav>

      {/* Hero Section */}
      <section className="max-w-7xl mx-auto px-6 py-24 text-center">
        <div className="inline-flex items-center gap-2 px-4 py-2 bg-blue-100 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800 rounded-full text-blue-700 dark:text-blue-400 text-sm mb-8">
          <Sparkles className="h-4 w-4" />
          Powered by Agentic OS
        </div>
        
        <h1 className="text-5xl md:text-6xl font-bold text-gray-900 dark:text-gray-100 mb-4">
          Meet <span className="text-blue-600">Professor</span>
        </h1>
        <p className="text-2xl md:text-3xl text-gray-600 dark:text-gray-300 mb-8">
          Your AI Teacher. Powered by Multi-Agent Intelligence.
        </p>
        
        <p className="text-lg text-gray-600 dark:text-gray-300 max-w-3xl mx-auto mb-12 leading-relaxed">
          Professor isn't just a chatbot — it's an <span className="font-semibold text-gray-800 dark:text-gray-200">Agentic OS</span> where 
          multiple AI agents work together to teach, quiz, motivate, and adapt to you. 
          Upload any book. Set any goal. Learn chapter by chapter, just like you would with an ordinary professor — 
          except this one never sleeps.
        </p>
        
        <Link
          href="/login"
          className="inline-flex items-center gap-2 px-8 py-4 bg-blue-600 text-white text-lg font-medium rounded-xl hover:bg-blue-700 transition shadow-lg shadow-blue-600/20"
        >
          Start Learning <ArrowRight className="h-5 w-5" />
        </Link>
        
        <p className="text-gray-500 dark:text-gray-400 text-sm mt-4">Free to start • No credit card required</p>
      </section>

      {/* How It Works - Visual Flow */}
      <section className="bg-white dark:bg-gray-800 py-20 border-t border-b dark:border-gray-700">
        <div className="max-w-7xl mx-auto px-6">
          <h2 className="text-3xl font-bold text-center mb-4 text-gray-900 dark:text-gray-100">How Professor Works</h2>
          <p className="text-gray-600 dark:text-gray-300 text-center mb-16 max-w-2xl mx-auto">
            Four simple steps to mastery
          </p>
          <div className="grid md:grid-cols-4 gap-8 relative">
            {/* Connecting line for desktop */}
            <div className="hidden md:block absolute top-8 left-[12%] right-[12%] h-0.5 bg-blue-100 dark:bg-blue-900/30" />
            
            <StepCard 
              number="1" 
              title="Upload" 
              description="Drop any PDF textbook or describe what you want to learn"
              icon={<BookOpen className="h-5 w-5" />}
            />
            <StepCard 
              number="2" 
              title="Plan" 
              description="Professor analyzes content and creates your personalized learning path"
              icon={<Target className="h-5 w-5" />}
            />
            <StepCard 
              number="3" 
              title="Learn" 
              description="Engage in conversations, ask questions, get clear explanations"
              icon={<Brain className="h-5 w-5" />}
            />
            <StepCard 
              number="4" 
              title="Master" 
              description="Take quizzes, track progress, receive summaries after each chapter"
              icon={<Trophy className="h-5 w-5" />}
            />
          </div>
        </div>
      </section>

      {/* The Agents Section */}
      <section className="py-20">
        <div className="max-w-7xl mx-auto px-6">
          <h2 className="text-3xl font-bold text-center mb-4 text-gray-900 dark:text-gray-100">The Agent Swarm</h2>
          <p className="text-gray-600 dark:text-gray-300 text-center mb-12 max-w-2xl mx-auto">
            Behind Professor is an orchestra of specialized AI agents, each with a unique role
          </p>
          <div className="grid md:grid-cols-3 gap-6">
            <AgentCard
              icon={<BookOpen className="h-6 w-6" />}
              title="Teaching Agent"
              description="Explains concepts with clarity, uses Socratic questioning, provides real-world examples"
              color="blue"
            />
            <AgentCard
              icon={<Target className="h-6 w-6" />}
              title="Quiz Agent"
              description="Generates contextual questions, validates your answers, gives detailed feedback"
              color="purple"
            />
            <AgentCard
              icon={<MessageCircle className="h-6 w-6" />}
              title="Motivation Agent"
              description="Tracks your engagement, sends WhatsApp nudges, keeps you on track"
              color="green"
            />
          </div>
          <p className="text-center text-gray-500 dark:text-gray-400 mt-8">
            + Planner, Assessment, Progress, Reminder, and more agents working behind the scenes
          </p>
        </div>
      </section>

      {/* Features Strip */}
      <section className="bg-gray-50 dark:bg-gray-900 py-16">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid md:grid-cols-4 gap-6">
            <FeatureItem
              icon={<Zap className="h-5 w-5" />}
              title="Agentic AI"
              description="Coordinated multi-agent system, not a simple chatbot"
            />
            <FeatureItem
              icon={<BookOpen className="h-5 w-5" />}
              title="Any Material"
              description="PDFs, textbooks, or just describe your learning goal"
            />
            <FeatureItem
              icon={<BarChart3 className="h-5 w-5" />}
              title="Progress Tracking"
              description="Visual analytics of your learning journey"
            />
            <FeatureItem
              icon={<Clock className="h-5 w-5" />}
              title="Always Available"
              description="Learn anytime, Professor adapts to your schedule"
            />
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="py-24 text-center">
        <div className="max-w-3xl mx-auto px-6">
          <h2 className="text-3xl md:text-4xl font-bold mb-4 text-gray-900 dark:text-gray-100">
            Ready to Learn Differently?
          </h2>
          <p className="text-gray-600 dark:text-gray-300 text-lg mb-8">
            Join learners who are mastering new subjects with the power of Agentic AI
          </p>
          <Link
            href="/login"
            className="inline-flex items-center gap-2 px-8 py-4 bg-blue-600 text-white text-lg font-medium rounded-xl hover:bg-blue-700 transition"
          >
            Meet Your Professor <ArrowRight className="h-5 w-5" />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t dark:border-gray-700 py-8">
        <div className="max-w-7xl mx-auto px-6 text-center text-gray-500 dark:text-gray-400 text-sm">
          <p>&copy; 2026 Professor. An Agentic OS for Learning.</p>
        </div>
      </footer>
    </div>
  )
}

function AgentCard({
  icon,
  title,
  description,
  color,
}: {
  icon: React.ReactNode
  title: string
  description: string
  color: 'blue' | 'purple' | 'green'
}) {
  const colors = {
    blue: 'bg-blue-50 dark:bg-blue-900/20 border-blue-100 dark:border-blue-800 text-blue-600',
    purple: 'bg-purple-50 dark:bg-purple-900/20 border-purple-100 dark:border-purple-800 text-purple-600',
    green: 'bg-green-50 dark:bg-green-900/20 border-green-100 dark:border-green-800 text-green-600',
  }
  
  return (
    <div className={`${colors[color]} border rounded-xl p-6`}>
      <div className="mb-4">{icon}</div>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">{title}</h3>
      <p className="text-gray-600 dark:text-gray-300 text-sm">{description}</p>
    </div>
  )
}

function StepCard({
  number,
  title,
  description,
  icon,
}: {
  number: string
  title: string
  description: string
  icon: React.ReactNode
}) {
  return (
    <div className="text-center relative">
      <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-600 text-white rounded-full mb-4 text-xl font-bold relative z-10">
        {number}
      </div>
      <h3 className="text-xl font-semibold mb-2 text-gray-900 dark:text-gray-100">{title}</h3>
      <p className="text-gray-600 dark:text-gray-300 text-sm">{description}</p>
    </div>
  )
}

function FeatureItem({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode
  title: string
  description: string
}) {
  return (
    <div className="flex items-start gap-3">
      <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg text-blue-600 flex-shrink-0">{icon}</div>
      <div>
        <h4 className="font-semibold text-gray-900 dark:text-gray-100">{title}</h4>
        <p className="text-sm text-gray-600 dark:text-gray-300">{description}</p>
      </div>
    </div>
  )
}
