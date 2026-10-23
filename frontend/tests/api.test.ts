import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch, readCsrfToken } from "../lib/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("CSRF fetch helper", () => {
  it("reads the CSRF cookie without confusing it with other cookies", () => {
    expect(readCsrfToken("theme=dark; csrf_token=abc%2F123; other=value")).toBe("abc/123");
    expect(readCsrfToken("theme=dark")).toBeNull();
  });

  it("sends the CSRF header for state-changing requests but not login", async () => {
    Object.defineProperty(globalThis, "document", {
      configurable: true,
      value: { cookie: "csrf_token=token-123" },
    });
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/auth/logout", { method: "POST" });
    await apiFetch("/api/auth/login", { method: "POST" });

    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get("X-CSRF-Token")).toBe("token-123");
    expect(new Headers(fetchMock.mock.calls[1][1]?.headers).get("X-CSRF-Token")).toBeNull();
    expect(fetchMock.mock.calls[0][1]?.credentials).toBe("same-origin");
  });
});
