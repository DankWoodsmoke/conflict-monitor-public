import {act} from "react";
import {createRoot,type Root} from "react-dom/client";
import {afterEach,beforeEach,describe,expect,it,vi} from "vitest";
import {IntelMediaView} from "./IntelMediaView";
import {apiFetch} from "../lib/api";
import {buildShowcase} from "../lib/showcase";
import {ShowcaseBriefing} from "./MediaFrame";
vi.mock("../lib/api",()=>({apiFetch:vi.fn()}));
const fetchMock=vi.mocked(apiFetch);const clock=Date.parse("2026-10-29T06:00:00Z"),fixture=buildShowcase(clock).events[0];
const report={...fixture,id:123,source:"rss_fixture",event_type:"unclassified" as const,severity:0,timestamp:new Date(clock-1000).toISOString(),confirmed_networks:"SATELLITE,WEST_PRESS",source_url:"javascript:alert(1)",summary:"Synthetic unscored source record"};
let host:HTMLDivElement,root:Root;
beforeEach(()=>{(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;vi.useFakeTimers();vi.setSystemTime(clock);fetchMock.mockReset();fetchMock.mockImplementation(async()=>Response.json({sitrep:null}));host=document.createElement("div");document.body.append(host);root=createRoot(host);});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.useRealTimers();});
describe("optional media truth and failure states",()=>{
 it("keeps provider captions outside the media surface so either caption position reserves layout space",async()=>{
  await act(async()=>root.render(<IntelMediaView events={[]}/>));
  const cards=[...host.querySelectorAll<HTMLElement>('.media-source-cell')];expect(cards).toHaveLength(3);
  for(const card of cards){const caption=card.querySelector('.media-source-caption'),content=card.querySelector('.media-source-content');expect(caption?.parentElement).toBe(card);expect(content?.parentElement).toBe(card);expect(content?.contains(caption!)).toBe(false);}
  expect(new Set(cards.map(card=>card.style.flexDirection))).toEqual(new Set(['column','column-reverse']));
 });
 it("makes the synthetic briefing a named keyboard scroll region with its original disclosure and control",async()=>{
  await act(async()=>root.render(<ShowcaseBriefing/>));const region=host.querySelector<HTMLElement>('[role="region"][aria-label="Synthetic briefing exercise"]')!;
  expect(region.tabIndex).toBe(0);region.focus();expect(document.activeElement).toBe(region);expect(region.textContent).toContain('no recorded footage or narration');
  await act(async()=>region.querySelector<HTMLButtonElement>('button')!.click());expect(region.querySelector('button')?.getAttribute('aria-pressed')).toBe('true');
 });
 it("shows unscored reports without invented priority, network confirmation or unsafe publisher links",async()=>{
  const future={...report,id:124,summary:"Future fixture",timestamp:new Date(clock+60000).toISOString()};
  await act(async()=>root.render(<IntelMediaView events={[report,future]}/>));
  expect(host.textContent).toContain("UNSCORED");expect(host.textContent).not.toMatch(/HIGH-PRIORITY|Future fixture|✓/);expect(host.querySelector('a[href^="javascript:"]')).toBeNull();
  expect(host.textContent).toContain("No source records available for this briefing");
 });
 it("distinguishes sensor/other families and includes unscored records in report mix",async()=>{
  await act(async()=>root.render(<IntelMediaView events={[report,{...report,id:2,source:"satellite_firms"},{...report,id:3,source:"unknown"}]}/>));
  await act(async()=>[...host.querySelectorAll("button")].find(b=>b.textContent?.includes("SOURCE RECORDS"))!.click());
  expect(host.textContent).toContain("SENSOR");expect(host.textContent).toContain("OTHER");expect(host.querySelector('[role="region"][aria-label="Source record counts"]')?.getAttribute("tabindex")).toBe("0");
  await act(async()=>[...host.querySelectorAll("button")].find(b=>b.textContent?.includes("REPORT MIX"))!.click());expect(host.textContent).toContain("UNSCORED");expect(host.textContent).not.toContain("THREAT MATRIX");expect(host.querySelector('[role="region"][aria-label="Report type counts"]')?.getAttribute("tabindex")).toBe("0");
 });
 it("labels empty versus failed briefing references and never leaves either in perpetual loading",async()=>{
  fetchMock.mockImplementation(async()=>new Response("{}",{status:503}));await act(async()=>root.render(<IntelMediaView events={[]}/>));
  expect(host.textContent).toContain("Source references unavailable");expect(host.textContent).toContain("Briefing service unavailable");expect(host.textContent).not.toContain("Loading briefing source records");
 });
 it("keeps cited free records unscored and removes inherited checkmarks from the source strip",async()=>{
  fetchMock.mockImplementation(async(input)=>Response.json(String(input).endsWith("/events")?[report]:{sitrep:{id:1,trigger:"source_digest",headline:"Synthetic source digest",events_analyzed:1,escalation_level:"UNASSESSED",generated_at:new Date(clock).toISOString()}}));
  await act(async()=>root.render(<IntelMediaView events={[report]}/>));expect(host.textContent).toContain("1 REPORTS");expect(host.textContent).not.toMatch(/SEV 0|TRIGGERS|✓/);expect(host.querySelector('a[href^="javascript:"]')).toBeNull();
 });
 it("expires a report from the recent window when the source clock advances without new data",async()=>{
  const boundary={...report,timestamp:new Date(clock-4*3600000+5000).toISOString()};await act(async()=>root.render(<IntelMediaView events={[boundary]}/>));
  await act(async()=>[...host.querySelectorAll("button")].find(b=>b.getAttribute("aria-label")==="Pause panel rotation")!.click());expect(host.textContent).toContain(report.summary);
  await act(async()=>vi.advanceTimersByTimeAsync(30000));expect(host.textContent).not.toContain(report.summary);
 });
});
