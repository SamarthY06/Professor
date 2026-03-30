'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  BookOpen,
  Key,
  Sparkles,
  Upload,
  ChevronRight,
  GraduationCap,
  Brain,
  CheckCircle2,
} from 'lucide-react'

interface OnboardingProps {
  userName: string
  hasApiKey: boolean
  hasBooks: boolean
  onDismiss: () => void
}

const STEPS = [
  {
    icon: Key,
    title: 'Add your OpenAI API key',
    description:
      'Head to Settings and paste your API key. We encrypt it and never share it.',
    href: '/settings',
    cta: 'Go to Settings',
    checkField: 'hasApiKey' as const,
  },
  {
    icon: Upload,
    title: 'Upload a textbook',
    description:
      'Upload any PDF — a textbook, research paper, or course notes — and we\'ll build a personalised learning plan.',
    href: '/library/upload',
    cta: 'Upload PDF',
    checkField: 'hasBooks' as const,
  },
  {
    icon: GraduationCap,
    title: 'Start learning!',
    description:
      'Pick your level (Bachelor, Master, PhD), set a schedule, and your AI professor will teach you chapter by chapter.',
    href: null,
    cta: null,
    checkField: null,
  },
]

export default function Onboarding({
  userName,
  hasApiKey,
  hasBooks,
  onDismiss,
}: OnboardingProps) {
  const router = useRouter()
  const checks = { hasApiKey, hasBooks }

  const completedCount = [hasApiKey, hasBooks].filter(Boolean).length
  const allDone = completedCount === 2

  return (
    <div className="relative rounded-2xl border border-primary/20 bg-gradient-to-br from-primary/5 via-card to-accent/5 dark:from-primary/10 dark:via-card dark:to-accent/10 p-6 mb-8 overflow-hidden">
      {/* Decorative blur */}
      <div className="absolute -top-20 -right-20 w-48 h-48 bg-primary/10 rounded-full blur-3xl pointer-events-none" />

      <div className="relative">
        {/* Header */}
        <div className="flex items-start justify-between mb-5">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Sparkles className="h-5 w-5 text-primary" />
              <h2 className="text-lg font-semibold text-foreground">
                Welcome to Professor, {userName}!
              </h2>
            </div>
            <p className="text-sm text-muted-foreground">
              Get set up in two quick steps and start learning with your own AI professor.
            </p>
          </div>
          <button
            onClick={onDismiss}
            className="text-xs text-muted-foreground hover:text-foreground transition"
          >
            Dismiss
          </button>
        </div>

        {/* Progress */}
        <div className="flex items-center gap-2 mb-5">
          <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all duration-500"
              style={{ width: `${(completedCount / 2) * 100}%` }}
            />
          </div>
          <span className="text-xs font-medium text-muted-foreground">
            {completedCount}/2
          </span>
        </div>

        {/* Steps */}
        <div className="grid sm:grid-cols-3 gap-4">
          {STEPS.map((step, i) => {
            const done = step.checkField ? checks[step.checkField] : allDone
            return (
              <div
                key={i}
                className={`rounded-xl border p-4 transition-all ${
                  done
                    ? 'border-emerald-200 dark:border-emerald-800 bg-emerald-50/50 dark:bg-emerald-950/30'
                    : 'border-border bg-card hover:border-primary/30'
                }`}
              >
                <div className="flex items-center gap-2 mb-2">
                  {done ? (
                    <CheckCircle2 className="h-5 w-5 text-emerald-500" />
                  ) : (
                    <step.icon className="h-5 w-5 text-primary" />
                  )}
                  <span className="text-sm font-medium text-foreground">
                    {step.title}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mb-3 leading-relaxed">
                  {step.description}
                </p>
                {step.href && !done && (
                  <button
                    onClick={() => router.push(step.href!)}
                    className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:text-primary/80 transition"
                  >
                    {step.cta}
                    <ChevronRight className="h-3 w-3" />
                  </button>
                )}
                {done && (
                  <span className="text-xs font-medium text-emerald-600 dark:text-emerald-400">
                    Done
                  </span>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
