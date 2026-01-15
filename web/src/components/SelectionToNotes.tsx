'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { BookmarkPlus, Check, Loader2 } from 'lucide-react';
import { notesStore, NotePage } from '@/lib/notes-store';

interface SelectionToNotesProps {
  containerRef: React.RefObject<HTMLElement>;
  context: {
    bookId?: string;
    bookTitle?: string;
    chapterId?: string;
    chapterNumber?: number;
    chapterTitle?: string;
  };
  onNoteSaved?: (note: NotePage) => void;
}

interface PopupPosition {
  x: number;
  y: number;
}

export default function SelectionToNotes({ 
  containerRef, 
  context, 
  onNoteSaved 
}: SelectionToNotesProps) {
  const [showPopup, setShowPopup] = useState(false);
  const [position, setPosition] = useState<PopupPosition>({ x: 0, y: 0 });
  const [selectedText, setSelectedText] = useState('');
  const [fullMessageContent, setFullMessageContent] = useState('');
  const [messageId, setMessageId] = useState<string>('');
  const [agentName, setAgentName] = useState<string>('');
  const [isSaving, setIsSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const popupRef = useRef<HTMLDivElement>(null);

  const handleSelection = useCallback(() => {
    const selection = window.getSelection();
    
    if (!selection || selection.isCollapsed || !containerRef.current) {
      setShowPopup(false);
      return;
    }

    const text = selection.toString().trim();
    if (text.length < 10) {
      setShowPopup(false);
      return;
    }

    // Check if selection is within our container
    const anchorNode = selection.anchorNode;
    const focusNode = selection.focusNode;
    
    if (!anchorNode || !focusNode) {
      setShowPopup(false);
      return;
    }

    const isInContainer = 
      containerRef.current.contains(anchorNode) && 
      containerRef.current.contains(focusNode);
    
    if (!isInContainer) {
      setShowPopup(false);
      return;
    }

    // Find the message element
    let messageElement = anchorNode.parentElement;
    while (messageElement && !messageElement.dataset.messageId) {
      messageElement = messageElement.parentElement;
    }

    if (messageElement) {
      setMessageId(messageElement.dataset.messageId || '');
      setAgentName(messageElement.dataset.agentName || '');
      setFullMessageContent(messageElement.textContent || text);
    }

    // Calculate position for popup
    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    
    setPosition({
      x: rect.left + rect.width / 2,
      y: rect.top - 10,
    });

    setSelectedText(text);
    setShowPopup(true);
    setSaved(false);
  }, [containerRef]);

  const handleSaveToNotes = async () => {
    if (!selectedText || isSaving) return;

    setIsSaving(true);
    
    try {
      const note = await notesStore.createFromSelection({
        selectedText,
        messageContent: fullMessageContent,
        messageId,
        agentName: agentName || undefined,
        bookId: context.bookId,
        bookTitle: context.bookTitle,
        chapterId: context.chapterId,
        chapterNumber: context.chapterNumber,
        chapterTitle: context.chapterTitle,
      });

      setSaved(true);
      onNoteSaved?.(note);

      // Clear selection and hide popup after a moment
      setTimeout(() => {
        window.getSelection()?.removeAllRanges();
        setShowPopup(false);
      }, 1000);
    } catch (error) {
      console.error('Failed to save note:', error);
    } finally {
      setIsSaving(false);
    }
  };

  // Listen for selection changes
  useEffect(() => {
    document.addEventListener('mouseup', handleSelection);
    document.addEventListener('keyup', handleSelection);

    return () => {
      document.removeEventListener('mouseup', handleSelection);
      document.removeEventListener('keyup', handleSelection);
    };
  }, [handleSelection]);

  // Close popup when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (popupRef.current && !popupRef.current.contains(e.target as Node)) {
        setShowPopup(false);
      }
    };

    if (showPopup) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showPopup]);

  if (!showPopup) return null;

  return (
    <div
      ref={popupRef}
      className="fixed z-50 transform -translate-x-1/2 -translate-y-full"
      style={{ left: position.x, top: position.y }}
    >
      <div className="bg-gray-900 text-white rounded-lg shadow-xl p-1 flex items-center gap-1 animate-fadeIn">
        <button
          onClick={handleSaveToNotes}
          disabled={isSaving || saved}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-md transition-colors ${
            saved 
              ? 'bg-green-600 text-white' 
              : 'hover:bg-gray-700'
          }`}
          title="Save to Notes"
        >
          {isSaving ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : saved ? (
            <Check className="w-4 h-4" />
          ) : (
            <BookmarkPlus className="w-4 h-4" />
          )}
          <span className="text-sm font-medium">
            {saved ? 'Saved!' : 'Save to Notes'}
          </span>
        </button>
      </div>
      
      {/* Arrow pointing down */}
      <div 
        className="absolute left-1/2 transform -translate-x-1/2 w-0 h-0 
                   border-l-8 border-r-8 border-t-8 
                   border-l-transparent border-r-transparent border-t-gray-900"
        style={{ top: '100%' }}
      />
    </div>
  );
}
