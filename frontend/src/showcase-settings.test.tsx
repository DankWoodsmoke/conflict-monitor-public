import {act} from "react";
import {createRoot,type Root} from "react-dom/client";
import {afterEach,beforeEach,expect,it,vi} from "vitest";
import App from "./App";
import {apiFetch} from "./lib/api";

vi.mock("./lib/runtime",async()=>({...await vi.importActual<typeof import("./lib/runtime")>("./lib/runtime"),SHOWCASE:true}));
vi.mock("./hooks/useEventStream",()=>({useEventStream:()=>({events:[],isConnected:false,loadFullHistory:vi.fn(),historyStatus:"idle",recoveryStatus:"idle",historyTruncated:false,historyStart:null})}));
vi.mock("./hooks/useTracking",()=>({useTracking:()=>({aircraft:[],vessels:[],jammingZones:[],loadingSnapshots:false,snapshotAt:null})}));
vi.mock("./components/CesiumView",()=>({CesiumView:({readOnly,onConfigure,googleKey,googleEnabled}:{readOnly:boolean;onConfigure:()=>void;googleKey:string;googleEnabled:boolean})=><div className="earth-canvas" data-google-key={googleKey} data-google-enabled={googleEnabled}><canvas/>{!readOnly&&<button aria-label="Configure Earth imagery" onClick={onConfigure}>Imagery</button>}</div>}));

let host:HTMLDivElement,root:Root;
beforeEach(()=>{
 (globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;
 window.history.replaceState(null,"","/?showcase=true&view=earth");
 vi.stubEnv("VITE_GOOGLE_MAPS_KEY","");
 vi.stubGlobal("fetch",vi.fn().mockRejectedValue(Error("Unexpected network request")));
 host=document.createElement("div");document.body.append(host);root=createRoot(host);
});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.unstubAllGlobals();vi.unstubAllEnvs();});

it("keeps manual Google imagery reachable in the explicit showcase while backend mutations remain isolated",async()=>{
 await act(async()=>root.render(<App/>));
 const canvas=host.querySelector("canvas");
 const settings=[...host.querySelectorAll<HTMLButtonElement>("button")].find(button=>button.textContent==="Settings")!;
 expect(settings).toBeTruthy();
 await act(async()=>settings.click());
 expect(host.querySelector('[role="dialog"]')?.textContent).toContain("reports remain synthetic");
 expect(host.querySelector('input[placeholder="Optional · your server\'s administrator key"]')).toBeNull();
 await act(async()=>host.querySelector<HTMLButtonElement>('[aria-label="Close settings"]')!.click());
 await act(async()=>host.querySelector<HTMLButtonElement>('[aria-label="Configure Earth imagery"]')!.click());
 const key=host.querySelector<HTMLInputElement>('.settings-key input')!;
 await act(async()=>{
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value")!.set!.call(key,"fixture-browser-restricted-key");
  key.dispatchEvent(new Event("input",{bubbles:true}));
 });
 await act(async()=>host.querySelector<HTMLInputElement>('.settings-checkbox input')!.click());
 await act(async()=>[...host.querySelectorAll<HTMLButtonElement>('.settings-dialog button')].find(button=>button.textContent?.startsWith("Apply settings"))!.click());
 expect(host.querySelector('[role="dialog"]')).toBeNull();
 expect(host.querySelector("canvas")).toBe(canvas);
 expect(host.querySelector(".earth-canvas")?.getAttribute("data-google-key")).toBe("fixture-browser-restricted-key");
 expect(host.querySelector(".earth-canvas")?.getAttribute("data-google-enabled")).toBe("true");
 expect((await apiFetch("/api/briefing/video",{method:"POST"})).status).toBe(405);
 expect(fetch).not.toHaveBeenCalled();
});
