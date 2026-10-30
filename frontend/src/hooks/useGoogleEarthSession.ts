import {useEffect,useRef,useState,type RefObject} from "react";
import * as Cesium from "cesium";
import {EARTH_DETAIL_ERROR,type EarthDetail} from "../lib/earth";

// Google documents at least three hours per root, not an exact expiry. This
// earlier rotation is application policy, measured from the root request.
export const GOOGLE_ROOT_ROTATION_MS=150*60_000;
export const GOOGLE_ROOT_REQUEST_TIMEOUT_MS=60_000;
export const GOOGLE_ROOT_HANDOFF_TIMEOUT_MS=120_000;
export const GOOGLE_ROOT_RETRY_MS=[30_000,120_000,600_000] as const;
export type EarthProviderState="offline"|"unconfigured"|"loading"|"ready"|"reference"|"error";
export type EarthSessionPhase="disabled"|"current"|"refreshing"|"retry_wait"|"paused"|"waiting"|"error";
type Session={phase:EarthSessionPhase;generation:number;attempt:number;rootAt:number|null;retries:number};
type Stamp={wall:number;mono:number};
const stamp=():Stamp=>({wall:Date.now(),mono:performance.now()});
// Monotonic time tolerates wall-clock corrections; wall time covers suspended
// platforms whose performance clock stops during sleep. Neither implies expiry.
const age=(value:Stamp)=>Math.max(0,Date.now()-value.wall,performance.now()-value.mono);
type Root={tiles:Cesium.Cesium3DTileset;started:Stamp;visible:number;pending:number;processing:number;failed:boolean;probe:boolean;remove:Array<()=>void>};
type Attempt={started:Stamp;invalid:boolean;root?:Root};

