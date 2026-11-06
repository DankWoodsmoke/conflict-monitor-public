import {act} from "react";
import {createRoot,type Root} from "react-dom/client";
import {afterEach,beforeEach,describe,expect,it,vi} from "vitest";
import {EarthContactsPanel} from "./EarthContactsPanel";
import type {EarthMarker} from "../lib/earth";

let host:HTMLDivElement,root:Root;
const markers:EarthMarker[]=Array.from({length:220},(_,i)=>({id:`${i%2?"vessel":"aircraft"}-${i}`,kind:i%2?"vessel":"aircraft",name:`Contact ${String(i).padStart(3,"0")}`,identifier:`ID ${i}`,searchTerms:[`code${i}`],lat:24+i/1000,lon:53+i/1000,height:0,color:"#8fd3f5",positionState:i%3?"last_known":"fresh",heading:i%4?90:null,details:[["Observed","2026-10-30 00:00:00 UTC · 60s before displayed clock"]]}));
beforeEach(()=>{(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;host=document.createElement("div");document.body.append(host);root=createRoot(host);});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();});
async function type(value:string){const input=host.querySelector("input")!;await act(async()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value")!.set!.call(input,value);input.dispatchEvent(new Event("input",{bubbles:true}));});}
const buttons=()=>host.querySelectorAll<HTMLButtonElement>("[data-contact-id]");
describe("dense contact access",()=>{
 it("lets long source text shrink inside the grid without removing its accessible content",async()=>{
  const longName="Contact "+"LONG-NAME-".repeat(30),longClock="2026-10-31 01:00:00 UTC · "+"source observation context ".repeat(20);
  const marker={...markers[0],name:longName,details:[["Observed",longClock]] as [string,string][]},choose=vi.fn();
  await act(async()=>root.render(<EarthContactsPanel markers={[marker]} areaGroup onChoose={choose} onZoom={()=>{}} onClose={()=>{}}/>));
  const list=host.querySelector<HTMLUListElement>(".earth-contact-list")!,button=buttons()[0];
  expect(list.style.gridTemplateColumns).toBe("minmax(0, 1fr)");expect(parseFloat(button.parentElement!.style.minWidth)).toBe(0);
  expect(button.style.width).toBe("100%");expect(parseFloat(button.style.minWidth)).toBe(0);expect(button.style.boxSizing).toBe("border-box");
  expect(button.textContent).toContain(longName);expect(button.textContent).toContain(longClock);expect(button.title).toContain(longName);expect(button.title).toContain(longClock);
  await act(async()=>button.click());expect(choose).toHaveBeenCalledExactlyOnceWith(marker);
 });
 it("counts every member, pages bounded rows and searches beyond the rendered page",async()=>{
  const choose=vi.fn();await act(async()=>root.render(<EarthContactsPanel markers={markers} areaGroup onChoose={choose} onZoom={()=>{}} onClose={()=>{}}/>));
  expect(buttons()).toHaveLength(40);expect(host.textContent).toContain("Area group · 220");expect(host.textContent).toContain("not a shared location");
  await type("code218");expect(buttons()).toHaveLength(1);expect(buttons()[0].dataset.contactId).toBe("aircraft-218");await act(async()=>buttons()[0].click());expect(choose).toHaveBeenCalledWith(markers[218]);expect(markers[218].lat).toBe(24.218);
  await type("");await act(async()=>[...host.querySelectorAll("button")].find(b=>b.textContent==="Show 40 more contacts")!.click());expect(buttons()).toHaveLength(80);
 });
 it("keeps vessel identity and observation age visible, and does not relabel retained positions fresh",async()=>{
  await act(async()=>root.render(<EarthContactsPanel markers={markers} areaGroup={false} onChoose={()=>{}} onZoom={()=>{}} onClose={()=>{}}/>));
  const select=host.querySelector("select")!;await act(async()=>{select.value="vessel";select.dispatchEvent(new Event("change",{bubbles:true}));});
  expect(host.textContent).toContain("110 current");for(const button of buttons()){expect(button.dataset.contactId).toMatch(/^vessel-/);expect(button.textContent).toContain("Vessel");expect(button.textContent).toContain("Observed");}
  expect(host.querySelector('[data-contact-id="vessel-1"]')?.textContent).toContain("Last known");
 });
 it("updates membership without inventing a missing position and makes empty selections explicit",async()=>{
  const props={areaGroup:true,onChoose:vi.fn(),onZoom:vi.fn(),onClose:vi.fn()};await act(async()=>root.render(<EarthContactsPanel {...props} markers={markers}/>));await type("code218");
  await act(async()=>root.render(<EarthContactsPanel {...props} markers={[]}/>));expect(buttons()).toHaveLength(1);expect(buttons()[0].disabled).toBe(true);expect(buttons()[0].textContent).toContain("No longer in current selection");expect(buttons()[0].textContent).toContain("Last displayed");expect(host.textContent).toContain("No matching contacts remain");expect([...host.querySelectorAll("button")].find(b=>b.textContent==="Zoom to group")!.disabled).toBe(true);
 });
 it("preserves pointer and keyboard row identity across inserts, removals and renames while choosing current coordinates",async()=>{
  const props={areaGroup:false,onChoose:vi.fn(),onZoom:vi.fn(),onClose:vi.fn()},initial=markers.slice(0,4);
  await act(async()=>root.render(<EarthContactsPanel {...props} markers={initial}/>));
  const target=buttons()[2];target.focus();await act(async()=>target.dispatchEvent(new MouseEvent("mousedown",{bubbles:true})));
  const updated={...initial[2],name:"AAA renamed contact with a much longer label",lat:35.1234,lon:42.3456,positionState:"fresh" as const,details:[["Observed","2026-10-31 01:00:00 UTC"]] as [string,string][]};
  const inserted={...markers[7],name:"000 sorts before every original row"};
  await act(async()=>root.render(<EarthContactsPanel {...props} markers={[inserted,initial[3],updated,initial[1]]}/>));
  expect([...buttons()].map(b=>b.dataset.contactId)).toEqual(initial.map(m=>m.id));expect(host.textContent).toContain("1 new matching contacts");
  expect(buttons()[2]).toBe(target);expect(document.activeElement).toBe(target);expect(buttons()[0].disabled).toBe(true);
  expect(target.textContent).toContain("35.1234");expect(target.textContent).toContain("Fresh observation");expect(target.textContent).toContain("2026-10-31");
  expect(target.style.height).toBe("124px");expect(target.querySelector("strong")!.style.whiteSpace).toBe("nowrap");
  await act(async()=>{target.dispatchEvent(new MouseEvent("mouseup",{bubbles:true}));target.click();});
  expect(props.onChoose).toHaveBeenCalledExactlyOnceWith(updated);
 });
 it("disables the exact departed target instead of choosing its replacement and reuses its slot on return",async()=>{
  const props={areaGroup:true,onChoose:vi.fn(),onZoom:vi.fn(),onClose:vi.fn()},initial=markers.slice(0,3);
  await act(async()=>root.render(<EarthContactsPanel {...props} markers={initial}/>));const target=buttons()[1];target.focus();
  await act(async()=>root.render(<EarthContactsPanel {...props} markers={[initial[0],initial[2],markers[9]]}/>));
  expect(buttons()[1]).toBe(target);expect(target.disabled).toBe(true);expect(target.textContent).toContain("No longer in current selection");expect(target.textContent).toContain("Last displayed");
  await act(async()=>target.click());expect(props.onChoose).not.toHaveBeenCalled();
  const returned={...initial[1],lat:31,lon:41};await act(async()=>root.render(<EarthContactsPanel {...props} markers={[returned,initial[0],initial[2]]}/>));
  expect(buttons()[1]).toBe(target);expect(target.disabled).toBe(false);await act(async()=>target.click());expect(props.onChoose).toHaveBeenCalledExactlyOnceWith(returned);
 });
 it("keeps filtered slots stable on source name changes and rebases only after explicit search or type changes",async()=>{
  const props={areaGroup:false,onChoose:vi.fn(),onZoom:vi.fn(),onClose:vi.fn()};
  await act(async()=>root.render(<EarthContactsPanel {...props} markers={markers}/>));await type("Contact 002");const target=buttons()[0];
  const changed=markers.map(m=>m.id===markers[2].id?{...m,name:"New callsign"}:m);
  await act(async()=>root.render(<EarthContactsPanel {...props} markers={changed}/>));expect(buttons()[0]).toBe(target);expect(target.textContent).toContain("New callsign");
  await type("New callsign");expect(buttons()).toHaveLength(1);expect(buttons()[0].dataset.contactId).toBe(markers[2].id);
  await type("code219");expect(buttons()).toHaveLength(1);expect(buttons()[0].dataset.contactId).toBe(markers[219].id);
  await type("");const select=host.querySelector("select")!;await act(async()=>{select.value="vessel";select.dispatchEvent(new Event("change",{bubbles:true}));});
  for(const button of buttons())expect(button.dataset.contactId).toMatch(/^vessel-/);
 });
 it("does not accumulate incoming IDs across repeated polls and includes them only on explicit refresh",async()=>{
  const props={areaGroup:false,onChoose:vi.fn(),onZoom:vi.fn(),onClose:vi.fn()},initial=markers.slice(0,3);
  await act(async()=>root.render(<EarthContactsPanel {...props} markers={initial}/>));
  const refresh=[...host.querySelectorAll("button")].find(b=>b.textContent==="Refresh contacts")!;
  const originalButtons=[...buttons()];let incoming:EarthMarker[]=[];
  for(let batch=0;batch<20;batch++){
   incoming=Array.from({length:50},(_,i)=>({...markers[i],id:`arrival-${batch}-${i}`,name:`Arrival ${batch} ${i}`}));
   await act(async()=>root.render(<EarthContactsPanel {...props} markers={incoming}/>));
   expect([...buttons()]).toEqual(originalButtons);expect([...buttons()].every(b=>b.disabled)).toBe(true);expect(host.textContent).toContain("50 new matching contacts");
   expect([...host.querySelectorAll("button")].find(b=>b.textContent==="Refresh contacts")).toBe(refresh);
  }
  await act(async()=>refresh.click());expect(buttons()).toHaveLength(40);expect(host.textContent).toContain("0 new matching contacts");
  expect([...buttons()].every(b=>!b.disabled&&b.dataset.contactId!.startsWith("arrival-19-"))).toBe(true);
  await act(async()=>[...host.querySelectorAll("button")].find(b=>b.textContent==="Show 40 more contacts")!.click());expect(buttons()).toHaveLength(50);
  await act(async()=>buttons()[0].click());expect(props.onChoose.mock.calls[0][0]).toBe(incoming.find(m=>m.id===buttons()[0].dataset.contactId));
 });
});
