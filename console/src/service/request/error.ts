import type { RequestInstance } from '@sa/axios';
import { BACKEND_ERROR_CODE } from '@sa/axios';
import type { AxiosError, AxiosInstance, AxiosResponse } from 'axios';

import { router } from '@/features/router';
import { $t } from '@/locales';

import { AUTH_URLS } from '../urls';

import { getAuthorization, handleExpiredRequest, showErrorMsg } from './shared';
import type { RequestInstanceState } from './type';

function redirectByStatus(status: number, reqUrl: string) {
  const authUrls: string[] = [
    AUTH_URLS.LOGIN,
    AUTH_URLS.REGISTER,
    AUTH_URLS.RESET_PWD,
    AUTH_URLS.SEND_CODE,
    AUTH_URLS.REFRESH_TOKEN
  ];
  const isAuthFlow = authUrls.includes(reqUrl);

  const pathname = router.reactRouter.state.location.pathname;
  const isPublicPage = pathname === '/public/catalyst' || pathname.startsWith('/public/catalyst/');

  // Public catalyst page must not be kicked to login by any 401.
  if (status === 401 && !isAuthFlow && !isPublicPage) {
    const location = router.reactRouter.state.location;
    const fullPath = location.pathname + location.search + location.hash;
    router.push('/login-out', { query: { redirect: fullPath } });
    return true;
  }

  if (status === 401 && isPublicPage) {
    return false;
  }

  const specialStatusRedirects: Record<number, string> = {
    403: '/403',
    404: '/404'
  };

  const target = specialStatusRedirects[status];
  if (target) {
    router.push(target);
    return true;
  }

  if (status >= 500) {
    router.push('/500');
    return true;
  }

  return false;
}

/** - 后端错误处理 */
export async function backEndFail(
  response: AxiosResponse<App.Service.Response<unknown>, any>,
  instance: AxiosInstance,
  request: RequestInstance<RequestInstanceState>
) {
  const responseCode = String(response.data.code);

  function handleLogout() {
    const location = router.reactRouter.state.location;
    const fullPath = location.pathname + location.search + location.hash;
    router.push('/login-out', { query: { redirect: fullPath } });
  }

  function logoutAndCleanup() {
    handleLogout();
    window.removeEventListener('beforeunload', handleLogout);

    request.state.errMsgStack = request.state.errMsgStack.filter(msg => msg !== (response.data as any).message);
  }

  // when the backend response code is in `logoutCodes`, it means the user will be logged out and redirected to login page
  const logoutCodes = import.meta.env.VITE_SERVICE_LOGOUT_CODES?.split(',') || [];
  if (logoutCodes.includes(responseCode)) {
    handleLogout();
    return null;
  }

  // when the backend response code is in `modalLogoutCodes`, it means the user will be logged out by displaying a modal
  const modalLogoutCodes = import.meta.env.VITE_SERVICE_MODAL_LOGOUT_CODES?.split(',') || [];
  if (modalLogoutCodes.includes(responseCode) && !request.state.errMsgStack?.includes((response.data as any).message)) {
    request.state.errMsgStack = [...(request.state.errMsgStack || []), (response.data as any).message];

    // prevent the user from refreshing the page
    window.addEventListener('beforeunload', handleLogout);

    window.$modal?.error({
      content: (response.data as any).message,
      keyboard: false,
      maskClosable: false,
      okText: $t('common.confirm'),
      onClose() {
        logoutAndCleanup();
      },
      onOk() {
        logoutAndCleanup();
      },
      title: $t('common.error')
    });

    return null;
  }

  // when the backend response code is in `expiredTokenCodes`, it means the token is expired, and refresh token
  // the api `refreshToken` can not return error code in `expiredTokenCodes`, otherwise it will be a dead loop, should return `logoutCodes` or `modalLogoutCodes`
  // when the backend response code is in `expiredTokenCodes`, it means the token is expired, and refresh token
  // the api `refreshToken` can not return error code in `expiredTokenCodes`, otherwise it will be a dead loop, should return `logoutCodes` or `modalLogoutCodes`
  const expiredTokenCodes = import.meta.env.VITE_SERVICE_EXPIRED_TOKEN_CODES?.split(',') || [];
  if (expiredTokenCodes.includes(responseCode)) {
    const success = await handleExpiredRequest(request.state);
    if (success) {
      const Authorization = getAuthorization();
      Object.assign(response.config.headers, { authorize: Authorization });

      return instance.request(response.config) as Promise<AxiosResponse>;
    }
  }

  return null;
}

/** - 网络错误处理 */
export function handleError(
  error: AxiosError<App.Service.Response<unknown>, any>,
  request: RequestInstance<RequestInstanceState>
) {
  // when the request is fail, you can show error message

  let message = error.message;
  let backendErrorCode = '';

  // get backend error message and code
  if (error.code === BACKEND_ERROR_CODE) {
    message = (error.response?.data as any)?.message || message;
    backendErrorCode = String(error.response?.data?.code || '');
  }

  const modalLogoutCodes = import.meta.env.VITE_SERVICE_MODAL_LOGOUT_CODES?.split(',') || [];
  const expiredTokenCodes = import.meta.env.VITE_SERVICE_EXPIRED_TOKEN_CODES?.split(',') || [];
  const skipCodes = new Set([...modalLogoutCodes, ...expiredTokenCodes]);
  if (backendErrorCode && skipCodes.has(backendErrorCode)) return;
  const status = Number(error.response?.status || 0);
  const reqUrl = (error.config as any)?.url || '';
  if (status && redirectByStatus(status, reqUrl)) return;
  showErrorMsg(request.state, message);
}
