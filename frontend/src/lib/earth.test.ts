import {describe,expect,it} from "vitest";
import * as Cesium from "cesium";
import {earthMarkers,enabledEarthMarkers,validCoordinates,trackClock,coordinateLabel,parseCoordinates,DEFAULT_EARTH_LAYERS,reportCameraRange} from "./earth";
import {applyEarthHorizon,earthPointVisible,syncEarthEntities} from "./earthScene";
import {workspaceView} from "./workspace";
import {buildShowcase} from "./showcase";
import {createElement} from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {CesiumView} from "../components/CesiumView";

const now=Date.parse("2026-10-29T03:00:00Z"),fixture=buildShowcase(now);
const event={...fixture.events[0],id:123,lat:-33.9,lon:151.2,geolocation_precision:"city" as const};
const options={events:[event],aircraft:[],vessels:[],navigation:[],hotspots:[],clock:now};

it("names the interactive Earth region without flattening its descendants and groups named camera controls",()=>{
 const host=document.createElement("div");host.innerHTML=renderToStaticMarkup(createElement(CesiumView,{focusEventId:null,googleKey:"",googleEnabled:false,onConfigure:()=>{},events:[],aircraft:[],vessels:[],jammingZones:[]}));
 expect(host.querySelector('.earth-canvas[role="region"][aria-label="Interactive Earth with reported positions"]')).not.toBeNull();
 expect(host.querySelector('.earth-canvas[aria-hidden],.earth-canvas[role="img"]')).toBeNull();
 expect(host.querySelectorAll('.earth-navigation[role="group"][aria-label="Camera controls"] button[aria-label]')).toHaveLength(3);
});

