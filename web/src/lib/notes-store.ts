/**
 * Local Notes Store - Stores notes as pages locally with IndexedDB
 * Notes are synced with backend but also available offline
 */

export interface NotePage {
  id: string;
  title: string;
  content: string; // Markdown content
  blocks: NoteBlock[]; // Structured blocks like Notion
  
  // Context
  book_id?: string;
  book_title?: string;
  chapter_id?: string;
  chapter_number?: number;
  chapter_title?: string;
  goal_id?: string;
  goal_title?: string;
  
  // Source tracking
  source_message_id?: string;
  source_agent?: string;
  source_timestamp?: string;
  
  // Metadata
  tags: string[];
  is_pinned: boolean;
  is_synced: boolean;
  created_at: string;
  updated_at: string;
}

export interface NoteBlock {
  id: string;
  type: 'text' | 'heading' | 'quote' | 'code' | 'list' | 'highlight' | 'divider';
  content: string;
  metadata?: {
    language?: string; // For code blocks
    level?: number; // For headings (1-3)
    style?: 'bullet' | 'numbered'; // For lists
    color?: string; // For highlights
  };
}

// IndexedDB database name and store
const DB_NAME = 'professor_notes';
const STORE_NAME = 'pages';
const DB_VERSION = 1;

class NotesStore {
  private db: IDBDatabase | null = null;
  private initPromise: Promise<void> | null = null;

  async init(): Promise<void> {
    if (this.db) return;
    if (this.initPromise) return this.initPromise;

    this.initPromise = new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);

      request.onerror = () => {
        console.error('Failed to open IndexedDB:', request.error);
        reject(request.error);
      };

