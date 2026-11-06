import * as Cesium from "cesium";
import type {EarthMarker} from "./earth";
import {earthPointVisible} from "./earthScene";
import {earthSymbol} from "./earthSymbols";

export const EARTH_GROUP_WIDTH=112,EARTH_GROUP_HEIGHT=64;
const CELL_WIDTH=128,CELL_HEIGHT=80,PIN_HALF_SIZE=20;
export type EarthGroupCounts={aircraft:number;vessel:number;ground:number;obstacle:number;unknown:number};
export type EarthGroupStates={fresh:number;last_known:number;recorded:number;unknown:number};
export type EarthGroup={
  id:string;memberIds:string[];counts:EarthGroupCounts;states:EarthGroupStates;anchorId:string;
  bounds:{west:number;south:number;east:number;north:number};screen:{x:number;y:number};
};
export type EarthDeclutterResult={groups:EarthGroup[];visibleIds:string[];individualIds:string[];signature:string};
export type EarthScreenRect={x:number;y:number;width:number;height:number};
export type ProjectedEarthTrack={id:string;x:number;y:number;lat:number;lon:number;kind:keyof EarthGroupCounts;state:keyof EarthGroupStates};
type Point={x:number;y:number};
type Slot=Point&{index:number};
type WorkingGroup={members:ProjectedEarthTrack[];slot:Slot};
const emptyCounts=():EarthGroupCounts=>({aircraft:0,vessel:0,ground:0,obstacle:0,unknown:0});
const emptyStates=():EarthGroupStates=>({fresh:0,last_known:0,recorded:0,unknown:0});
const distance2=(a:Point,b:Point)=>(a.x-b.x)**2+(a.y-b.y)**2;
const overlaps=(a:Point,aw:number,ah:number,b:Point,bw:number,bh:number)=>Math.abs(a.x-b.x)<(aw+bw)/2+4&&Math.abs(a.y-b.y)<(ah+bh)/2+4;

/** A minimum circular longitude interval; west > east explicitly crosses the date line. */
export function earthGroupBounds(points:ReadonlyArray<Pick<ProjectedEarthTrack,"lat"|"lon">>):EarthGroup["bounds"]{
  if(!points.length)throw new Error("An Earth group requires source members");
  const longs=points.map(p=>((p.lon%360)+360)%360).sort((a,b)=>a-b);
  let gap=-1,index=0;
  for(let i=0;i<longs.length;i++){const next=i+1<longs.length?longs[i+1]:longs[0]+360;if(next-longs[i]>gap){gap=next-longs[i];index=i;}}
  const normalized=(n:number)=>((n+180)%360)-180;
  return{west:normalized(longs[(index+1)%longs.length]),east:normalized(longs[index]),south:Math.min(...points.map(p=>p.lat)),north:Math.max(...points.map(p=>p.lat))};
}

/** Display aggregation only: deterministic screen cells, never incident matching or coordinate averaging.
 * Source singletons keep their exact pixel position unless they collide with another symbol/badge.
 * Every badge occupies a distinct full-footprint slot; a selected source pin reserves its own space.
 */