describe("Earth position and clock policy",()=>{
 it.each([[0,0],[-90,-180],[90,180],[-33.9,151.2]])("retains valid signed coordinates including zero",(lat,lon)=>expect(validCoordinates(lat,lon)).toBe(true));
 it.each([[null,0],[0,null],[NaN,1],[1,Infinity],[91,0],[0,181],["1",2]])("rejects unknown or invalid coordinates instead of guessing",(lat,lon)=>expect(validCoordinates(lat,lon)).toBe(false));
 it("uses truthful S/W labels and validates coordinate search",()=>{expect(coordinateLabel(-1,-2)).toBe("1.0000°S, 2.0000°W");expect(parseCoordinates("0, 0")).toEqual({lat:0,lon:0});expect(parseCoordinates("-33.9,151.2")).toEqual({lat:-33.9,lon:151.2});expect(parseCoordinates("91,45")).toBeNull();});
 it("keeps unresolved reports out of the scene and scales camera context to stated precision",()=>{
   const result=earthMarkers({...options,events:[event,{...event,id:124,lat:null}]});expect(result.filter(row=>row.kind==="report")).toHaveLength(1);
   expect(reportCameraRange({...event,geolocation_precision:"country"})).toBeGreaterThan(reportCameraRange(event));
 });
 it("preserves genuine zero altitude as metadata and never creates a10km aircraft position",()=>{
   const ac={...fixture.aircraft[0],altitude:0,observed_at:new Date(now-10000).toISOString()};
   const marker=earthMarkers({...options,aircraft:[ac]}).find(row=>row.kind==="aircraft")!;
   expect(marker.height).toBe(0);expect(marker.details).toContainEqual(["Reported altitude","0 m"]);expect(marker.details).toContainEqual(["Position display","Surface projection; aircraft height is not inferred"]);
   const unknown=earthMarkers({...options,aircraft:[{...ac,altitude:null}]}).find(row=>row.kind==="aircraft")!;expect(unknown.details).toContainEqual(["Reported altitude","Unknown"]);expect(unknown.height).toBe(0);
 });
 it("expires stale/future positions against the displayed clock and preserves receipt versus observation",()=>{
   expect(trackClock({observed_at:new Date(now-121000).toISOString()},now,120000)).toBeNull();
   expect(trackClock({observed_at:new Date(now+61000).toISOString()},now,120000)).toBeNull();
   expect(trackClock({received_at:new Date(now-10000).toISOString()},now,120000)?.[0]).toContain("observation time unknown");
   expect(trackClock({},now,120000)).toBeNull();
   expect(trackClock({observed_at:new Date(now+30000).toISOString()},now,120000)?.[1]).toContain("30s ahead of displayed clock");
   expect(trackClock({snapshot_at:new Date(now-10000).toISOString()},now,120000)?.[0]).toContain("Snapshot captured");
 });
 it("retains source-stale aircraft as last known within120s without weakening the45s freshness gate",()=>{
   const ac={...fixture.aircraft[0],icao24:"aging",stale:true,observed_at:new Date(now-60000).toISOString()};
   const marker=earthMarkers({...options,aircraft:[ac]}).find(row=>row.kind==="aircraft")!;
   expect(marker.positionState).toBe("last_known");expect(marker.details).toContainEqual(["Position state","Last-known observation · not a current position"]);
   expect(marker.lat).toBe(ac.lat);expect(marker.lon).toBe(ac.lon);expect(marker.height).toBe(0);
   expect(earthMarkers({...options,aircraft:[{...ac,observed_at:new Date(now-121000).toISOString()}]}).some(row=>row.kind==="aircraft")).toBe(false);
   expect(earthMarkers({...options,aircraft:[{...ac,observed_at:new Date(now+61000).toISOString()}]}).some(row=>row.kind==="aircraft")).toBe(false);
   const fresh=earthMarkers({...options,aircraft:[{...ac,stale:false,observed_at:new Date(now-44000).toISOString()}]}).find(row=>row.kind==="aircraft")!;
   expect(fresh.positionState).toBe("fresh");
   const agedBetweenPolls=earthMarkers({...options,aircraft:[{...ac,stale:false,observed_at:new Date(now-46000).toISOString()}]}).find(row=>row.kind==="aircraft")!;
   expect(agedBetweenPolls.positionState).toBe("last_known");
 });
 it("keeps bounded aging vessel observations optional and separates recorded snapshots from fresh observations",()=>{
   const vessel={...fixture.vessels[0],stale:true,observed_at:new Date(now-200000).toISOString()};
   const models=earthMarkers({...options,vessels:[vessel]});const marker=models.find(row=>row.kind==="vessel")!;
   expect(marker.positionState).toBe("last_known");expect(DEFAULT_EARTH_LAYERS.lastKnown).toBe(true);
   expect(enabledEarthMarkers(models,DEFAULT_EARTH_LAYERS)).toContain(marker);
   expect(enabledEarthMarkers(models,{...DEFAULT_EARTH_LAYERS,lastKnown:false})).not.toContain(marker);
   expect(earthMarkers({...options,vessels:[{...vessel,observed_at:new Date(now-601000).toISOString()}]}).some(row=>row.kind==="vessel")).toBe(false);
   const recorded=earthMarkers({...options,replaying:true,aircraft:[{...fixture.aircraft[0],snapshot_at:new Date(now-10000).toISOString()}]}).find(row=>row.kind==="aircraft")!;
   expect(recorded.positionState).toBe("recorded");
   expect(recorded.details).toContainEqual(["Position state","Recorded snapshot · not a live position"]);
 });
 it("never draws current thermal data into an earlier replay or calls inherited references observations",()=>{
   const result=earthMarkers({...options,clock:now-3600000,hotspots:[{lat:1,lon:2,frp:12,conf:null,ts:new Date(now).toISOString()}]});
   expect(result.some(row=>row.kind==="thermal")).toBe(false);expect(DEFAULT_EARTH_LAYERS.reference).toBe(false);expect(DEFAULT_EARTH_LAYERS.routes).toBe(false);expect(DEFAULT_EARTH_LAYERS.thermal).toBe(false);
   expect(result.find(row=>row.kind==="reference")?.details).toContainEqual(["Source / survey date","Unverified; retained from recovered application"]);
 });
 it.each([null,"map","3d","earth","invalid"])("normalizes earlier spatial bookmarks to a single Earth workspace",value=>expect(workspaceView(value)).toBe("earth"));
});

