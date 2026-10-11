import { localStg } from '@/utils/storage';

import { request } from '../request';
import { NOTE_URLS } from '../urls';

import type { NoteItem } from './notes';

export interface NoteCategory {
  color: string;
  createdTime: string;
  description: string;
  id: string;
  name: string;
  sortOrder: number;
  status: number;
  updatedTime: string;
}

export function fetchEnabledNoteCategories() {
  return request<NoteCategory[]>({
    method: 'get',
    url: NOTE_URLS.GET_ENABLED_CATEGORIES
  });
}

export interface NoteListItem {
  categoryId: string;
  content: string;
  createdTime: string;
  id: string;
  tags: string;
  title: string;
  updatedTime: string;
}

export function fetchNoteList(params: { categoryId?: string; date: string; limit?: number }) {
  return request<NoteListItem[]>({
    method: 'get',
    params,
    url: NOTE_URLS.LIST
  }).then(list =>
    list.map(item => {
      const tags = item.tags
        ? item.tags
            .split(',')
            .map(s => s.trim())
            .filter(Boolean)
        : [];
      return {
        category: '',
        categoryId: item.categoryId,
        content: item.content,
        createTime: new Date(item.createdTime).getTime(),
        id: item.id,
        tags,
        title: item.title,
        updateTime: new Date(item.updatedTime).getTime()
      } as NoteItem;
    })
  );
}

export interface NoteCountItem {
  count: number;
  date: string;
}

export function fetchNoteMonthCount(month: string) {
  return request<NoteCountItem[]>({
    method: 'get',
    params: { month },
    url: NOTE_URLS.COUNT_MONTH
  });
}

export function createNote(data: { categoryId: string; content: string; tags: string[]; title: string }) {
  const token = localStg.get('token');
  const tags = (data.tags || []).join(',');
  return request<boolean>({
    data: { ...data, tags },
    headers: {
      Authorize: token || ''
    },
    method: 'post',
    url: NOTE_URLS.CREATE
  });
}

export function updateNote(
  id: string,
  data: { categoryId?: string; content?: string; tags?: string[]; title?: string }
) {
  const token = localStg.get('token');
  const tags = (data.tags || []).join(',');
  return request<boolean>({
    data: { id, ...data, tags },
    headers: {
      Authorize: token || ''
    },
    method: 'put',
    url: NOTE_URLS.CREATE
  });
}

export function deleteNote(id: string) {
  const token = localStg.get('token');
  return request<boolean>({
    headers: {
      Authorize: token || ''
    },
    method: 'delete',
    url: `${NOTE_URLS.CREATE}/${id}`
  });
}

export function topNote(id: string) {
  const token = localStg.get('token');
  return request<boolean>({
    headers: {
      Authorize: token || ''
    },
    method: 'post',
    url: NOTE_URLS.TOP(id)
  });
}
