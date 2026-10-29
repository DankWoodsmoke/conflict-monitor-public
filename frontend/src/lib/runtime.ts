/** Explicit runtime selection. A failed live request never becomes demo data. */
export const SHOWCASE = typeof window !== "undefined" &&
  new URLSearchParams(window.location.search).get("showcase") === "true";
export const API_BASE = ((import.meta as any).env?.VITE_API_URL || "/api").replace(/\/$/, "");
export const MEDIA_BASE = ((import.meta as any).env?.VITE_MEDIA_URL || "").replace(/\/$/, "");

export function websocketUrl(): string {
  const url = new URL(`${API_BASE}/ws/events`, window.location.href);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.href;
}

export function safeUrl(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) return "";
  try {
    const url = new URL(value, typeof window === "undefined" ? "https://localhost" : window.location.origin);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch { return ""; }
}
