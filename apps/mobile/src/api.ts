import * as SecureStore from "expo-secure-store";
import type { User } from "./types";

const TOKEN_KEY = "orin.mobile.access-token.v1";
const WORKSPACE_KEY = "orin.mobile.workspace-id.v1";
const configuredBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL;
const isDevelopment = typeof __DEV__ !== "undefined" && __DEV__;

export const normalizeBaseUrl = (value: string) =>
  value.trim().replace(/\/+$/, "");
const selectedBaseUrl = normalizeBaseUrl(
  configuredBaseUrl || (isDevelopment ? "http://10.0.2.2:8100" : ""),
);
const isUsbTestEndpoint =
  process.env.EXPO_PUBLIC_USB_TEST_MODE === "true" &&
  selectedBaseUrl === "http://127.0.0.1:8100";
export const API_BASE_URL =
  !isDevelopment &&
  !isUsbTestEndpoint &&
  selectedBaseUrl &&
  !selectedBaseUrl.startsWith("https://")
    ? ""
    : selectedBaseUrl;

let accessToken: string | null = null;
let activeWorkspaceId: string | null = null;
let refreshPromise: Promise<boolean> | null = null;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export const errorMessage = (value: unknown) =>
  value instanceof Error ? value.message : "Something went wrong.";

export const errorDetail = (data: unknown, fallback: string) => {
  if (!data || typeof data !== "object" || !("detail" in data)) return fallback;
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail
      .map((item) => {
        if (
          item &&
          typeof item === "object" &&
          "msg" in item &&
          typeof item.msg === "string"
        )
          return item.msg;
        return "Invalid input";
      })
      .join("; ");
  if (
    detail &&
    typeof detail === "object" &&
    "message" in detail &&
    typeof detail.message === "string"
  )
    return detail.message;
  return fallback;
};

const fetchWithTimeout = async (
  url: string,
  init: RequestInit,
  timeoutMs = 120_000,
) => {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, {
      ...init,
      signal: init.signal ?? controller.signal,
    });
  } finally {
    clearTimeout(timeout);
  }
};

const persistToken = async (token: string | null) => {
  accessToken = token;
  if (token) await SecureStore.setItemAsync(TOKEN_KEY, token);
  else await SecureStore.deleteItemAsync(TOKEN_KEY);
};

export const hydrateSession = async () => {
  [accessToken, activeWorkspaceId] = await Promise.all([
    SecureStore.getItemAsync(TOKEN_KEY),
    SecureStore.getItemAsync(WORKSPACE_KEY),
  ]);
};

export const setActiveWorkspace = async (id: string | null) => {
  activeWorkspaceId = id;
  if (id) await SecureStore.setItemAsync(WORKSPACE_KEY, id);
  else await SecureStore.deleteItemAsync(WORKSPACE_KEY);
};
export const getActiveWorkspaceId = () => activeWorkspaceId;

const refresh = async () => {
  if (!API_BASE_URL) return false;
  if (!refreshPromise) {
    refreshPromise = fetchWithTimeout(
      `${API_BASE_URL}/api/v1/auth/refresh`,
      {
        method: "POST",
        credentials: "include",
      },
      10_000,
    )
      .then(async (response) => {
        if (!response.ok) {
          await persistToken(null);
          return false;
        }
        const data = (await response.json()) as { access_token: string };
        await persistToken(data.access_token);
        return true;
      })
      .catch(async () => {
        await persistToken(null);
        return false;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
};

export async function request<T>(
  path: string,
  options: RequestInit = {},
  retry = true,
): Promise<T> {
  if (!API_BASE_URL)
    throw new ApiError(
      "EXPO_PUBLIC_API_BASE_URL must be an HTTPS URL in production.",
      0,
    );
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type"))
    headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (activeWorkspaceId) headers.set("X-Orin-Workspace-Id", activeWorkspaceId);
  let response: Response;
  try {
    response = await fetchWithTimeout(`${API_BASE_URL}/api/v1${path}`, {
      ...options,
      headers,
      credentials: "include",
    });
  } catch (cause) {
    const timedOut = cause instanceof Error && cause.name === "AbortError";
    throw new ApiError(
      timedOut
        ? "Orin took too long to respond."
        : `Could not reach Orin at ${API_BASE_URL}.`,
      0,
    );
  }
  if (response.status === 401 && retry && !path.startsWith("/auth/")) {
    if (await refresh()) return request<T>(path, options, false);
  }
  if (!response.ok) {
    const fallback = `Request failed (${response.status}).`;
    let data: unknown;
    try {
      data = await response.json();
    } catch {
      data = null;
    }
    throw new ApiError(errorDetail(data, fallback), response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const login = async (email: string, password: string) => {
  const result = await request<{ access_token: string }>(
    "/auth/login",
    {
      method: "POST",
      body: JSON.stringify({ email: email.trim(), password }),
    },
    false,
  );
  await persistToken(result.access_token);
  return request<User>("/auth/me", {}, false);
};

export const register = async (
  email: string,
  password: string,
  displayName: string,
) => {
  await request<User>(
    "/auth/register",
    {
      method: "POST",
      body: JSON.stringify({
        email: email.trim(),
        password,
        display_name: displayName.trim(),
      }),
    },
    false,
  );
  return login(email, password);
};

export const restoreSession = async () => {
  await hydrateSession();
  if (!accessToken && !(await refresh())) return null;
  try {
    return await request<User>("/auth/me", {}, false);
  } catch {
    if (await refresh()) return request<User>("/auth/me", {}, false);
    return null;
  }
};

export const logout = async () => {
  try {
    await request<void>("/auth/logout", { method: "POST" }, false);
  } finally {
    await Promise.all([persistToken(null), setActiveWorkspace(null)]);
  }
};
