import apiService from './api';

const PREFIX = '/api/v1';

export async function getPostConfig(postId) {
  return apiService.get(`${PREFIX}/posts/${postId}/configuration`);
}

export async function updatePostConfig(postId, data) {
  return apiService.put(`${PREFIX}/posts/${postId}/configuration`, data);
}

export async function updatePostZones(postId, zones) {
  return apiService.post(`${PREFIX}/posts/${postId}/zones`, zones);
}

export async function getSchedules(postId) {
  return apiService.get(`${PREFIX}/posts/${postId}/schedules`);
}

export async function createSchedule(postId, data) {
  return apiService.post(`${PREFIX}/posts/${postId}/schedules`, data);
}

export async function updateSchedule(scheduleId, data) {
  return apiService.put(`${PREFIX}/schedules/${scheduleId}`, data);
}

export async function deleteSchedule(scheduleId) {
  return apiService.delete(`${PREFIX}/schedules/${scheduleId}`);
}
