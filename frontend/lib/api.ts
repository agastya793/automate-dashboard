/**
 * Centralized API Client with Cookie Authentication & CSRF Protection (Milestone 5)
 *
 * Enforces:
 * - credentials: "include" on every request to pass HTTP-only session cookies
 * - Automatic X-CSRF-Token header inclusion on state-changing requests (POST, PUT, DELETE, PATCH)
 * - Safe error handling without logging sensitive information
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") ||
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") ||
  "http://localhost:18001";

/**
 * Read cookie value from document.cookie in browser context.
 */
export function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp("(^|;\\s*)(" + name + ")=([^;]*)"));
  return match ? decodeURIComponent(match[3]) : null;
}

/**
 * Fetch a fresh CSRF token from FastAPI and return it.
 */
export async function fetchCsrfToken(): Promise<string | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/csrf`, {
      method: "GET",
      credentials: "include",
    });
    if (res.ok) {
      const data = await res.json();
      return data.csrf_token || getCookie("csrf_token");
    }
  } catch {
    // Non-fatal if offline
  }
  return getCookie("csrf_token");
}

/**
 * Centralized fetch wrapper ensuring secure session cookies and CSRF headers.
 */
export async function apiFetch(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const url = path.startsWith("http") ? path : `${API_BASE_URL}${path}`;
  const method = (options.method || "GET").toUpperCase();

  const headers = new Headers(options.headers || {});

  // JSON requests must advertise their payload type.  FormData requests are
  // intentionally left alone so the browser can supply the multipart boundary.
  if (
    options.body &&
    typeof options.body === "string" &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  // Add CSRF token on state-changing requests
  if (["POST", "PUT", "DELETE", "PATCH"].includes(method)) {
    let csrfToken = getCookie("csrf_token");
    if (!csrfToken && typeof document !== "undefined") {
      csrfToken = await fetchCsrfToken();
    }
    if (csrfToken && !headers.has("X-CSRF-Token")) {
      headers.set("X-CSRF-Token", csrfToken);
    }
  }

  const fetchOptions: RequestInit = {
    ...options,
    headers,
    credentials: "include", // Always include cookies for session authentication
  };

  return fetch(url, fetchOptions);
}
