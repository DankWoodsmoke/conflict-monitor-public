import {act} from "react";
import {createRoot,type Root} from "react-dom/client";
import {afterEach,beforeEach,describe,expect,it,vi} from "vitest";
import {useWorkspacePanelFocus} from "./useWorkspacePanelFocus";
import type {ViewMode} from "../lib/workspace";

let host:HTMLDivElement,root:Root;
function Harness({mode,overlay=true,onClose=()=>{}}:{mode:ViewMode;overlay?:boolean;onClose?:()=>void}){
 const {panelRef,stageRef}=useWorkspacePanelFocus(mode,onClose);
 return <><nav aria-label="Workspace views"><button>Earth</button><button id="media-opener">Media</button></nav><div ref={stageRef} data-stage inert={mode!=="earth"&&overlay}><button>Earth control</button><canvas/></div>{mode!=="earth"&&<aside ref={panelRef}><button data-panel-close>Back to Earth</button><input aria-label="Panel field"/></aside>}</>;
}
beforeEach(()=>{(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;host=document.createElement("div");document.body.append(host);root=createRoot(host);});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();});
describe("persistent workspace keyboard access",()=>{
 it("deactivates a covered Earth stage, hands focus to the panel and preserves the exact canvas",async()=>{
  await act(async()=>root.render(<Harness mode="earth"/>));const canvas=host.querySelector("canvas");
  host.querySelector<HTMLButtonElement>('#media-opener')!.focus();
  await act(async()=>root.render(<Harness mode="media"/>));
  expect(host.querySelector('[data-stage]')?.hasAttribute("inert")).toBe(true);
  expect(document.activeElement).toBe(host.querySelector('[data-panel-close]'));expect(host.querySelector("canvas")).toBe(canvas);
  await act(async()=>root.render(<Harness mode="earth"/>));
  expect(host.querySelector('[data-stage]')?.hasAttribute("inert")).toBe(false);expect(document.activeElement?.id).toBe("media-opener");expect(host.querySelector("canvas")).toBe(canvas);
 });
 it("keeps side-by-side desktop Earth interactive and does not refocus during unrelated refreshes",async()=>{
  await act(async()=>root.render(<Harness mode="media" overlay={false} onClose={()=>{}}/>));
  const field=host.querySelector<HTMLInputElement>("aside input")!;field.focus();
  await act(async()=>root.render(<Harness mode="media" overlay={false} onClose={()=>{}}/>));
  expect(host.querySelector('[data-stage]')?.hasAttribute("inert")).toBe(false);expect(document.activeElement).toBe(field);
 });
 it("reserves Escape for a foreground modal and otherwise invokes the latest panel close callback",async()=>{
  const first=vi.fn(),latest=vi.fn();await act(async()=>root.render(<Harness mode="media" onClose={first}/>));
  await act(async()=>root.render(<Harness mode="media" onClose={latest}/>));
  const dialog=document.createElement("div");dialog.setAttribute("role","dialog");document.body.append(dialog);
  await act(async()=>window.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",cancelable:true})));expect(latest).not.toHaveBeenCalled();dialog.remove();
  await act(async()=>window.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",cancelable:true})));expect(first).not.toHaveBeenCalled();expect(latest).toHaveBeenCalledOnce();
 });
});
