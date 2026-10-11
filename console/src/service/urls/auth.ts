/** Auth module URLs */

export const AUTH_URLS = {
  ERROR: '/api/auth/error',
  GET_USER_INFO: '/api/user/personal',
  LOGIN: '/auth/login',
  REFRESH_TOKEN: '/api/auth/refreshToken',
  REGISTER: '/api/user/register',
  RESET_PWD: '/api/user/reset-pwd',
  SEND_CODE: '/api/user/send-code'
} as const;
