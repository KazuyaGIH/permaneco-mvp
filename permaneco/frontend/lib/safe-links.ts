const allowedDomains = ["cvv.org.br", "gov.br", "example.com"];

export function safeLink(value: string): string | null {
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" && url.protocol !== "http:") return null;
    const host = url.hostname.toLowerCase().replace(/\.$/, "");
    return allowedDomains.some((domain) => host === domain || host.endsWith(`.${domain}`))
      ? url.toString()
      : null;
  } catch {
    return null;
  }
}
