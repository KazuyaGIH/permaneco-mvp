const stateChangingMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function isLoginRequest(path: string): boolean {
  return path.split("?")[0]?.endsWith("/api/auth/login") ?? false;
}

export function readCsrfToken(cookieString: string): string | null {
  const item = cookieString
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith("csrf_token="));
  return item ? decodeURIComponent(item.slice("csrf_token=".length)) : null;
}

export function redirectOnUnauthorized(
  response: Pick<Response, "status">,
  path: string,
  redirect: (destination: string) => void,
): boolean {
  if (response.status !== 401 || isLoginRequest(path)) return false;
  redirect("/");
  return true;
}

export function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const method = (init.method ?? "GET").toUpperCase();
  const path = typeof input === "string" ? input : input.toString();
  const loginRequest = isLoginRequest(path);
  const headers = new Headers(init.headers);
  if (
    stateChangingMethods.has(method) &&
    !loginRequest &&
    typeof document !== "undefined"
  ) {
    const token = readCsrfToken(document.cookie);
    if (token) headers.set("X-CSRF-Token", token);
  }
  return fetch(input, { ...init, headers, credentials: "same-origin" }).then((response) => {
    if (typeof window !== "undefined") {
      redirectOnUnauthorized(response, path, (destination) => window.location.assign(destination));
    }
    return response;
  });
}
