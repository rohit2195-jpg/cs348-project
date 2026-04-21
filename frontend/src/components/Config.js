// Single source of truth for the API base URL.
// Local development falls back to the Flask default.
const defaultApi = "http://127.0.0.1:5000/api";

export const API = import.meta.env.VITE_API_BASE_URL || defaultApi;
