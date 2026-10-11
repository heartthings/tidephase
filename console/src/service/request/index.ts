import { BACKEND_ERROR_CODE, createRequest } from '@sa/axios';

import { globalConfig } from '@/config';
import { localStg } from '@/utils/storage';

import { backEndFail, handleError } from './error';
import { getAuthorization } from './shared';
import type { RequestInstanceState } from './type';

export const request = createRequest<App.Service.Response, RequestInstanceState>(
  {
    baseURL: globalConfig.serviceBaseURL,
    timeout: 20000
  },
  {
    isBackendSuccess(response) {
      // when the backend response code is "0000"(default), it means the request is success
      // to change this logic by yourself, you can modify the `VITE_SERVICE_SUCCESS_CODE` in `.env` file
      return String(response.data.code) === import.meta.env.VITE_SERVICE_SUCCESS_CODE;
    },
    async onBackendFail(response, instance) {
      await backEndFail(response, instance, request);
    },
    onError(error) {
      handleError(error, request);
    },
    async onRequest(config) {
      const url = config.url as string | undefined;
      if (url && url.startsWith('/') && !url.startsWith('/api/') && !url.startsWith('/auth/')) {
        config.url = `/api${url}`;
      }

      const Authorization = getAuthorization();
      Object.assign(config.headers, { authorize: Authorization });

      return config;
    },
    transformBackendResponse(response) {
      return response.data.data;
    }
  }
);

export const demoRequest = createRequest<App.Service.DemoResponse>(
  {
    baseURL: globalConfig.serviceOtherBaseURL.demo
  },
  {
    isBackendSuccess(response) {
      // when the backend response code is "200", it means the request is success
      // you can change this logic by yourself
      return response.data.status === '200';
    },
    async onBackendFail(_response) {
      // when the backend response code is not "200", it means the request is fail
      // for example: the token is expired, refresh token and retry request
    },
    onError(error) {
      // when the request is fail, you can show error message

      let message = error.message;

      // show backend error message
      if (error.code === BACKEND_ERROR_CODE) {
        message = error.response?.data?.message || message;
      }

      window.$message?.error(message);
    },
    async onRequest(config) {
      const { headers } = config;

      // set token
      const token = localStg.get('token');
      const Authorization = token ? `${token}` : null;
      Object.assign(headers, { Authorization });

      return config;
    },
    transformBackendResponse(response) {
      return response.data.result;
    }
  }
);
