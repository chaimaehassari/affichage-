import apiService from './api';

const PREFIX = '/api/v1';

export async function startSync(postId, scheduledAt) {
  return apiService.post(`${PREFIX}/posts/${postId}/sync`, { scheduled_at: scheduledAt || null });
}

export async function getSyncJob(jobId) {
  return apiService.get(`${PREFIX}/sync-jobs/${jobId}`);
}

export async function getPostSyncStatus(postId) {
  return apiService.get(`${PREFIX}/posts/${postId}/sync-status`);
}

export async function syncGroup(groupId) {
  return apiService.post(`${PREFIX}/groups/${groupId}/sync`);
}

export async function getGroupMediaHierarchy(groupId) {
  return apiService.get(`${PREFIX}/groups/${groupId}/media-hierarchy`);
}

export async function getGroupMediaSyncStatus(groupId) {
  return apiService.get(`${PREFIX}/groups/${groupId}/media-sync-status`);
}

export async function syncGroupMedia(groupId, mediaId) {
  return apiService.post(`${PREFIX}/groups/${groupId}/media/${mediaId}/sync`);
}
