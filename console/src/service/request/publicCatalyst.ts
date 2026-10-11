import { BACKEND_ERROR_CODE, createRequest } from '@sa/axios';

import { globalConfig } from '@/config';
import { buildPublicCatalystToken } from '@/features/catalyst/publicToken';

import type { RequestInstanceState } from '../request/type';

/** Public catalyst request: AES token header, no login Authorize, no login-out redirect. */
export const publicCatalystRequest = createRequest<App.Service.Response, RequestInstanceState>(
  {
    baseURL: globalConfig.serviceBaseURL,
    timeout: 20000
  },
  {
    isBackendSuccess(response) {
      return String(response.data.code) === import.meta.env.VITE_SERVICE_SUCCESS_CODE;
    },
    async onBackendFail(response) {
      const message = (response.data as { message?: string })?.message || '请求失败';
      window.$message?.error(message);
    },
    onError(error) {
      let message = error.message;
      if (error.code === BACKEND_ERROR_CODE) {
        message = (error.response?.data as { message?: string } | undefined)?.message || message;
      }
      window.$message?.error(message);
    },
    async onRequest(config) {
      const url = config.url as string | undefined;
      if (url && url.startsWith('/') && !url.startsWith('/api/')) {
        config.url = `/api${url}`;
      }

      const publicToken = await buildPublicCatalystToken();
      Object.assign(config.headers, { 'X-Public-Token': publicToken });

      return config;
    },
    transformBackendResponse(response) {
      return response.data.data;
    }
  }
);
