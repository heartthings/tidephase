import { nanoid } from '@sa/utils';

export interface NoteItem {
  // timestamp
  category: string;
  categoryId?: string;
  content: string;
  createTime: number;
  id: string;
  tags: string[];
  title: string;
  // timestamp
  updateTime: number;
}

const STORAGE_KEY = 'trading_notes_data';

function getNotesFromStorage(): NoteItem[] {
  try {
    const data = localStorage.getItem(STORAGE_KEY);
    const arr = data ? JSON.parse(data) : [];
    return (arr as any[]).map(item => {
      return {
        ...item,
        tags: Array.isArray(item.tags) ? item.tags : [],
        title:
          typeof item.title === 'string' && item.title.length > 0
            ? item.title
            : String(item.content || '')
                .replace(/<[^>]+>/g, '')
                .slice(0, 8)
      } as NoteItem;
    });
  } catch {
    return [];
  }
}

function saveNotesToStorage(notes: NoteItem[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(notes));
}

export async function fetchNotes(params?: { date?: string; keyword?: string }) {
  // Simulate network delay
  await new Promise<void>(resolve => {
    setTimeout(resolve, 500);
  });

  let notes = getNotesFromStorage();

  // Filter by date
  if (params?.date) {
    // Assuming date is YYYY-MM-DD
    const targetDate = new Date(params.date).toDateString();
    notes = notes.filter(note => new Date(note.createTime).toDateString() === targetDate);
  }

  // Filter by keyword
  if (params?.keyword) {
    const lowerKeyword = params.keyword.toLowerCase();
    notes = notes.filter(
      note => note.content.toLowerCase().includes(lowerKeyword) || note.category.toLowerCase().includes(lowerKeyword)
    );
  }

  // Sort by time desc
  return notes.sort((a, b) => b.createTime - a.createTime);
}

export async function addNote(data: Omit<NoteItem, 'createTime' | 'id' | 'updateTime'>) {
  await new Promise<void>(resolve => {
    setTimeout(resolve, 300);
  });
  const notes = getNotesFromStorage();
  const newNote: NoteItem = {
    ...data,
    createTime: Date.now(),
    id: nanoid(),
    updateTime: Date.now()
  };
  if (!newNote.title || newNote.title.trim().length === 0) {
    const plain = newNote.content.replace(/<[^>]+>/g, '');
    newNote.title = plain.slice(0, 8);
  }
  if (!Array.isArray(newNote.tags)) {
    newNote.tags = [];
  }
  notes.unshift(newNote);
  saveNotesToStorage(notes);
  return newNote;
}

export async function updateNote(id: string, data: Partial<Omit<NoteItem, 'createTime' | 'id' | 'updateTime'>>) {
  await new Promise<void>(resolve => {
    setTimeout(resolve, 300);
  });
  const notes = getNotesFromStorage();
  const index = notes.findIndex(n => n.id === id);
  if (index > -1) {
    notes[index] = { ...notes[index], ...data, updateTime: Date.now() };
    saveNotesToStorage(notes);
    return notes[index];
  }
  throw new Error('Note not found');
}

export async function deleteNote(id: string) {
  await new Promise<void>(resolve => {
    setTimeout(resolve, 300);
  });
  const notes = getNotesFromStorage();
  const newNotes = notes.filter(n => n.id !== id);
  saveNotesToStorage(newNotes);
  return true;
}

export async function analyzeNotes(notes: NoteItem[]) {
  await new Promise<void>(resolve => {
    setTimeout(resolve, 1500);
  });

  if (notes.length === 0) {
    return '今天还没有任何笔记，无法进行分析。请先添加一些操盘记录。';
  }

  return `
    ## 操盘复盘与指导建议

    根据您今天的 ${notes.length} 条交易笔记，以下是投资教练总结：

    1. **交易频率**：${notes.length > 5 ? '交易较为频繁，请注意手续费成本和情绪管理。' : '交易频率适中，保持耐心。'}
    2. **主要关注点**：检测到您主要关注 ${[...new Set(notes.map(n => n.category))].join(', ')} 方面的动态。
    3. **情绪分析**：${notes.some(n => n.content.includes('止损') || n.content.includes('亏')) ? '检测到有止损或亏损记录，请保持冷静，严格执行交易纪律。' : '整体情绪稳定，继续保持。'}

    **建议**：
    - 建议复盘今日 ${new Date().toLocaleTimeString()} 之前的关键决策点。
    - 关注明日开盘的市场情绪指标。
  `;
}
