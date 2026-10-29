import { describe, it, expect, vi, afterEach } from "vitest";
import { buildShowcase } from "./showcase";
import { sanitizeHtml, escapeHtml } from "./html";
import { safeUrl } from "./runtime";
import { hasMultipleReports, getNetworks } from "../utils/verification";

const clock = Date.parse("2026-10-28T12:00:00Z");
const fixture = buildShowcase(clock);

describe("source and inference boundaries",()=>{
  it("does not turn political network labels or repeated copies into confirmation",()=>{
    const event={...fixture.events[0],evidence:undefined,source_reliability:5,report_count:100,confirmed_networks:"TG,WEST_PRESS,SATELLITE"};
    expect(hasMultipleReports(event)).toBe(false);
    expect(getNetworks(event)).toEqual(["TG","WEST_PRESS","SATELLITE"]);
  });
  it("counts multiple source records without claiming origin independence",()=>{
    expect(hasMultipleReports(fixture.events[0])).toBe(true);
    expect(fixture.events[0].evidence?.independent_origin_count).toBeNull();
    expect(fixture.events[0].evidence?.verification_basis).toBe("none");
  });
  it("retains unresolved locations rather than parking them in an ocean",()=>{
    expect(fixture.events[9].lat).toBeNull();expect(fixture.events[9].lon).toBeNull();
    expect(fixture.events[9].geolocation_precision).toBe("unknown");
  });
});

describe("replayable synthetic exercise",()=>{
  it("produces identical output for an explicit reference clock",()=>{
    expect(buildShowcase(clock)).toEqual(fixture);
    expect(new Set(fixture.events.map(e=>e.id)).size).toBe(fixture.events.length);
  });
  it("labels every report and track synthetic and supplies no real incident links",()=>{
    expect(fixture.events.every(e=>e.synthetic && e.summary.startsWith("Exercise:") && e.source_url?.startsWith("https://example.org/"))).toBe(true);
    expect(fixture.aircraft.every(a=>a.synthetic)).toBe(true);
    expect(fixture.vessels.every(v=>v.synthetic)).toBe(true);
    expect(fixture.sitrep.synthetic).toBe(true);
  });
  it("supplies categorical thermal observations",()=>{
    expect(fixture.orbits).toHaveLength(4);
    expect(fixture.orbits.every(o=>o.synthetic && o.omm.NORAD_CAT_ID>99999)).toBe(true);
    expect(fixture.hotspots[0].conf).toBeNull();expect(fixture.hotspots[0].matched).toBe(false);
  });
  it("keeps replay snapshots chronological and source references resolvable",()=>{
    expect(fixture.snapshots.every((s,i)=>i===0||s.ts>fixture.snapshots[i-1].ts)).toBe(true);
    const ids=new Set(fixture.events.map(e=>e.id));
    const cited=[...JSON.stringify(fixture.sitrep).matchAll(/\[src:([\d,]+)\]/g)].flatMap(m=>m[1].split(",").map(Number));
    expect(cited.length).toBeGreaterThan(0);expect(cited.every(id=>ids.has(id))).toBe(true);
  });
});

describe("untrusted report rendering",()=>{
  it.each([
    '<img src=x onerror="alert(document.cookie)">',
    '<svg><g onload="alert(1)"></g></svg>',
    '<a href="javascript:alert(1)">source</a>',
    '<iframe srcdoc="<script>alert(1)</script>"></iframe>',
  ])("removes executable markup from a Leaflet sink: %s",payload=>{
    const el=document.createElement("div");el.innerHTML=sanitizeHtml(payload);
    expect(el.querySelector("script,iframe")).toBeNull();
    expect([...el.querySelectorAll("*")].flatMap(n=>[...n.attributes]).some(a=>/^on/i.test(a.name)||/^javascript:/i.test(a.value))).toBe(false);
  });
  it("escapes source text without turning it into provider-controlled HTML",()=>{
    const text='<img src="https://example.org/beacon">';
    const el=document.createElement("div");el.innerHTML=escapeHtml(text);
    expect(el.textContent).toBe(text);expect(el.querySelector("img")).toBeNull();
  });
  it.each(["javascript:alert(1)","data:text/html,<script>alert(1)</script>","file:///etc/passwd"])("rejects unsafe source links: %s",url=>expect(safeUrl(url)).toBe(""));
  it("preserves safe original-source HTTPS links",()=>expect(safeUrl("https://example.org/report?q=1")).toBe("https://example.org/report?q=1"));
});

describe("showcase network isolation",()=>{
  afterEach(()=>{vi.unstubAllGlobals();window.history.replaceState(null,"","/");});
  it("serves fixtures locally and fails unknown providers closed",async()=>{
    window.history.replaceState(null,"","/?showcase=true");vi.resetModules();
    const network=vi.fn();vi.stubGlobal("fetch",network);
    const {apiFetch}=await import("./api");
    const data=await (await apiFetch("/api/events?limit=5")).json();
    expect(data).toHaveLength(5);
    expect((await apiFetch("https://external.invalid/events")).status).toBe(503);
    expect((await apiFetch("/api/auth/telegram/start",{method:"POST"})).status).toBe(405);
    expect(network).not.toHaveBeenCalled();
  });
  it("does not substitute demo data when an operational request fails",async()=>{
    window.history.replaceState(null,"","/");vi.resetModules();
    const network=vi.fn().mockRejectedValue(new TypeError("offline"));vi.stubGlobal("fetch",network);
    const {apiFetch}=await import("./api");
    await expect(apiFetch("/api/events")).rejects.toThrow("offline");
    expect(network).toHaveBeenCalledOnce();
  });
});
