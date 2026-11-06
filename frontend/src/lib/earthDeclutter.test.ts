import {describe,it,expect,vi} from "vitest";
import * as Cesium from "cesium";
import {planEarthGroups,earthGroupBounds,createEarthDeclutter,EARTH_GROUP_WIDTH,EARTH_GROUP_HEIGHT,type ProjectedEarthTrack} from "./earthDeclutter";
import {syncEarthEntities} from "./earthScene";
import type {EarthMarker} from "./earth";

const track=(id:string,x:number,y:number,kind:ProjectedEarthTrack["kind"]="aircraft",state:ProjectedEarthTrack["state"]="fresh"):ProjectedEarthTrack=>({id,x,y,lat:29,lon:44,kind,state});
const intersects=(a:{x:number;y:number},aw:number,ah:number,b:{x:number;y:number},bw:number,bh:number)=>Math.abs(a.x-b.x)<(aw+bw)/2&&Math.abs(a.y-b.y)<(ah+bh)/2;
function partition(points:ProjectedEarthTrack[],width:number,height:number,pin:{x:number;y:number}|null=null){
  const result=planEarthGroups(points,width,height,pin),ids=[...result.individualIds,...result.groups.flatMap(g=>g.memberIds)];
  expect(ids.slice().sort()).toEqual(points.map(p=>p.id).sort());expect(new Set(ids).size).toBe(ids.length);
  const byId=new Map(points.map(p=>[p.id,p]));
  for(const group of result.groups){
    expect(Object.values(group.counts).reduce((a,b)=>a+b,0)).toBe(group.memberIds.length);
    expect(Object.values(group.states).reduce((a,b)=>a+b,0)).toBe(group.memberIds.length);
    expect(group.memberIds).toContain(group.anchorId);
    expect(group.screen.x-EARTH_GROUP_WIDTH/2).toBeGreaterThanOrEqual(0);expect(group.screen.x+EARTH_GROUP_WIDTH/2).toBeLessThanOrEqual(width);
    expect(group.screen.y-EARTH_GROUP_HEIGHT/2).toBeGreaterThanOrEqual(0);expect(group.screen.y+EARTH_GROUP_HEIGHT/2).toBeLessThanOrEqual(height);
    if(pin)expect(intersects(group.screen,112,64,pin,40,40)).toBe(false);
    for(const id of result.individualIds)expect(intersects(group.screen,112,64,byId.get(id)!,40,40)).toBe(false);
  }
  for(let i=0;i<result.groups.length;i++)for(let j=i+1;j<result.groups.length;j++)expect(intersects(result.groups[i].screen,112,64,result.groups[j].screen,112,64)).toBe(false);
  for(let i=0;i<result.individualIds.length;i++)for(let j=i+1;j<result.individualIds.length;j++)expect(intersects(byId.get(result.individualIds[i])!,40,40,byId.get(result.individualIds[j])!,40,40)).toBe(false);
  return result;
}