export function planEarthGroups(input:ReadonlyArray<ProjectedEarthTrack>,width:number,height:number,selected:Point|null=null,reservedRects:ReadonlyArray<EarthScreenRect>=[]):{groups:EarthGroup[];individualIds:string[]}{
  const tracks=[...input].sort((a,b)=>a.id.localeCompare(b.id));
  if(width<CELL_WIDTH||height<CELL_HEIGHT)return{groups:[],individualIds:tracks.map(p=>p.id)};
  const columns=Math.max(1,Math.floor(width/CELL_WIDTH)),rows=Math.max(1,Math.floor(height/CELL_HEIGHT));
  const cellWidth=width/columns,cellHeight=height/rows;
  const slots:Slot[]=Array.from({length:columns*rows},(_,index)=>({index,x:(index%columns+.5)*cellWidth,y:(Math.floor(index/columns)+.5)*cellHeight}));
  const reserved=reservedRects.filter(r=>[r.x,r.y,r.width,r.height].every(Number.isFinite)&&r.width>0&&r.height>0);
  const available=new Map(slots.filter(slot=>(!selected||!overlaps(slot,EARTH_GROUP_WIDTH,EARTH_GROUP_HEIGHT,selected,PIN_HALF_SIZE*2,PIN_HALF_SIZE*2))&&!reserved.some(r=>overlaps(slot,EARTH_GROUP_WIDTH,EARTH_GROUP_HEIGHT,{x:r.x+r.width/2,y:r.y+r.height/2},r.width,r.height))).map(slot=>[slot.index,slot]));
  if(!available.size)return{groups:[],individualIds:tracks.map(p=>p.id)};
  const buckets=new Map<number,ProjectedEarthTrack[]>();
  for(const track of tracks){const col=Math.max(0,Math.min(columns-1,Math.floor(track.x/cellWidth))),row=Math.max(0,Math.min(rows-1,Math.floor(track.y/cellHeight)));const key=row*columns+col;const bucket=buckets.get(key)||[];bucket.push(track);buckets.set(key,bucket);}
  const groups:WorkingGroup[]=[],singles=new Map<string,ProjectedEarthTrack>();
  const nearestSlot=(target:Point)=>[...available.values()].sort((a,b)=>distance2(a,target)-distance2(b,target)||a.index-b.index)[0];
  const addGroup=(members:ProjectedEarthTrack[])=>{
    const target={x:members.reduce((n,p)=>n+p.x,0)/members.length,y:members.reduce((n,p)=>n+p.y,0)/members.length};
    const slot=nearestSlot(target);
    if(slot){available.delete(slot.index);groups.push({members:[...members],slot});}
    else{const nearest=[...groups].sort((a,b)=>distance2(a.slot,target)-distance2(b.slot,target)||a.slot.index-b.slot.index)[0];nearest.members.push(...members);}
  };
  for(const [,members] of [...buckets].sort(([a],[b])=>a-b))if(members.length>1)addGroup(members);else singles.set(members[0].id,members[0]);
  // Each pass removes a singleton, so dense input cannot loop indefinitely.
  let changed=true;
  while(changed){
    changed=false;
    for(const group of groups)for(const [id,single] of singles)if(overlaps(group.slot,EARTH_GROUP_WIDTH,EARTH_GROUP_HEIGHT,single,PIN_HALF_SIZE*2,PIN_HALF_SIZE*2)){group.members.push(single);singles.delete(id);changed=true;}
    const remaining=[...singles.values()];
    for(let i=0;i<remaining.length;i++){
      const first=remaining[i];if(!singles.has(first.id))continue;
      if(selected&&overlaps(first,PIN_HALF_SIZE*2,PIN_HALF_SIZE*2,selected,PIN_HALF_SIZE*2,PIN_HALF_SIZE*2)){singles.delete(first.id);addGroup([first]);changed=true;continue;}
      for(let j=i+1;j<remaining.length;j++){const second=remaining[j];if(singles.has(second.id)&&overlaps(first,PIN_HALF_SIZE*2,PIN_HALF_SIZE*2,second,PIN_HALF_SIZE*2,PIN_HALF_SIZE*2)){singles.delete(first.id);singles.delete(second.id);addGroup([first,second]);changed=true;break;}}
    }
  }
  return{groups:groups.map(({members,slot})=>{
    members.sort((a,b)=>a.id.localeCompare(b.id));const counts=emptyCounts(),states=emptyStates();for(const p of members){counts[p.kind]++;states[p.state]++;}
    const anchor=[...members].sort((a,b)=>distance2(a,slot)-distance2(b,slot)||a.id.localeCompare(b.id))[0];
    const memberIds=members.map(p=>p.id);
    // Full member identity avoids hash collisions or falsely reusing a group after its membership changes.
    return{id:`earth-area:${JSON.stringify(memberIds)}`,memberIds,counts,states,anchorId:anchor.id,bounds:earthGroupBounds(members),screen:{x:slot.x,y:slot.y}};
  }).sort((a,b)=>a.id.localeCompare(b.id)),individualIds:[...singles.keys()].sort()};
}

function setVisible(property:Cesium.BillboardGraphics|Cesium.LabelGraphics|undefined,visible:boolean,time:Cesium.JulianDate){
  if(property&&(property.show?.getValue(time)??true)!==visible){property.show=new Cesium.ConstantProperty(visible);return true;}
  return false;
}

