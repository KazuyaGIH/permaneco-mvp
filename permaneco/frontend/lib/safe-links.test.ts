import { describe, expect, it } from "vitest";

import { safeLink } from "./safe-links";

describe("safeLink", () => {
  it("allows the configured domain and its subdomains", () => {
    expect(safeLink("https://cvv.org.br/")).not.toBeNull();
    expect(safeLink("https://atendimento.cvv.org.br/")).not.toBeNull();
    expect(safeLink("https://example.com/guia")).not.toBeNull();
  });

  it("rejects lookalikes and non-web protocols", () => {
    expect(safeLink("https://gov.br.evil.example/")).toBeNull();
    expect(safeLink("https://notgov.br/")).toBeNull();
    expect(safeLink("javascript:alert(1)")).toBeNull();
  });
});
