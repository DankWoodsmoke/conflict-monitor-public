import * as Cesium from "cesium";
import type {EarthMarker} from "./earth";

/** Replace all changing properties for a retained ID, including source clocks and labels. */
export function syncEarthEntities(source:Cesium.CustomDataSource,markers:EarthMarker[]){
  const wanted=new Set(markers.map(marker=>marker.id));
  source.entities.suspendEvents();
  try{
    for(const entity of [...source.entities.values])if(!wanted.has(entity.id))source.entities.remove(entity);
    for(const marker of markers){
      let entity=source.entities.getById(marker.id);
      if(!entity)entity=source.entities.add({id:marker.id});
      entity.name=marker.name;
      entity.position=new Cesium.ConstantPositionProperty(Cesium.Cartesian3.fromDegrees(marker.lon,marker.lat,marker.height));
      const historical=marker.positionState==="last_known"||marker.positionState==="recorded";
      const color=historical?"#9aabb8":marker.color;
      entity.properties=new Cesium.PropertyBag({kind:marker.kind,latitude:marker.lat,longitude:marker.lon,displayHeightMeters:marker.height,displayMode:"surface_projection",positionState:marker.positionState||"not_applicable"});
      entity.point=new Cesium.PointGraphics({pixelSize:marker.kind==="report"?11:marker.kind==="thermal"?7:8,color:Cesium.Color.fromCssColorString(marker.color),outlineColor:Cesium.Color.fromCssColorString("#07121d"),outlineWidth:2,heightReference:Cesium.HeightReference.CLAMP_TO_GROUND,disableDepthTestDistance:0});
      if(marker.kind==="aircraft"||marker.kind==="vessel"){
        const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32"><circle cx="16" cy="16" r="12" fill="#07121d" stroke="${color}" stroke-width="2"${historical?' stroke-dasharray="3 2"':""}/><path d="M16 6 L23 23 L16 19 L9 23 Z" fill="${historical?"none":color}" stroke="${color}" stroke-width="1.5"/></svg>`;
        entity.billboard=new Cesium.BillboardGraphics({image:`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`,width:marker.kind==="aircraft"?23:19,height:marker.kind==="aircraft"?23:19,heightReference:Cesium.HeightReference.CLAMP_TO_GROUND,disableDepthTestDistance:0,rotation:typeof marker.heading==="number"&&Number.isFinite(marker.heading)?-Cesium.Math.toRadians(marker.heading):0,alignedAxis:Cesium.Cartesian3.UNIT_Z});
        entity.point=undefined;
      }else entity.billboard=undefined;
      const label=`${marker.positionState==="last_known"?"LAST KNOWN · ":marker.positionState==="recorded"?"RECORDED · ":""}${marker.name}`;
      entity.label=new Cesium.LabelGraphics({text:label.length>80?`${label.slice(0,77)}…`:label,font:"12px sans-serif",fillColor:Cesium.Color.fromCssColorString(color),outlineColor:Cesium.Color.fromCssColorString("#07121d"),outlineWidth:3,style:Cesium.LabelStyle.FILL_AND_OUTLINE,pixelOffset:new Cesium.Cartesian2(11,-8),heightReference:Cesium.HeightReference.CLAMP_TO_GROUND,disableDepthTestDistance:0,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,marker.kind==="reference"?180000:550000)});
      entity.ellipse=marker.radius?new Cesium.EllipseGraphics({semiMajorAxis:marker.radius,semiMinorAxis:marker.radius,material:Cesium.Color.fromCssColorString(marker.color).withAlpha(.12),heightReference:Cesium.HeightReference.CLAMP_TO_GROUND}):undefined;
    }
  }finally{source.entities.resumeEvents();}
}

/** Independent of globe.show: Google tiles may leave the far hemisphere without depth. */
export function applyEarthHorizon(source:Cesium.CustomDataSource,camera:Cesium.Cartesian3):number{
  let visible=0;
  for(const entity of source.entities.values){
    const props=entity.properties?.getValue(Cesium.JulianDate.now());
    if(!props)continue;
    // The surface footprint, not a screen overlay or an invented orbital height, owns visibility.
    const anchor=Cesium.Cartesian3.fromDegrees(props.longitude,props.latitude,0);
    entity.show=earthPointVisible(camera,anchor);if(entity.show)visible++;
  }
  return visible;
}

/** Public Cesium ray/ellipsoid intersection API; independent of the visible globe primitive. */
export function earthPointVisible(camera:Cesium.Cartesian3,point:Cesium.Cartesian3):boolean{
  const direction=Cesium.Cartesian3.subtract(point,camera,new Cesium.Cartesian3());
  const distance=Cesium.Cartesian3.magnitude(direction);if(distance<1)return true;
  Cesium.Cartesian3.normalize(direction,direction);
  const intersection=Cesium.IntersectionTests.rayEllipsoid(new Cesium.Ray(camera,direction),Cesium.Ellipsoid.WGS84);
  return !intersection||intersection.start>=distance-1;
}
