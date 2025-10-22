import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

export async function apiRequest(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || data.message || `HTTP ${response.status}`);
  }
  return data;
}

export function useSchemes() {
  return useQuery({
    queryKey: ['schemes'],
    queryFn: () => apiRequest('/api/schemes').then((r) => r.data),
    refetchInterval: 15000,
  });
}

export function useMonitorStatus() {
  return useQuery({
    queryKey: ['monitor-status'],
    queryFn: () => apiRequest('/api/monitor/status').then((r) => r.data),
    refetchInterval: 15000,
  });
}

export function useSystemInfo() {
  return useQuery({
    queryKey: ['system-info'],
    queryFn: () => apiRequest('/api/system/info').then((r) => r.data),
    refetchInterval: 15000,
  });
}

export function useSchemeDetail(schemeId) {
  return useQuery({
    queryKey: ['scheme-detail', schemeId],
    queryFn: () => apiRequest(`/api/schemes/${schemeId}`).then((r) => r.data),
    enabled: !!schemeId,
    refetchInterval: 15000,
  });
}

export function useGlobalSettings() {
  return useQuery({
    queryKey: ['global-settings'],
    queryFn: () => apiRequest('/api/global-settings').then((r) => r.data),
  });
}

export function useWechatStatus() {
  return useQuery({
    queryKey: ['wechat-status'],
    queryFn: async () => {
      const status = await apiRequest('/api/wechat/status').then((r) => r.data);
      const account = status?.account || null;
      const convUrl = account?.account_id
        ? `/api/wechat/conversations?account_id=${encodeURIComponent(account.account_id)}`
        : '/api/wechat/conversations';
      const conversations = await apiRequest(convUrl).then((r) => r.data || []);
      const accounts = account ? [account] : [];
      return { status, account, accounts, conversations };
    },
    refetchInterval: 5000,
  });
}

export function useSetConversationRemark() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ conversationId, remark }) =>
      apiRequest(`/api/wechat/conversations/${conversationId}/remark`, {
        method: 'PUT',
        body: JSON.stringify({ remark }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['wechat-status'] });
    },
  });
}

export function useCreateScheme() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload) => apiRequest('/api/schemes', { method: 'POST', body: JSON.stringify(payload) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['schemes'] });
      qc.invalidateQueries({ queryKey: ['monitor-status'] });
      qc.invalidateQueries({ queryKey: ['system-info'] });
    },
  });
}

export function useUpdateScheme() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...payload }) => apiRequest(`/api/schemes/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['schemes'] });
      qc.invalidateQueries({ queryKey: ['monitor-status'] });
      qc.invalidateQueries({ queryKey: ['system-info'] });
      qc.invalidateQueries({ queryKey: ['scheme-detail', variables.id] });
    },
  });
}

export function useDeleteScheme() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => apiRequest(`/api/schemes/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['schemes'] });
      qc.invalidateQueries({ queryKey: ['monitor-status'] });
      qc.invalidateQueries({ queryKey: ['system-info'] });
    },
  });
}

export function useAddKeyword(schemeId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload) => apiRequest(`/api/schemes/${schemeId}/keywords`, { method: 'POST', body: JSON.stringify(payload) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['scheme-detail', schemeId] });
      qc.invalidateQueries({ queryKey: ['monitor-status'] });
    },
  });
}

export function useUpdateKeyword(schemeId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...payload }) => apiRequest(`/api/keywords/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['scheme-detail', schemeId] });
    },
  });
}

export function useDeleteKeyword(schemeId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => apiRequest(`/api/keywords/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['scheme-detail', schemeId] });
    },
  });
}

export function useRestartScheme() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => apiRequest(`/api/schemes/${id}/restart`, { method: 'POST' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['monitor-status'] });
    },
  });
}

export function useTestWebhook() {
  return useMutation({
    mutationFn: ({ webhook_url, secret }) => apiRequest('/api/test-webhook', { method: 'POST', body: JSON.stringify({ webhook_url, secret: secret || '' }) }),
  });
}

export function useTestWechat() {
  return useMutation({
    mutationFn: (payload) => apiRequest('/api/test-wechat', { method: 'POST', body: JSON.stringify(payload) }),
  });
}

export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload) => apiRequest('/api/global-settings', { method: 'PUT', body: JSON.stringify(payload) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['global-settings'] });
    },
  });
}

export function useRestartServer() {
  return useMutation({
    mutationFn: (port) => apiRequest('/api/server/restart', { method: 'POST', body: JSON.stringify({ port }) }),
  });
}