      request.onsuccess = () => {
        this.db = request.result;
        resolve();
      };

      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;
        
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          const store = db.createObjectStore(STORE_NAME, { keyPath: 'id' });
          store.createIndex('book_id', 'book_id', { unique: false });
          store.createIndex('chapter_id', 'chapter_id', { unique: false });
          store.createIndex('goal_id', 'goal_id', { unique: false });
          store.createIndex('is_pinned', 'is_pinned', { unique: false });
          store.createIndex('updated_at', 'updated_at', { unique: false });
        }
      };
    });

    return this.initPromise;
  }

  private async getStore(mode: IDBTransactionMode = 'readonly'): Promise<IDBObjectStore> {
    await this.init();
    if (!this.db) throw new Error('Database not initialized');
    const tx = this.db.transaction(STORE_NAME, mode);
    return tx.objectStore(STORE_NAME);
  }

  // Create a new note page
  async createPage(data: Partial<NotePage>): Promise<NotePage> {
    const page: NotePage = {
      id: `note_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      title: data.title || 'Untitled Note',
      content: data.content || '',
      blocks: data.blocks || [],
      book_id: data.book_id,
      book_title: data.book_title,
      chapter_id: data.chapter_id,
      chapter_number: data.chapter_number,
      chapter_title: data.chapter_title,
      goal_id: data.goal_id,
      goal_title: data.goal_title,
      source_message_id: data.source_message_id,
      source_agent: data.source_agent,
      source_timestamp: data.source_timestamp,
      tags: data.tags || [],
      is_pinned: data.is_pinned || false,
      is_synced: false,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    const store = await this.getStore('readwrite');
    
    return new Promise((resolve, reject) => {
      const request = store.add(page);
      request.onsuccess = () => resolve(page);
      request.onerror = () => reject(request.error);
    });
  }

  // Create a note from selected text in chat
  async createFromSelection(data: {
    selectedText: string;
    messageContent: string;
    messageId: string;
    agentName?: string;
    bookId?: string;
    bookTitle?: string;
    chapterId?: string;
    chapterNumber?: number;
    chapterTitle?: string;
  }): Promise<NotePage> {
    // Auto-generate title from first line or first 50 chars
    const firstLine = data.selectedText.split('\n')[0].trim();
    const title = firstLine.length > 50 
      ? firstLine.substring(0, 50) + '...'
      : firstLine || 'Note from Learning Session';

    // Create structured blocks
    const blocks: NoteBlock[] = [
      {
        id: `block_${Date.now()}_1`,
        type: 'quote',
        content: data.selectedText,
        metadata: { color: 'blue' },
      },
    ];

    // If there's surrounding context, add it
    if (data.messageContent !== data.selectedText) {
      blocks.push({
        id: `block_${Date.now()}_2`,
        type: 'text',
        content: '\n---\n*Context from the full response:*',
      });
      blocks.push({
        id: `block_${Date.now()}_3`,
        type: 'text',
        content: data.messageContent.substring(0, 500) + (data.messageContent.length > 500 ? '...' : ''),
      });
    }

    return this.createPage({
      title,
      content: data.selectedText,
      blocks,
      book_id: data.bookId,
      book_title: data.bookTitle,
      chapter_id: data.chapterId,
      chapter_number: data.chapterNumber,
      chapter_title: data.chapterTitle,
      source_message_id: data.messageId,
      source_agent: data.agentName,
      source_timestamp: new Date().toISOString(),
      tags: data.agentName ? [data.agentName.toLowerCase()] : [],
    });
  }

  // Get all pages
  async getAllPages(): Promise<NotePage[]> {
    const store = await this.getStore();
    
    return new Promise((resolve, reject) => {
      const request = store.getAll();
      request.onsuccess = () => {
        const pages = request.result as NotePage[];
        // Sort by pinned first, then updated_at desc
        pages.sort((a, b) => {
          if (a.is_pinned && !b.is_pinned) return -1;
          if (!a.is_pinned && b.is_pinned) return 1;
          return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
        });
        resolve(pages);
      };
      request.onerror = () => reject(request.error);
    });
  }

  // Get page by ID
  async getPage(id: string): Promise<NotePage | null> {
    const store = await this.getStore();
    
    return new Promise((resolve, reject) => {
      const request = store.get(id);
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(request.error);
    });
  }

  // Get pages by book
  async getPagesByBook(bookId: string): Promise<NotePage[]> {
    const store = await this.getStore();
    const index = store.index('book_id');
    
    return new Promise((resolve, reject) => {
      const request = index.getAll(bookId);
      request.onsuccess = () => resolve(request.result as NotePage[]);
      request.onerror = () => reject(request.error);
    });
  }

  // Get pages by chapter
  async getPagesByChapter(chapterId: string): Promise<NotePage[]> {
    const store = await this.getStore();
    const index = store.index('chapter_id');
    
    return new Promise((resolve, reject) => {
      const request = index.getAll(chapterId);
      request.onsuccess = () => resolve(request.result as NotePage[]);
      request.onerror = () => reject(request.error);
    });
  }

  // Update a page
  async updatePage(id: string, updates: Partial<NotePage>): Promise<NotePage | null> {
    const page = await this.getPage(id);
    if (!page) return null;

    const updatedPage: NotePage = {
      ...page,
      ...updates,
      updated_at: new Date().toISOString(),
      is_synced: false, // Mark as needing sync
    };

    const store = await this.getStore('readwrite');
    
    return new Promise((resolve, reject) => {
      const request = store.put(updatedPage);
      request.onsuccess = () => resolve(updatedPage);
      request.onerror = () => reject(request.error);
    });
  }

  // Delete a page
  async deletePage(id: string): Promise<boolean> {
    const store = await this.getStore('readwrite');
    
    return new Promise((resolve, reject) => {
      const request = store.delete(id);
      request.onsuccess = () => resolve(true);
      request.onerror = () => reject(request.error);
    });
  }

  // Toggle pin status
  async togglePin(id: string): Promise<NotePage | null> {
    const page = await this.getPage(id);
    if (!page) return null;
    return this.updatePage(id, { is_pinned: !page.is_pinned });
  }

  // Search pages
  async searchPages(query: string): Promise<NotePage[]> {
    const allPages = await this.getAllPages();
    const lowerQuery = query.toLowerCase();
    
    return allPages.filter(page => 
      page.title.toLowerCase().includes(lowerQuery) ||
      page.content.toLowerCase().includes(lowerQuery) ||
      page.tags.some(tag => tag.toLowerCase().includes(lowerQuery)) ||
      page.book_title?.toLowerCase().includes(lowerQuery) ||
      page.chapter_title?.toLowerCase().includes(lowerQuery)
    );
  }

  // Add a block to a page
  async addBlock(pageId: string, block: Omit<NoteBlock, 'id'>): Promise<NotePage | null> {
    const page = await this.getPage(pageId);
    if (!page) return null;

    const newBlock: NoteBlock = {
      ...block,
      id: `block_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    };

    return this.updatePage(pageId, {
      blocks: [...page.blocks, newBlock],
      content: page.content + '\n' + block.content,
    });
  }

  // Export page as markdown
  exportAsMarkdown(page: NotePage): string {
    let md = `# ${page.title}\n\n`;
    
    if (page.book_title) {
      md += `> 📚 From: ${page.book_title}`;
      if (page.chapter_number) md += ` - Chapter ${page.chapter_number}`;
      if (page.chapter_title) md += `: ${page.chapter_title}`;
      md += '\n\n';
    }

    if (page.tags.length > 0) {
      md += `Tags: ${page.tags.map(t => `#${t}`).join(' ')}\n\n`;
    }

    md += '---\n\n';

    for (const block of page.blocks) {
      switch (block.type) {
        case 'heading':
          md += `${'#'.repeat(block.metadata?.level || 2)} ${block.content}\n\n`;
          break;
        case 'quote':
          md += block.content.split('\n').map(line => `> ${line}`).join('\n') + '\n\n';
          break;
        case 'code':
          md += `\`\`\`${block.metadata?.language || ''}\n${block.content}\n\`\`\`\n\n`;
          break;
        case 'list':
          const prefix = block.metadata?.style === 'numbered' ? '1.' : '-';
          md += block.content.split('\n').map(line => `${prefix} ${line}`).join('\n') + '\n\n';
          break;
        case 'divider':
          md += '---\n\n';
          break;
        case 'highlight':
          md += `==${block.content}==\n\n`;
          break;
        default:
          md += block.content + '\n\n';
      }
    }

    md += `\n---\n*Created: ${new Date(page.created_at).toLocaleString()}*\n`;
    if (page.source_agent) {
      md += `*Source: ${page.source_agent}*\n`;
    }

    return md;
  }
}

// Singleton instance
export const notesStore = new NotesStore();
