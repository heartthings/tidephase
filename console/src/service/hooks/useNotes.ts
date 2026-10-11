import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';

import { createNote, deleteNote, fetchNoteList, topNote, updateNote } from '../api/note';
import type { NoteItem } from '../api/notes';
import { analyzeNotes } from '../api/notes';

export const QUERY_KEY = 'trading-notes';

export function useNotes(params?: { categoryId?: string; date?: string; keyword?: string }) {
  return useQuery({
    queryFn: async () => {
      const date = params?.date || dayjs().format('YYYY-MM-DD');
      const list = await fetchNoteList({ categoryId: params?.categoryId, date, limit: 100 });
      if (params?.keyword) {
        const kw = params.keyword.toLowerCase();
        return list.filter(
          n =>
            n.title.toLowerCase().includes(kw) ||
            n.content.toLowerCase().includes(kw) ||
            n.tags.join(',').toLowerCase().includes(kw)
        );
      }
      return list;
    },
    queryKey: [QUERY_KEY, params],
    staleTime: 0
  });
}

export function useNoteMutations() {
  const queryClient = useQueryClient();

  const addMutation = useMutation({
    mutationFn: (data: { categoryId: string; content: string; tags: string[]; title: string }) => createNote(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY] });
    }
  });

  const updateMutation = useMutation({
    mutationFn: (vars: { data: Partial<NoteItem>; id: string }) =>
      updateNote(vars.id, {
        categoryId: vars.data.categoryId,
        content: vars.data.content,
        tags: vars.data.tags,
        title: vars.data.title
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY] });
    }
  });
  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteNote(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY] });
    }
  });

  const topMutation = useMutation({
    mutationFn: (id: string) => topNote(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY] });
    }
  });

  return {
    add: addMutation,
    delete: deleteMutation,
    top: topMutation,
    update: updateMutation
  };
}

export function useNoteAnalysis() {
  return useMutation({
    mutationFn: analyzeNotes
  });
}
