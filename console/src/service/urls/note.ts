/** Note module URLs */

export const NOTE_URLS = {
  COUNT_MONTH: '/api/note/count/month',
  CREATE: '/api/note',
  GET_ENABLED_CATEGORIES: '/api/note/category/enabled',
  LIST: '/api/note/list',
  TOP: (id: string) => `/api/note/${id}/top`
} as const;
