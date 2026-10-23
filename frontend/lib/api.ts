const stateChangingMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export function readCsrfToken(cookieString: string): string | null {
  const item = cookieString
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith("csrf_token="));
  return item ? decodeURIComponent(item.slice("csrf_token=".length)) : null;
}

export function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const method = (init.method ?? "GET").toUpperCase();
  const path = typeof input === "string" ? input : input.toString();
  const headers = new Headers(init.headers);
  if (
    stateChangingMethods.has(method) &&
    !path.endsWith("/api/auth/login") &&
    typeof document !== "undefined"
  ) {
    const token = readCsrfToken(document.cookie);
    if (token) headers.set("X-CSRF-Token", token);
  }
  return fetch(input, { ...init, headers, credentials: "same-origin" });
}
