import request from '@/utils/request';

function authHeaders(token) {
  return { Authorization: 'Bearer ' + String(token || '') };
}

export function listApiKeys(token) {
  return request({
    url: '/admin/api-keys',
    method: 'get',
    headers: authHeaders(token)
  });
}

export function listApiKeysById(token, id) {
  const n = Number(id || 0);
  const params = Number.isFinite(n) && n > 0 ? { id: Math.floor(n) } : undefined;
  return request({
    url: '/admin/api-keys',
    method: 'get',
    headers: authHeaders(token),
    params
  });
}

export function createApiKey(token, value, note) {
  const v = typeof value === 'undefined' ? '' : String(value || '').trim();
  const data = {};
  if (v) data.value = v;
  const n = typeof note === 'undefined' ? '' : String(note || '').trim();
  if (n) data.note = n;
  return request({
    url: '/admin/api-keys',
    method: 'post',
    headers: authHeaders(token),
    data
  });
}

export function updateApiKey(token, id, payload) {
  const data = {};
  if (payload && typeof payload.note !== 'undefined') data.note = String(payload.note || '');
  if (payload && typeof payload.enabled !== 'undefined') data.enabled = !!payload.enabled;
  return request({
    url: `/admin/api-keys/${Number(id)}`,
    method: 'patch',
    headers: authHeaders(token),
    data
  });
}

export function deleteApiKey(token, id) {
  return request({
    url: `/admin/api-keys/${Number(id)}`,
    method: 'delete',
    headers: authHeaders(token)
  });
}

export function resetApiKey(token, id) {
  return request({
    url: `/admin/api-keys/${Number(id)}/reset`,
    method: 'post',
    headers: authHeaders(token)
  });
}
