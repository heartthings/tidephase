/** Trading system module URLs */

export const TRADING_SYSTEM_URLS = {
  CREATE_NODE: '/trading-system/node',
  DELETE_NODE: (id: string) => `/trading-system/node/${id}`,
  GET_NODE: (id: string) => `/trading-system/node/${id}`,
  TREE: '/trading-system/tree',
  UPDATE_NODE: '/trading-system/node',
  UPDATE_NODE_BY_ID: (id: string) => `/trading-system/node/${id}`
} as const;
