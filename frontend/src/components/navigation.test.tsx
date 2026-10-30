import { act, useEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Header } from "./Header";
import { SettingsPanel } from "./SettingsPanel";
import { AboutPanel } from "./AboutPanel";
import { useTracking } from "../hooks/useTracking";
import {ShowcaseBar} from './ShowcaseBar';

vi.mock("../lib/api",()=>({apiFetch:vi.fn(async(input:string)=>Response.json(
  input.includes("/tracking/aircraft") ? [{icao24:"test",callsign:"SYNTHETIC",lat:0,lon:0,altitude:1000,on_ground:false}] :
  input.includes("/costs/") ? {configured:false,avg_daily_cost:null} : []
))}));

let root:Root;let host:HTMLDivElement;
beforeEach(()=>{(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;host=document.createElement("div");document.body.append(host);root=createRoot(host);});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.restoreAllMocks();});
const base={isConnected:false,eventCount:0,aircraftCount:0,vesselCount:0,demoMode:true,onAboutClick:vi.fn(),onSettingsClick:vi.fn(),viewMode:"earth" as const,onViewModeChange:vi.fn(),activeSources:new Set(["rss"]),onSourceToggle:vi.fn()};

describe("workspace navigation",()=>{
  it("gives the nonmodal capability tour a focus entry and return while respecting a foreground modal's Escape",async()=>{
    vi.spyOn(HTMLElement.prototype,'getClientRects').mockReturnValue([{width:100,height:40}] as any);
    await act(async()=>root.render(<ShowcaseBar view="earth" onView={()=>{}}/>));
    const trigger=host.querySelector<HTMLButtonElement>('[aria-controls="capability-tour"]')!;trigger.focus();await act(async()=>trigger.click());
    const close=host.querySelector<HTMLButtonElement>('[aria-label="Close capability tour"]')!;expect(document.activeElement).toBe(close);expect(host.querySelector('.showcase-tour')?.getAttribute('aria-modal')).toBe('false');
    const foreground=document.createElement('section');foreground.setAttribute('role','dialog');foreground.setAttribute('aria-modal','true');document.body.append(foreground);
    await act(async()=>window.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',cancelable:true})));expect(host.querySelector('.showcase-tour')).not.toBeNull();foreground.remove();
    await act(async()=>window.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',cancelable:true})));expect(host.querySelector('.showcase-tour')).toBeNull();expect(document.activeElement).toBe(trigger);
    await act(async()=>trigger.click());await act(async()=>host.querySelector<HTMLButtonElement>('[aria-label="Close capability tour"]')!.click());expect(document.activeElement).toBe(trigger);
  });
  it("uses the workspace view names and explains the free source briefing",async()=>{
    await act(async()=>root.render(<AboutPanel onClose={()=>{}}/>));
    expect([...host.querySelectorAll('h3')].map(h=>h.textContent)).toEqual(["01 / Earth","02 / Media","03 / Brief"]);
    expect(host.textContent).toContain("free attributed source digests");expect(host.textContent).toContain("unassessed risk");
  });
  it("exposes the Earth workspace and auxiliary panels with an active state and a working Earth button",async()=>{
    const onView=vi.fn();await act(async()=>root.render(<Header {...base} onViewModeChange={onView}/>));
    const nav=host.querySelector('nav[aria-label="Workspace views"]')!;
    expect([...nav.querySelectorAll("button")].map(button=>button.textContent)).toEqual(["Earth","Media","Brief"]);
    expect(nav.querySelector('[aria-pressed="true"]')?.textContent).toBe("Earth");
    await act(async()=>(nav.querySelectorAll("button")[0] as HTMLButtonElement).click());
    expect(onView).toHaveBeenCalledWith("earth");
  });
  it("makes provider settings and evidence methods directly accessible",async()=>{
    const settings=vi.fn(),methods=vi.fn();await act(async()=>root.render(<Header {...base} onSettingsClick={settings} onAboutClick={methods}/>));
    await act(async()=>{[...host.querySelectorAll("button")].find(b=>b.textContent==="Settings")!.click();host.querySelector<HTMLButtonElement>('[aria-label="Methods and evidence limitations"]')!.click();});
    expect(settings).toHaveBeenCalledOnce();expect(methods).toHaveBeenCalledOnce();
  });
  it("applies a provider key only through the memory callback, with no browser persistence",async()=>{
    const save=vi.spyOn(Storage.prototype,"setItem");const apply=vi.fn();
    await act(async()=>root.render(<SettingsPanel googleKey="synthetic-test-key" googleEnabled={true} onApply={apply} onClose={()=>{}}/>));
    expect(host.querySelector('input[type="password"]')).not.toBeNull();
    await act(async()=>[...host.querySelectorAll("button")].find(b=>b.textContent?.startsWith("Apply"))!.click());
    expect(apply).toHaveBeenCalledWith("synthetic-test-key",true);expect(save).not.toHaveBeenCalled();
  });
  it("keeps an explicit generation operator key in the session callback and never browser storage",async()=>{
    const save=vi.spyOn(Storage.prototype,"setItem"),operator=vi.fn(),apply=vi.fn();
    await act(async()=>root.render(<SettingsPanel googleKey="" googleEnabled={false} operatorKey="synthetic-operator-fixture" onOperatorKeyChange={operator} onApply={apply} onClose={()=>{}}/>));
    expect(host.textContent).toContain("Sent to your configured backend only after you explicitly request analysis or video");
    await act(async()=>[...host.querySelectorAll("button")].find(button=>button.textContent?.startsWith("Apply"))!.click());
    expect(operator).toHaveBeenCalledWith("synthetic-operator-fixture");expect(save).not.toHaveBeenCalled();
  });
  it("preserves an edited field across parent callback changes and invokes the latest Escape handler",async()=>{
    const opener=document.createElement("button");document.body.append(opener);opener.focus();
    const first=vi.fn(),latest=vi.fn();
    await act(async()=>root.render(<SettingsPanel googleKey="synthetic-key" googleEnabled onApply={()=>{}} onClose={first}/>));
    const field=host.querySelector<HTMLInputElement>('input[type="password"]')!;field.focus();
    await act(async()=>root.render(<SettingsPanel googleKey="synthetic-key" googleEnabled onApply={()=>{}} onClose={latest}/>));
    expect(document.activeElement).toBe(field);
    await act(async()=>window.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape"})));
    expect(first).not.toHaveBeenCalled();expect(latest).toHaveBeenCalledOnce();
    await act(async()=>root.render(null));expect(document.activeElement).toBe(opener);opener.remove();
  });
});

describe("historical tracking boundary",()=>{
  it("clears live tracks during replay when the requested snapshot is unavailable",async()=>{
    let count=-1;
    function Harness({cursor}:{cursor:number|null}){const data=useTracking({replayCursor:cursor,replayWindow:cursor==null?null:{start:0,end:cursor}});useEffect(()=>{count=data.aircraft.length;},[data.aircraft]);return null;}
    await act(async()=>root.render(<Harness cursor={null}/>));expect(count).toBe(1);
    await act(async()=>root.render(<Harness cursor={1000}/>));expect(count).toBe(0);
  });
});
