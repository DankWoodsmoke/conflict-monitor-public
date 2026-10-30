import {useCallback,useEffect,useMemo,useRef,useState} from "react";
import * as Cesium from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import {SHOWCASE,safeUrl} from "../lib/runtime";
import {nowMs} from "../lib/clock";
import {EvidenceDetails} from "./EvidenceDetails";
import {useModalFocus} from "../hooks/useModalFocus";
import {CAMERA_PLACES,DEFAULT_EARTH_LAYERS,EARTH_DETAIL_ERROR,earthResolutionScale,coordinateLabel,earthMarkers,enabledEarthMarkers,parseCoordinates,reportCameraRange,utc,type EarthDetail,type EarthKind,type EarthLayers,type EarthMarker,type ThermalObservation} from "../lib/earth";
import {applyEarthHorizon,earthPointVisible,syncEarthEntities} from "../lib/earthScene";
import {OIL_PIPELINES,GAS_PIPELINES} from "../lib/earthReference";
import type {ConflictEvent} from "../types/event";
import type {Aircraft,Vessel,JammingZone} from "../hooks/useTracking";

interface CesiumViewProps {
  focusEventId:number|null;googleKey:string;googleEnabled:boolean;onConfigure:()=>void;
  events:ConflictEvent[];aircraft:Aircraft[];vessels:Vessel[];jammingZones:JammingZone[];
  firmsHotspots?:ThermalObservation[];replayCursor?:number|null;windowStart?:number;
  loadingSnapshots?:boolean;snapshotAt?:string|null;
}
const LAYERS:Array<[EarthKind,string,string]>=[
  ["report","Reports","Only valid reported coordinates. Unresolved locations stay in the feed."],
  ["aircraft","Aircraft projections","Surface position only. Mixed provider altitude references are shown in details."],
  ["vessel","Vessel positions","AIS source positions; incomplete receiver coverage."],
  ["thermal","Thermal observations","VIIRS detections; not a cause, strike or actor assessment."],
  ["navigation","Navigation-quality candidates","Heuristic position-quality clusters; not evidence of intentional interference."],
  ["reference","Reference infrastructure","Inherited, unverified locations and ownership; original source and survey date unknown."],
];
const TYPES=["unclassified","military","diplomatic","economic","cyber","humanitarian","protest","thermal_anomaly"];

