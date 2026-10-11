import apiService from './api';

const PREFIX = '/api/v1';

export async function getClients() {
  return apiService.get(`${PREFIX}/clients`);
}

export async function getClientDetail(code) {
  return apiService.get(`${PREFIX}/clients/${code}`);
}

export async function createClient(data) {
  return apiService.post(`${PREFIX}/clients`, data);
}

export async function updateClientLicense(code, licenseSites, licensePosts) {
  return apiService.put(`${PREFIX}/clients/${code}/license`, {
    license_sites: licenseSites,
    license_posts: licensePosts,
  });
}

export async function getAdmins() {
  return apiService.get(`${PREFIX}/admins`);
}

export async function getAdmin(id) {
  return apiService.get(`${PREFIX}/admins/${id}`);
}

export async function createAdmin(data) {
  return apiService.post(`${PREFIX}/admins`, data);
}

export async function updateAdmin(id, data) {
  return apiService.put(`${PREFIX}/admins/${id}`, data);
}

export async function deleteAdmin(id) {
  return apiService.delete(`${PREFIX}/admins/${id}`);
}

export async function assignAdminClient(adminId, clientCode) {
  return apiService.post(`${PREFIX}/admins/${adminId}/clients`, { client_code: clientCode });
}

export async function removeAdminClient(adminId, clientCode) {
  return apiService.delete(`${PREFIX}/admins/${adminId}/clients/${clientCode}`);
}