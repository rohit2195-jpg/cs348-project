// Single source of truth for the API base URL.
// Local development falls back to the Flask default.
const defaultApi = "http://127.0.0.1:5000/api";
const TOKEN_KEY = "cs348_session_token";

export const API = import.meta.env.VITE_API_BASE_URL || defaultApi;

export function getAuthToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setAuthToken(token) {
  try {
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
    } else {
      localStorage.removeItem(TOKEN_KEY);
    }
  } catch {}
}

export function apiFetch(path, options = {}) {
  const token = getAuthToken();
  return fetch(`${API}${path}`, {
    credentials: "include",
    ...options,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });
}

export async function apiJson(path, options = {}) {
  const res = await apiFetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const error = new Error(data.error || `Request failed (${res.status})`);
    error.status = res.status;
    error.payload = data;
    throw error;
  }
  return data;
}
