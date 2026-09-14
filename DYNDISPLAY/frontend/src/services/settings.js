import apiService from './api';

const PREFIX = '/api/v1';

export async function verifyClientCode(code) {
  return apiService.post(`${PREFIX}/settings/verify-client-code`, { code });
}

export async function getSettings() {
  return apiService.get(`${PREFIX}/settings`);
}

export async function updateSettings(data) {
  return apiService.put(`${PREFIX}/settings`, data);
}

export async function updateLicenses(code, sites, posts) {
  return apiService.post(`${PREFIX}/settings/license/update`, { code, sites, posts });
}

export async function getFtpProfiles() {
  return apiService.get(`${PREFIX}/ftp-profiles`);
}

export async function createFtpProfile(data) {
  return apiService.post(`${PREFIX}/ftp-profiles`, data);
}

export async function updateFtpProfile(id, data) {
  return apiService.put(`${PREFIX}/ftp-profiles/${id}`, data);
}

export async function deleteFtpProfile(id) {
  return apiService.delete(`${PREFIX}/ftp-profiles/${id}`);
}

export async function testFtpConnection(profileId) {
  return apiService.post(`${PREFIX}/settings/test-ftp`, { profile_id: profileId });
}

export async function changePassword(currentPassword, newPassword) {
  return apiService.post(`${PREFIX}/settings/change-password`, { current_password: currentPassword, new_password: newPassword });
}

export async function regenerateClientCode() {
  return apiService.post(`${PREFIX}/settings/regenerate-client-code`);
}

export async function verifyAccessPassword(password) {
  return apiService.post(`${PREFIX}/settings/verify-access`, { password });
}
