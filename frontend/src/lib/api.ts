import { SHOWCASE } from "./runtime";
import { showcaseResponse } from "./showcase";

export async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  if (init?.signal?.aborted) throw new DOMException("Request aborted", "AbortError");
  if (!SHOWCASE) {
    const timeout=AbortSignal.timeout(12000);
    const signal=init?.signal ? AbortSignal.any([init.signal,timeout]) : timeout;
    return fetch(input,{...init,signal});
  }
  const url = new URL(input instanceof Request ? input.url : String(input), window.location.href);
  const method = init?.method || (input instanceof Request ? input.method : "GET");
  if (method !== "GET") return Response.json({detail:"Showcase is read-only; no requests are sent."}, {status:405});
  // Static local cartography is part of the distribution. No external API fallback.
  if (url.origin === window.location.origin && url.pathname.startsWith("/textures/")) return fetch(input, init);
  const data = url.origin === window.location.origin ? showcaseResponse(url) : undefined;
  return data === undefined
    ? Response.json({detail:"This provider is not connected in the synthetic showcase."}, {status:503})
    : Response.json(data, {headers:{"X-Data-Mode":"synthetic-showcase"}});
}
