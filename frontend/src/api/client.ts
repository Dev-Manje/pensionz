const BASE_URL = import.meta.env.VITE_API_BASE_URL;

const ACCESS_KEY = "access_token";
const REFRESH_KEY = "refresh_token";

let accessToken: string | null = localStorage.getItem(ACCESS_KEY);
let refreshToken: string | null = localStorage.getItem(REFRESH_KEY);

export interface Tokens {
  access_token: string;
  refresh_token: string;
}

// Store (or, with null, clear) the session's token pair.
export function setTokens(tokens: Tokens | null) {
  accessToken = tokens?.access_token ?? null;
  refreshToken = tokens?.refresh_token ?? null;
  for (const [key, value] of [
    [ACCESS_KEY, accessToken],
    [REFRESH_KEY, refreshToken],
  ] as const) {
    if (value) localStorage.setItem(key, value);
    else localStorage.removeItem(key);
  }
}

export function getAccessToken() {
  return accessToken;
}

// Called when the session can't be recovered (a 401 that a token refresh
// didn't fix). AuthContext registers this to sign the user out, and the
// router then sends them to /login?next=<where they were>.
let unauthorizedHandler: (() => void) | null = null;

export function onUnauthorized(handler: (() => void) | null) {
  unauthorizedHandler = handler;
}

// One refresh at a time: when several requests hit an expired access token
// together, they all wait on the same refresh instead of each sending one.
let refreshInFlight: Promise<boolean> | null = null;

function refreshSession(): Promise<boolean> {
  if (!refreshToken) return Promise.resolve(false);
  refreshInFlight ??= (async () => {
    try {
      const response = await fetch(`${BASE_URL}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!response.ok) return false;
      setTokens((await response.json()) as Tokens);
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

// fetch with the bearer token; on a 401 for a request that carried a token,
// refresh the session once and retry. If that fails, sign out.
async function authorizedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const send = async () => {
    const headers = new Headers(init.headers);
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
    try {
      return await fetch(`${BASE_URL}${path}`, { ...init, headers });
    } catch {
      // fetch only rejects when no response arrived (offline, server down, blocked)
      throw new ApiError(0, NETWORK_ERROR);
    }
  };
  const sentToken = accessToken;
  let response = await send();
  if (response.status !== 401 || !sentToken) return response;

  if (await refreshSession()) {
    response = await send();
    if (response.status !== 401) return response;
  }
  setTokens(null);
  unauthorizedHandler?.();
  return response;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export const NETWORK_ERROR = "Couldn't reach the server. Check your connection and try again.";

async function toApiError(response: Response): Promise<ApiError> {
  let detail =
    response.status >= 500
      ? `Something went wrong on our side (error ${response.status}). Please try again in a moment.`
      : response.statusText || `Request failed (error ${response.status}).`;
  try {
    const data = await response.json();
    detail = describeDetail(data.detail) ?? detail;
  } catch {
    // response had no JSON body
  }
  return new ApiError(response.status, detail);
}

// FastAPI sends a string, or for invalid input a list of {loc, msg} — show
// the messages rather than "[object Object]".
export function describeDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : null))
      .filter(Boolean);
    return msgs.length ? msgs.join("; ") : null;
  }
  return null;
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await authorizedFetch(path, { ...options, headers });
  if (!response.ok) throw await toApiError(response);

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

// For endpoints that return a raw file (PDF/Excel export) rather than
// JSON — fetches with the same auth handling apiFetch uses, then triggers a
// normal browser download via a throwaway anchor element.
export async function downloadFile(path: string, filenameFallback: string): Promise<void> {
  const response = await authorizedFetch(path);
  if (!response.ok) throw await toApiError(response);

  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition");
  const filename = disposition?.match(/filename="?([^"]+)"?/)?.[1] ?? filenameFallback;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