describe("actual Cesium entity reconciliation and ellipsoid occlusion",()=>{
 it("changes an existing track to hollow last-known styling and restores fresh styling only after a fresh source observation",()=>{
   const source=new Cesium.CustomDataSource(),ac={...fixture.aircraft[0],icao24:"aging",stale:false,observed_at:new Date(now-10000).toISOString()};
   const render=(row:typeof ac)=>{const marker=earthMarkers({...options,aircraft:[row]}).filter(value=>value.kind==="aircraft");syncEarthEntities(source,marker);return source.entities.values[0];};
   const entity=render(ac);const time=Cesium.JulianDate.now();const freshImage=entity.billboard!.image!.getValue(time);
   render({...ac,stale:true,observed_at:new Date(now-60000).toISOString()});
   expect(source.entities.values[0]).toBe(entity);expect(entity.properties!.getValue(time).positionState).toBe("last_known");
   expect(entity.label!.text!.getValue(time)).toContain("LAST KNOWN");expect(decodeURIComponent(entity.billboard!.image!.getValue(time))).toContain('fill="none"');
   expect(entity.billboard!.image!.getValue(time)).not.toBe(freshImage);
   render({...ac,observed_at:new Date(now).toISOString()});expect(entity.properties!.getValue(time).positionState).toBe("fresh");
   expect(entity.label!.text!.getValue(time)).not.toContain("LAST KNOWN");expect(entity.billboard!.image!.getValue(time)).toBe(freshImage);
 });
 it("updates same-ID coordinates, heading, label and detail model instead of freezing its first observation",()=>{
   const source=new Cesium.CustomDataSource();const ac={...fixture.aircraft[0],icao24:"abc123",callsign:"BEFORE",heading:0,lat:10,lon:20,observed_at:new Date(now).toISOString()};
   let markers=earthMarkers({...options,aircraft:[ac]}).filter(row=>row.kind==="aircraft");syncEarthEntities(source,markers);
   const entity=source.entities.getById("aircraft-abc123")!;
   markers=earthMarkers({...options,aircraft:[{...ac,callsign:"AFTER",heading:90,lat:-10,lon:-20}]}).filter(row=>row.kind==="aircraft");syncEarthEntities(source,markers);
   expect(source.entities.values).toHaveLength(1);expect(source.entities.getById(entity.id)).toBe(entity);expect(entity.name).toBe("AFTER");
   const position=Cesium.Cartographic.fromCartesian(entity.position!.getValue(Cesium.JulianDate.now())!);
   expect(Cesium.Math.toDegrees(position.latitude)).toBeCloseTo(-10,8);expect(Cesium.Math.toDegrees(position.longitude)).toBeCloseTo(-20,8);expect(position.height).toBeCloseTo(0,6);
   expect(entity.billboard!.rotation!.getValue(Cesium.JulianDate.now())).toBeCloseTo(-Math.PI/2);expect(entity.billboard!.disableDepthTestDistance!.getValue(Cesium.JulianDate.now())).toBe(0);
   expect(markers[0].details).toContainEqual(["Heading","90 degrees"]);expect(entity.label!.text!.getValue(Cesium.JulianDate.now())).toBe("AFTER");
 });
 it("updates retained report coordinates and removes missing IDs",()=>{
   const source=new Cesium.CustomDataSource();syncEarthEntities(source,earthMarkers(options).filter(row=>row.kind==="report"));
   syncEarthEntities(source,earthMarkers({...options,events:[{...event,lat:0,lon:0,summary:"Corrected source position"}]}).filter(row=>row.kind==="report"));
   expect(source.entities.values[0].name).toBe("Corrected source position");expect(source.entities.values[0].properties!.getValue(Cesium.JulianDate.now()).latitude).toBe(0);
   syncEarthEntities(source,[]);expect(source.entities.values).toHaveLength(0);
 });
 it("rejects the far hemisphere with no visible globe dependency and restores it after moving the camera",()=>{
   const near=Cesium.Cartesian3.fromDegrees(0,0,0),far=Cesium.Cartesian3.fromDegrees(180,0,0),camera=Cesium.Cartesian3.fromDegrees(0,0,3000000);
   expect(earthPointVisible(camera,near)).toBe(true);expect(earthPointVisible(camera,far)).toBe(false);
   const source=new Cesium.CustomDataSource();const marker=earthMarkers({...options,events:[{...event,lat:0,lon:180}]}).filter(row=>row.kind==="report");syncEarthEntities(source,marker);
   expect(applyEarthHorizon(source,camera)).toBe(0);expect(source.entities.values[0].show).toBe(false);
   expect(applyEarthHorizon(source,Cesium.Cartesian3.fromDegrees(180,0,3000000))).toBe(1);expect(source.entities.values[0].show).toBe(true);
 });
});
