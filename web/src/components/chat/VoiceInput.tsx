'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { Mic, Square, Loader2 } from 'lucide-react';
import api from '@/lib/api';

type VoiceState = 'idle' | 'recording' | 'transcribing';

interface VoiceInputProps {
  onTranscription: (text: string) => void;
  disabled?: boolean;
  token: string;
}

function getSupportedMimeType(): string {
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4',
    'audio/ogg;codecs=opus',
  ];
  for (const mime of candidates) {
    if (MediaRecorder.isTypeSupported(mime)) return mime;
  }
  return '';
}

export default function VoiceInput({ onTranscription, disabled, token }: VoiceInputProps) {
  const [state, setState] = useState<VoiceState>('idle');
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const mediaRecorder = useRef<MediaRecorder | null>(null);
  const audioChunks = useRef<Blob[]>([]);
  const stream = useRef<MediaStream | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (stream.current) stream.current.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const startRecording = useCallback(async () => {
    setError(null);

    try {
      const audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.current = audioStream;

      const mimeType = getSupportedMimeType();
      const recorder = mimeType
        ? new MediaRecorder(audioStream, { mimeType })
        : new MediaRecorder(audioStream);

      audioChunks.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.current.push(e.data);
      };

      recorder.onstop = async () => {
        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }
        audioStream.getTracks().forEach((t) => t.stop());
        stream.current = null;

        const blob = new Blob(audioChunks.current, {
          type: recorder.mimeType || 'audio/webm',
        });

        if (blob.size < 100) {
          setError('Recording too short');
          setState('idle');
          setElapsed(0);
          return;
        }

        setState('transcribing');
        try {
          const result = await api.voice.transcribe(token, blob);
          if (result.text) {
            onTranscription(result.text);
          } else {
            setError('No speech detected');
          }
        } catch {
          setError('Transcription failed');
        } finally {
          setState('idle');
          setElapsed(0);
        }
      };

      mediaRecorder.current = recorder;
      recorder.start(250);
      setState('recording');
      setElapsed(0);

      timerRef.current = setInterval(() => {
        setElapsed((prev) => prev + 1);
      }, 1000);
    } catch {
      setError('Microphone access denied');
      setState('idle');
    }
  }, [token, onTranscription]);

  const stopRecording = useCallback(() => {
    if (mediaRecorder.current && mediaRecorder.current.state !== 'inactive') {
      mediaRecorder.current.stop();
    }
  }, []);

  const handleClick = useCallback(() => {
    if (state === 'idle') {
      startRecording();
    } else if (state === 'recording') {
      stopRecording();
    }
  }, [state, startRecording, stopRecording]);

  const isDisabled = disabled || state === 'transcribing';

  return (
    <div className="relative flex items-center">
      <button
        type="button"
        onClick={handleClick}
        disabled={isDisabled}
        className={`p-2 rounded-lg transition-colors ${
          state === 'recording'
            ? 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 animate-pulse'
            : state === 'transcribing'
            ? 'text-gray-400 cursor-wait'
            : 'text-gray-500 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-gray-100 dark:hover:bg-gray-800'
        } disabled:opacity-50 disabled:cursor-not-allowed`}
        aria-label={
          state === 'recording' ? 'Stop recording' : state === 'transcribing' ? 'Transcribing...' : 'Start voice input'
        }
        title={
          state === 'recording'
            ? `Recording... ${elapsed}s (click to stop)`
            : state === 'transcribing'
            ? 'Transcribing audio...'
            : 'Voice input'
        }
      >
        {state === 'recording' ? (
          <div className="flex items-center gap-1.5">
            <Square className="h-4 w-4 fill-current" />
            <span className="text-xs font-mono tabular-nums">{elapsed}s</span>
          </div>
        ) : state === 'transcribing' ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Mic className="h-4 w-4" />
        )}
      </button>

      {error && (
        <div
          className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 whitespace-nowrap px-2 py-1 text-xs rounded bg-red-100 dark:bg-red-900/50 text-red-700 dark:text-red-300 shadow-sm"
          onAnimationEnd={() => setError(null)}
          style={{ animation: 'fadeOut 3s forwards' }}
        >
          {error}
        </div>
      )}

      <style jsx>{`
        @keyframes fadeOut {
          0%, 70% { opacity: 1; }
          100% { opacity: 0; }
        }
      `}</style>
    </div>
  );
}