/** One active root plus one bounded candidate; no camera, layer or credit DOM replacement. */
export function useGoogleEarthSession(viewerRef:RefObject<Cesium.Viewer|null>,key:string,enabled:boolean,detail:EarthDetail,offline:boolean){
  const [providerState,setProviderState]=useState<EarthProviderState>(offline?"offline":"unconfigured");
  const [tileStatus,setTileStatus]=useState({pending:0,processing:0,visible:0});
  const [session,setSession]=useState<Session>({phase:"disabled",generation:0,attempt:0,rootAt:null,retries:0});
  const detailRef=useRef(detail);detailRef.current=detail;
  const refreshRef=useRef<()=>void>(()=>{}),applyDetailRef=useRef<()=>void>(()=>{});
  useEffect(()=>{
    const viewer=viewerRef.current;if(!viewer||viewer.isDestroyed())return;
    let disposed=false,active:Root|undefined,candidate:Attempt|undefined,outstanding:Attempt|undefined;
    let timer:ReturnType<typeof setTimeout>|undefined,watchdog:ReturnType<typeof setTimeout>|undefined;
    let retryAt:Stamp|undefined,retryDelay=0,retries=0,generation=0,attempts=0,manual=false;
    const usable=()=>!disposed&&!viewer.isDestroyed();
    const foreground=()=>document.visibilityState!=="hidden"&&navigator.onLine!==false;
    const publish=(phase:EarthSessionPhase)=>{if(!disposed)setSession({phase,generation,attempt:attempts,rootAt:active?.started.wall??null,retries});};
    const requestRender=()=>{if(usable())viewer.scene.requestRender();};
    const stop=(root:Root)=>{
      root.remove.forEach(remove=>remove());root.remove=[];
      if(!viewer.isDestroyed())viewer.scene.primitives.remove(root.tiles);
      if(!root.tiles.isDestroyed())root.tiles.destroy();
    };
    const clearTimer=()=>{clearTimeout(timer);timer=undefined;};
    const showActive=()=>{
      if(!usable())return;
      const ready=!!active&&!active.failed&&active.tiles.tilesLoaded&&active.visible>0;
      const next:EarthProviderState=active?.failed?"error":active?.tiles.tilesLoaded?(ready?"ready":"reference"):active?"loading":candidate?"loading":"error";
      if(viewer.scene.globe.show===ready){viewer.scene.globe.show=!ready;requestRender();}
      setProviderState(next);
      const status=active?{pending:active.pending,processing:active.processing,visible:active.visible}:{pending:0,processing:0,visible:0};
      setTileStatus(prior=>prior.pending===status.pending&&prior.processing===status.processing&&prior.visible===status.visible?prior:status);
    };
    const schedule=()=>{clearTimer();if(!usable()||!foreground()||candidate||outstanding)return;const remaining=retryAt?retryDelay-age(retryAt):active?GOOGLE_ROOT_ROTATION_MS-age(active.started):0;timer=setTimeout(check,Math.max(1,Math.min(60_000,remaining)));};
    const retry=()=>{
      if(!usable())return;
      if(retries>GOOGLE_ROOT_RETRY_MS.length){publish("error");return;}
      retryAt=stamp();retryDelay=GOOGLE_ROOT_RETRY_MS[Math.max(0,retries-1)];
      publish(foreground()?"retry_wait":"paused");schedule();
    };
    const fail=(value:Attempt)=>{
      if(!usable()||value.invalid)return;
      value.invalid=true;clearTimeout(watchdog);watchdog=undefined;
      if(value.root)stop(value.root);if(candidate===value)candidate=undefined;
      retries++;showActive();requestRender();
      // Cesium's fromUrl has no public AbortSignal contract. Do not start a
      // parallel root after a hanging request; discard its eventual result,
      // then enter bounded backoff. Destroying a tileset cancels its tile work.
      if(outstanding===value)publish(foreground()?"waiting":"paused");else retry();
    };
    const commit=(value:Attempt)=>{
      if(!usable()||value.invalid||!value.root)return;
      clearTimeout(watchdog);watchdog=undefined;
      const prior=active;active=value.root;active.tiles.show=true;active.tiles.preloadWhenHidden=false;candidate=undefined;
      generation++;retries=0;retryAt=undefined;manual=false;
      if(prior)stop(prior);
      showActive();publish(foreground()?"current":"paused");requestRender();schedule();
    };
    const start=()=>{
      if(!usable()||candidate||outstanding)return;
      clearTimer();manual=false;retryAt=undefined;
      const value:Attempt={started:stamp(),invalid:false};candidate=value;outstanding=value;attempts++;publish("refreshing");
      if(!active)setProviderState("loading");
      watchdog=setTimeout(()=>fail(value),GOOGLE_ROOT_REQUEST_TIMEOUT_MS);
      void Cesium.Cesium3DTileset.fromUrl(`https://tile.googleapis.com/v1/3dtiles/root.json?key=${encodeURIComponent(key)}`,{showCreditsOnScreen:true,enableCollision:true,maximumScreenSpaceError:EARTH_DETAIL_ERROR[detailRef.current],cacheBytes:384*1024*1024,maximumCacheOverflowBytes:256*1024*1024}).then(tiles=>{
        if(outstanding===value)outstanding=undefined;
        if(!usable()||value.invalid){if(!tiles.isDestroyed())tiles.destroy();if(usable())retry();return;}
        clearTimeout(watchdog);watchdog=undefined;
        const root:Root={tiles,started:value.started,visible:0,pending:0,processing:0,failed:false,probe:false,remove:[]};value.root=root;
        tiles.maximumScreenSpaceError=EARTH_DETAIL_ERROR[detailRef.current];
        tiles.show=!active;tiles.preloadWhenHidden=!!active&&foreground();
        viewer.scene.primitives.add(tiles);
        root.remove.push(tiles.tileVisible.addEventListener(()=>{root.visible++;}));
        root.remove.push(tiles.loadProgress.addEventListener((pending:number,processing:number)=>{root.pending=pending;root.processing=processing;requestRender();}));
        root.remove.push(tiles.tileFailed.addEventListener(()=>{
          if(!usable())return;
          if(candidate===value)fail(value);
          else if(active===root&&!root.failed){root.failed=true;tiles.show=false;showActive();requestRender();if(!candidate&&!outstanding){retries++;retry();}}
        }));
        if(!active){commit(value);return;}
        watchdog=setTimeout(()=>fail(value),GOOGLE_ROOT_HANDOFF_TIMEOUT_MS);requestRender();
      }).catch(()=>{
        if(outstanding===value)outstanding=undefined;
        if(!usable())return;
        if(value.invalid){retry();return;}fail(value);
      });
    };
    function check(){
      clearTimer();if(!usable())return;
      if(!foreground()){if(candidate?.root){candidate.root.tiles.show=false;candidate.root.tiles.preloadWhenHidden=false;candidate.root.probe=false;}publish("paused");return;}
      if(candidate||outstanding){
        if(candidate?.root){candidate.root.tiles.preloadWhenHidden=!!active;requestRender();}
        publish(candidate?"refreshing":"waiting");return;
      }
      if(retries>GOOGLE_ROOT_RETRY_MS.length&&!manual){publish("error");return;}
      const due=manual||(retryAt?age(retryAt)>=retryDelay:!active||age(active.started)>=GOOGLE_ROOT_ROTATION_MS);
      if(due)start();else{publish(retryAt?"retry_wait":"current");schedule();}
    }
    viewer.scene.globe.show=true;setTileStatus({pending:0,processing:0,visible:0});requestRender();
    if(!enabled||!key){setProviderState(offline?"offline":"unconfigured");publish("disabled");return;}
    const removePre=viewer.scene.preRender.addEventListener(()=>{if(active)active.visible=0;if(candidate?.root)candidate.root.visible=0;});
    const removePost=viewer.scene.postRender.addEventListener(()=>{
      if(!usable())return;showActive();
      const value=candidate,root=value?.root;
      if(!value||!root||value.invalid||!foreground())return;
      // Hidden preloading avoids replacing usable old imagery with partial
      // content. A rendered-frame probe then proves actual current-view content
      // before the old root is removed; tileVisible itself never mutates primitives.
      if(!root.probe&&root.tiles.tilesLoaded){root.probe=true;root.tiles.show=true;root.tiles.preloadWhenHidden=false;requestRender();return;}
      if(root.probe&&root.tiles.tilesLoaded&&(root.visible>0||!!active&&!active.failed&&active.tiles.tilesLoaded&&active.visible===0)){commit(value);return;}
      if(root.probe){root.probe=false;root.tiles.show=false;root.tiles.preloadWhenHidden=true;requestRender();}
    });
    refreshRef.current=()=>{if(!usable()||candidate||outstanding)return;retries=0;manual=true;retryAt=undefined;check();};
    applyDetailRef.current=()=>{for(const root of [active,candidate?.root])if(root&&!root.tiles.isDestroyed())root.tiles.maximumScreenSpaceError=EARTH_DETAIL_ERROR[detailRef.current];requestRender();};
    document.addEventListener("visibilitychange",check);window.addEventListener("online",check);window.addEventListener("offline",check);window.addEventListener("pageshow",check);window.addEventListener("focus",check);
    check();
    return()=>{
      disposed=true;clearTimer();clearTimeout(watchdog);removePre();removePost();
      document.removeEventListener("visibilitychange",check);window.removeEventListener("online",check);window.removeEventListener("offline",check);window.removeEventListener("pageshow",check);window.removeEventListener("focus",check);
      refreshRef.current=()=>{};applyDetailRef.current=()=>{};
      if(candidate){candidate.invalid=true;if(candidate.root)stop(candidate.root);}if(outstanding)outstanding.invalid=true;if(active)stop(active);
    };
  },[viewerRef,key,enabled,offline]);
  useEffect(()=>applyDetailRef.current(),[detail]);
  return {providerState,tileStatus,session,refresh:()=>refreshRef.current()};
}
