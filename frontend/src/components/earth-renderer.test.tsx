import {act} from 'react';
import {createRoot,type Root} from 'react-dom/client';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import * as Cesium from 'cesium';
import {CesiumView} from './CesiumView';
const fixture=vi.hoisted(()=>({viewer:null as any,options:null as any,fromUrl:vi.fn(),withCreditDOM:false,credit:null as any}));
vi.mock('cesium',async importOriginal=>{
 const real=await importOriginal<typeof import('cesium')>();
 return {...real,Cesium3DTileset:{fromUrl:fixture.fromUrl},Viewer:class {
  scene:any;camera:any;canvas:any;dataSources={add:vi.fn()};screenSpaceEventHandler={setInputAction:vi.fn()};imageryLayers={addImageryProvider:vi.fn(()=>({fixtureLayer:true})),remove:vi.fn()};resolutionScale=0;destroyed=false;resize=vi.fn();flyTo=vi.fn();nativeNodes:HTMLElement[]=[];
  constructor(_container:HTMLElement,options:unknown){fixture.viewer=this;fixture.options=options;
   this.canvas={clientWidth:1118,clientHeight:757};this.scene={globe:{show:true},renderError:new real.Event(),preRender:new real.Event(),postRender:new real.Event(),requestRender:vi.fn(),primitives:{add:vi.fn(),remove:vi.fn()},pickPositionSupported:false};
   this.camera={pitch:-Math.PI/2,heading:0,positionWC:real.Cartesian3.fromDegrees(44,29,2000000),positionCartographic:{height:2000000},setView:vi.fn(),flyToBoundingSphere:vi.fn(),pickEllipsoid:vi.fn(()=>real.Cartesian3.fromDegrees(44,29,0))};
   if(fixture.withCreditDOM){
    const overlay=document.createElement('div'),dialog=document.createElement('div'),close=document.createElement('a'),source=document.createElement('a'),expand=document.createElement('a');
    overlay.className='cesium-credit-lightbox-overlay';overlay.style.display='none';dialog.className='cesium-credit-lightbox';close.className='cesium-credit-lightbox-close';close.textContent='×';source.href='https://provider.example/attribution';source.textContent='Provider attribution';expand.className='cesium-credit-expand-link';expand.textContent='Data attribution';
    dialog.append(close,source);overlay.append(dialog);_container.append(overlay);(options as any).creditContainer.append(expand);this.nativeNodes.push(overlay,expand);
    const credit={overlay,dialog,close,source,expand,opens:0};expand.onclick=()=>{credit.opens++;overlay.style.display='block';};close.onclick=()=>{overlay.style.display='none';};fixture.credit=credit;
   }
  }
  isDestroyed(){return this.destroyed;}destroy(){this.destroyed=true;this.nativeNodes.forEach(node=>node.remove());}
 }};
});
let host:HTMLDivElement,root:Root;
const props={focusEventId:null,googleKey:'public-browser-fixture',googleEnabled:true,onConfigure:()=>{},events:[],aircraft:[],vessels:[],jammingZones:[]};
function tiles(){return {show:true,tilesLoaded:false,maximumScreenSpaceError:8,tileVisible:new Cesium.Event(),loadProgress:new Cesium.Event(),tileFailed:new Cesium.Event(),destroy:vi.fn(),isDestroyed:()=>false};}
async function frame(tile:ReturnType<typeof tiles>,visible=1){await act(async()=>{fixture.viewer.scene.preRender.raiseEvent();for(let i=0;i<visible;i++)tile.tileVisible.raiseEvent();fixture.viewer.scene.postRender.raiseEvent();});}
beforeEach(()=>{(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;fixture.fromUrl.mockReset();fixture.viewer=null;fixture.withCreditDOM=false;fixture.credit=null;vi.stubGlobal('devicePixelRatio',1.25);host=document.createElement('div');document.body.append(host);root=createRoot(host);});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();document.querySelectorAll('[data-credit-test-outside]').forEach(node=>node.remove());vi.restoreAllMocks();vi.unstubAllGlobals();});
describe('Earth imagery rendering lifecycle',()=>{
 it('integrates native attribution with keyboard activation, modal focus/inert ownership, trapping and Escape return without rewriting credits',async()=>{
  fixture.withCreditDOM=true;fixture.fromUrl.mockResolvedValue(tiles());vi.spyOn(HTMLElement.prototype,'getClientRects').mockReturnValue([{width:100,height:30}] as any);await act(async()=>root.render(<CesiumView {...props}/>));const viewer=fixture.viewer,{overlay,dialog,close,source,expand}=fixture.credit;
  expect(dialog.hasAttribute('role')).toBe(false);expect(expand.getAttribute('role')).toBe('button');expect(expand.tabIndex).toBe(0);expect(expand.getAttribute('aria-haspopup')).toBe('dialog');expand.focus();
  const press=async(node:HTMLElement,key:string,shiftKey=false)=>act(async()=>node.dispatchEvent(new KeyboardEvent('keydown',{key,shiftKey,bubbles:true,cancelable:true})));
  await press(expand,'Enter');expect(overlay.style.display).toBe('block');expect(dialog.getAttribute('role')).toBe('dialog');expect(dialog.getAttribute('aria-modal')).toBe('true');expect(dialog.getAttribute('aria-label')).toBe('Imagery data attribution');expect(document.activeElement).toBe(close);expect(host.querySelector('.earth-controls')?.hasAttribute('inert')).toBe(true);
  source.focus();await press(source,'Tab');expect(document.activeElement).toBe(close);await press(close,'Tab',true);expect(document.activeElement).toBe(source);
  await press(source,'Escape');expect(overlay.style.display).toBe('none');expect(dialog.hasAttribute('role')).toBe(false);expect(document.activeElement).toBe(expand);expect(host.querySelector('.earth-controls')?.hasAttribute('inert')).toBe(false);
  await press(expand,' ');expect(document.activeElement).toBe(close);await press(close,'Enter');expect(overlay.style.display).toBe('none');expect(document.activeElement).toBe(expand);
  await press(expand,'Enter');await press(close,' ');expect(overlay.style.display).toBe('none');await act(async()=>expand.click());await act(async()=>close.click());expect(document.activeElement).toBe(expand);
  expect(source.href).toBe('https://provider.example/attribution');expect(source.textContent).toBe('Provider attribution');expect(fixture.viewer).toBe(viewer);
 });
 it('disconnects native attribution observation and keyboard listeners before destroying its viewer, releasing outside inert state',async()=>{
  fixture.withCreditDOM=true;fixture.fromUrl.mockResolvedValue(tiles());vi.spyOn(HTMLElement.prototype,'getClientRects').mockReturnValue([{width:100,height:30}] as any);const outside=document.createElement('button');outside.setAttribute('data-credit-test-outside','');document.body.append(outside);
  await act(async()=>root.render(<CesiumView {...props}/>));const viewer=fixture.viewer,credit=fixture.credit;credit.expand.focus();await act(async()=>credit.expand.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true})));expect(outside.hasAttribute('inert')).toBe(true);
  await act(async()=>root.render(<div>Replacement workspace</div>));expect(viewer.destroyed).toBe(true);expect(outside.hasAttribute('inert')).toBe(false);const opens=credit.opens;
  await act(async()=>{credit.overlay.style.display='none';credit.expand.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));});expect(credit.opens).toBe(opens);
  const escape=new KeyboardEvent('keydown',{key:'Escape',cancelable:true});window.dispatchEvent(escape);expect(escape.defaultPrevented).toBe(false);expect(host.querySelector('[role="dialog"]')).toBeNull();
 });
 it('reports failed reference tiles honestly and retries only that owned layer without recreating Google or the canvas',async()=>{
  fixture.fromUrl.mockResolvedValue(tiles());await act(async()=>root.render(<CesiumView {...props} googleEnabled={false}/>));const viewer=fixture.viewer,provider=viewer.imageryLayers.addImageryProvider.mock.calls[0][0];
  await act(async()=>provider.errorEvent.raiseEvent({message:'controlled reference failure'}));expect(host.querySelector('.earth-workspace')?.getAttribute('data-earth-reference')).toBe('error');expect(host.textContent).toContain('Reference imagery incomplete');
  await act(async()=>[...host.querySelectorAll('button')].find(button=>button.textContent==='Retry reference imagery')!.click());expect(viewer.imageryLayers.remove).toHaveBeenCalledTimes(1);expect(viewer.imageryLayers.addImageryProvider).toHaveBeenCalledTimes(2);expect(fixture.fromUrl).not.toHaveBeenCalled();expect(fixture.viewer).toBe(viewer);
 });
 it('keeps small-screen navigation collapsed until requested without replacing the renderer or provider',async()=>{
  vi.stubGlobal('innerWidth',390);vi.stubGlobal('innerHeight',844);fixture.fromUrl.mockResolvedValue(tiles());await act(async()=>root.render(<CesiumView {...props}/>));const viewer=fixture.viewer;
  const toggle=host.querySelector<HTMLButtonElement>('[aria-label="Controls — show Earth navigation"]')!;expect(toggle.getAttribute('aria-expanded')).toBe('false');expect(host.querySelector<HTMLElement>('#earth-navigation-body')!.hidden).toBe(true);
  const namedCaptions=()=>{for(const button of host.querySelectorAll<HTMLButtonElement>('button[aria-label]')){const caption=button.textContent!.trim().replace(/\s+/g,' ').toLowerCase();if(/[a-z]{2}/.test(caption))expect(button.getAttribute('aria-label')!.toLowerCase()).toContain(caption);}};
  namedCaptions();await act(async()=>toggle.click());namedCaptions();expect(toggle.getAttribute('aria-label')).toBe('Hide controls — Earth navigation');expect(host.querySelector<HTMLElement>('#earth-navigation-body')!.hidden).toBe(false);expect(fixture.viewer).toBe(viewer);expect(fixture.fromUrl).toHaveBeenCalledTimes(1);
 });
 it('preserves the reference globe until a nonempty current view is refined, including later camera views',async()=>{
  const tile=tiles();fixture.fromUrl.mockResolvedValue(tile);await act(async()=>root.render(<CesiumView {...props}/>));
  expect(fixture.options.useBrowserRecommendedResolution).toBe(false);expect(fixture.viewer.resolutionScale).toBe(1);
  expect(fixture.viewer.scene.globe.show).toBe(true);tile.tilesLoaded=true;await frame(tile,0);
  expect(host.querySelector('.earth-workspace')?.getAttribute('data-earth-provider')).toBe('reference');expect(fixture.viewer.scene.globe.show).toBe(true);
  await frame(tile);expect(host.querySelector('.earth-workspace')?.getAttribute('data-earth-provider')).toBe('ready');expect(fixture.viewer.scene.globe.show).toBe(false);
  tile.tilesLoaded=false;await frame(tile);expect(host.querySelector('.earth-workspace')?.getAttribute('data-earth-provider')).toBe('loading');expect(fixture.viewer.scene.globe.show).toBe(true);
  tile.tilesLoaded=true;await frame(tile);expect(host.querySelector('.earth-workspace')?.getAttribute('data-earth-provider')).toBe('ready');
 });
 it('shows honest raster fallback after a post-root tile failure and rebuilds a root only on explicit retry',async()=>{
  const first=tiles(),second=tiles();fixture.fromUrl.mockResolvedValueOnce(first).mockResolvedValueOnce(second);await act(async()=>root.render(<CesiumView {...props}/>));first.tilesLoaded=true;await frame(first);
  await act(async()=>first.tileFailed.raiseEvent({message:'fixture failure'}));expect(first.show).toBe(false);expect(fixture.viewer.scene.globe.show).toBe(true);expect(host.textContent).toContain('Google unavailable · Esri satellite reference');expect(fixture.fromUrl).toHaveBeenCalledTimes(1);
  await act(async()=>[...host.querySelectorAll('button')].find(button=>button.textContent==='Retry Google imagery')!.click());expect(fixture.fromUrl).toHaveBeenCalledTimes(2);expect(fixture.viewer.scene.primitives.remove).toHaveBeenCalledWith(first);
  second.tilesLoaded=true;await frame(second);expect(fixture.viewer.scene.globe.show).toBe(false);expect(host.querySelector('.earth-workspace')?.getAttribute('data-earth-provider')).toBe('ready');
 });
 it('changes mesh detail on the same provider without a second billable root request',async()=>{
  const tile=tiles();fixture.fromUrl.mockResolvedValue(tile);await act(async()=>root.render(<CesiumView {...props}/>));
  const select=host.querySelector<HTMLSelectElement>('[aria-label="Imagery render detail"]')!;await act(async()=>{select.value='detail';select.dispatchEvent(new Event('change',{bubbles:true}));});
  expect(tile.maximumScreenSpaceError).toBe(4);expect(fixture.fromUrl).toHaveBeenCalledTimes(1);
 });
 it('applies a detail choice made while the Google root is still loading when that root resolves',async()=>{
  let finish!:(value:any)=>void;fixture.fromUrl.mockReturnValue(new Promise(resolve=>{finish=resolve;}));await act(async()=>root.render(<CesiumView {...props}/>));
  const select=host.querySelector<HTMLSelectElement>('[aria-label="Imagery render detail"]')!;await act(async()=>{select.value='detail';select.dispatchEvent(new Event('change',{bubbles:true}));});
  const tile=tiles();await act(async()=>finish(tile));expect(tile.maximumScreenSpaceError).toBe(4);expect(fixture.fromUrl).toHaveBeenCalledTimes(1);
 });
 it('offers actual close city inspection and center-preserving top-down navigation without altering source positions',async()=>{
  fixture.fromUrl.mockResolvedValue(tiles());await act(async()=>root.render(<CesiumView {...props}/>));
  await act(async()=>[...host.querySelectorAll('button')].find(button=>button.textContent==='Dubai')!.click());let args=fixture.viewer.camera.flyToBoundingSphere.mock.calls.at(-1);expect(args[1].offset.range).toBe(6500);expect(args[1].offset.pitch).toBeCloseTo(-Math.PI/4);
  await act(async()=>[...host.querySelectorAll('button')].find(button=>button.textContent==='Top down')!.click());args=fixture.viewer.camera.flyToBoundingSphere.mock.calls.at(-1);expect(args[1].offset.pitch).toBeCloseTo(-Math.PI/2);expect(fixture.viewer.camera.pickEllipsoid).toHaveBeenCalled();
 });
 it('keeps a pending provider resolution from touching a destroyed viewer',async()=>{
  let finish!:(value:any)=>void;fixture.fromUrl.mockReturnValue(new Promise(resolve=>{finish=resolve;}));await act(async()=>root.render(<CesiumView {...props}/>));const viewer=fixture.viewer,tile=tiles();
  await act(async()=>root.render(<div/>));await act(async()=>finish(tile));expect(viewer.destroyed).toBe(true);expect(tile.destroy).toHaveBeenCalledOnce();expect(viewer.scene.primitives.add).not.toHaveBeenCalled();
 });
});
