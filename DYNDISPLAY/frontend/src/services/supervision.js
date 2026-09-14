import apiService from './api';

const PREFIX = '/api/v1';

export async function getSupervision() {
  return apiService.get(`${PREFIX}/supervision`);
}

export async function sendHeartbeat(postId) {
  return apiService.post(`${PREFIX}/posts/heartbeat`, { post_id: postId });
}

export async function pingPost(postId) {
  return apiService.post(`${PREFIX}/posts/${postId}/ping`);
}
