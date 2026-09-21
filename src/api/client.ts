import axios, { AxiosError } from "axios";
import type { ApiErrorBody } from "../types";

export const API_BASE_STORAGE_KEY = "digidara-api-base-url";

export function getApiBaseUrl(): string {
  return (
    localStorage.getItem(API_BASE_STORAGE_KEY) ||
    import.meta.env.VITE_API_BASE_URL ||
    "http://localhost:8000"
  ).replace(/\/$/, "");
}

export const api = axios.create({
  baseURL: getApiBaseUrl(),
  headers: {
    "Content-Type": "application/json"
  }
});

api.interceptors.request.use((config) => {
  config.baseURL = getApiBaseUrl();
  const token = localStorage.getItem("digidara-token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// A stale/expired token still passes ProtectedRoute's client-side shape
// check, so every request on the page then fails with 401 while the user
// stays stuck looking at a broken dashboard. Clear it and bounce to login
// the moment the backend actually rejects it.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (
      axios.isAxiosError(error) &&
      error.response?.status === 401 &&
      !window.location.pathname.startsWith("/login")
    ) {
      localStorage.removeItem("digidara-token");
      localStorage.removeItem("digidara-user");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<ApiErrorBody>;
    const body = axiosError.response?.data;
    return body?.detail || body?.error || body?.message || axiosError.message;
  }
  return error instanceof Error ? error.message : "Something went wrong";
}
