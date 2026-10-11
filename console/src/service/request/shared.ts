import { router } from '@/features/router';
import { localStg } from '@/utils/storage';

import { fetchRefreshToken } from '../api';

import type { RequestInstanceState } from './type';

export function getAuthorization() {
  const token = localStg.get('token');
  const Authorization = token ? `${token}` : null;

  return Authorization;
}

/**
 * refresh token
 *
 * @param axiosConfig - request config when the token is expired
 */
export async function handleRefreshToken() {
  const refreshToken = localStg.get('refreshToken') || '';
  try {
    const data = await fetchRefreshToken(refreshToken);
    localStg.set('token', data.token);
    localStg.set('refreshToken', data.refreshToken);
    return true;
  } catch {
    const location = router.reactRouter.state.location;
    const fullPath = location.pathname + location.search + location.hash;
    router.push('/login-out', { query: { redirect: fullPath } });
    return false;
  }
}

export async function handleExpiredRequest(state: RequestInstanceState) {
  if (!state.refreshTokenFn) {
    state.refreshTokenFn = handleRefreshToken();
  }

  const success = await state.refreshTokenFn;

  setTimeout(() => {
    state.refreshTokenFn = null;
  }, 1000);

  return success;
}

export function showErrorMsg(state: RequestInstanceState, message: string) {
  if (!state.errMsgStack?.length) {
    state.errMsgStack = [];
  }

  const isExist = state.errMsgStack.includes(message);

  if (!isExist) {
    state.errMsgStack.push(message);

    window.$message?.error({
      content: message,
      onClose: () => {
        state.errMsgStack = state.errMsgStack.filter(msg => msg !== message);

        setTimeout(() => {
          state.errMsgStack = [];
        }, 5000);
      }
    });
  }
}