describe("screen area groups preserve source identities and display semantics",()=>{
  it.each([[320,740],[412,915],[1200,800],[1920,1080]])("preserves every mixed-domain member without badge/single/pin collisions at %sx%s",(width,height)=>{
    const points=Array.from({length:480},(_,i)=>track(`source-${i}`,8+((i*47)%Math.floor(width-16)),8+((i*79)%Math.floor(height-16)),(["aircraft","vessel","ground","obstacle"] as const)[i%4],(["fresh","last_known","recorded","unknown"] as const)[i%4]));
    const before=JSON.stringify(points),result=partition(points,width,height,{x:width/2,y:height/2});
    expect(result.groups.length).toBeGreaterThan(0);expect(result.groups.length+result.individualIds.length).toBeLessThan(480/2);
    expect(JSON.stringify(points)).toBe(before);expect(planEarthGroups(points.slice().reverse(),width,height,{x:width/2,y:height/2})).toEqual(result);
  });
  it("keeps isolated source pixels untouched, merges touching cell-edge singletons, and excludes the selected source exactly once",()=>{
    const isolated=[track("left",50,60),track("right",400,300)];expect(planEarthGroups(isolated,600,400)).toEqual({groups:[],individualIds:["left","right"]});
    const points=[track("a",127,80),track("b",129,80,"vessel"),track("c",132,81,"ground","last_known")];
    const result=partition(points,640,400,{x:128,y:80});expect(result.groups.flatMap(g=>g.memberIds).sort()).toEqual(["a","b","c"]);
    expect(result.groups.reduce((n,g)=>n+g.counts.aircraft,0)).toBe(1);expect(result.groups.reduce((n,g)=>n+g.counts.vessel,0)).toBe(1);expect(result.groups.reduce((n,g)=>n+g.counts.ground,0)).toBe(1);expect(result.groups.reduce((n,g)=>n+g.states.last_known,0)).toBe(1);
  });
  it("supports dense same-pixel tracks and a fully occupied viewport without overwriting group identities",()=>{
    const points=Array.from({length:1000},(_,i)=>track(`coincident-${i}`,160,200,i%2?"aircraft":"vessel",i%3?"last_known":"recorded"));
    const result=partition(points,320,480,{x:160,y:200});expect(result.groups).toHaveLength(1);expect(result.groups[0].memberIds).toHaveLength(1000);
    expect(planEarthGroups(points,320,480,{x:160,y:200}).groups[0].id).toBe(result.groups[0].id);
    expect(planEarthGroups(points.slice(1),320,480,{x:160,y:200}).groups[0].id).not.toBe(result.groups[0].id);
  });
  it("uses the shortest date-line interval and keeps polar latitudes unmodified",()=>{
    const bounds=earthGroupBounds([{lat:89.7,lon:179.8},{lat:89.9,lon:-179.7}]);expect(bounds.west).toBeCloseTo(179.8,10);expect(bounds.east).toBeCloseTo(-179.7,10);expect(bounds.south).toBe(89.7);expect(bounds.north).toBe(89.9);
    const one=earthGroupBounds([{lat:-89.9,lon:-180}]);expect(one).toEqual({west:-180,east:-180,south:-89.9,north:-89.9});
  });
  it("retains individual source positions in an impossibly small viewport instead of clipping a fabricated group",()=>{
    expect(planEarthGroups([track("a",10,10),track("b",11,11)],100,60)).toEqual({groups:[],individualIds:["a","b"]});
  });
  it("keeps mobile badges outside reserved controls and preserves all IDs if overlays leave no usable slots",()=>{
    const points=Array.from({length:320},(_,i)=>track(`source-${i}`,10+(i*37)%300,10+(i*53)%720)),reserved=[{x:0,y:0,width:320,height:400},{x:0,y:680,width:320,height:60}];
    const result=planEarthGroups(points,320,740,null,reserved),ids=[...result.individualIds,...result.groups.flatMap(g=>g.memberIds)];
    expect(ids.sort()).toEqual(points.map(p=>p.id).sort());expect(new Set(ids).size).toBe(320);expect(result.groups.length).toBeGreaterThan(0);
    for(const group of result.groups)for(const r of reserved)expect(intersects(group.screen,112,64,{x:r.x+r.width/2,y:r.y+r.height/2},r.width,r.height)).toBe(false);
    const blocked=planEarthGroups(points,320,740,null,[{x:0,y:0,width:320,height:740}]);expect(blocked.groups).toHaveLength(0);expect(blocked.individualIds).toEqual(points.map(p=>p.id).sort());
  });

});

