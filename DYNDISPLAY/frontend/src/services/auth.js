import apiService from './api';

const AUTH_PREFIX = '/api/v1/auth';

export async function loginRequest(login, password, clientCode) {
  const body = { login, password };
  if (clientCode) body.client_code = clientCode;
  return apiService.post(`${AUTH_PREFIX}/login`, body);
}

export async function getMe() {
  return apiService.get(`${AUTH_PREFIX}/me`);
}

export async function logoutRequest() {
  return apiService.post(`${AUTH_PREFIX}/logout`);
}

export async function getLogins() {
  return apiService.get(`${AUTH_PREFIX}/logins`);
}

export async function forgotPassword(login) {
  return apiService.post(`${AUTH_PREFIX}/forgot-password`, { login });
}

export async function resetPassword(token, newPassword, passwordConfirm) {
  return apiService.post(`${AUTH_PREFIX}/reset-password`, {
    token,
    new_password: newPassword,
    password_confirm: passwordConfirm,
  });
}

export async function activateAccount(code) {
  return apiService.post(`${AUTH_PREFIX}/activate`, { code });
}
