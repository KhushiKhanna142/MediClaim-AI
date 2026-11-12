const API_BASE = '/api';

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const err = await res.json();
      msg = err.detail || msg;
    } catch {
      // ignore
    }
    throw new Error(msg);
  }
  return res.json();
}

export const api = {
  listClaims: (params = {}) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v) qs.set(k, v);
    });
    const q = qs.toString();
    return request(`/claims${q ? `?${q}` : ''}`);
  },

  getQueue: (params = {}) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v && v !== 'All') qs.set(k, v);
    });
    const q = qs.toString();
    return request(`/queue${q ? `?${q}` : ''}`);
  },

  getClaim: (id) => request(`/claims/${encodeURIComponent(id)}`),

  getClaimStatus: (id) => request(`/claims/${encodeURIComponent(id)}/status`),

  getFileInfo: (id, filename) =>
    request(`/claims/${encodeURIComponent(id)}/files/${encodeURIComponent(filename)}/info`),

  getFilePageUrl: (id, filename, page, dpi = 140) =>
    `${API_BASE}/claims/${encodeURIComponent(id)}/files/${encodeURIComponent(filename)}/page/${page}?dpi=${dpi}`,

  getFileDownloadUrl: (id, filename) =>
    `${API_BASE}/claims/${encodeURIComponent(id)}/files/${encodeURIComponent(filename)}`,

  submitDemoClaim: (demoClaimId, policyId) => {
    const form = new FormData();
    form.append('policy_id', policyId || 'niva_aspire');
    form.append('demo_claim_id', demoClaimId);
    return request('/claims', { method: 'POST', body: form });
  },

  takeClaim: (id, reviewer) =>
    request(`/claims/${encodeURIComponent(id)}/take?reviewer=${encodeURIComponent(reviewer)}`, {
      method: 'POST',
    }),

  rerunDecision: (id, fieldUpdates) =>
    request(`/claims/${encodeURIComponent(id)}/rerun`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ field_updates: fieldUpdates }),
    }),

  submitReview: (id, payload) =>
    request(`/claims/${encodeURIComponent(id)}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  searchPolicies: (q, policy = 'all', mode = 'hybrid', k = 5) => {
    const qs = new URLSearchParams({ q, mode, k: String(k) });
    if (policy && policy !== 'all') qs.set('policy', policy);
    return request(`/policies/search?${qs.toString()}`);
  },

  getPolicyClauses: (policyId) =>
    request(`/policies/${encodeURIComponent(policyId)}/clauses`),

  getSingleClause: (policyId, clauseId) =>
    request(`/policies/clause/${encodeURIComponent(policyId)}/${encodeURIComponent(clauseId)}`),

  getAboutInfo: () => request('/about/info'),
};

