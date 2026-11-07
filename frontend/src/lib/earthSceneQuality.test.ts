import {describe,expect,it} from "vitest";
import * as Cesium from "cesium";
import {syncEarthEntities,applyEarthHorizon} from "./earthScene";
import type {EarthMarker} from "./earth";

const marker:EarthMarker={id:"aircraft-fixture",kind:"aircraft",name:"Synthetic track",lat:25,lon:55,height:0,color:"#8fd3f5",details:[],positionState:"fresh"};
describe("track symbols retain source meaning at inspection and overview scales",()=>{
 it("shows direction only for valid reported headings, including north, and updates the same entity",()=>{
  const source=new Cesium.CustomDataSource(),time=Cesium.JulianDate.now();
  for(const heading of [null,undefined,NaN,-1,360,511,0,90]){
   syncEarthEntities(source,[{...marker,heading}]);const entity=source.entities.getById(marker.id)!;
   const directional=heading===0||heading===90;
   expect(entity.properties!.getValue(time).directionShown).toBe(directional);
   expect(entity.properties!.getValue(time).symbol).toBe(directional?"aircraft":"aircraft_unknown");
   expect(entity.billboard!.alignedAxis!.getValue(time)).toEqual(directional?Cesium.Cartesian3.UNIT_Z:Cesium.Cartesian3.ZERO);
   expect(entity.billboard!.rotation!.getValue(time)).toBeCloseTo(heading===90?-Math.PI/2:0,12);
   expect(entity.billboard!.disableDepthTestDistance!.getValue(time)).toBe(Number.POSITIVE_INFINITY);
   expect(entity.billboard!.heightReference!.getValue(time)).toBe(Cesium.HeightReference.CLAMP_TO_GROUND);
  }
  expect(source.entities.values).toHaveLength(1);
 });
 it("keeps surface annotations whole while independent horizon masks all source kinds",()=>{
  const source=new Cesium.CustomDataSource(),time=Cesium.JulianDate.now();
  const rows=(["aircraft","vessel","report","thermal","reference","navigation"] as const).map(kind=>({...marker,id:kind,kind,lat:30.077362,lon:32.305567,heading:145.29}));
  syncEarthEntities(source,rows);
  for(const entity of source.entities.values){
   expect(entity.position!.getValue(time)).toEqual(Cesium.Cartesian3.fromDegrees(32.305567,30.077362,0));
   expect(entity.billboard!.disableDepthTestDistance!.getValue(time)).toBe(Number.POSITIVE_INFINITY);
   expect(entity.label!.disableDepthTestDistance!.getValue(time)).toBe(Number.POSITIVE_INFINITY);
  }
  expect(applyEarthHorizon(source,Cesium.Cartesian3.fromDegrees(32.305567,30.077362,60000))).toBe(rows.length);
  expect(applyEarthHorizon(source,Cesium.Cartesian3.fromDegrees(32.305567-180,-30.077362,60000))).toBe(0);
  expect(source.entities.values.every(e=>!e.show)).toBe(true);
 });
 it("reduces regional symbol clutter without removing positions or losing last-known styling",()=>{
  const source=new Cesium.CustomDataSource(),time=Cesium.JulianDate.now();
  syncEarthEntities(source,[{...marker,heading:180,positionState:"last_known"}]);
  const entity=source.entities.getById(marker.id)!;
  const scale=entity.billboard!.scaleByDistance!.getValue(time);
  expect(scale.nearValue).toBe(1);expect(entity.billboard!.width!.getValue(time)*scale.farValue).toBe(24);expect(scale.far).toBeGreaterThan(scale.near);
  expect(entity.label!.distanceDisplayCondition!.getValue(time).far).toBe(50000);
  expect(decodeURIComponent(entity.billboard!.image!.getValue(time))).toContain('stroke-dasharray="3 2"');
  expect(entity.label!.text!.getValue(time)).toContain("LAST KNOWN");
  expect(source.entities.values).toHaveLength(1);
 });
});
