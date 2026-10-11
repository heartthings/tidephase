import dayjs from 'dayjs';

// no storage utils import to avoid type constraints; use localStorage directly

import { fetchNoteList } from './note';

export async function buildTodayNotesJson() {
  const date = dayjs().format('YYYY-MM-DD');
  const list = await fetchNoteList({ date, limit: 100 });
  const payload = list.map(item => ({
    categoryId: item.categoryId || '',
    content: item.content,
    createdTime: dayjs(item.createTime).format('YYYY-MM-DDTHH:mm:ss'),
    tags: Array.isArray(item.tags) ? item.tags.join(',') : '',
    title: item.title
  }));
  return JSON.stringify(payload);
}

export async function coachCompletionStream(notesJson: string, onChunk: (text: string) => void) {
  const apiKey =
    (localStorage.getItem('DASHSCOPE_API_KEY') as string) || (import.meta.env.VITE_DASHSCOPE_API_KEY as string);
  const res = await fetch('https://dashscope.aliyuncs.com/api/v1/apps/710325aaa6634d3fb42a256dfd68e2dc/completion', {
    body: JSON.stringify({
      debug: {},
      input: { prompt: { query: JSON.parse(notesJson) } },
      parameters: { incremental_output: true }
    }),
    headers: {
      Accept: 'text/event-stream',
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json'
    },
    method: 'POST'
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(text || `HTTP ${res.status}`);
  }
  const reader = res.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  async function pump(r: ReadableStreamDefaultReader<Uint8Array>) {
    const { done, value } = await r.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split(/\r?\n\r?\n/);
    buffer = parts.pop() || '';
    parts.forEach(part => {
      const line = part.split(/\r?\n/).find(l => l.startsWith('data:'));
      if (!line) return;
      const jsonStr = line.slice(5).trim();
      if (!jsonStr) return;
      try {
        const obj = JSON.parse(jsonStr);
        const text = obj?.output?.text;
        if (typeof text === 'string' && text.length > 0) {
          onChunk(text);
        }
      } catch {
        // ignore
      }
    });
    await pump(r);
  }
  await pump(reader);
  if (buffer) {
    const line = buffer.split(/\r?\n/).find(l => l.startsWith('data:'));
    const jsonStr = line ? line.slice(5).trim() : '';
    if (jsonStr) {
      try {
        const obj = JSON.parse(jsonStr);
        const text = obj?.output?.text;
        if (typeof text === 'string' && text.length > 0) {
          onChunk(text);
        }
      } catch {}
    }
  }
}
