import {describe,expect,it} from "vitest";
import * as Cesium from "cesium";
import {syncEarthEntities} from "./earthScene";
import type {EarthMarker} from "./earth";

const marker:EarthMarker={id:"aircraft-fixture",kind:"aircraft",name:"Synthetic track",lat:25,lon:55,height:0,color:"#8fd3f5",details:[],positionState:"fresh"};
describe("track symbols retain source meaning at inspection and overview scales",()=>{
 it("shows direction only for valid reported headings, including north, and updates the same entity",()=>{
  const source=new Cesium.CustomDataSource(),time=Cesium.JulianDate.now();
  for(const heading of [null,undefined,NaN,-1,360,511,0,90]){
   syncEarthEntities(source,[{...marker,heading}]);const entity=source.entities.getById(marker.id)!;
   const svg=decodeURIComponent(entity.billboard!.image!.getValue(time));
   const directional=heading===0||heading===90;
   expect(svg.includes("<path")).toBe(directional);
   expect(entity.billboard!.rotation!.getValue(time)).toBeCloseTo(heading===90?-Math.PI/2:0,12);
   expect(entity.billboard!.disableDepthTestDistance!.getValue(time)).toBe(0);
   expect(entity.billboard!.heightReference!.getValue(time)).toBe(Cesium.HeightReference.CLAMP_TO_GROUND);
  }
  expect(source.entities.values).toHaveLength(1);
 });
 it("reduces regional symbol clutter without removing positions or losing last-known styling",()=>{
  const source=new Cesium.CustomDataSource(),time=Cesium.JulianDate.now();
  syncEarthEntities(source,[{...marker,heading:180,positionState:"last_known"}]);
  const entity=source.entities.getById(marker.id)!;
  const scale=entity.billboard!.scaleByDistance!.getValue(time);
  expect(scale.nearValue).toBe(1);expect(scale.farValue).toBe(.5);expect(scale.far).toBeGreaterThan(scale.near);
  expect(entity.label!.distanceDisplayCondition!.getValue(time).far).toBe(50000);
  expect(decodeURIComponent(entity.billboard!.image!.getValue(time))).toContain('stroke-dasharray="3 2"');
  expect(entity.label!.text!.getValue(time)).toContain("LAST KNOWN");
  expect(source.entities.values).toHaveLength(1);
 });
});
