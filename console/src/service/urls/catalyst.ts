export const CATALYST_URLS = {
  ACCURACY: '/catalyst/accuracy',
  ACTIVE_MESSAGE_UPDATE: (id: number) => `/catalyst/active-messages/${id}/update`,
  ACTIVE_MESSAGES: '/catalyst/active-messages',
  DASHBOARD: '/catalyst/dashboard',
  IMPACT: (id: number) => `/catalyst/impacts/${id}`,
  IMPACTS: '/catalyst/impacts',
  PREDICTION: (id: number) => `/catalyst/predictions/${id}`,
  PREDICTIONS: '/catalyst/predictions',
  PREDICTIONS_PENDING: '/catalyst/predictions/pending',
  SYSTEM_STATES: '/catalyst/system-states'
} as const;
