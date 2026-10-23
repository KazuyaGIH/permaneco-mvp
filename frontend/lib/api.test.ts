import { describe, expect, it } from "vitest";

import { redirectOnUnauthorized } from "./api";

describe("unauthorized API responses", () => {
  it("redirects to the login page", () => {
    const destinations: string[] = [];
    const redirected = redirectOnUnauthorized({ status: 401 }, "/api/me/profile", (destination) => {
      destinations.push(destination);
    });

    expect(redirected).toBe(true);
    expect(destinations).toEqual(["/"]);
  });

  it("does not redirect when login rejects credentials", () => {
    const destinations: string[] = [];
    const redirected = redirectOnUnauthorized({ status: 401 }, "/api/auth/login", (destination) => {
      destinations.push(destination);
    });

    expect(redirected).toBe(false);
    expect(destinations).toEqual([]);
  });
});
