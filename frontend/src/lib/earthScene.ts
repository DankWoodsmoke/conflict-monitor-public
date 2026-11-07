import * as Cesium from "cesium";
import type {EarthMarker} from "./earth";
import {earthSymbol,earthSymbolImage,earthMarkerLabel,hasReportedDirection,isAreaReference} from "./earthSymbols";

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
      const symbol=earthSymbol(marker),directional=(symbol==="aircraft"||symbol==="vessel")&&hasReportedDirection(marker);
      entity.properties=new Cesium.PropertyBag({kind:marker.kind,symbol,identifier:marker.identifier||marker.id,directionShown:directional,locationDisplay:isAreaReference(marker)?"area_reference":"supplied_position",latitude:marker.lat,longitude:marker.lon,displayHeightMeters:marker.height,displayMode:"surface_projection",positionState:marker.positionState||"not_applicable"});
      const track=marker.kind==="aircraft"||marker.kind==="vessel";
      const size=track?36:marker.kind==="thermal"?24:28;
      // Screen annotations sit on exact surface anchors. Terrain depth must not cut
      // their silhouettes; applyEarthHorizon owns independent far-hemisphere masking.
      entity.billboard=new Cesium.BillboardGraphics({image:earthSymbolImage(symbol,color,historical,isAreaReference(marker)),width:size,height:size,scaleByDistance:new Cesium.NearFarScalar(50000,1,3000000,track?2/3:.5),heightReference:Cesium.HeightReference.CLAMP_TO_GROUND,disableDepthTestDistance:Number.POSITIVE_INFINITY,rotation:directional?-Cesium.Math.toRadians(marker.heading!):0,alignedAxis:directional?Cesium.Cartesian3.UNIT_Z:Cesium.Cartesian3.ZERO});
      entity.point=undefined;
      const label=earthMarkerLabel(marker);
      const labelRange=marker.kind==="reference"?180000:marker.kind==="aircraft"||marker.kind==="vessel"?50000:550000;
      entity.label=new Cesium.LabelGraphics({text:label.length>80?`${label.slice(0,77)}…`:label,font:"12px sans-serif",fillColor:Cesium.Color.fromCssColorString(color),outlineColor:Cesium.Color.fromCssColorString("#07121d"),outlineWidth:3,style:Cesium.LabelStyle.FILL_AND_OUTLINE,pixelOffset:new Cesium.Cartesian2(11,-8),heightReference:Cesium.HeightReference.CLAMP_TO_GROUND,disableDepthTestDistance:Number.POSITIVE_INFINITY,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,labelRange)});
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
