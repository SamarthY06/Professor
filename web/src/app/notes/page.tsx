'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { 
  Plus, Search, Pin, Trash2, Edit, Book, Target, 
  ChevronDown, Calendar, Tag, MoreVertical, Download,
  ArrowLeft, FileText, Quote, Code, List, Type, Loader2,
  Brain, ExternalLink, Copy, Check
} from 'lucide-react';
import { notesStore, NotePage, NoteBlock } from '@/lib/notes-store';

export default function NotesPage() {
  const [notes, setNotes] = useState<NotePage[]>([]);
  const [filteredNotes, setFilteredNotes] = useState<NotePage[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterSource, setFilterSource] = useState<'all' | 'books' | 'goals'>('all');
  const [showPinnedOnly, setShowPinnedOnly] = useState(false);
  const [selectedNote, setSelectedNote] = useState<NotePage | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [editContent, setEditContent] = useState({ title: '', content: '', tags: '' });
  const [copied, setCopied] = useState(false);

  // Load notes from IndexedDB
  useEffect(() => {
    const loadNotes = async () => {
      try {
        setIsLoading(true);
        const pages = await notesStore.getAllPages();
        setNotes(pages);
      } catch (error) {
        console.error('Failed to load notes:', error);
      } finally {
        setIsLoading(false);
      }
    };

    loadNotes();
  }, []);

  // Filter notes
  useEffect(() => {
    let filtered = [...notes];
    
    if (filterSource === 'books') {
      filtered = filtered.filter((n) => n.book_id);
    } else if (filterSource === 'goals') {
      filtered = filtered.filter((n) => n.goal_id);
    }
    
    if (showPinnedOnly) {
      filtered = filtered.filter((n) => n.is_pinned);
    }
    
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (n) =>
          n.title.toLowerCase().includes(query) ||
          n.content.toLowerCase().includes(query) ||
          n.tags.some((t) => t.toLowerCase().includes(query))
      );
    }
    
    filtered.sort((a, b) => {
      if (a.is_pinned && !b.is_pinned) return -1;
      if (!a.is_pinned && b.is_pinned) return 1;
      return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
    });
    
    setFilteredNotes(filtered);
  }, [notes, searchQuery, filterSource, showPinnedOnly]);

  const handleTogglePin = async (noteId: string) => {
    try {
      const updated = await notesStore.togglePin(noteId);
      if (updated) {
        setNotes((prev) =>
          prev.map((n) => (n.id === noteId ? updated : n))
        );
        if (selectedNote?.id === noteId) {
          setSelectedNote(updated);
        }
      }
    } catch (error) {
      console.error('Failed to toggle pin:', error);
    }
  };

  const handleDeleteNote = async (noteId: string) => {
    if (confirm('Are you sure you want to delete this note?')) {
      try {
        await notesStore.deletePage(noteId);
        setNotes((prev) => prev.filter((n) => n.id !== noteId));
        if (selectedNote?.id === noteId) {
          setSelectedNote(null);
        }
      } catch (error) {
        console.error('Failed to delete note:', error);
      }
    }
  };

  const handleEditNote = (note: NotePage) => {
    setSelectedNote(note);
    setEditContent({
      title: note.title,
      content: note.content,
      tags: note.tags.join(', '),
    });
    setIsEditing(true);
  };

  const handleSaveNote = async () => {
    if (!selectedNote) return;
    
    try {
      const updated = await notesStore.updatePage(selectedNote.id, {
        title: editContent.title,
        content: editContent.content,
        tags: editContent.tags.split(',').map((t) => t.trim()).filter(Boolean),
      });

      if (updated) {
        setNotes((prev) =>
          prev.map((n) => (n.id === selectedNote.id ? updated : n))
        );
        setSelectedNote(updated);
      }
      setIsEditing(false);
    } catch (error) {
      console.error('Failed to save note:', error);
    }
  };

  const handleCreateNote = async () => {
    try {
      const newNote = await notesStore.createPage({
        title: 'Untitled Note',
        content: '',
        blocks: [{ id: '1', type: 'text', content: '' }],
      });
      
      setNotes((prev) => [newNote, ...prev]);
      handleEditNote(newNote);
    } catch (error) {
      console.error('Failed to create note:', error);
    }
  };

  const handleExportMarkdown = (note: NotePage) => {
    const markdown = notesStore.exportAsMarkdown(note);
    const blob = new Blob([markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${note.title.replace(/[^a-z0-9]/gi, '_')}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleCopyContent = async (note: NotePage) => {
    try {
      await navigator.clipboard.writeText(note.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error('Failed to copy:', error);
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: date.getFullYear() !== new Date().getFullYear() ? 'numeric' : undefined,
    });
  };

  // Render block content
  const renderBlock = (block: NoteBlock) => {
    switch (block.type) {
      case 'heading':
        const HeadingTag = `h${block.metadata?.level || 2}` as keyof JSX.IntrinsicElements;
        return <HeadingTag className="font-bold my-2">{block.content}</HeadingTag>;
      case 'quote':
        return (
          <blockquote className="border-l-4 border-blue-400 pl-4 py-2 my-2 bg-blue-50 rounded-r-lg italic">
            {block.content}
          </blockquote>
        );
      case 'code':
        return (
          <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg my-2 overflow-x-auto">
            <code>{block.content}</code>
          </pre>
        );
      case 'list':
        return (
          <ul className="list-disc list-inside my-2">
            {block.content.split('\n').map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        );
      case 'highlight':
        return (
          <mark className="bg-yellow-200 px-1 rounded">
            {block.content}
          </mark>
        );
      case 'divider':
        return <hr className="my-4 border-gray-200" />;
      default:
        return <p className="my-2 whitespace-pre-wrap">{block.content}</p>;
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin text-blue-600 mx-auto mb-4" />
          <p className="text-gray-600">Loading your notes...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 flex">
      {/* Sidebar - Notes List */}
      <div className="w-96 bg-white border-r flex flex-col h-screen">
        {/* Header */}
        <div className="p-4 border-b">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Link href="/dashboard" className="p-2 hover:bg-gray-100 rounded-lg">
                <ArrowLeft className="h-4 w-4" />
              </Link>
              <h1 className="text-xl font-bold">My Notes</h1>
            </div>
            
            <button
              onClick={handleCreateNote}
              className="p-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>
          
          {/* Search */}
          <div className="relative mb-3">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="Search notes..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-100"
            />
          </div>
          
          {/* Filters */}
          <div className="flex items-center gap-2">
            <select
              value={filterSource}
              onChange={(e) => setFilterSource(e.target.value as typeof filterSource)}
              className="flex-1 px-3 py-1.5 text-sm border rounded-lg"
            >
              <option value="all">All Sources</option>
              <option value="books">From Books</option>
              <option value="goals">From Goals</option>
            </select>
            
            <button
              onClick={() => setShowPinnedOnly(!showPinnedOnly)}
              className={`p-2 border rounded-lg ${showPinnedOnly ? 'bg-blue-50 border-blue-300' : ''}`}
            >
              <Pin className="w-4 h-4" />
            </button>
          </div>
        </div>
        
        {/* Notes List */}
        <div className="flex-1 overflow-y-auto">
          {filteredNotes.length === 0 ? (
            <div className="p-8 text-center">
              <FileText className="w-12 h-12 mx-auto mb-4 text-gray-300" />
              <p className="text-gray-500 mb-2">
                {searchQuery ? 'No notes found' : 'No notes yet'}
              </p>
              <p className="text-sm text-gray-400 mb-4">
                Select text while learning to save notes
              </p>
            </div>
          ) : (
            <div className="divide-y">
              {filteredNotes.map((note) => (
                <button
                  key={note.id}
                  onClick={() => {
                    setSelectedNote(note);
                    setIsEditing(false);
                  }}
                  className={`w-full p-4 text-left hover:bg-gray-50 transition ${
                    selectedNote?.id === note.id ? 'bg-blue-50' : ''
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="font-medium line-clamp-1 flex-1">{note.title}</h3>
                    {note.is_pinned && <Pin className="w-3 h-3 text-blue-500 flex-shrink-0" />}
                  </div>
                  
                  {note.book_title && (
                    <div className="flex items-center gap-1 text-xs text-gray-500 mt-1">
                      <Book className="w-3 h-3" />
                      <span className="line-clamp-1">
                        {note.book_title}
                        {note.chapter_number && ` • Ch. ${note.chapter_number}`}
                      </span>
                    </div>
                  )}
                  
                  <p className="text-sm text-gray-500 line-clamp-2 mt-1">
                    {note.content}
                  </p>
                  
                  <div className="flex items-center gap-2 mt-2 text-xs text-gray-400">
                    <Calendar className="w-3 h-3" />
                    {formatDate(note.updated_at)}
                    {note.source_agent && (
                      <>
                        <span>•</span>
                        <Brain className="w-3 h-3" />
                        {note.source_agent}
                      </>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
        
        {/* Stats */}
        <div className="p-4 border-t text-sm text-gray-500">
          {notes.length} notes • {notes.filter(n => n.is_pinned).length} pinned
        </div>
      </div>
      
      {/* Main Content - Note View/Edit */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        {selectedNote ? (
          <>
            {/* Note Header */}
            <div className="bg-white border-b px-6 py-4 flex items-center justify-between">
              <div className="flex-1">
                {isEditing ? (
                  <input
                    type="text"
                    value={editContent.title}
                    onChange={(e) => setEditContent({ ...editContent, title: e.target.value })}
                    className="text-xl font-bold w-full border-b-2 border-blue-300 focus:outline-none pb-1"
                    autoFocus
                  />
                ) : (
                  <h2 className="text-xl font-bold">{selectedNote.title}</h2>
                )}
                
                {selectedNote.book_title && (
                  <div className="flex items-center gap-2 text-sm text-gray-500 mt-1">
                    <Book className="w-4 h-4" />
                    <span>{selectedNote.book_title}</span>
                    {selectedNote.chapter_number && (
                      <span>• Chapter {selectedNote.chapter_number}</span>
                    )}
                  </div>
                )}
              </div>
              
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleTogglePin(selectedNote.id)}
                  className={`p-2 rounded-lg hover:bg-gray-100 ${
                    selectedNote.is_pinned ? 'text-blue-500' : 'text-gray-400'
                  }`}
                >
                  <Pin className="w-5 h-5" />
                </button>
                
                <button
                  onClick={() => handleCopyContent(selectedNote)}
                  className="p-2 rounded-lg hover:bg-gray-100 text-gray-400"
                  title="Copy content"
                >
                  {copied ? <Check className="w-5 h-5 text-green-500" /> : <Copy className="w-5 h-5" />}
                </button>
                
                <button
                  onClick={() => handleExportMarkdown(selectedNote)}
                  className="p-2 rounded-lg hover:bg-gray-100 text-gray-400"
                  title="Export as Markdown"
                >
                  <Download className="w-5 h-5" />
                </button>
                
                {isEditing ? (
                  <>
                    <button
                      onClick={() => setIsEditing(false)}
                      className="px-3 py-1.5 text-sm border rounded-lg hover:bg-gray-50"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleSaveNote}
                      className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                    >
                      Save
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={() => handleEditNote(selectedNote)}
                      className="p-2 rounded-lg hover:bg-gray-100 text-gray-400"
                    >
                      <Edit className="w-5 h-5" />
                    </button>
                    <button
                      onClick={() => handleDeleteNote(selectedNote.id)}
                      className="p-2 rounded-lg hover:bg-gray-100 text-red-400"
                    >
                      <Trash2 className="w-5 h-5" />
                    </button>
                  </>
                )}
              </div>
            </div>
            
            {/* Note Content */}
            <div className="flex-1 overflow-y-auto p-6">
              <div className="max-w-3xl mx-auto">
                {/* Tags */}
                {isEditing ? (
                  <div className="mb-6">
                    <label className="block text-sm font-medium text-gray-600 mb-1">Tags</label>
                    <input
                      type="text"
                      value={editContent.tags}
                      onChange={(e) => setEditContent({ ...editContent, tags: e.target.value })}
                      placeholder="e.g., important, chapter-5, review"
                      className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-100"
                    />
                  </div>
                ) : selectedNote.tags.length > 0 ? (
                  <div className="flex flex-wrap gap-2 mb-6">
                    {selectedNote.tags.map((tag) => (
                      <span key={tag} className="px-2 py-1 text-xs bg-gray-100 text-gray-600 rounded-full">
                        #{tag}
                      </span>
                    ))}
                  </div>
                ) : null}
                
                {/* Source Info */}
                {selectedNote.source_agent && !isEditing && (
                  <div className="mb-6 p-3 bg-blue-50 rounded-lg text-sm">
                    <div className="flex items-center gap-2 text-blue-700">
                      <Brain className="w-4 h-4" />
                      <span>Saved from {selectedNote.source_agent} response</span>
                    </div>
                    {selectedNote.source_timestamp && (
                      <div className="text-blue-600 text-xs mt-1">
                        {new Date(selectedNote.source_timestamp).toLocaleString()}
                      </div>
                    )}
                  </div>
                )}
                
                {/* Blocks/Content */}
                {isEditing ? (
                  <textarea
                    value={editContent.content}
                    onChange={(e) => setEditContent({ ...editContent, content: e.target.value })}
                    className="w-full min-h-[400px] p-4 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-100 resize-none font-mono text-sm"
                    placeholder="Write your notes here..."
                  />
                ) : (
                  <div className="prose prose-sm max-w-none">
                    {selectedNote.blocks.length > 0 ? (
                      selectedNote.blocks.map((block) => (
                        <div key={block.id}>{renderBlock(block)}</div>
                      ))
                    ) : (
                      <p className="whitespace-pre-wrap">{selectedNote.content}</p>
                    )}
                  </div>
                )}
                
                {/* Metadata */}
                {!isEditing && (
                  <div className="mt-8 pt-4 border-t text-xs text-gray-400">
                    <div>Created: {new Date(selectedNote.created_at).toLocaleString()}</div>
                    <div>Updated: {new Date(selectedNote.updated_at).toLocaleString()}</div>
                    {!selectedNote.is_synced && (
                      <div className="text-yellow-600 mt-1">⚠ Stored locally only</div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <FileText className="w-16 h-16 mx-auto mb-4 text-gray-200" />
              <h3 className="text-lg font-medium text-gray-600 mb-2">Select a note</h3>
              <p className="text-sm text-gray-400">
                Choose a note from the sidebar to view or edit
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
