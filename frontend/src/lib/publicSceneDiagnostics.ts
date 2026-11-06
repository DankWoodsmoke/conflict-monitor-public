import * as Cesium from "cesium";
import {validCoordinates} from "./earth";

export type PublicationReceipt={batch_id:string|null;status:string;failed:boolean;received_at:number|null};
export type PublicSceneReceipts={observations:PublicationReceipt;aircraft:PublicationReceipt};
export type PositionProjection=Array<[string,number,number]>;

/** Read synchronized entities, not React inputs. Coordinates must also agree with
 * actual Cartesian anchors within 0.01 mm; this is not a ground-truth claim. */
export function readPublicEntityProjection(source:Cesium.CustomDataSource,time:Cesium.JulianDate){
 const rows:{observations:PositionProjection;aircraft:PositionProjection}={observations:[],aircraft:[]};
 if(source.entities.values.length>7000)throw Error("Public scene exceeds diagnostic bound");
 for(const entity of source.entities.values){
  const props=entity.properties?.getValue(time),kind=props?.kind;
  if(kind!=="thermal"&&kind!=="aircraft")throw Error("Unexpected public entity kind");
  const lat=props.latitude,lon=props.longitude,position=entity.position?.getValue(time);
  if(!validCoordinates(lat,lon)||!position||props.displayHeightMeters!==0||props.displayMode!=="surface_projection"||
     !Number.isFinite(position.x)||!Number.isFinite(position.y)||!Number.isFinite(position.z)||
     Cesium.Cartesian3.distance(position,Cesium.Cartesian3.fromDegrees(lon,lat,0))>0.00001)throw Error("Public entity anchor differs from its coordinates");
  rows[kind==="thermal"?"observations":"aircraft"].push([entity.id,lat,lon]);
 }
 for(const [kind,limit] of [["observations",2000],["aircraft",5000]] as const){
  if(rows[kind].length>limit)throw Error("Public dataset exceeds diagnostic bound");
  rows[kind].sort((a,b)=>a[0]<b[0]?-1:a[0]>b[0]?1:0);
 }
 return rows;
}

export async function hashPositionProjection(rows:PositionProjection){
 const bytes=new TextEncoder().encode(JSON.stringify(rows));
 return Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",bytes)),byte=>byte.toString(16).padStart(2,"0")).join("");
}

/** Called only after entity synchronization, never on animation-frame ticks. */
export async function publicSceneDiagnostic(source:Cesium.CustomDataSource,time:Cesium.JulianDate,clock:number,receipts:PublicSceneReceipts){
 const rows=readPublicEntityProjection(source,time);
 const [observations,aircraft]=await Promise.all([hashPositionProjection(rows.observations),hashPositionProjection(rows.aircraft)]);
 return {version:1,state:"synchronized",clock,observations:{...receipts.observations,count:rows.observations.length,sha256:observations},
  aircraft:{...receipts.aircraft,count:rows.aircraft.length,sha256:aircraft}};
}
