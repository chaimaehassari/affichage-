import apiService from './api';

const PREFIX = '/api/v1';

export async function getLayouts() {
  return apiService.get(`${PREFIX}/layouts`);
}

export async function getLayout(id) {
  return apiService.get(`${PREFIX}/layouts/${id}`);
}

export async function createLayout(data) {
  return apiService.post(`${PREFIX}/layouts`, data);
}

export async function updateLayout(id, data) {
  return apiService.put(`${PREFIX}/layouts/${id}`, data);
}

export async function deleteLayout(id) {
  return apiService.delete(`${PREFIX}/layouts/${id}`);
}
