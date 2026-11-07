import {describe,it,expect,vi,afterEach} from "vitest";
import {webcrypto} from "node:crypto";
import * as Cesium from "cesium";
import {syncEarthEntities} from "./earthScene";
import type {EarthMarker} from "./earth";
import {readPublicEntityProjection,publicSceneDiagnostic} from "./publicSceneDiagnostics";
const marker:EarthMarker={id:"aircraft-abc123",kind:"aircraft",name:"Test",lat:29,lon:44,height:0,color:"#ffffff",details:[]};
const receipts={observations:{batch_id:"a".repeat(64),status:"empty",failed:false,received_at:1},aircraft:{batch_id:"b".repeat(64),status:"fresh",failed:false,received_at:1}};
afterEach(()=>vi.unstubAllGlobals());
describe("public synchronized entity diagnostics",()=>{
 it("changes the digest for an updated actual anchor and records bounded receipts",async()=>{
  vi.stubGlobal("crypto",webcrypto);const source=new Cesium.CustomDataSource(),time=Cesium.JulianDate.now();
  syncEarthEntities(source,[marker]);const first=await publicSceneDiagnostic(source,time,100,receipts);
  syncEarthEntities(source,[{...marker,lat:30}]);const second=await publicSceneDiagnostic(source,time,100,receipts);
  expect(first.aircraft.count).toBe(1);expect(first.aircraft.sha256).not.toBe(second.aircraft.sha256);
  expect(second.aircraft.batch_id).toBe(receipts.aircraft.batch_id);expect(JSON.stringify(second)).not.toContain('latitude');
  syncEarthEntities(source,[]);expect((await publicSceneDiagnostic(source,time,100,{...receipts,aircraft:{...receipts.aircraft,failed:true}})).aircraft).toMatchObject({failed:true,count:0});
 });
 it("rejects a moved/stale Cartesian position even when coordinate properties look correct",()=>{
  const source=new Cesium.CustomDataSource(),time=Cesium.JulianDate.now();syncEarthEntities(source,[marker]);
  source.entities.getById(marker.id)!.position=new Cesium.ConstantPositionProperty(Cesium.Cartesian3.fromDegrees(43,29,0));
  expect(()=>readPublicEntityProjection(source,time)).toThrow(/anchor differs/);
 });
 it("rejects changed coordinate properties, missing positions and unexpected private kinds",()=>{
  const source=new Cesium.CustomDataSource(),time=Cesium.JulianDate.now();syncEarthEntities(source,[marker]);
  source.entities.getById(marker.id)!.properties!.latitude=new Cesium.ConstantProperty(28);
  expect(()=>readPublicEntityProjection(source,time)).toThrow(/anchor differs/);
  syncEarthEntities(source,[marker]);source.entities.getById(marker.id)!.position=undefined;
  expect(()=>readPublicEntityProjection(source,time)).toThrow(/anchor differs/);
  syncEarthEntities(source,[{...marker,kind:"report"}]);expect(()=>readPublicEntityProjection(source,time)).toThrow(/Unexpected public entity kind/);
 });
});
