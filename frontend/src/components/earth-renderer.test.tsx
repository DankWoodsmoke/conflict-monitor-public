import {act,StrictMode,useState} from 'react';
import {createRoot,type Root} from 'react-dom/client';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import * as Cesium from 'cesium';
import {CesiumView} from './CesiumView';
import {AboutPanel} from './AboutPanel';
import {buildShowcase} from '../lib/showcase';
import {GOOGLE_ROOT_ROTATION_MS,GOOGLE_ROOT_REQUEST_TIMEOUT_MS,GOOGLE_ROOT_HANDOFF_TIMEOUT_MS,GOOGLE_ROOT_RETRY_MS} from '../hooks/useGoogleEarthSession';
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
function tiles(){return {show:true,preloadWhenHidden:false,tilesLoaded:false,maximumScreenSpaceError:8,tileVisible:new Cesium.Event(),loadProgress:new Cesium.Event(),tileFailed:new Cesium.Event(),destroy:vi.fn(),isDestroyed:()=>false};}
async function frame(tile:ReturnType<typeof tiles>,visible=1){await act(async()=>{fixture.viewer.scene.preRender.raiseEvent();for(let i=0;i<visible;i++)tile.tileVisible.raiseEvent();fixture.viewer.scene.postRender.raiseEvent();});}
beforeEach(()=>{(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;fixture.fromUrl.mockReset();fixture.viewer=null;fixture.withCreditDOM=false;fixture.credit=null;vi.stubGlobal('devicePixelRatio',1.25);host=document.createElement('div');document.body.append(host);root=createRoot(host);});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();document.querySelectorAll('[data-credit-test-outside]').forEach(node=>node.remove());vi.useRealTimers();vi.restoreAllMocks();vi.unstubAllGlobals();});
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
 it('shows honest raster fallback after a post-root tile failure and safely hands off an explicit retry',async()=>{
  const first=tiles(),second=tiles();fixture.fromUrl.mockResolvedValueOnce(first).mockResolvedValueOnce(second);await act(async()=>root.render(<CesiumView {...props}/>));first.tilesLoaded=true;await frame(first);
  await act(async()=>first.tileFailed.raiseEvent({message:'fixture failure'}));expect(first.show).toBe(false);expect(fixture.viewer.scene.globe.show).toBe(true);expect(host.textContent).toContain('Google unavailable · Esri satellite reference');expect(fixture.fromUrl).toHaveBeenCalledTimes(1);
  await act(async()=>[...host.querySelectorAll('button')].find(button=>button.textContent==='Retry Google imagery')!.click());expect(fixture.fromUrl).toHaveBeenCalledTimes(2);expect(fixture.viewer.scene.primitives.remove).not.toHaveBeenCalledWith(first);
  second.tilesLoaded=true;await frame(second);await frame(second);expect(fixture.viewer.scene.primitives.remove).toHaveBeenCalledWith(first);expect(fixture.viewer.scene.globe.show).toBe(false);expect(host.querySelector('.earth-workspace')?.getAttribute('data-earth-provider')).toBe('ready');
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

describe('long-session Google access rotation',()=>{
 const state=()=>host.querySelector<HTMLElement>('.earth-workspace')!.dataset;
 const tick=async(ms:number)=>act(async()=>{await vi.advanceTimersByTimeAsync(ms);});
 const frames=async(...values:ReturnType<typeof tiles>[])=>act(async()=>{fixture.viewer.scene.preRender.raiseEvent();for(const tile of values)if(tile.show)tile.tileVisible.raiseEvent();fixture.viewer.scene.postRender.raiseEvent();});
 const refresh=async()=>act(async()=>[...host.querySelectorAll('button')].find(button=>button.textContent==='Refresh Google imagery access')!.click());
 beforeEach(()=>{vi.useFakeTimers();vi.setSystemTime('2026-10-30T00:00:00Z');vi.spyOn(document,'visibilityState','get').mockReturnValue('visible');vi.spyOn(navigator,'onLine','get').mockReturnValue(true);});
 it('rotates at the conservative policy boundary, retains old imagery through a visible-frame handoff, and preserves camera/layers/credits',async()=>{
  fixture.withCreditDOM=true;const first=tiles(),second=tiles();fixture.fromUrl.mockResolvedValueOnce(first).mockResolvedValueOnce(second);
  await act(async()=>root.render(<CesiumView {...props}/>));first.tilesLoaded=true;await frames(first);const viewer=fixture.viewer,credits=fixture.credit,initialCameraCalls=viewer.camera.setView.mock.calls.length,sourceAdds=viewer.dataSources.add.mock.calls.length;
  expect(state().earthSessionGeneration).toBe('1');await tick(GOOGLE_ROOT_ROTATION_MS-1);expect(fixture.fromUrl).toHaveBeenCalledOnce();
  await tick(1);expect(fixture.fromUrl).toHaveBeenCalledTimes(2);expect(second.show).toBe(false);expect(second.preloadWhenHidden).toBe(true);expect(state().earthSession).toBe('refreshing');expect(first.destroy).not.toHaveBeenCalled();
  // Pending candidate frames cannot clear the old current-view readiness.
  await frames(first,second);expect(state().earthProvider).toBe('ready');expect(viewer.scene.globe.show).toBe(false);expect(first.destroy).not.toHaveBeenCalled();
  second.tilesLoaded=true;await frames(first,second);expect(second.show).toBe(true);expect(first.destroy).not.toHaveBeenCalled();
  await frames(first,second);expect(first.destroy).toHaveBeenCalledOnce();expect(state().earthSessionGeneration).toBe('2');expect(state().earthSession).toBe('current');expect(state().earthProvider).toBe('ready');
  expect(viewer.camera.setView).toHaveBeenCalledTimes(initialCameraCalls);expect(viewer.camera.flyToBoundingSphere).not.toHaveBeenCalled();expect(viewer.dataSources.add).toHaveBeenCalledTimes(sourceAdds);expect(fixture.credit).toBe(credits);expect(fixture.viewer).toBe(viewer);
  expect(first.tileVisible.numberOfListeners).toBe(0);expect(first.tileFailed.numberOfListeners).toBe(0);expect(second.tileVisible.numberOfListeners).toBe(1);
 });
 it('serializes duplicate wake/manual events, retains usable imagery after candidate failure, and stops after bounded retries',async()=>{
  const first=tiles();fixture.fromUrl.mockResolvedValueOnce(first).mockRejectedValue(new Error('controlled root failure'));
  await act(async()=>root.render(<CesiumView {...props}/>));first.tilesLoaded=true;await frames(first);await refresh();
  expect(fixture.fromUrl).toHaveBeenCalledTimes(2);expect(state().earthSession).toBe('retry_wait');expect(state().earthProvider).toBe('ready');expect(first.show).toBe(true);expect(first.destroy).not.toHaveBeenCalled();
  await act(async()=>{window.dispatchEvent(new Event('focus'));window.dispatchEvent(new Event('online'));document.dispatchEvent(new Event('visibilitychange'));});expect(fixture.fromUrl).toHaveBeenCalledTimes(2);
  for(const delay of GOOGLE_ROOT_RETRY_MS)await tick(delay);
  expect(fixture.fromUrl).toHaveBeenCalledTimes(5);expect(state().earthSession).toBe('error');expect(state().earthSessionRetries).toBe('4');await tick(3_600_000);expect(fixture.fromUrl).toHaveBeenCalledTimes(5);expect(first.destroy).not.toHaveBeenCalled();
 });
 it('pauses root rotation in hidden/offline tabs and checks elapsed wall time on resume without duplicate requests',async()=>{
  const first=tiles(),second=tiles();fixture.fromUrl.mockResolvedValueOnce(first).mockResolvedValueOnce(second);let visibility:DocumentVisibilityState='visible',online=true;vi.spyOn(document,'visibilityState','get').mockImplementation(()=>visibility);vi.spyOn(navigator,'onLine','get').mockImplementation(()=>online);
  await act(async()=>root.render(<CesiumView {...props}/>));first.tilesLoaded=true;await frames(first);
  visibility='hidden';await act(async()=>document.dispatchEvent(new Event('visibilitychange')));await tick(GOOGLE_ROOT_ROTATION_MS+60_000);expect(fixture.fromUrl).toHaveBeenCalledOnce();expect(state().earthSession).toBe('paused');
  visibility='visible';online=false;await act(async()=>document.dispatchEvent(new Event('visibilitychange')));expect(fixture.fromUrl).toHaveBeenCalledOnce();
  online=true;await act(async()=>{window.dispatchEvent(new Event('online'));window.dispatchEvent(new Event('focus'));window.dispatchEvent(new Event('pageshow'));});expect(fixture.fromUrl).toHaveBeenCalledTimes(2);
  second.tilesLoaded=true;await frames(first,second);await frames(first,second);expect(state().earthSessionGeneration).toBe('2');expect(first.destroy).toHaveBeenCalledOnce();
 });
 it('keeps a hanging root serialized after timeout and destroys a late result before scheduling retry',async()=>{
  const first=tiles(),late=tiles();let finish!:(value:any)=>void;fixture.fromUrl.mockResolvedValueOnce(first).mockReturnValueOnce(new Promise(resolve=>finish=resolve));
  await act(async()=>root.render(<CesiumView {...props}/>));first.tilesLoaded=true;await frames(first);await refresh();await tick(GOOGLE_ROOT_REQUEST_TIMEOUT_MS);
  expect(state().earthSession).toBe('waiting');expect(state().earthProvider).toBe('ready');await tick(600_000);await refresh();expect(fixture.fromUrl).toHaveBeenCalledTimes(2);
  await act(async()=>finish(late));expect(late.destroy).toHaveBeenCalledOnce();expect(fixture.viewer.scene.primitives.add).not.toHaveBeenCalledWith(late);expect(state().earthSession).toBe('retry_wait');expect(first.destroy).not.toHaveBeenCalled();
 });
 it('rejects an empty/unready replacement after its bounded handoff window without discarding useful old tiles',async()=>{
  const first=tiles(),second=tiles();fixture.fromUrl.mockResolvedValueOnce(first).mockResolvedValueOnce(second);
  await act(async()=>root.render(<CesiumView {...props}/>));first.tilesLoaded=true;await frames(first);await refresh();second.tilesLoaded=true;
  await frames(first);await frames(first);expect(state().earthSessionGeneration).toBe('1');await tick(GOOGLE_ROOT_HANDOFF_TIMEOUT_MS);
  expect(second.destroy).toHaveBeenCalledOnce();expect(first.destroy).not.toHaveBeenCalled();expect(state().earthProvider).toBe('ready');expect(state().earthSession).toBe('retry_wait');
 });
 it('cleans candidate listeners/timers on disable and rejects late root results after unmount',async()=>{
  const first=tiles(),second=tiles(),late=tiles();let finish!:(value:any)=>void;fixture.fromUrl.mockResolvedValueOnce(first).mockResolvedValueOnce(second).mockReturnValueOnce(new Promise(resolve=>finish=resolve));
  await act(async()=>root.render(<CesiumView {...props}/>));first.tilesLoaded=true;await frames(first);await refresh();const viewer=fixture.viewer;
  await act(async()=>root.render(<CesiumView {...props} googleEnabled={false}/>));expect(first.destroy).toHaveBeenCalledOnce();expect(second.destroy).toHaveBeenCalledOnce();expect(first.tileVisible.numberOfListeners).toBe(0);expect(second.tileVisible.numberOfListeners).toBe(0);expect(state().earthSession).toBe('disabled');
  await tick(GOOGLE_ROOT_ROTATION_MS);expect(fixture.fromUrl).toHaveBeenCalledTimes(2);
  await act(async()=>root.render(<CesiumView {...props}/>));await act(async()=>root.render(<div/>));await act(async()=>finish(late));expect(late.destroy).toHaveBeenCalledOnce();expect(viewer.scene.primitives.add).not.toHaveBeenCalledWith(late);
 });
 it('applies detail changes to both roots during handoff without refetching and retains the latest detail on a pending root',async()=>{
  const first=tiles(),second=tiles();let finish!:(value:any)=>void;fixture.fromUrl.mockResolvedValueOnce(first).mockReturnValueOnce(new Promise(resolve=>finish=resolve));
  await act(async()=>root.render(<CesiumView {...props}/>));await refresh();const select=host.querySelector<HTMLSelectElement>('[aria-label="Imagery render detail"]')!;
  await act(async()=>{select.value='detail';select.dispatchEvent(new Event('change',{bubbles:true}));});await act(async()=>finish(second));expect(first.maximumScreenSpaceError).toBe(4);expect(second.maximumScreenSpaceError).toBe(4);expect(fixture.fromUrl).toHaveBeenCalledTimes(2);
 });
 it('retains a good active root when replacement tile content fails and falls back honestly if active content then fails',async()=>{
  const first=tiles(),second=tiles();fixture.fromUrl.mockResolvedValueOnce(first).mockResolvedValueOnce(second);
  await act(async()=>root.render(<CesiumView {...props}/>));first.tilesLoaded=true;await frames(first);await refresh();
  await act(async()=>second.tileFailed.raiseEvent({url:'not-saved',message:'controlled candidate failure'}));expect(second.destroy).toHaveBeenCalledOnce();expect(first.show).toBe(true);expect(first.destroy).not.toHaveBeenCalled();expect(state().earthProvider).toBe('ready');expect(state().earthSession).toBe('retry_wait');
  await act(async()=>first.tileFailed.raiseEvent({message:'controlled active failure'}));expect(first.show).toBe(false);expect(fixture.viewer.scene.globe.show).toBe(true);expect(state().earthProvider).toBe('error');expect(fixture.fromUrl).toHaveBeenCalledTimes(2);
 });
 it('checks a wall-clock sleep gap on focus without treating three hours as an exact provider expiry',async()=>{
  const first=tiles(),second=tiles();fixture.fromUrl.mockResolvedValueOnce(first).mockResolvedValueOnce(second);
  await act(async()=>root.render(<CesiumView {...props}/>));first.tilesLoaded=true;await frames(first);
  vi.setSystemTime(Date.now()+4*3_600_000);await act(async()=>window.dispatchEvent(new Event('focus')));expect(fixture.fromUrl).toHaveBeenCalledTimes(2);expect(first.show).toBe(true);expect(first.destroy).not.toHaveBeenCalled();expect(state().earthProvider).toBe('ready');
 });
 it('ignores a prior-key promise after configuration changes and keeps the reference selected during the new request',async()=>{
  const obsolete=tiles(),current=tiles();let finish!:(value:any)=>void;fixture.fromUrl.mockReturnValueOnce(new Promise(resolve=>finish=resolve)).mockResolvedValueOnce(current);
  await act(async()=>root.render(<CesiumView {...props}/>));await act(async()=>root.render(<CesiumView {...props} googleKey='replacement-public-browser-fixture'/>));
  expect(fixture.viewer.scene.globe.show).toBe(true);await act(async()=>finish(obsolete));expect(obsolete.destroy).toHaveBeenCalledOnce();expect(fixture.viewer.scene.primitives.add).not.toHaveBeenCalledWith(obsolete);
  current.tilesLoaded=true;await frames(current);expect(state().earthProvider).toBe('ready');expect(state().earthSessionGeneration).toBe('1');expect(fixture.fromUrl).toHaveBeenCalledTimes(2);
 });
 it('destroys a retired development StrictMode root without adding it to the replacement viewer',async()=>{
  const retired=tiles(),current=tiles();let finish!:(value:any)=>void;fixture.fromUrl.mockReturnValueOnce(new Promise(resolve=>finish=resolve)).mockResolvedValueOnce(current);
  await act(async()=>root.render(<StrictMode><CesiumView {...props}/></StrictMode>));const viewer=fixture.viewer;
  expect(fixture.fromUrl).toHaveBeenCalledTimes(2);await act(async()=>finish(retired));expect(retired.destroy).toHaveBeenCalledOnce();expect(viewer.scene.primitives.add).not.toHaveBeenCalledWith(retired);
  current.tilesLoaded=true;await frames(current);expect(state().earthProvider).toBe('ready');expect(state().earthSessionGeneration).toBe('1');expect(fixture.viewer).toBe(viewer);
 });
});

describe('renderer keyboard ownership and stable focus',()=>{
 beforeEach(()=>{fixture.fromUrl.mockResolvedValue(tiles());vi.spyOn(HTMLElement.prototype,'getClientRects').mockReturnValue([{width:100,height:30}] as any);});
 const button=(label:string)=>host.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`)!;
 const layers=()=>host.querySelector<HTMLButtonElement>('button[aria-controls="earth-layers"]')!;
 const pressEscape=()=>act(async()=>document.activeElement?.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true})));
 const enterQuery=async(value:string)=>act(async()=>{const input=host.querySelector<HTMLInputElement>('#earth-search')!;input.focus();Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(input,value);input.dispatchEvent(new Event('input',{bubbles:true}));});
 const chooseFirst=async()=>act(async()=>{const result=host.querySelector<HTMLButtonElement>('.earth-search-results button')!;result.focus();result.click();});
 const sample=()=>({icao24:'abc123',callsign:'FOCUS123',origin_country:'',lat:0,lon:0,altitude:null,velocity:null,heading:null,on_ground:false,position_source:0,observed_at:new Date().toISOString()});
 it('enters nonmodal Layers and returns to its opener after both close and Escape',async()=>{
  await act(async()=>root.render(<CesiumView {...props}/>));const opener=layers();opener.focus();await act(async()=>opener.click());expect(document.activeElement).toBe(button('Close spatial layers'));
  await act(async()=>button('Close spatial layers').click());expect(document.activeElement).toBe(opener);expect(host.querySelector('#earth-layers')).toBeNull();
  await act(async()=>opener.click());host.querySelector<HTMLInputElement>('#earth-layers input')!.focus();await pressEscape();expect(host.querySelector('#earth-layers')).toBeNull();expect(document.activeElement).toBe(opener);expect(fixture.fromUrl).toHaveBeenCalledOnce();
 });
 it('returns to visible Controls if the original Layers opener has been collapsed',async()=>{
  await act(async()=>root.render(<CesiumView {...props}/>));await act(async()=>layers().click());const toggle=host.querySelector<HTMLButtonElement>('.earth-navigation-toggle')!;toggle.focus();await act(async()=>toggle.click());
  button('Close spatial layers').focus();await pressEscape();expect(document.activeElement).toBe(toggle);expect(toggle.getAttribute('aria-expanded')).toBe('false');
 });
 it('lets the real Methods dialog own Escape without dismissing underlying Layers',async()=>{
  function Surface(){const [open,setOpen]=useState(false);return <><button onClick={()=>setOpen(true)}>Methods fixture opener</button><CesiumView {...props}/>{open&&<AboutPanel onClose={()=>setOpen(false)}/>}</>;}
  await act(async()=>root.render(<Surface/>));await act(async()=>layers().click());const opener=[...host.querySelectorAll('button')].find(node=>node.textContent==='Methods fixture opener')!;opener.focus();await act(async()=>opener.click());expect(host.querySelector('.methods-dialog')).not.toBeNull();await pressEscape();
  expect(host.querySelector('.methods-dialog')).toBeNull();expect(host.querySelector('#earth-layers')).not.toBeNull();expect(document.activeElement).toBe(opener);
 });
 it('does not claim Escape from other workspace controls or from an already-handled event',async()=>{
  await act(async()=>root.render(<><button data-external-control>Other workspace action</button><CesiumView {...props}/></>));await act(async()=>layers().click());const outside=host.querySelector<HTMLButtonElement>('[data-external-control]')!;outside.focus();await pressEscape();expect(host.querySelector('#earth-layers')).not.toBeNull();
  button('Close spatial layers').focus();const event=new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true});event.preventDefault();await act(async()=>document.activeElement?.dispatchEvent(event));expect(host.querySelector('#earth-layers')).not.toBeNull();
 });
 it('clears coordinate/reference search results without abandoning keyboard focus',async()=>{
  await act(async()=>root.render(<CesiumView {...props}/>));for(const query of ['0,0','Dubai']){await enterQuery(query);await chooseFirst();expect(host.querySelector('.earth-search-results')).toBeNull();expect(document.activeElement).toBe(host.querySelector('#earth-search'));}
 });
 it('hands marker search to selected details, supports repeated same-ID selection, and restores search on close',async()=>{
  await act(async()=>root.render(<CesiumView {...props} aircraft={[sample()]}/>));const viewer=fixture.viewer;
  for(let i=0;i<2;i++){await enterQuery('FOCUS123');await chooseFirst();expect(document.activeElement).toBe(host.querySelector('.earth-selection'));}
  button('Close selected position').focus();await pressEscape();expect(host.querySelector('.earth-selection')).toBeNull();expect(document.activeElement).toBe(host.querySelector('#earth-search'));expect(fixture.viewer).toBe(viewer);expect(fixture.fromUrl).toHaveBeenCalledOnce();
 });
 it('returns focus safely when a selected live track expires without stealing another control focus',async()=>{
  await act(async()=>root.render(<CesiumView {...props} aircraft={[sample()]}/>));await enterQuery('FOCUS123');await chooseFirst();
  await act(async()=>root.render(<CesiumView {...props} aircraft={[]}/>));expect(document.activeElement).toBe(host.querySelector('#earth-search'));
  await act(async()=>root.render(<CesiumView {...props} aircraft={[sample()]}/>));await enterQuery('FOCUS123');await chooseFirst();const imagery=button('Configure Earth imagery');imagery.focus();await act(async()=>root.render(<CesiumView {...props} aircraft={[]}/>));expect(document.activeElement).toBe(imagery);
 });
 it('gives canvas-picked selections a named focus target and returns to Earth on close',async()=>{
  await act(async()=>root.render(<CesiumView {...props} aircraft={[sample()]}/>));const viewer=fixture.viewer,source=viewer.dataSources.add.mock.calls[0][0],entity=source.entities.getById('aircraft-abc123');viewer.scene.pick=()=>({id:entity});const pick=viewer.screenSpaceEventHandler.setInputAction.mock.calls[0][0];
  await act(async()=>pick({position:new Cesium.Cartesian2()}));expect(document.activeElement).toBe(host.querySelector('.earth-selection'));button('Close selected position').focus();await act(async()=>button('Close selected position').click());expect(document.activeElement).toBe(host.querySelector('.earth-canvas'));
 });
 it('keeps separate Layers and selection Escape actions from cascading through both surfaces',async()=>{
  await act(async()=>root.render(<CesiumView {...props} aircraft={[sample()]}/>));await act(async()=>layers().click());await enterQuery('FOCUS123');await chooseFirst();await pressEscape();expect(host.querySelector('.earth-selection')).toBeNull();expect(host.querySelector('#earth-layers')).not.toBeNull();
  await pressEscape();expect(host.querySelector('#earth-layers')).toBeNull();expect(document.activeElement).toBe(layers());
 });
 it('moves keyboard focus off a retry control before it disables or disappears',async()=>{
  await act(async()=>root.render(<CesiumView {...props}/>));const manual=[...host.querySelectorAll<HTMLButtonElement>('button')].find(node=>node.textContent==='Refresh Google imagery access')!;manual.focus();await act(async()=>manual.click());expect(document.activeElement).toBe(button('Configure Earth imagery'));
  await act(async()=>root.render(<CesiumView {...props} googleEnabled={false}/>));const provider=fixture.viewer.imageryLayers.addImageryProvider.mock.calls[0][0];await act(async()=>provider.errorEvent.raiseEvent({message:'controlled failure'}));const retry=[...host.querySelectorAll<HTMLButtonElement>('button')].find(node=>node.textContent==='Retry reference imagery')!;retry.focus();await act(async()=>retry.click());expect(document.activeElement).toBe(button('Configure Earth imagery'));
 });
 it('hands external report-location actions to details and returns to their stable report origin',async()=>{
  const report=buildShowcase(Date.now()).events[0];const view=(id:number|null)=><><button data-report-origin>Locate report fixture</button><CesiumView {...props} events={[report]} focusEventId={id}/></>;
  await act(async()=>root.render(view(null)));const opener=host.querySelector<HTMLButtonElement>('[data-report-origin]')!;opener.focus();await act(async()=>root.render(view(report.id)));expect(document.activeElement).toBe(host.querySelector('.earth-selection'));
  await act(async()=>button('Close selected position').click());expect(document.activeElement).toBe(opener);
 });
 it('does not steal a foreground dialog focus when an external report action arrives',async()=>{
  const report=buildShowcase(Date.now()).events[0];const view=(id:number|null)=><><CesiumView {...props} events={[report]} focusEventId={id}/><div role="dialog" aria-modal="true" aria-label="Foreground fixture"><input data-dialog-input/></div></>;
  await act(async()=>root.render(view(null)));const input=host.querySelector<HTMLInputElement>('[data-dialog-input]')!;input.focus();await act(async()=>root.render(view(report.id)));expect(host.querySelector('.earth-selection')).not.toBeNull();expect(document.activeElement).toBe(input);
 });
});