export function createEarthDeclutter(viewer:Cesium.Viewer){
  const sourceProperties=new Map<string,{source:Cesium.CustomDataSource;id:string}>();
  let destroyed=false;
  let removeSettlingFrame:(()=>void)|undefined;
  return{
    sync(source:Cesium.CustomDataSource,markers:EarthMarker[],selectedId:string|null,enabled:boolean,reservedRects:ReadonlyArray<EarthScreenRect>=[]):EarthDeclutterResult{
      if(destroyed)throw new Error("Earth declutter controller is destroyed");
      const time=viewer.clock.currentTime,width=viewer.scene.canvas.clientWidth,height=viewer.scene.canvas.clientHeight;
      let renderChanged=false;
      const camera=viewer.camera,culling=camera.frustum.computeCullingVolume(camera.positionWC,camera.directionWC,camera.upWC);
      const visibleIds:string[]=[],projected=new Map<string,ProjectedEarthTrack>(),byId=new Map(markers.map(m=>[m.id,m]));let selected:Point|null=null;
      for(const marker of markers){
        const entity=source.entities.getById(marker.id);if(!entity)continue;
        const position=Cesium.Cartesian3.fromDegrees(marker.lon,marker.lat,0),horizon=earthPointVisible(camera.positionWC,position);if(entity.show!==horizon){entity.show=horizon;renderChanged=true;}
        sourceProperties.set(marker.id,{source,id:marker.id});
        if(!horizon||culling.computeVisibility(new Cesium.BoundingSphere(position,0))===Cesium.Intersect.OUTSIDE)continue;
        const pixel=Cesium.SceneTransforms.worldToWindowCoordinates(viewer.scene,position);
        if(!pixel||!Number.isFinite(pixel.x)||!Number.isFinite(pixel.y)||pixel.x<0||pixel.y<0||pixel.x>width||pixel.y>height)continue;
        if(marker.id===selectedId)selected=pixel;
        if(marker.kind!=="aircraft"&&marker.kind!=="vessel")continue;
        visibleIds.push(marker.id);if(marker.id===selectedId)continue;
        const symbol=earthSymbol(marker),kind:keyof EarthGroupCounts=symbol==="emitter_unknown"?"unknown":symbol==="ground"?"ground":symbol==="obstacle"?"obstacle":marker.kind;
        const state=marker.positionState&&["fresh","last_known","recorded"].includes(marker.positionState)?marker.positionState as keyof EarthGroupStates:"unknown";
        projected.set(marker.id,{id:marker.id,x:pixel.x,y:pixel.y,lat:marker.lat,lon:marker.lon,kind,state});
      }
      const plan=enabled?planEarthGroups([...projected.values()],width,height,selected,reservedRects):{groups:[],individualIds:[...projected.keys()].sort()};
      const groupedIds=new Set(plan.groups.flatMap(group=>group.memberIds));
      for(const marker of markers){const entity=source.entities.getById(marker.id);if(entity){renderChanged=setVisible(entity.billboard,!groupedIds.has(marker.id),time)||renderChanged;renderChanged=setVisible(entity.label,!groupedIds.has(marker.id),time)||renderChanged;}}
      for(const [id] of sourceProperties)if(!source.entities.getById(id))sourceProperties.delete(id);
      const individuals=visibleIds.filter(id=>!groupedIds.has(id)).sort();
      const groups=plan.groups,signature=JSON.stringify({groups:groups.map(g=>[g.id,g.counts,g.states,g.screen.x,g.screen.y]),visible:visibleIds.slice().sort(),individuals});
      // Entity visualizers update before preRender. A changed layout needs one following
      // frame to consume the changed graphics, including after a polling refresh replaces them.
      if(renderChanged&&!removeSettlingFrame)removeSettlingFrame=viewer.scene.postRender.addEventListener(()=>{removeSettlingFrame?.();removeSettlingFrame=undefined;if(!destroyed)viewer.scene.requestRender();});
      return{groups,visibleIds:visibleIds.sort(),individualIds:individuals,signature};
    },
    destroy(){
      if(destroyed)return;destroyed=true;removeSettlingFrame?.();removeSettlingFrame=undefined;
      for(const {source,id} of sourceProperties.values()){const entity=source.entities.getById(id);if(entity){entity.billboard&&(entity.billboard.show=new Cesium.ConstantProperty(true));entity.label&&(entity.label.show=new Cesium.ConstantProperty(true));}}
      sourceProperties.clear();
    },
  };
}