export function CesiumView({focusEventId,googleKey,googleEnabled,onConfigure,events,aircraft,vessels,jammingZones,firmsHotspots=[],replayCursor=null,windowStart,loadingSnapshots=false,snapshotAt=null}:CesiumViewProps){
  const container=useRef<HTMLDivElement>(null),credits=useRef<HTMLDivElement>(null),viewerRef=useRef<Cesium.Viewer|null>(null),sourceRef=useRef<Cesium.CustomDataSource|null>(null),routesRef=useRef<Cesium.CustomDataSource|null>(null),tilesetRef=useRef<Cesium.Cesium3DTileset|null>(null);
  const [providerState,setProviderState]=useState<"offline"|"unconfigured"|"loading"|"ready"|"reference"|"error">(SHOWCASE?"offline":"unconfigured");
  const [detail,setDetail]=useState<EarthDetail>("balanced"),[imageryAttempt,setImageryAttempt]=useState(0),[pose,setPose]=useState<"overhead"|"oblique">("overhead");
  const [navigationOpen,setNavigationOpen]=useState(()=>window.innerWidth>768&&window.innerHeight>500);
  const [creditOpen,setCreditOpen]=useState(false),creditCloseRef=useRef<HTMLElement|null>(null);
  const creditDialogRef=useModalFocus(creditOpen,()=>{if(creditCloseRef.current)creditCloseRef.current.click();else setCreditOpen(false);});
  const detailRef=useRef(detail);detailRef.current=detail;
  const [tileStatus,setTileStatus]=useState({pending:0,processing:0,visible:0});
  const [sceneError,setSceneError]=useState(false),[referenceState,setReferenceState]=useState<"loading"|"available"|"error">("loading"),[referenceAttempt,setReferenceAttempt]=useState(0),[layersOpen,setLayersOpen]=useState(false),[layers,setLayers]=useState<EarthLayers>({...DEFAULT_EARTH_LAYERS});
  const [types,setTypes]=useState(new Set(TYPES)),[minimum,setMinimum]=useState(0),[query,setQuery]=useState(""),[selectedId,setSelectedId]=useState<string|null>(null);
  const [wallClock,setWallClock]=useState(nowMs),[visibleCount,setVisibleCount]=useState(0),[cameraHeight,setCameraHeight]=useState(0),[cameraPitch,setCameraPitch]=useState(-90);
  const lastFocused=useRef<number|null>(null);
  useEffect(()=>{if(SHOWCASE)return;const timer=setInterval(()=>setWallClock(nowMs()),10000);return()=>clearInterval(timer);},[]);
  const clock=replayCursor??wallClock;
  const models=useMemo(()=>earthMarkers({events,aircraft,vessels,navigation:jammingZones,hotspots:firmsHotspots,clock,windowStart,replaying:replayCursor!=null,synthetic:SHOWCASE}),[events,aircraft,vessels,jammingZones,firmsHotspots,clock,windowStart,replayCursor]);
  const shown=useMemo(()=>enabledEarthMarkers(models,layers).filter(marker=>marker.kind!=="report"||(types.has(marker.report!.event_type)&&(minimum===0||marker.report!.severity>=minimum))),[models,layers,types,minimum]);
  const selected=shown.find(marker=>marker.id===selectedId);
  const shownRef=useRef(shown);shownRef.current=shown;
  const fly=useCallback((lat:number,lon:number,range=120000,view:typeof pose=pose)=>{
    const viewer=viewerRef.current;if(!viewer||viewer.isDestroyed())return;
    viewer.camera.flyToBoundingSphere(new Cesium.BoundingSphere(Cesium.Cartesian3.fromDegrees(lon,lat,0),0),{duration:1.1,offset:new Cesium.HeadingPitchRange(0,Cesium.Math.toRadians(view==="overhead"?-90:-45),range)});
  },[pose]);
  const referenceView=useCallback((place:typeof CAMERA_PLACES[number])=>{setSelectedId(null);setQuery("");const next=place.range<100000?"oblique":"overhead";setPose(next);fly(place.lat,place.lon,place.range,next);},[fly]);
  const orient=useCallback((next:typeof pose)=>{
    const viewer=viewerRef.current;if(!viewer||viewer.isDestroyed())return;setPose(next);
    const center=new Cesium.Cartesian2(viewer.canvas.clientWidth/2,viewer.canvas.clientHeight/2);
    let target:Cesium.Cartesian3|undefined;
    try{if(viewer.scene.pickPositionSupported)target=viewer.scene.pickPosition(center);}catch{/* Depth picking is optional; keep navigation available. */}
    target??=viewer.camera.pickEllipsoid(center,Cesium.Ellipsoid.WGS84);
    const pitch=Cesium.Math.toRadians(next==="overhead"?-90:-45);
    if(target){const range=Math.max(150,Cesium.Cartesian3.distance(viewer.camera.positionWC,target));viewer.camera.flyToBoundingSphere(new Cesium.BoundingSphere(target,0),{duration:.6,offset:new Cesium.HeadingPitchRange(viewer.camera.heading,pitch,range)});}
    else viewer.camera.setView({orientation:{heading:viewer.camera.heading,pitch,roll:0}});
    viewer.scene.requestRender();
  },[]);
  const choose=useCallback((marker:EarthMarker)=>{setSelectedId(marker.id);setQuery("");fly(marker.lat,marker.lon,marker.report?reportCameraRange(marker.report):marker.kind==="reference"?90000:60000);},[fly]);

  useEffect(()=>{
    if(!container.current||!credits.current)return;
    let viewer:Cesium.Viewer;
    try{viewer=new Cesium.Viewer(container.current,{creditContainer:credits.current,creditViewport:container.current,useBrowserRecommendedResolution:false,requestRenderMode:true,maximumRenderTimeChange:Infinity,timeline:false,animation:false,shouldAnimate:false,baseLayerPicker:false,geocoder:false,homeButton:false,navigationHelpButton:false,sceneModePicker:false,fullscreenButton:false,selectionIndicator:true,infoBox:false,baseLayer:false,skyBox:false,skyAtmosphere:false,terrainProvider:new Cesium.EllipsoidTerrainProvider()});}
    catch{container.current?.replaceChildren();credits.current?.replaceChildren();setSceneError(true);return;}
    setSceneError(false);
    viewerRef.current=viewer;viewer.scene.globe.depthTestAgainstTerrain=true;
    let removeCreditBindings=()=>{};
    const overlay=container.current.querySelector<HTMLElement>(".cesium-credit-lightbox-overlay"),lightbox=overlay?.querySelector<HTMLDivElement>(".cesium-credit-lightbox"),creditClose=lightbox?.querySelector<HTMLElement>(".cesium-credit-lightbox-close"),creditExpand=credits.current.querySelector<HTMLElement>(".cesium-credit-expand-link");
    if(overlay&&lightbox&&creditClose&&creditExpand){
      let active=true;
      creditDialogRef.current=lightbox;creditCloseRef.current=creditClose;
      lightbox.setAttribute("aria-label","Imagery data attribution");lightbox.tabIndex=-1;
      creditClose.setAttribute("role","button");creditClose.tabIndex=0;creditClose.setAttribute("aria-label","Close data attribution");creditClose.setAttribute("data-modal-close","");
      creditExpand.setAttribute("role","button");creditExpand.tabIndex=0;creditExpand.setAttribute("aria-label","Data attribution");creditExpand.setAttribute("aria-haspopup","dialog");
      const sync=()=>{
        if(!active)return;const open=overlay.style.display==="block";
        if(open){lightbox.setAttribute("role","dialog");lightbox.setAttribute("aria-modal","true");}
        else{lightbox.removeAttribute("role");lightbox.removeAttribute("aria-modal");}
        creditExpand.setAttribute("aria-expanded",String(open));setCreditOpen(open);
      };
      const activate=(event:KeyboardEvent)=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();event.stopPropagation();(event.currentTarget as HTMLElement).click();}};
      creditExpand.addEventListener("keydown",activate);creditClose.addEventListener("keydown",activate);
      const creditObserver=new MutationObserver(sync);creditObserver.observe(overlay,{attributes:true,attributeFilter:["style"]});sync();
      removeCreditBindings=()=>{active=false;creditObserver.disconnect();creditExpand.removeEventListener("keydown",activate);creditClose.removeEventListener("keydown",activate);creditCloseRef.current=null;creditDialogRef.current=null;setCreditOpen(false);};
    }
    const removeError=viewer.scene.renderError.addEventListener(()=>setSceneError(true));
    viewer.scene.backgroundColor=Cesium.Color.fromCssColorString("#07111a");viewer.scene.globe.baseColor=Cesium.Color.fromCssColorString("#112530");
    viewer.scene.globe.enableLighting=false;viewer.scene.skyBox=undefined;
    if(viewer.scene.sun)viewer.scene.sun.show=false;if(viewer.scene.moon)viewer.scene.moon.show=false;
    const source=new Cesium.CustomDataSource("earth-observations"),routes=new Cesium.CustomDataSource("inherited-reference-routes");
    sourceRef.current=source;routesRef.current=routes;void viewer.dataSources.add(source);void viewer.dataSources.add(routes);
    viewer.camera.setView({destination:Cesium.Cartesian3.fromDegrees(44,29,2000000),orientation:{heading:0,pitch:-Math.PI/2,roll:0}});
    const resize=()=>{if(viewer.isDestroyed())return;viewer.resolutionScale=earthResolutionScale(viewer.canvas.clientWidth||1,viewer.canvas.clientHeight||1,window.devicePixelRatio);viewer.resize();viewer.scene.requestRender();};
    const observer=typeof ResizeObserver!=="undefined"?new ResizeObserver(resize):null;observer?.observe(container.current);window.addEventListener("resize",resize);resize();
    const removeRender=viewer.scene.preRender.addEventListener(()=>{
      const visible=applyEarthHorizon(source,viewer.camera.positionWC);setVisibleCount(prior=>prior===visible?prior:visible);
      const height=Math.round(viewer.camera.positionCartographic.height/100)*100;setCameraHeight(prior=>prior===height?prior:height);
      const pitch=Math.round(Cesium.Math.toDegrees(viewer.camera.pitch));setCameraPitch(prior=>prior===pitch?prior:pitch);
      for(const route of routes.entities.values){const points=route.polyline?.positions?.getValue(viewer.clock.currentTime)||[];route.show=points.every((point:Cesium.Cartesian3)=>earthPointVisible(viewer.camera.positionWC,point));}
    });
    viewer.screenSpaceEventHandler.setInputAction((click:{position:Cesium.Cartesian2})=>{const picked=viewer.scene.pick(click.position);const entity=picked?.id;setSelectedId(entity instanceof Cesium.Entity&&source.entities.contains(entity)?entity.id:null);},Cesium.ScreenSpaceEventType.LEFT_CLICK);
    return()=>{removeCreditBindings();observer?.disconnect();window.removeEventListener("resize",resize);removeError();removeRender();sourceRef.current=null;routesRef.current=null;viewerRef.current=null;viewer.destroy();};
  },[]);

  useEffect(()=>{
    const viewer=viewerRef.current;if(!viewer)return;
    let cancelled=false,failed=false,layer:Cesium.ImageryLayer|undefined,removeError:(()=>void)|undefined;
    setReferenceState("loading");
    const fail=()=>{if(cancelled||viewer.isDestroyed())return;failed=true;setReferenceState("error");viewer.scene.requestRender();};
    const add=(provider:Cesium.ImageryProvider)=>{if(cancelled||viewer.isDestroyed())return;removeError=provider.errorEvent.addEventListener(fail);layer=viewer.imageryLayers.addImageryProvider(provider);viewer.scene.requestRender();};
    if(SHOWCASE)void Cesium.SingleTileImageryProvider.fromUrl("/textures/earth-day-2048.jpg",{credit:new Cesium.Credit("NASA Earth Observatory · Blue Marble May 2004 composite · static global reference",true)}).then(add).catch(fail);
    else add(new Cesium.UrlTemplateImageryProvider({url:"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",credit:"Esri, Vantor, Earthstar Geographics, and the GIS User Community",maximumLevel:19}));
    const removeRender=viewer.scene.postRender.addEventListener(()=>{if(cancelled||failed||!layer||!viewer.scene.globe.show)return;setReferenceState(viewer.scene.globe.tilesLoaded?"available":"loading");});
    return()=>{cancelled=true;removeError?.();removeRender();if(layer&&!viewer.isDestroyed())viewer.imageryLayers.remove(layer,true);};
  },[referenceAttempt]);

  useEffect(()=>{
    const viewer=viewerRef.current;if(!viewer)return;
    let cancelled=false,failed=false,visible=0,pending=0,processing=0,tileset:Cesium.Cesium3DTileset|undefined;const removeListeners:Array<()=>void>=[];
    viewer.scene.globe.show=true;
    setTileStatus({pending:0,processing:0,visible:0});
    if(!googleEnabled){setProviderState(SHOWCASE?"offline":"unconfigured");viewer.scene.requestRender();return;}
    if(!googleKey){setProviderState("unconfigured");return;}
    setProviderState("loading");
    const fallback=()=>{if(cancelled||viewer.isDestroyed())return;failed=true;if(tileset)tileset.show=false;viewer.scene.globe.show=true;setProviderState("error");viewer.scene.requestRender();};
    void Cesium.Cesium3DTileset.fromUrl(`https://tile.googleapis.com/v1/3dtiles/root.json?key=${encodeURIComponent(googleKey)}`,{showCreditsOnScreen:true,enableCollision:true,maximumScreenSpaceError:EARTH_DETAIL_ERROR[detailRef.current],cacheBytes:384*1024*1024,maximumCacheOverflowBytes:256*1024*1024}).then(tiles=>{
      if(cancelled||viewer.isDestroyed()){tiles.destroy();return;}
      tiles.maximumScreenSpaceError=EARTH_DETAIL_ERROR[detailRef.current];
      tileset=tiles;tilesetRef.current=tiles;viewer.scene.primitives.add(tiles);
      removeListeners.push(viewer.scene.preRender.addEventListener(()=>{visible=0;}));
      removeListeners.push(tiles.tileVisible.addEventListener(()=>{visible++;}));
      removeListeners.push(tiles.loadProgress.addEventListener((requests:number,work:number)=>{if(pending!==requests||processing!==work){pending=requests;processing=work;viewer.scene.requestRender();}}));
      removeListeners.push(tiles.tileFailed.addEventListener(fallback));
      removeListeners.push(viewer.scene.postRender.addEventListener(()=>{
        if(cancelled||failed)return;
        const ready=tiles.tilesLoaded&&visible>0,reference=tiles.tilesLoaded&&visible===0;
        if(viewer.scene.globe.show===ready){viewer.scene.globe.show=!ready;viewer.scene.requestRender();}
        setProviderState(ready?"ready":reference?"reference":"loading");
        setTileStatus(prior=>prior.pending===pending&&prior.processing===processing&&prior.visible===visible?prior:{pending,processing,visible});
      }));
      viewer.scene.requestRender();
    }).catch(fallback);
    return()=>{cancelled=true;removeListeners.forEach(remove=>remove());tilesetRef.current=null;if(tileset&&!viewer.isDestroyed())viewer.scene.primitives.remove(tileset);};
  },[googleKey,googleEnabled,imageryAttempt]);
  useEffect(()=>{const tiles=tilesetRef.current,viewer=viewerRef.current;if(tiles&&!tiles.isDestroyed()){tiles.maximumScreenSpaceError=EARTH_DETAIL_ERROR[detail];viewer?.scene.requestRender();}},[detail]);

  useEffect(()=>{
    const source=sourceRef.current,viewer=viewerRef.current;if(!source||!viewer)return;
    syncEarthEntities(source,shown);applyEarthHorizon(source,viewer.camera.positionWC);viewer.scene.requestRender();
  },[shown]);
  useEffect(()=>{
    const source=routesRef.current,viewer=viewerRef.current;if(!source||!viewer)return;
    source.entities.removeAll();
    if(layers.routes)for(const route of [...OIL_PIPELINES,...GAS_PIPELINES])source.entities.add({id:route.name,name:`Unverified schematic route: ${route.name}`,polyline:{positions:route.points.map(([lat,lon])=>Cesium.Cartesian3.fromDegrees(lon,lat,0)),clampToGround:true,width:2,material:Cesium.Color.fromCssColorString("#b8a981").withAlpha(.7)}});
    viewer.scene.requestRender();
  },[layers.routes]);
  useEffect(()=>{
    if(focusEventId==null){lastFocused.current=null;return;}if(lastFocused.current===focusEventId)return;
    const marker=models.find(row=>row.id===`report-${focusEventId}`);if(!marker)return;
    lastFocused.current=focusEventId;setLayers(prior=>({...prior,report:true}));setTypes(prior=>new Set([...prior,marker.report!.event_type]));setMinimum(0);choose(marker);
  },[focusEventId,models,choose]);
  useEffect(()=>{const key=(event:KeyboardEvent)=>{if(event.key==="Escape"){setSelectedId(null);setLayersOpen(false);setQuery("");}};window.addEventListener("keydown",key);return()=>window.removeEventListener("keydown",key);},[]);

  const coordinates=parseCoordinates(query);
  const matches=query.trim()?shown.filter(marker=>`${marker.name} ${marker.report?.location_name||""}`.toLowerCase().includes(query.trim().toLowerCase())).slice(0,6):[];
  const places=query.trim()?CAMERA_PLACES.filter(place=>place.name.toLowerCase().includes(query.trim().toLowerCase())).slice(0,4):[];
  const counts=(kind:EarthKind)=>models.filter(model=>model.kind===kind).length;
  const reportCount=counts("report"),unlocated=events.length-reportCount;
  const referenceName=SHOWCASE?"NASA 2004 static reference":"Esri satellite reference";
  const providerSummary=sceneError?"Earth renderer unavailable":referenceState==="error"&&providerState!=="ready"?`${providerState==="error"?"Google unavailable · ":""}Reference imagery incomplete · reports remain accessible`:providerState==="ready"?"Photographic imagery · capture dates vary":providerState==="error"?`Google unavailable · ${referenceName}`:providerState==="reference"?`No visible Google 3D tiles · ${referenceName}`:providerState==="loading"?`Refining Google imagery · ${referenceName} underneath`:referenceState==="loading"?`Loading ${referenceName}`:`${referenceName} · Google not enabled`;
  return <div className="earth-workspace" data-earth-provider={providerState} data-earth-reference={referenceState} data-earth-detail={detail} data-earth-camera-pitch={cameraPitch}>
    <div ref={container} className="earth-canvas" role="region" aria-label="Interactive Earth with reported positions"/>
    <section className="earth-controls" aria-label="Earth controls">
      <div className="earth-provider-row"><div><span className="earth-eyebrow">ONE EARTH / {SHOWCASE?"EXERCISE":"SOURCE CONTEXT"}</span><h2>{providerState==="ready"?"Google 3D imagery":providerState==="loading"?"Loading Google 3D":"Earth workspace"}</h2></div><div className="earth-provider-actions"><button onClick={onConfigure} aria-label="Configure Earth imagery">Imagery</button><button className="earth-navigation-toggle" onClick={()=>setNavigationOpen(value=>!value)} aria-label={navigationOpen?"Hide controls — Earth navigation":"Controls — show Earth navigation"} aria-expanded={navigationOpen} aria-controls="earth-navigation-body">{navigationOpen?"Hide controls":"Controls"}</button></div></div>
      <p className="earth-provider-status" role="status">{providerSummary}</p>
      {googleEnabled&&googleKey&&providerState==="error"&&<button className="earth-retry-imagery" onClick={()=>setImageryAttempt(value=>value+1)}>Retry Google imagery</button>}
      {referenceState==="error"&&providerState!=="ready"&&<button className="earth-retry-imagery" onClick={()=>setReferenceAttempt(value=>value+1)}>Retry reference imagery</button>}
      {sceneError&&<button onClick={()=>window.location.reload()}>Reload Earth workspace</button>}
      <div id="earth-navigation-body" className="earth-navigation-body" hidden={!navigationOpen} style={navigationOpen?undefined:{display:"none"}}>
      <form className="earth-search" role="search" onSubmit={event=>{event.preventDefault();if(coordinates){fly(coordinates.lat,coordinates.lon);setQuery("");}else if(matches[0])choose(matches[0]);else if(places[0])referenceView(places[0]);}}>
        <label htmlFor="earth-search">Find a position</label><div><input id="earth-search" value={query} onChange={event=>setQuery(event.target.value)} placeholder="Place, report, track or latitude, longitude" autoComplete="off"/><button type="submit">Go</button></div>
      </form>
      {query.trim()&&<div className="earth-search-results" role="group" aria-label="Position search results">{coordinates&&<button onClick={()=>{fly(coordinates.lat,coordinates.lon);setQuery("");}}>Coordinates · {coordinateLabel(coordinates.lat,coordinates.lon)}</button>}{matches.map(marker=><button key={marker.id} onClick={()=>choose(marker)}><small>{marker.kind}</small>{marker.name}</button>)}{places.map(place=><button key={place.name} onClick={()=>referenceView(place)}><small>Reference camera location</small>{place.name}</button>)}{!coordinates&&!matches.length&&!places.length&&<p>No known position matches. Search the report feed for unresolved reports; coordinates are not inferred.</p>}</div>}
      <div className="earth-toolbar earth-toolbar-primary"><button onClick={()=>referenceView(CAMERA_PLACES[0])}>Region</button><button onClick={()=>{setPose("overhead");fly(0,0,18000000,"overhead");}}>Globe</button><button onClick={()=>setLayersOpen(value=>!value)} aria-expanded={layersOpen} aria-controls="earth-layers">Layers {layersOpen?"−":"+"}</button><button onClick={()=>{const source=sourceRef.current;if(source&&source.entities.values.length)void viewerRef.current?.flyTo(source,{duration:1.1,offset:new Cesium.HeadingPitchRange(0,-Math.PI/3,0)});}} disabled={!shown.length}>Fit positions</button></div>
      <div className="earth-location-presets" role="group" aria-label="Reference city views"><span>Inspect city</span>{["Dubai","Tel Aviv","Tehran","Gaza"].map(name=><button key={name} onClick={()=>referenceView(CAMERA_PLACES.find(place=>place.name===name)!)} title="Reference camera view; not a report location">{name}</button>)}</div>
      <div className="earth-view-controls" role="group" aria-label="Earth view angle"><button aria-pressed={cameraPitch<=-80} onClick={()=>orient("overhead")}>Top down</button><button aria-pressed={cameraPitch>-80} onClick={()=>orient("oblique")}>Oblique 3D</button></div>
      <details className="earth-imagery-details"><summary className="earth-imagery-summary">Imagery and detail</summary><p>Google photographic imagery is geographic context, not current event footage. Resolution, coverage and capture dates vary; 3D buildings are available only where the provider supplies them. {SHOWCASE?"The keyless reference is NASA Blue Marble May 2004 composite, approximately 20 km/pixel; other exercise sources remain synthetic.":"The fallback is Esri reference satellite/aerial imagery over an ellipsoid."}</p><div className="earth-quality-controls"><label>Render detail<select aria-label="Imagery render detail" value={detail} onChange={event=>setDetail(event.target.value as EarthDetail)}><option value="balanced">Balanced</option><option value="detail">Detailed inspection</option></select></label></div><p>Native display pixels are capped at 2× and 8 million pixels. Detail refines the rendered mesh; it cannot increase the source image resolution or update its capture date.</p>{googleEnabled&&<p>{tileStatus.pending} tile requests · {tileStatus.processing} processing · {tileStatus.visible} visible tiles</p>}<p className="earth-coverage" data-visible-count={visibleCount} data-position-count={shown.length} data-last-known-count={shown.filter(marker=>marker.positionState==="last_known").length}>{visibleCount} on visible hemisphere · {shown.length} positions enabled · {shown.filter(marker=>marker.positionState==="last_known").length} last known · {unlocated} reports without usable coordinates</p></details>
      </div>
    </section>
    {layersOpen&&<section id="earth-layers" className="earth-layer-panel" aria-label="Spatial layers"><div className="earth-panel-heading"><h2>Spatial layers</h2><button onClick={()=>setLayersOpen(false)} aria-label="Close spatial layers">×</button></div><p>Source and time filters apply to reports. Track positions use their own observation clocks.</p>{LAYERS.map(([kind,label,help])=><label key={kind}><input type="checkbox" checked={layers[kind]} onChange={()=>setLayers(prior=>({...prior,[kind]:!prior[kind]}))}/><span>{label} <b>{counts(kind)}</b><small>{help}</small></span></label>)}<label><input type="checkbox" aria-label="Show last-known positions" checked={layers.lastKnown} onChange={()=>setLayers(prior=>({...prior,lastKnown:!prior.lastKnown}))}/><span>Last-known positions<small>Muted, hollow symbols retain aging observations within 120s for aircraft and 600s for vessels. They are not current or extrapolated positions; source clocks remain visible in details. Recorded replay positions also use hollow symbols.</small></span></label><label><input type="checkbox" checked={layers.routes} onChange={()=>setLayers(prior=>({...prior,routes:!prior.routes}))}/><span>Schematic reference routes<small>Inherited approximate waypoints. Source, survey date and current operating status unverified.</small></span></label><fieldset><legend>Spatial report types</legend>{TYPES.map(type=><label key={type}><input type="checkbox" checked={types.has(type)} onChange={()=>setTypes(prior=>{const next=new Set(prior);next.has(type)?next.delete(type):next.add(type);return next;})}/>{type.replace(/_/g," ")}</label>)}</fieldset><label>Scored report minimum<select value={minimum} onChange={event=>setMinimum(Number(event.target.value))}><option value={0}>All · includes unscored</option>{[3,5,7,9].map(value=><option key={value} value={value}>{value}/10 and above</option>)}</select></label><p>These layer controls change spatial symbols; the report feed remains searchable independently. Orbit markers have been removed: orbital models do not provide current observation coverage.</p></section>}
    <div className="earth-navigation" role="group" aria-label="Camera controls"><button aria-label="Zoom in" onClick={()=>{const camera=viewerRef.current?.camera;if(camera)camera.zoomIn(Math.max(100,camera.positionCartographic.height*.35));}}>+</button><button aria-label="Zoom out" onClick={()=>{const camera=viewerRef.current?.camera;if(camera)camera.zoomOut(Math.max(100,camera.positionCartographic.height*.5));}}>−</button><button onClick={()=>{const camera=viewerRef.current?.camera;if(camera)camera.setView({orientation:{heading:0,pitch:camera.pitch,roll:0}});}} aria-label="Orient north up">N</button><small>{cameraHeight>=1000000?`${(cameraHeight/1000000).toFixed(1)} Mm`:`${Math.round(cameraHeight/1000)} km`}<span>camera height</span></small></div>
    <div className="earth-bottom-stack"><div className="earth-clock" role="status"><span className="earth-position-legend">Tracks: solid = fresh observation · hollow = last known / recorded</span> {replayCursor!=null?`REPLAY · ${utc(new Date(replayCursor).toISOString())} · ${loadingSnapshots?"loading snapshots":snapshotAt?`snapshot ${utc(snapshotAt)}`:"no track snapshot"}`:SHOWCASE?"SYNTHETIC EXERCISE · fixed reference clock":"Source positions · no motion extrapolation · aircraft shown as surface projections"}</div><div ref={credits} className="earth-attribution" role="region" aria-label="Imagery and renderer attribution"/></div>
    {selected&&<aside className="earth-selection" aria-label="Selected position"><div className="earth-panel-heading"><span>{selected.kind.toUpperCase()} / SOURCE POSITION</span><button onClick={()=>setSelectedId(null)} aria-label="Close selected position">×</button></div><h2>{selected.name}</h2><dl>{selected.details.map(([name,value],i)=><div key={`${name}-${i}`}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>{safeUrl(selected.url)&&<a href={safeUrl(selected.url)} target="_blank" rel="noopener noreferrer">Open original source ↗</a>}{selected.report&&<EvidenceDetails event={selected.report}/>}</aside>}
  </div>;
}
