import { request } from '../request';
import { AUTH_URLS } from '../urls';

/**
 * Login
 *
 * @param params Login parameters
 */
export function fetchLogin(params: Api.Auth.LoginParams) {
  return request<Api.Auth.LoginResponse>({
    data: {
      deviceType: 'PC',
      password: params.password,
      username: params.userName
    },
    method: 'post',
    url: AUTH_URLS.LOGIN
  });
}

/** Get user info */
export async function fetchGetUserInfo() {
  const userInfo = await request<Api.Auth.UserInfo & { username?: string }>({ url: AUTH_URLS.GET_USER_INFO });

  if (userInfo.username) {
    userInfo.userName = userInfo.username;
  }

  return userInfo;
}

/**
 * Refresh token
 *
 * @param refreshToken Refresh token
 */
export function fetchRefreshToken(refreshToken: string) {
  return request<Api.Auth.LoginToken>({
    data: {
      refreshToken
    },
    method: 'post',
    url: AUTH_URLS.REFRESH_TOKEN
  });
}

/**
 * return custom backend error
 *
 * @param code error code
 * @param msg error message
 */
export function fetchCustomBackendError(code: string, msg: string) {
  return request({ params: { code, msg }, url: AUTH_URLS.ERROR });
}

/** Send verification code */
export function fetchSendCode(phone: string) {
  return request<unknown>({
    data: { phone },
    method: 'post',
    url: AUTH_URLS.SEND_CODE
  });
}

/** Register account */
export function fetchRegister(params: Api.Auth.RegisterParams) {
  return request<unknown>({
    data: params,
    method: 'post',
    url: AUTH_URLS.REGISTER
  });
}

/** Reset password */
export function fetchResetPwd(params: Api.Auth.ResetPwdParams) {
  return request<unknown>({
    data: params,
    method: 'post',
    url: AUTH_URLS.RESET_PWD
  });
}
