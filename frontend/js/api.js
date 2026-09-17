const DEFAULT_BASE = "/api/v1";
const STORAGE_KEY = "psychromol.apiBase";

function normaliseBase(url) {
  const trimmed = url.trim().replace(/\/+$/, "");
  return trimmed || DEFAULT_BASE;
}

function getBase() {
  try {
    return localStorage.getItem(STORAGE_KEY) || DEFAULT_BASE;
  } catch {
    return DEFAULT_BASE;
  }
}

function setBase(url) {
  const base = normaliseBase(url);
  try {
    localStorage.setItem(STORAGE_KEY, base);
  } catch {}
  return base;
}

async function probeBase(url) {
  const base = normaliseBase(url);
  const response = await fetch(`${base}/meta`);
  if (!response.ok) throw new Error(`server replied with ${response.status}`);
  return response.json();
}

async function request(path, options = {}) {
  const response = await fetch(`${getBase()}${path}`, {
    headers: options.body instanceof FormData
      ? {}
      : { "Content-Type": "application/json" },
    ...options,
  });
  if (response.status === 204) return null;
  const text = await response.text();
  let payload = null;
  if (text) {
    try { payload = JSON.parse(text); } catch { payload = text; }
  }
  if (!response.ok) {
    const detail = payload && payload.detail
      ? payload.detail
      : `request failed (${response.status})`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload;
}

const send = (method, path, body) =>
  request(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  getBase,
  setBase,
  probeBase,

  meta: () => request("/meta"),
  previewSource: (url) => request(`/sources/preview?url=${encodeURIComponent(url)}`),

  crops: () => request("/crops"),
  addCrop: (body) => send("POST", "/crops", body),
  updateCrop: (id, body) => send("PUT", `/crops/${id}`, body),
  deleteCrop: (id) => send("DELETE", `/crops/${id}`),

  facilities: () => request("/facilities"),
  addFacility: (body) => send("POST", "/facilities", body),
  updateFacility: (id, body) => send("PUT", `/facilities/${id}`, body),
  deleteFacility: (id) => send("DELETE", `/facilities/${id}`),

  profiles: () => request("/profiles"),
  addProfile: (body) => send("POST", "/profiles", body),
  updateProfile: (id, body) => send("PUT", `/profiles/${id}`, body),
  deleteProfile: (id) => send("DELETE", `/profiles/${id}`),

  current: (id) => request(`/profiles/${id}/current`),
  chart: (id, kind) => request(`/profiles/${id}/chart?kind=${kind}`),
  readings: (id, query) => request(`/profiles/${id}/readings?${query}`),
  refresh: (id) => send("POST", `/profiles/${id}/refresh`),
  paste: (id, body) => send("POST", `/profiles/${id}/paste`, body),
  upload: (id, formData) =>
    request(`/profiles/${id}/upload`, { method: "POST", body: formData }),
  exportUrl: (id, query) => `${getBase()}/profiles/${id}/export?${query}`,

  rules: () => request("/rules"),
  addRule: (body) => send("POST", "/rules", body),
  updateRule: (id, body) => send("PUT", `/rules/${id}`, body),
  deleteRule: (id) => send("DELETE", `/rules/${id}`),
  resetRules: () => send("POST", "/rules/reset"),
};
