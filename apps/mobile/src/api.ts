import * as SecureStore from "expo-secure-store";
import type { User } from "./types";

const TOKEN_KEY = "orin.mobile.access-token.v1";
const WORKSPACE_KEY = "orin.mobile.workspace-id.v1";
const LOGOUT_PENDING_KEY = "orin.mobile.logout-pending.v1";
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
let authRevision = 0;
let tokenWriteQueue: Promise<void> = Promise.resolve();
let workspaceWriteQueue: Promise<void> = Promise.resolve();

// Fence responses from a previous account/session, including in-flight refreshes.
const beginAuthTransition = () => {
  authRevision += 1;
  refreshPromise = null;
  return authRevision;
};

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

const persistToken = async (token: string | null, revision = authRevision) => {
  // Serialize secure-storage writes so an older refresh cannot finish after a
  // newer login and overwrite the new account's stored credentials.
  const write = tokenWriteQueue.catch(() => undefined).then(async () => {
    if (revision !== authRevision) return;
    accessToken = token;
    if (token) await SecureStore.setItemAsync(TOKEN_KEY, token);
    else await SecureStore.deleteItemAsync(TOKEN_KEY);
  });
  tokenWriteQueue = write;
  await write;
};

export const hydrateSession = async () => {
  const revision = authRevision;
  // Do not read credentials while a prior secure-storage write is unfinished.
  await Promise.all([
    tokenWriteQueue.catch(() => undefined),
    workspaceWriteQueue.catch(() => undefined),
  ]);
  const [token, workspace] = await Promise.all([
    SecureStore.getItemAsync(TOKEN_KEY),
    SecureStore.getItemAsync(WORKSPACE_KEY),
  ]);
  if (revision !== authRevision) return;
  accessToken = token;
  activeWorkspaceId = workspace;
};

export const setActiveWorkspace = async (id: string | null, revision = authRevision) => {
  const write = workspaceWriteQueue.catch(() => undefined).then(async () => {
    if (revision !== authRevision) return;
    activeWorkspaceId = id;
    if (id) await SecureStore.setItemAsync(WORKSPACE_KEY, id);
    else await SecureStore.deleteItemAsync(WORKSPACE_KEY);
  });
  workspaceWriteQueue = write;
  await write;
};
export const getActiveWorkspaceId = () => activeWorkspaceId;

const refresh = async () => {
  if (!API_BASE_URL) return false;
  if (!refreshPromise) {
    const revision = authRevision;
    refreshPromise = fetchWithTimeout(
      `${API_BASE_URL}/api/v1/auth/refresh`,
      {
        method: "POST",
        credentials: "include",
      },
      10_000,
    )
      .then(async (response) => {
        if (revision !== authRevision) return false;
        if (!response.ok) {
          // A rejected refresh credential ends the session. Temporary server
          // errors must not erase a still-valid token from secure storage.
          if (response.status === 401 || response.status === 403)
            await persistToken(null, revision);
          return false;
        }
        const data = (await response.json()) as { access_token: string };
        if (revision !== authRevision) return false;
        await persistToken(data.access_token, revision);
        return revision === authRevision;
      })
      .catch(() => false)
      .finally(() => {
        // Do not clear a newer account's independently started refresh.
        if (revision === authRevision) refreshPromise = null;
      });
  }
  return refreshPromise;
};

export async function request<T>(
  path: string,
  options: RequestInit = {},
  retry = true,
  timeoutMs = 120_000,
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
    }, timeoutMs);
  } catch (cause) {
    const timedOut = cause instanceof Error && cause.name === "AbortError";
    throw new ApiError(
      timedOut
        ? "Orin took too long to respond."
        : [
            `Could not reach Orin at ${API_BASE_URL}.`,
            "On a physical phone, check /health/ready in its browser.",
            "Use a reachable LAN address in development or HTTPS in release builds.",
          ].join(" "),
      0,
    );
  }
  if (response.status === 401 && retry && (!path.startsWith("/auth/") || path === "/auth/logout")) {
    if (await refresh()) return request<T>(path, options, false, timeoutMs);
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
  const revision = beginAuthTransition();
  // An unsuccessful account switch must not silently restore the old cookie
  // on the next launch. Only a verified explicit login clears this marker.
  await SecureStore.setItemAsync(LOGOUT_PENDING_KEY, "1");
  // A new account must never inherit the previous account's token or workspace.
  await Promise.all([persistToken(null, revision), setActiveWorkspace(null, revision)]);
  const result = await request<{ access_token: string }>(
    "/auth/login",
    {
      method: "POST",
      body: JSON.stringify({ email: email.trim(), password }),
    },
    false,
  );
  if (revision !== authRevision) throw new ApiError("Authentication changed during login.", 0);
  await persistToken(result.access_token, revision);
  const user = await request<User>("/auth/me", {}, false);
  if (revision !== authRevision) throw new ApiError("Authentication changed during login.", 0);
  // A successful explicit login supersedes a previously unconfirmed logout.
  await SecureStore.deleteItemAsync(LOGOUT_PENDING_KEY);
  return user;
};

export const register = async (
  email: string,
  password: string,
  displayName: string,
) => {
  const revision = beginAuthTransition();
  await SecureStore.setItemAsync(LOGOUT_PENDING_KEY, "1");
  // Registration is also an account switch: never attach a prior identity.
  await Promise.all([persistToken(null, revision), setActiveWorkspace(null, revision)]);
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
  if (revision !== authRevision) throw new ApiError("Authentication changed during registration.", 0);
  return login(email, password);
};

export const restoreSession = async () => {
  const revision = authRevision;
  await hydrateSession();
  if (revision !== authRevision) return null;
  // Offline logout may leave a valid HttpOnly refresh cookie on the device.
  // Never silently restore that session until the user signs in explicitly.
  if (await SecureStore.getItemAsync(LOGOUT_PENDING_KEY)) {
    accessToken = null;
    activeWorkspaceId = null;
    return null;
  }
  if (!accessToken && !(await refresh())) return null;
  if (revision !== authRevision) return null;
  try {
    const user = await request<User>("/auth/me", {}, false);
    return revision === authRevision ? user : null;
  } catch (cause) {
    // Retry authentication only when the API actually rejected the token.
    // Offline errors must not trigger a destructive refresh attempt.
    if (revision !== authRevision || !(cause instanceof ApiError) || cause.status !== 401) return null;
    if (!(await refresh()) || revision !== authRevision) return null;
    try {
      const user = await request<User>("/auth/me", {}, false);
      return revision === authRevision ? user : null;
    } catch {
      return null;
    }
  }
};

export const logout = async () => {
  const revision = beginAuthTransition();
  let revoked = false;
  try {
    // Persist the marker before the network request: a crash or offline
    // failure must not permit cookie-backed restoration on next launch.
    await SecureStore.setItemAsync(LOGOUT_PENDING_KEY, "1");
    // An expired access token may still have a valid refresh cookie.
    await request<void>("/auth/logout", { method: "POST" }, true, 8_000);
    revoked = true;
  } finally {
    // An older logout must not clear credentials from a newer explicit login.
    if (revision === authRevision) {
      await Promise.all([persistToken(null, revision), setActiveWorkspace(null, revision)]);
      if (revoked) await SecureStore.deleteItemAsync(LOGOUT_PENDING_KEY);
    }
  }
};
