import {useCallback,useEffect,useMemo,useRef,useState} from "react";
import * as Cesium from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import {SHOWCASE,safeUrl} from "../lib/runtime";
import {nowMs} from "../lib/clock";
import {EvidenceDetails} from "./EvidenceDetails";
import {CAMERA_PLACES,DEFAULT_EARTH_LAYERS,coordinateLabel,earthMarkers,enabledEarthMarkers,parseCoordinates,reportCameraRange,utc,type EarthKind,type EarthLayers,type EarthMarker,type ThermalObservation} from "../lib/earth";
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
  const container=useRef<HTMLDivElement>(null),credits=useRef<HTMLDivElement>(null),viewerRef=useRef<Cesium.Viewer|null>(null),sourceRef=useRef<Cesium.CustomDataSource|null>(null),routesRef=useRef<Cesium.CustomDataSource|null>(null);
  const [providerState,setProviderState]=useState<"offline"|"unconfigured"|"loading"|"ready"|"error">(SHOWCASE?"offline":"unconfigured");
  const [sceneError,setSceneError]=useState(false),[layersOpen,setLayersOpen]=useState(false),[layers,setLayers]=useState<EarthLayers>({...DEFAULT_EARTH_LAYERS});
  const [types,setTypes]=useState(new Set(TYPES)),[minimum,setMinimum]=useState(0),[query,setQuery]=useState(""),[selectedId,setSelectedId]=useState<string|null>(null);
  const [wallClock,setWallClock]=useState(nowMs),[visibleCount,setVisibleCount]=useState(0),[cameraHeight,setCameraHeight]=useState(0);
  const lastFocused=useRef<number|null>(null);
  useEffect(()=>{if(SHOWCASE)return;const timer=setInterval(()=>setWallClock(nowMs()),10000);return()=>clearInterval(timer);},[]);
  const clock=replayCursor??wallClock;
  const models=useMemo(()=>earthMarkers({events,aircraft,vessels,navigation:jammingZones,hotspots:firmsHotspots,clock,windowStart,replaying:replayCursor!=null,synthetic:SHOWCASE}),[events,aircraft,vessels,jammingZones,firmsHotspots,clock,windowStart,replayCursor]);
  const shown=useMemo(()=>enabledEarthMarkers(models,layers).filter(marker=>marker.kind!=="report"||(types.has(marker.report!.event_type)&&(minimum===0||marker.report!.severity>=minimum))),[models,layers,types,minimum]);
  const selected=shown.find(marker=>marker.id===selectedId);
  const shownRef=useRef(shown);shownRef.current=shown;
  const fly=useCallback((lat:number,lon:number,range=120000)=>{
    const viewer=viewerRef.current;if(!viewer||viewer.isDestroyed())return;
    viewer.camera.flyToBoundingSphere(new Cesium.BoundingSphere(Cesium.Cartesian3.fromDegrees(lon,lat,0),0),{duration:1.1,offset:new Cesium.HeadingPitchRange(0,Cesium.Math.toRadians(-55),range)});
  },[]);
  const choose=useCallback((marker:EarthMarker)=>{setSelectedId(marker.id);setQuery("");fly(marker.lat,marker.lon,marker.report?reportCameraRange(marker.report):marker.kind==="reference"?90000:60000);},[fly]);

  useEffect(()=>{
    if(!container.current||!credits.current)return;
    let viewer:Cesium.Viewer;
    try{viewer=new Cesium.Viewer(container.current,{creditContainer:credits.current,creditViewport:container.current,requestRenderMode:true,maximumRenderTimeChange:Infinity,timeline:false,animation:false,shouldAnimate:false,baseLayerPicker:false,geocoder:false,homeButton:false,navigationHelpButton:false,sceneModePicker:false,fullscreenButton:false,selectionIndicator:true,infoBox:false,baseLayer:false,skyBox:false,skyAtmosphere:false,terrainProvider:new Cesium.EllipsoidTerrainProvider()});}
    catch{container.current?.replaceChildren();credits.current?.replaceChildren();setSceneError(true);return;}
    setSceneError(false);
    viewerRef.current=viewer;viewer.scene.globe.depthTestAgainstTerrain=true;
    const removeError=viewer.scene.renderError.addEventListener(()=>setSceneError(true));
    viewer.scene.backgroundColor=Cesium.Color.fromCssColorString("#07111a");viewer.scene.globe.baseColor=Cesium.Color.fromCssColorString("#112530");
    viewer.scene.globe.enableLighting=false;viewer.scene.skyBox=undefined;
    if(viewer.scene.sun)viewer.scene.sun.show=false;if(viewer.scene.moon)viewer.scene.moon.show=false;
    const source=new Cesium.CustomDataSource("earth-observations"),routes=new Cesium.CustomDataSource("inherited-reference-routes");
    sourceRef.current=source;routesRef.current=routes;void viewer.dataSources.add(source);void viewer.dataSources.add(routes);
    if(SHOWCASE){void Cesium.SingleTileImageryProvider.fromUrl("/textures/earth-night.jpg",{credit:new Cesium.Credit("NASA Earth Observatory · Black Marble 2016 reference",true)}).then(provider=>{if(!viewer.isDestroyed()){viewer.imageryLayers.addImageryProvider(provider);viewer.scene.requestRender();}}).catch(()=>{if(!viewer.isDestroyed())setSceneError(true);});}
    else viewer.imageryLayers.addImageryProvider(new Cesium.UrlTemplateImageryProvider({url:"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",credit:"Esri, Maxar, Earthstar Geographics",maximumLevel:19}));
    viewer.camera.setView({destination:Cesium.Cartesian3.fromDegrees(44,29,4800000),orientation:{heading:0,pitch:-Math.PI/2,roll:0}});
    const removeRender=viewer.scene.preRender.addEventListener(()=>{
      const visible=applyEarthHorizon(source,viewer.camera.positionWC);setVisibleCount(prior=>prior===visible?prior:visible);
      const height=Math.round(viewer.camera.positionCartographic.height/100)*100;setCameraHeight(prior=>prior===height?prior:height);
      for(const route of routes.entities.values){const points=route.polyline?.positions?.getValue(viewer.clock.currentTime)||[];route.show=points.every((point:Cesium.Cartesian3)=>earthPointVisible(viewer.camera.positionWC,point));}
    });
    viewer.screenSpaceEventHandler.setInputAction((click:{position:Cesium.Cartesian2})=>{const picked=viewer.scene.pick(click.position);const entity=picked?.id;setSelectedId(entity instanceof Cesium.Entity&&source.entities.contains(entity)?entity.id:null);},Cesium.ScreenSpaceEventType.LEFT_CLICK);
    return()=>{removeError();removeRender();sourceRef.current=null;routesRef.current=null;viewerRef.current=null;viewer.destroy();};
  },[]);

  useEffect(()=>{
    const viewer=viewerRef.current;if(!viewer)return;
    let cancelled=false,tileset:Cesium.Cesium3DTileset|undefined;const removeListeners:Array<()=>void>=[];
    viewer.scene.globe.show=true;
    if(!googleEnabled){setProviderState(SHOWCASE?"offline":"unconfigured");viewer.scene.requestRender();return;}
    if(!googleKey){setProviderState("unconfigured");return;}
    setProviderState("loading");
    void Cesium.Cesium3DTileset.fromUrl(`https://tile.googleapis.com/v1/3dtiles/root.json?key=${encodeURIComponent(googleKey)}`,{showCreditsOnScreen:true,maximumScreenSpaceError:12}).then(tiles=>{
      if(cancelled||viewer.isDestroyed()){tiles.destroy();return;}
      tileset=tiles;viewer.scene.primitives.add(tiles);viewer.scene.globe.show=false;
      removeListeners.push(tiles.initialTilesLoaded.addEventListener(()=>{if(!cancelled)setProviderState("ready");}));
      removeListeners.push(tiles.tileFailed.addEventListener(()=>{if(!cancelled)setProviderState("error");}));
      viewer.scene.requestRender();
    }).catch(()=>{if(!cancelled&&!viewer.isDestroyed())setProviderState("error");});
    return()=>{cancelled=true;removeListeners.forEach(remove=>remove());if(tileset&&!viewer.isDestroyed())viewer.scene.primitives.remove(tileset);};
  },[googleKey,googleEnabled]);

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
  return <div className="earth-workspace" data-earth-provider={providerState}>
    <div ref={container} className="earth-canvas" role="region" aria-label="Interactive Earth with reported positions"/>
    <section className="earth-controls" aria-label="Earth controls">
      <div className="earth-provider-row"><div><span className="earth-eyebrow">ONE EARTH / {SHOWCASE?"EXERCISE":"SOURCE CONTEXT"}</span><h2>{providerState==="ready"?"Google Earth":providerState==="loading"?"Loading Google imagery…":providerState==="error"?"Google imagery incomplete":"Earth workspace"}</h2></div><button onClick={onConfigure} aria-label="Configure Earth imagery">Imagery</button></div>
      <p role="status">{sceneError?"Earth renderer unavailable. Reports and sources remain available.":providerState==="ready"?"Google 3D tiles connected · capture dates vary; imagery is not event verification":providerState==="error"?"Some Google tiles failed. Coverage, key restrictions and provider availability may limit this view.":providerState==="loading"?"Connecting to Google and loading the visible area…":SHOWCASE?"NASA Black Marble 2016 reference · no current satellite imagery":"Google is not configured · Esri reference imagery over an ellipsoid"}</p>
      {sceneError&&<button onClick={()=>window.location.reload()}>Reload Earth workspace</button>}
      <form className="earth-search" role="search" onSubmit={event=>{event.preventDefault();if(coordinates){fly(coordinates.lat,coordinates.lon);setQuery("");}else if(matches[0])choose(matches[0]);else if(places[0]){fly(places[0].lat,places[0].lon,places[0].range);setQuery("");}}}>
        <label htmlFor="earth-search">Find a position</label><div><input id="earth-search" value={query} onChange={event=>setQuery(event.target.value)} placeholder="Place, report, track or latitude, longitude" autoComplete="off"/><button type="submit">Go</button></div>
      </form>
      {query.trim()&&<div className="earth-search-results" role="group" aria-label="Position search results">{coordinates&&<button onClick={()=>{fly(coordinates.lat,coordinates.lon);setQuery("");}}>Coordinates · {coordinateLabel(coordinates.lat,coordinates.lon)}</button>}{matches.map(marker=><button key={marker.id} onClick={()=>choose(marker)}><small>{marker.kind}</small>{marker.name}</button>)}{places.map(place=><button key={place.name} onClick={()=>{fly(place.lat,place.lon,place.range);setQuery("");}}><small>Reference camera location</small>{place.name}</button>)}{!coordinates&&!matches.length&&!places.length&&<p>No known position matches. Search the report feed for unresolved reports; coordinates are not inferred.</p>}</div>}
      <div className="earth-toolbar"><button onClick={()=>fly(29,44,3500000)}>Region</button><button onClick={()=>fly(0,0,18000000)}>Globe</button><button onClick={()=>setLayersOpen(value=>!value)} aria-expanded={layersOpen} aria-controls="earth-layers">Layers {layersOpen?"−":"+"}</button><button onClick={()=>{const source=sourceRef.current;if(source&&source.entities.values.length)void viewerRef.current?.flyTo(source,{duration:1.1,offset:new Cesium.HeadingPitchRange(0,-Math.PI/3,0)});}} disabled={!shown.length}>Fit positions</button></div>
      <p className="earth-coverage" data-visible-count={visibleCount} data-position-count={shown.length} data-last-known-count={shown.filter(marker=>marker.positionState==="last_known").length}>{visibleCount} on visible hemisphere · {shown.length} positions enabled · {shown.filter(marker=>marker.positionState==="last_known").length} last known · {unlocated} reports without usable coordinates</p>
    </section>
    {layersOpen&&<section id="earth-layers" className="earth-layer-panel" aria-label="Spatial layers"><div className="earth-panel-heading"><h2>Spatial layers</h2><button onClick={()=>setLayersOpen(false)} aria-label="Close spatial layers">×</button></div><p>Source and time filters apply to reports. Track positions use their own observation clocks.</p>{LAYERS.map(([kind,label,help])=><label key={kind}><input type="checkbox" checked={layers[kind]} onChange={()=>setLayers(prior=>({...prior,[kind]:!prior[kind]}))}/><span>{label} <b>{counts(kind)}</b><small>{help}</small></span></label>)}<label><input type="checkbox" aria-label="Show last-known positions" checked={layers.lastKnown} onChange={()=>setLayers(prior=>({...prior,lastKnown:!prior.lastKnown}))}/><span>Last-known positions<small>Muted, hollow symbols retain aging observations within 120s for aircraft and 600s for vessels. They are not current or extrapolated positions; source clocks remain visible in details. Recorded replay positions also use hollow symbols.</small></span></label><label><input type="checkbox" checked={layers.routes} onChange={()=>setLayers(prior=>({...prior,routes:!prior.routes}))}/><span>Schematic reference routes<small>Inherited approximate waypoints. Source, survey date and current operating status unverified.</small></span></label><fieldset><legend>Spatial report types</legend>{TYPES.map(type=><label key={type}><input type="checkbox" checked={types.has(type)} onChange={()=>setTypes(prior=>{const next=new Set(prior);next.has(type)?next.delete(type):next.add(type);return next;})}/>{type.replace(/_/g," ")}</label>)}</fieldset><label>Scored report minimum<select value={minimum} onChange={event=>setMinimum(Number(event.target.value))}><option value={0}>All · includes unscored</option>{[3,5,7,9].map(value=><option key={value} value={value}>{value}/10 and above</option>)}</select></label><p>These layer controls change spatial symbols; the report feed remains searchable independently. Orbit markers have been removed: orbital models do not provide current observation coverage.</p></section>}
    <div className="earth-navigation" role="group" aria-label="Camera controls"><button aria-label="Zoom in" onClick={()=>{const camera=viewerRef.current?.camera;if(camera)camera.zoomIn(Math.max(100,camera.positionCartographic.height*.35));}}>+</button><button aria-label="Zoom out" onClick={()=>{const camera=viewerRef.current?.camera;if(camera)camera.zoomOut(Math.max(100,camera.positionCartographic.height*.5));}}>−</button><button onClick={()=>{const camera=viewerRef.current?.camera;if(camera)camera.setView({orientation:{heading:0,pitch:camera.pitch,roll:0}});}} aria-label="Orient north up">N</button><small>{cameraHeight>=1000000?`${(cameraHeight/1000000).toFixed(1)} Mm`:`${Math.round(cameraHeight/1000)} km`}<span>camera height</span></small></div>
    <div className="earth-bottom-stack"><div className="earth-clock" role="status"><span className="earth-position-legend">Tracks: solid = fresh observation · hollow = last known / recorded</span> {replayCursor!=null?`REPLAY · ${utc(new Date(replayCursor).toISOString())} · ${loadingSnapshots?"loading snapshots":snapshotAt?`snapshot ${utc(snapshotAt)}`:"no track snapshot"}`:SHOWCASE?"SYNTHETIC EXERCISE · fixed reference clock":"Source positions · no motion extrapolation · aircraft shown as surface projections"}</div><div ref={credits} className="earth-attribution" role="region" aria-label="Imagery and renderer attribution"/></div>
    {selected&&<aside className="earth-selection" aria-label="Selected position"><div className="earth-panel-heading"><span>{selected.kind.toUpperCase()} / SOURCE POSITION</span><button onClick={()=>setSelectedId(null)} aria-label="Close selected position">×</button></div><h2>{selected.name}</h2><dl>{selected.details.map(([name,value],i)=><div key={`${name}-${i}`}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>{safeUrl(selected.url)&&<a href={safeUrl(selected.url)} target="_blank" rel="noopener noreferrer">Open original source ↗</a>}{selected.report&&<EvidenceDetails event={selected.report}/>}</aside>}
  </div>;
}