function viewerFixture(){
  const scene:any={canvas:{clientWidth:1200,clientHeight:800},drawingBufferWidth:1200,drawingBufferHeight:800,mode:Cesium.SceneMode.SCENE3D,frameState:{mode:Cesium.SceneMode.SCENE3D},ellipsoid:Cesium.Ellipsoid.WGS84,mapProjection:new Cesium.GeographicProjection(),postRender:new Cesium.Event(),requestRender:()=>{}};
  const camera=new Cesium.Camera(scene);scene.camera=camera;camera.setView({destination:Cesium.Cartesian3.fromDegrees(44,29,2100000),orientation:{heading:0,pitch:-Math.PI/2,roll:0}});
  return{scene,camera,clock:new Cesium.Clock()} as unknown as Cesium.Viewer;
}
describe("real Cesium projection and source-entity ownership",()=>{
  it("requests one settling frame after replacement graphics, then stays idle and removes its pending listener on destroy",()=>{
    const viewer=viewerFixture(),request=vi.fn();viewer.scene.requestRender=request;
    const source=new Cesium.CustomDataSource(),controller=createEarthDeclutter(viewer);
    const markers:EarthMarker[]=[0,1].map(i=>({id:`source-${i}`,kind:"aircraft",name:"Fixture",lat:29,lon:44+i*.001,height:0,color:"#aabbcc",positionState:"fresh",details:[]}));
    syncEarthEntities(source,markers);controller.sync(source,markers,null,true);expect(request).not.toHaveBeenCalled();viewer.scene.postRender.raiseEvent();expect(request).toHaveBeenCalledTimes(1);
    controller.sync(source,markers,null,true);viewer.scene.postRender.raiseEvent();expect(request).toHaveBeenCalledTimes(1);
    syncEarthEntities(source,markers);controller.sync(source,markers,null,true);expect(source.entities.values.every(e=>e.billboard!.show!.getValue(viewer.clock.currentTime)===false)).toBe(true);viewer.scene.postRender.raiseEvent();expect(request).toHaveBeenCalledTimes(2);
    syncEarthEntities(source,markers);controller.sync(source,markers,null,true);controller.destroy();viewer.scene.postRender.raiseEvent();expect(request).toHaveBeenCalledTimes(2);
  });
  it("conserves current near-side tracks, exempts selection, restores disabled markers and never rewrites source positions",()=>{
    const viewer=viewerFixture(),source=new Cesium.CustomDataSource(),controller=createEarthDeclutter(viewer);
    const marker=(id:string,lat:number,lon:number,kind:EarthMarker["kind"]="aircraft"):EarthMarker=>({id,kind,name:id,lat,lon,height:0,color:"#aabbcc",positionState:"last_known",details:[]});
    const markers=[...Array.from({length:240},(_,i)=>marker(`near-${i}`,29+(i%20)*.03,44+Math.floor(i/20)*.03,i%2?"aircraft":"vessel")),marker("far",-29,-136),marker("report",29,44,"report")];
    syncEarthEntities(source,markers);const time=viewer.clock.currentTime,before=source.entities.values.map(e=>[e.id,Cesium.Cartesian3.clone(e.position!.getValue(time)!)]);
    const result=controller.sync(source,markers,"near-0",true);expect(result.visibleIds).toHaveLength(240);expect(result.visibleIds).not.toContain("report");expect(result.visibleIds).not.toContain("far");expect(result.individualIds).toContain("near-0");
    expect(result.groups.flatMap(g=>g.memberIds)).not.toContain("near-0");expect(result.groups.reduce((n,g)=>n+g.memberIds.length,0)+result.individualIds.length).toBe(240);
    expect(source.entities.getById("far")!.show).toBe(false);expect(source.entities.getById("near-0")!.billboard!.show?.getValue(time)??true).toBe(true);
    expect(controller.sync(source,markers,"near-0",true).signature).toBe(result.signature);
    const disabled=controller.sync(source,markers,null,false);expect(disabled.groups).toHaveLength(0);expect(disabled.individualIds).toHaveLength(240);
    for(const [id,position] of before)expect(source.entities.getById(id as string)!.position!.getValue(time)).toEqual(position);
    for(const entity of source.entities.values)expect(entity.billboard!.show?.getValue(time)??true).toBe(true);
    controller.destroy();expect(()=>controller.sync(source,markers,null,true)).toThrow('destroyed');
  });
});
