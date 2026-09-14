import apiService from './api';

const PREFIX = '/api/v1';

// --- Sites ---
export async function getSites(search) {
  const params = search ? `?search=${encodeURIComponent(search)}` : '';
  return apiService.get(`${PREFIX}/sites${params}`);
}

export async function getSite(id) {
  return apiService.get(`${PREFIX}/sites/${id}`);
}

export async function createSite(data) {
  return apiService.post(`${PREFIX}/sites`, data);
}

export async function updateSite(id, data) {
  return apiService.put(`${PREFIX}/sites/${id}`, data);
}

export async function deleteSite(id) {
  return apiService.delete(`${PREFIX}/sites/${id}`);
}

// --- Posts ---
export async function getPosts(siteId) {
  const params = siteId ? `?site_id=${siteId}` : '';
  return apiService.get(`${PREFIX}/posts${params}`);
}

export async function getPost(id) {
  return apiService.get(`${PREFIX}/posts/${id}`);
}

export async function getPostConfiguration(id) {
  return apiService.get(`${PREFIX}/posts/${id}/configuration`);
}

export async function createPost(data) {
  return apiService.post(`${PREFIX}/posts`, data);
}

export async function updatePost(id, data) {
  return apiService.put(`${PREFIX}/posts/${id}`, data);
}

export async function deletePost(id) {
  return apiService.delete(`${PREFIX}/posts/${id}`);
}

// --- Groups ---
export async function getGroups() {
  return apiService.get(`${PREFIX}/groups`);
}

export async function getGroup(id) {
  return apiService.get(`${PREFIX}/groups/${id}`);
}

export async function createGroup(data) {
  return apiService.post(`${PREFIX}/groups`, data);
}

export async function updateGroup(id, data) {
  return apiService.put(`${PREFIX}/groups/${id}`, data);
}

export async function deleteGroup(id) {
  return apiService.delete(`${PREFIX}/groups/${id}`);
}

export async function getGroupPosts(groupId) {
  return apiService.get(`${PREFIX}/groups/${groupId}/posts`);
}

export async function addPostsToGroup(groupId, postIds) {
  return apiService.post(`${PREFIX}/groups/${groupId}/posts`, { post_ids: postIds });
}

export async function removePostsFromGroup(groupId, postIds) {
  return apiService.request(`${PREFIX}/groups/${groupId}/posts`, {
    method: 'DELETE',
    body: JSON.stringify({ post_ids: postIds }),
    headers: { 'Content-Type': 'application/json' },
  });
}

export async function getGroupComposition(groupId) {
  return apiService.get(`${PREFIX}/groups/${groupId}/composition`);
}

export async function setGroupMembership(groupId, postIds) {
  return apiService.put(`${PREFIX}/groups/${groupId}/membership`, { post_ids: postIds });
}

export async function applyConfigToGroup(groupId, payload) {
  return apiService.post(`${PREFIX}/groups/${groupId}/apply-configuration`, payload);
}

// --- Batch Assign ---
export async function batchAssignMedia(payload) {
  return apiService.post(`${PREFIX}/posts/batch-assign-media`, payload);
}

// --- Media ---
export async function getMedia(mediaType) {
  const params = mediaType ? `?media_type=${mediaType}` : '';
  return apiService.get(`${PREFIX}/media${params}`);
}

export async function uploadMedia(file, onProgress) {
  const formData = new FormData();
  formData.append('file', file);

  const token = localStorage.getItem('dyndisplay_token');
  const url = `${apiService.baseUrl}${PREFIX}/media/upload`;

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);
    if (token) {
      xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    }
    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    });
    xhr.addEventListener('load', () => {
      try {
        const data = JSON.parse(xhr.responseText);
        resolve({ data, status: xhr.status, ok: xhr.status >= 200 && xhr.status < 300 });
      } catch {
        resolve({ data: null, status: xhr.status, ok: false, error: 'Invalid JSON' });
      }
    });
    xhr.addEventListener('error', () => {
      resolve({ data: null, status: 0, ok: false, error: 'Network error' });
    });
    xhr.send(formData);
  });
}

export async function deleteMedia(id) {
  return apiService.delete(`${PREFIX}/media/${id}`);
}

export async function getMediaById(id) {
  return apiService.get(`${PREFIX}/media/${id}`);
}
