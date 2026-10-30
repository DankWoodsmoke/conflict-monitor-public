import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TimelineScrubber,dayAxisTicks } from "./TimelineScrubber";
import { LiveFeed } from "./LiveFeed";
import { buildShowcase } from "../lib/showcase";

let root:Root,host:HTMLDivElement;
beforeEach(()=>{(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;host=document.createElement("div");document.body.append(host);root=createRoot(host);});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.useRealTimers();vi.restoreAllMocks();});

describe("report timeline state",()=>{
  it("keeps a 244-day history domain while bounding labels to readable desktop and phone spacing",async()=>{
    vi.useFakeTimers();vi.setSystemTime(new Date("2026-10-29T00:00:00Z"));
    const start=Date.parse("2026-02-28T00:00:00Z"),end=Date.now();
    for(const width of [320,390,1100,1536]){
      const labels=dayAxisTicks(start,end,width);
      expect(labels[0].ts).toBe(start);expect(labels.length).toBeLessThanOrEqual(Math.floor(width/64));
      expect(labels[labels.length-1].dayNum).toBeGreaterThan(180);
      for(let i=1;i<labels.length;i++)expect((labels[i].pct-labels[i-1].pct)*width/100).toBeGreaterThanOrEqual(64);
    }
    await act(async()=>root.render(<TimelineScrubber allEvents={[]} timeRange={null} activeRange={null} onRangeChange={()=>{}} historyStart="2026-02-28T00:00:00Z"/>));
    expect(host.querySelectorAll('[data-axis-day]').length).toBeLessThanOrEqual(16);
    expect(host.textContent).toContain("DAY 244");
  });
  it("preserves window duration at the right boundary instead of shrinking or inverting on repeated arrow keys",async()=>{
    vi.useFakeTimers();vi.setSystemTime(new Date("2026-10-29T03:00:00Z"));
    const now=Date.now(),duration=22*3600000;let current:{start:Date;end:Date}|null=null;
    function Harness(){const [range,setRange]=useState<{start:Date;end:Date}|null>({start:new Date(now-24*3600000),end:new Date(now-2*3600000)});current=range;return <TimelineScrubber allEvents={[]} timeRange={null} activeRange={range} onRangeChange={setRange}/>;}
    await act(async()=>root.render(<Harness/>));
    for(let i=0;i<30;i++)await act(async()=>window.dispatchEvent(new KeyboardEvent("keydown",{code:"ArrowRight"})));
    expect(current!.end.getTime()).toBe(now);expect(current!.start.getTime()).toBe(now-duration);
    expect(current!.end.getTime()-current!.start.getTime()).toBe(duration);
  });
  it("leaves media, nested button, editor, custom control and Earth canvas arrows with their native owner",async()=>{
    const change=vi.fn(),now=Date.now(),range={start:new Date(now-86400000),end:new Date(now)};
    await act(async()=>root.render(<><TimelineScrubber allEvents={[]} timeRange={null} activeRange={range} onRangeChange={change}/><div>
      <video controls/><audio controls/><button><span data-button-child>Overview</span></button><input/><textarea/><select><option>Choice</option></select><a href="#fixture">Link</a><details><summary>More</summary></details><div contentEditable suppressContentEditableWarning><span data-editor-child>Editable text</span></div><div role="slider"/><div tabIndex={0} aria-label="Scrollable context"/><canvas/>
    </div></>));
    for(const selector of ['video','audio','[data-button-child]','input','textarea','select','a','summary','[data-editor-child]','[role="slider"]','[tabindex="0"]','canvas'])for(const code of ['ArrowLeft','ArrowRight']){
      const event=new KeyboardEvent('keydown',{code,bubbles:true,cancelable:true});await act(async()=>host.querySelector(selector)!.dispatchEvent(event));
      expect(event.defaultPrevented,selector).toBe(false);expect(change,selector).not.toHaveBeenCalled();expect(host.textContent).toContain('● LIVE');
    }
  });
  it("does not steal arrows dispatched at window while an outside control owns focus",async()=>{
    const change=vi.fn(),now=Date.now();await act(async()=>root.render(<><TimelineScrubber allEvents={[]} timeRange={null} activeRange={{start:new Date(now-86400000),end:new Date(now)}} onRangeChange={change}/><button data-focus-owner>Outside control</button></>));
    host.querySelector<HTMLButtonElement>('[data-focus-owner]')!.focus();const event=new KeyboardEvent('keydown',{code:'ArrowLeft',cancelable:true});await act(async()=>window.dispatchEvent(event));
    expect(event.defaultPrevented).toBe(false);expect(change).not.toHaveBeenCalled();expect(host.textContent).toContain('● LIVE');
  });
  it("respects foreground modals even with body focus, but not a hidden native attribution dialog",async()=>{
    const change=vi.fn(),now=Date.now();await act(async()=>root.render(<><TimelineScrubber allEvents={[]} timeRange={null} activeRange={{start:new Date(now-86400000),end:new Date(now)}} onRangeChange={change}/><div data-overlay><div role="dialog" aria-modal="true">Fixture foreground</div></div></>));
    const event=new KeyboardEvent('keydown',{code:'ArrowLeft',cancelable:true});await act(async()=>window.dispatchEvent(event));expect(event.defaultPrevented).toBe(false);expect(change).not.toHaveBeenCalled();
    host.querySelector<HTMLElement>('[data-overlay]')!.style.display='none';const background=new KeyboardEvent('keydown',{code:'ArrowLeft',cancelable:true});await act(async()=>host.querySelector('.timeline-stats')!.dispatchEvent(new MouseEvent('click',{bubbles:true})));await act(async()=>window.dispatchEvent(background));
    expect(background.defaultPrevented).toBe(true);expect(change).toHaveBeenCalledOnce();expect(change.mock.calls[0][0].end.getTime()-change.mock.calls[0][0].start.getTime()).toBe(86400000);expect(host.textContent).not.toContain('● LIVE');
  });
  it("respects prior event ownership, composition and modifier chords without changing LIVE",async()=>{
    const change=vi.fn(),now=Date.now();await act(async()=>root.render(<TimelineScrubber allEvents={[]} timeRange={null} activeRange={{start:new Date(now-86400000),end:new Date(now)}} onRangeChange={change}/>));
    for(const init of [{isComposing:true},{altKey:true},{ctrlKey:true},{metaKey:true},{shiftKey:true}]){
      const event=new KeyboardEvent('keydown',{code:'ArrowRight',cancelable:true,...init});await act(async()=>window.dispatchEvent(event));expect(event.defaultPrevented).toBe(false);expect(change).not.toHaveBeenCalled();
    }
    const prevented=new KeyboardEvent('keydown',{code:'ArrowLeft',cancelable:true});prevented.preventDefault();await act(async()=>window.dispatchEvent(prevented));expect(change).not.toHaveBeenCalled();expect(host.textContent).toContain('● LIVE');
  });
  it("labels its geolocated subset rather than implying unlocated reports are missing",async()=>{
    const fixture=buildShowcase(Date.now()).events[0];const events=[fixture,{...fixture,id:fixture.id+1,lat:null,lon:null}];
    await act(async()=>root.render(<TimelineScrubber allEvents={events} timeRange={null} activeRange={null} onRangeChange={()=>{}}/>));
    expect(host.querySelector('.timeline-stats')?.textContent).toContain("1 / 1 MAPPED REPORTS");
  });
  it("preserves the replay cursor on pause and labels it explicitly",async()=>{
    vi.useFakeTimers();const now=Date.now(),start=now-3600000;
    let current:number|null=null;
    function Harness(){const [cursor,setCursor]=useState<number|null>(null);current=cursor;return <TimelineScrubber allEvents={[]} timeRange={null} activeRange={{start:new Date(start),end:new Date(now)}} onRangeChange={()=>{}} replayCursor={cursor} onReplayCursorChange={setCursor}/>;}
    await act(async()=>root.render(<Harness/>));
    await act(async()=>host.querySelector<HTMLButtonElement>('[title="Replay events in current window"]')!.click());
    await act(async()=>vi.advanceTimersByTime(50));const beforePause=current;
    await act(async()=>host.querySelector<HTMLButtonElement>('[title="Pause replay"]')!.click());
    expect(current).toBe(beforePause);expect(current).not.toBeNull();expect(host.textContent).toContain("REPLAY PAUSED");expect(host.textContent).not.toContain("● LIVE");
    await act(async()=>vi.advanceTimersByTime(1000));expect(current).toBe(beforePause);
    await act(async()=>host.querySelector<HTMLButtonElement>('[title="Resume replay"]')!.click());
    await act(async()=>vi.advanceTimersByTime(50));expect(current).toBeGreaterThan(beforePause!);
    await act(async()=>[...host.querySelectorAll("button")].find(b=>b.textContent?.trim()==="24H")!.click());
    expect(current).toBeNull();expect(host.textContent).toContain("● LIVE");
  });
  it("discloses capped coverage and uses the server-configured history origin",async()=>{
    const load=vi.fn();await act(async()=>root.render(<TimelineScrubber allEvents={[]} timeRange={null} activeRange={null} onRangeChange={()=>{}} historyStart="2026-10-01T00:00:00Z" historyStatus="limited" historyTruncated onLoadHistory={load}/>));
    expect(host.querySelector('[role="status"]')?.textContent).toContain("5,000");
    expect(host.querySelector('[role="status"]')?.textContent).toContain("incomplete");
    const all=[...host.querySelectorAll("button")].find(b=>b.textContent?.trim()==="ALL")!;
    expect(all.title).toContain("01 OCT");
    await act(async()=>all.click());expect(load).toHaveBeenCalledOnce();expect(host.textContent).toContain("LOADED HISTORY");expect(host.textContent).not.toContain("FULL CONFLICT");
  });
  it.each(["error", "limited"] as const)("discloses incomplete connection recovery while transport can remain up (%s)",async(status)=>{
    await act(async()=>root.render(<TimelineScrubber allEvents={[]} timeRange={null} activeRange={null} onRangeChange={()=>{}} historyStatus="loaded" recoveryStatus={status}/>));
    const receipt=host.querySelector('[role="status"]');
    expect(receipt?.textContent).toContain("reports may be missing");expect(receipt?.getAttribute("data-state")).toBe(status);
  });
  it("keeps a native, labeled locate action available to keyboard users",async()=>{
    const event=buildShowcase(Date.now()).events[0],locate=vi.fn();
    await act(async()=>root.render(<LiveFeed events={[event]} onEventClick={locate}/>));
    const button=host.querySelector<HTMLButtonElement>('button[aria-label^="Locate report:"]');
    expect(button).not.toBeNull();button!.focus();expect(document.activeElement).toBe(button);
    await act(async()=>button!.click());expect(locate).toHaveBeenCalledWith(event);
  });
});
