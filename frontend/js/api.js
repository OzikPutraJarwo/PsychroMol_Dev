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
  const response = await fetch(`${normaliseBase(url)}/health`);
  if (!response.ok) throw new Error(`server replied with ${response.status}`);
  return response.json();
}

function describe(detail, status) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => {
      const where = (item.loc || []).filter((part) => part !== "body").join(" ").replace(/_/g, " ");
      const message = String(item.msg || "").replace(/^Value error, /, "");
      return where ? `${where}: ${message}` : message;
    }).join("; ");
  }
  return `request failed (${status})`;
}

async function request(path, options = {}) {
  const response = await fetch(`${getBase()}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (response.status === 204) return null;
  const text = await response.text();
  let payload = null;
  if (text) {
    try { payload = JSON.parse(text); } catch { payload = text; }
  }
  if (!response.ok) throw new Error(describe(payload?.detail, response.status));
  return payload;
}

const send = (method, path, body) =>
  request(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });

function query(parameters) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(parameters)) {
    if (value !== null && value !== undefined && value !== "") search.set(key, String(value));
  }
  return search.toString();
}

export const api = {
  getBase,
  setBase,
  probeBase,

  profiles: () => request("/profiles"),
  addProfile: (body) => send("POST", "/profiles", body),
  updateProfile: (id, body) => send("PUT", `/profiles/${id}`, body),
  deleteProfile: (id) => send("DELETE", `/profiles/${id}`),
  refresh: (id) => send("POST", `/profiles/${id}/refresh`),

  latest: (id) => request(`/profiles/${id}/readings/latest`),
  readings: (id, parameters) => request(`/profiles/${id}/readings?${query(parameters)}`),

  rules: (profileId) => request(`/profiles/${profileId}/rules`),
  replaceRules: (profileId, rules) => send("PUT", `/profiles/${profileId}/rules`, rules),
  addRule: (profileId, body) => send("POST", `/profiles/${profileId}/rules`, body),
  updateRule: (id, body) => send("PUT", `/rules/${id}`, body),
  deleteRule: (id) => send("DELETE", `/rules/${id}`),

  fetchThroughServer: (url) => request(`/sources/fetch?${query({ url })}`),
};
