'use client'

import * as ToastPrimitive from '@radix-ui/react-toast'
import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from 'react'
import { X } from 'lucide-react'

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */
type ToastVariant = 'default' | 'success' | 'error' | 'warning'

interface Toast {
  id: string
  title?: string
  description: string
  variant: ToastVariant
}

interface ToastContextValue {
  toast: (opts: Omit<Toast, 'id'>) => void
  success: (description: string, title?: string) => void
  error: (description: string, title?: string) => void
  warning: (description: string, title?: string) => void
}

/* ------------------------------------------------------------------ */
/*  Context                                                            */
/* ------------------------------------------------------------------ */
const ToastContext = createContext<ToastContextValue | undefined>(undefined)

/* ------------------------------------------------------------------ */
/*  Provider                                                           */
/* ------------------------------------------------------------------ */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const addToast = useCallback((opts: Omit<Toast, 'id'>) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
    setToasts((prev) => [...prev, { ...opts, id }])
  }, [])

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const ctx: ToastContextValue = {
    toast: addToast,
    success: (description, title) =>
      addToast({ description, title, variant: 'success' }),
    error: (description, title) =>
      addToast({ description, title, variant: 'error' }),
    warning: (description, title) =>
      addToast({ description, title, variant: 'warning' }),
  }

  return (
    <ToastContext.Provider value={ctx}>
      <ToastPrimitive.Provider swipeDirection="right" duration={4000}>
        {children}

        {toasts.map((t) => (
          <ToastPrimitive.Root
            key={t.id}
            className={toastVariantClasses[t.variant]}
            onOpenChange={(open) => {
              if (!open) removeToast(t.id)
            }}
          >
            <div className="flex-1">
              {t.title && (
                <ToastPrimitive.Title className="text-sm font-semibold mb-0.5">
                  {t.title}
                </ToastPrimitive.Title>
              )}
              <ToastPrimitive.Description className="text-sm opacity-90">
                {t.description}
              </ToastPrimitive.Description>
            </div>
            <ToastPrimitive.Close
              className="rounded p-1 opacity-60 hover:opacity-100 transition"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </ToastPrimitive.Close>
          </ToastPrimitive.Root>
        ))}

        <ToastPrimitive.Viewport className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 w-[360px] max-w-[calc(100vw-2rem)]" />
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  )
}

/* ------------------------------------------------------------------ */
/*  Hook                                                               */
/* ------------------------------------------------------------------ */
export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}

/* ------------------------------------------------------------------ */
/*  Variant styles                                                     */
/* ------------------------------------------------------------------ */
const base =
  'flex items-start gap-3 rounded-lg border px-4 py-3 shadow-lg backdrop-blur-sm ' +
  'data-[state=open]:animate-in data-[state=closed]:animate-out ' +
  'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 ' +
  'data-[state=closed]:slide-out-to-right-full data-[state=open]:slide-in-from-right-full'

const toastVariantClasses: Record<ToastVariant, string> = {
  default: `${base} bg-card text-card-foreground border-border`,
  success: `${base} bg-emerald-50 dark:bg-emerald-950/60 text-emerald-900 dark:text-emerald-100 border-emerald-200 dark:border-emerald-800`,
  error: `${base} bg-red-50 dark:bg-red-950/60 text-red-900 dark:text-red-100 border-red-200 dark:border-red-800`,
  warning: `${base} bg-amber-50 dark:bg-amber-950/60 text-amber-900 dark:text-amber-100 border-amber-200 dark:border-amber-800`,
}
