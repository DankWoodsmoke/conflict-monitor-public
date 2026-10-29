import {act,useEffect} from "react";
import {createRoot,type Root} from "react-dom/client";
import {afterEach,beforeEach,describe,expect,it,vi} from "vitest";
import {useEarthProvider,type EarthProviderConfig} from "./useEarthProvider";

const mode=vi.hoisted(()=>({showcase:false}));
vi.mock("../lib/runtime",()=>({get SHOWCASE(){return mode.showcase;}}));
let host:HTMLDivElement,root:Root,latest:ReturnType<typeof useEarthProvider>;
function Harness({config}:{config?:Promise<EarthProviderConfig>}){
  const provider=useEarthProvider();
  useEffect(()=>{latest=provider;},[provider]);
  useEffect(()=>{let active=true;void config?.then(value=>{if(active)provider.applyServerConfig(value);});return()=>{active=false;};},[config,provider.applyServerConfig]);
  return <output>{provider.googleEnabled?"enabled":"disabled"}</output>;
}
beforeEach(()=>{
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;mode.showcase=false;vi.stubEnv("VITE_GOOGLE_MAPS_KEY","");
  window.history.replaceState(null,"","/");host=document.createElement("div");document.body.append(host);root=createRoot(host);
});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.unstubAllEnvs();});
const server={google_earth_enabled:true,google_maps_browser_key:"public-browser-key-fixture"};

describe("production Google provider configuration",()=>{
  it("applies the explicitly enabled public browser key in live mode without browser persistence",async()=>{
    const storage=vi.spyOn(Storage.prototype,"setItem");
    await act(async()=>root.render(<Harness config={Promise.resolve(server)}/>));
    expect(latest.googleKey).toBe(server.google_maps_browser_key);expect(host.textContent).toBe("enabled");expect(storage).not.toHaveBeenCalled();
  });
  it.each([
    {google_earth_enabled:false,google_maps_browser_key:"unused-fixture"},
    {google_earth_enabled:"true",google_maps_browser_key:"unused-fixture"},
    {google_earth_enabled:true,google_maps_browser_key:"  "},
    {google_earth_enabled:true},
  ])("requires an explicit boolean enablement and a nonempty key",async(config)=>{
    await act(async()=>root.render(<Harness config={Promise.resolve(config)}/>));
    expect(latest.googleKey).toBe("");expect(host.textContent).toBe("disabled");
  });
  it("preserves a manual session choice made before the server response arrives",async()=>{
    let resolve!:(config:EarthProviderConfig)=>void;const pending=new Promise<EarthProviderConfig>(release=>{resolve=release;});
    await act(async()=>root.render(<Harness config={pending}/>));
    await act(async()=>latest.applyManual("manual-fixture",false));
    await act(async()=>resolve(server));
    expect(latest.googleKey).toBe("manual-fixture");expect(latest.googleEnabled).toBe(false);
  });
  it("treats explicit provider events as manual session choices and preserves them",async()=>{
    await act(async()=>root.render(<Harness config={Promise.resolve(server)}/>));
    await act(async()=>window.dispatchEvent(new CustomEvent("cm-earth-provider",{detail:{key:"operator-fixture",enabled:false}})));
    await act(async()=>latest.applyServerConfig(server));
    expect(latest.googleKey).toBe("operator-fixture");expect(latest.googleEnabled).toBe(false);
  });
  it("ignores server defaults in showcase but permits an explicit manual provider selection",async()=>{
    mode.showcase=true;await act(async()=>root.render(<Harness config={Promise.resolve(server)}/>));
    expect(latest.googleKey).toBe("");expect(latest.googleEnabled).toBe(false);
    await act(async()=>latest.applyManual("operator-fixture",true));
    expect(latest.googleKey).toBe("operator-fixture");expect(latest.googleEnabled).toBe(true);
  });
});
