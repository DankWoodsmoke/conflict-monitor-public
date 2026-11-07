import {describe,it,expect} from "vitest";
import * as Cesium from "cesium";
import {renderToStaticMarkup} from "react-dom/server";
import {earthMarkers,type EarthMarker} from "./earth";
import {syncEarthEntities,applyEarthHorizon} from "./earthScene";
import {EARTH_SYMBOLS,earthSymbol,earthSymbolImage,earthMarkerLabel,earthMarkerSearchText,isAreaReference} from "./earthSymbols";
import {EarthSymbolLegend} from "../components/EarthSymbolLegend";
import {LiveFeed} from "../components/LiveFeed";
import {buildShowcase} from "./showcase";
import type {ConflictEvent} from "../types/event";

const now=Date.parse("2026-10-30T12:00:00Z"),fixture=buildShowcase(now);
const event:ConflictEvent={...fixture.events[0],id:42,lat:25,lon:55,classification_status:"extracted"};
const base={events:[] as ConflictEvent[],aircraft:[],vessels:[],hotspots:[],navigation:[],clock:now};
const report=(changes:Partial<ConflictEvent>={}):EarthMarker=>earthMarkers({...base,events:[{...event,...changes}]}).find(row=>row.kind==="report")!;

describe("source-bound Earth symbols",()=>{
  it("keeps feed category badges neutral for denied, unknown and asserted military claims",()=>{
    const events:ConflictEvent[]=["denied","unknown","asserted"].map((stance,i)=>({...event,id:42+i,timestamp:new Date().toISOString(),summary:`Synthetic ${stance} claim`,military_subtype:"airstrike",claim_stance:stance as ConflictEvent["claim_stance"],claim_stance_basis:"source_review"}));
    const host=document.createElement("div");host.innerHTML=renderToStaticMarkup(<LiveFeed events={events}/>);
    const cards=[...host.querySelectorAll(".intel-card")];expect(cards).toHaveLength(3);
    for(const card of cards){expect(card.textContent).toContain("🛡 MILITARY");expect(card.textContent).not.toContain("💥");}
  });
  it("uses distinct actual billboards for aircraft and vessels without changing their source positions",()=>{
    const aircraft={...fixture.aircraft[0],icao24:"abc123",heading:90,observed_at:new Date(now).toISOString()};
    const vessel={...fixture.vessels[0],mmsi:"123456789",heading:90,heading_basis:"true_heading",observed_at:new Date(now).toISOString()};
    const rows=earthMarkers({...base,aircraft:[aircraft],vessels:[vessel]}).filter(row=>["aircraft","vessel"].includes(row.kind));
    const source=new Cesium.CustomDataSource(),time=Cesium.JulianDate.now();syncEarthEntities(source,rows);
    const ac=source.entities.getById("aircraft-abc123")!,ship=source.entities.getById("vessel-123456789")!;
    expect(ac.billboard!.image!.getValue(time)).not.toBe(ship.billboard!.image!.getValue(time));
    expect(ac.properties!.getValue(time).symbol).toBe("aircraft");expect(ship.properties!.getValue(time).symbol).toBe("vessel");
    for(const [entity,row] of [[ac,rows[0]],[ship,rows[1]]] as const){
      const position=Cesium.Cartographic.fromCartesian(entity.position!.getValue(time)!);
      expect(Cesium.Math.toDegrees(position.latitude)).toBeCloseTo(row.lat,8);expect(Cesium.Math.toDegrees(position.longitude)).toBeCloseTo(row.lon,8);
      expect(position.height).toBeCloseTo(0,6);expect(entity.billboard!.disableDepthTestDistance!.getValue(time)).toBe(Number.POSITIVE_INFINITY);
      expect(entity.billboard!.heightReference!.getValue(time)).toBe(Cesium.HeightReference.CLAMP_TO_GROUND);
    }
    expect(applyEarthHorizon(source,Cesium.Cartesian3.fromDegrees(-125,-25,3000000))).toBe(0);
  });

  it("identifies aircraft and vessels by their source layer even when names suggest the other kind",()=>{
    const aircraft={...fixture.aircraft[0],icao24:"abc123",callsign:"BOAT",heading:null,observed_at:new Date(now).toISOString()};
    const vessel={...fixture.vessels[0],mmsi:"123456789",name:"PLANE",heading:null,observed_at:new Date(now).toISOString()};
    const markers=earthMarkers({...base,aircraft:[aircraft],vessels:[vessel]}).filter(m=>m.kind==="aircraft"||m.kind==="vessel");
    const source=new Cesium.CustomDataSource();syncEarthEntities(source,markers);const time=Cesium.JulianDate.now();
    expect(markers.map(earthSymbol)).toEqual(["aircraft_unknown","vessel_unknown"]);
    expect(markers.map(earthMarkerLabel)).toEqual(["ICAO abc123 · Aircraft · BOAT","MMSI 123456789 · Vessel · PLANE"]);
    for(const entity of source.entities.values){expect(entity.properties!.getValue(time).directionShown).toBe(false);expect(entity.billboard!.rotation!.getValue(time)).toBe(0);expect(entity.billboard!.alignedAxis!.getValue(time)).toEqual(Cesium.Cartesian3.ZERO);}
    const aircraftImage=source.entities.getById("aircraft-abc123")!.billboard!.image!.getValue(time),vesselImage=source.entities.getById("vessel-123456789")!.billboard!.image!.getValue(time);
    expect(aircraftImage).not.toBe(vesselImage);
    for(const marker of markers){const monochrome=earthSymbolImage(earthSymbol(marker),"#c3d6de"),hollow=earthSymbolImage(earthSymbol(marker),"#c3d6de",true);expect(monochrome).not.toBe(hollow);expect(earthMarkerLabel({...marker,positionState:"recorded"})).toMatch(/^RECORDED · /);}
    expect(earthSymbolImage("aircraft_unknown","#c3d6de")).not.toBe(earthSymbolImage("vessel_unknown","#c3d6de"));
  });

  it("keeps source identifiers first and explicitly names reported ground categories rather than aircraft",()=>{
    for(const [category,label] of [["C2","Ground emitter"],["C3","Obstruction"]]){
      const marker=earthMarkers({...base,aircraft:[{...fixture.aircraft[0],icao24:"~894f5d",category,callsign:"SYNTHETIC",observed_at:new Date(now).toISOString()}]}).find(m=>m.kind==="aircraft")!;
      expect(earthMarkerLabel(marker)).toBe(`Non-ICAO address ~894f5d · ${label} · SYNTHETIC`);
    }
  });

  it("keeps track glyphs at least 24 CSS pixels across the full distance scale for recognition",()=>{
    const observed_at=new Date(now).toISOString();
    const markers=earthMarkers({...base,aircraft:[{...fixture.aircraft[0],icao24:"abc123",observed_at},{...fixture.aircraft[0],icao24:"~abcdef",category:"C2",observed_at}],vessels:[{...fixture.vessels[0],observed_at}]}).filter(m=>m.kind==="aircraft"||m.kind==="vessel");
    const source=new Cesium.CustomDataSource();syncEarthEntities(source,markers);const time=Cesium.JulianDate.now();
    expect(source.entities.values).toHaveLength(3);
    for(const entity of source.entities.values){
      const billboard=entity.billboard!,width=billboard.width!.getValue(time),height=billboard.height!.getValue(time),scale=billboard.scaleByDistance!.getValue(time);
      expect(width).toBe(height);
      // The interpolated scale stays between its endpoint values, and clamps outside them.
      expect(width*Math.min(scale.nearValue,scale.farValue)).toBeGreaterThanOrEqual(24);
      expect(width*Math.max(scale.nearValue,scale.farValue)).toBeLessThanOrEqual(36);
    }
  });

  it.each(["airstrike","explosion"])("shows a burst only for explicit extracted %s metadata, not text guesses",military_subtype=>{
    const reviewed={claim_stance:"asserted",claim_stance_basis:"source_review"} as const;
    expect(earthSymbol(report({military_subtype,...reviewed}))).toBe(military_subtype);
    expect(earthSymbol(report({military_subtype}))).toBe("military");
    expect(earthSymbol(report({military_subtype,claim_stance:"asserted"}))).toBe("military");
    expect(earthSymbol(report({military_subtype,claim_stance:"asserted",claim_stance_basis:"unreviewed_extraction"}))).toBe("military");
    for(const claim_stance of ["denied","questioned","quoted","unknown"] as const)expect(earthSymbol(report({military_subtype,...reviewed,claim_stance}))).toBe("military");
    for(const classification_status of [undefined,"legacy_unknown","invalid","unavailable","not_requested"] as const){
      expect(["airstrike","explosion"]).not.toContain(earthSymbol(report({military_subtype,...reviewed,classification_status})));
    }
    expect(earthSymbol(report({event_type:"unclassified",military_subtype,summary:"An explosion and airstrike were denied"}))).toBe("report");
    expect(earthSymbol(report({military_subtype:"",summary:"Airstrike planned; explosion denied"}))).toBe("military");
  });

  it.each(["missile","drone","naval","artillery","ground","interception","rocket","mortar","sabotage","assassination","AIRSTRIKE"," airstrike "])("does not turn %s equipment/category metadata into an impact",military_subtype=>{
    expect(earthSymbol(report({military_subtype}))).toBe("military");
  });

  it("keeps sensor observations distinct from explosion claims and renders every supported stored category",()=>{
    const thermal=earthMarkers({...base,hotspots:[{lat:25,lon:55,ts:new Date(now).toISOString(),frp:900,conf:99}]}).find(row=>row.kind==="thermal")!;
    expect(earthSymbol(thermal)).toBe("thermal");
    expect(earthSymbolImage(earthSymbol(thermal),thermal.color)).not.toBe(earthSymbolImage("explosion",thermal.color));
    for(const event_type of ["military","diplomatic","economic","cyber","humanitarian","protest"] as const)expect(earthSymbol(report({event_type,military_subtype:""}))).toBe(event_type);
    expect(earthSymbol(report({event_type:"thermal_anomaly",military_subtype:"airstrike"}))).toBe("thermal");
  });

  it("updates corrected semantics and IDs on a retained entity without an old strike glyph surviving",()=>{
    const source=new Cesium.CustomDataSource(),time=Cesium.JulianDate.now();syncEarthEntities(source,[report({military_subtype:"airstrike",claim_stance:"asserted",claim_stance_basis:"source_review"})]);
    const entity=source.entities.getById("report-42")!,oldImage=entity.billboard!.image!.getValue(time);
    syncEarthEntities(source,[report({military_subtype:"airstrike",claim_stance:"denied",claim_stance_basis:"source_review"})]);
    expect(source.entities.getById("report-42")).toBe(entity);expect(entity.properties!.getValue(time).symbol).toBe("military");
    expect(entity.billboard!.image!.getValue(time)).not.toBe(oldImage);
    syncEarthEntities(source,[report({event_type:"unclassified",classification_status:"not_requested",military_subtype:"airstrike"})]);
    expect(source.entities.getById("report-42")).toBe(entity);expect(entity.properties!.getValue(time).symbol).toBe("report");
    expect(entity.billboard!.image!.getValue(time)).not.toBe(oldImage);expect(entity.point).toBeUndefined();
    expect(entity.properties!.getValue(time).identifier).toBe("Report #42");
  });

  it.each([undefined,"unknown","city","region","country"] as const)("marks %s precision as a reference anchor without inventing an error radius or an impact point",geolocation_precision=>{
    const marker=report({geolocation_precision,military_subtype:"airstrike",claim_stance:"asserted",claim_stance_basis:"source_review"}),source=new Cesium.CustomDataSource(),time=Cesium.JulianDate.now();syncEarthEntities(source,[marker]);
    const entity=source.entities.getById(marker.id)!;
    expect(isAreaReference(marker)).toBe(true);expect(entity.properties!.getValue(time).locationDisplay).toBe("area_reference");
    expect(entity.label!.text!.getValue(time)).toContain("AREA REF");expect(entity.ellipse).toBeUndefined();
    expect(marker.details).toContainEqual(["Location use","Area/reference anchor; no exact impact location established"]);
    const site=report({geolocation_precision:"site",military_subtype:"airstrike",claim_stance:"asserted",claim_stance_basis:"source_review"});syncEarthEntities(source,[site]);
    expect(isAreaReference(site)).toBe(false);expect(entity.label!.text!.getValue(time)).not.toContain("AREA REF");
    expect(entity.position!.getValue(time)).toEqual(Cesium.Cartesian3.fromDegrees(marker.lon,marker.lat,0));
    expect(entity.billboard!.image!.getValue(time)).not.toBe(earthSymbolImage("airstrike",marker.color,false,true));
    const pixel=report({geolocation_precision:"sensor_pixel",event_type:"thermal_anomaly"});
    expect(isAreaReference(pixel)).toBe(false);expect(pixel.details).toContainEqual(["Location use","Sensor pixel center; not an exact impact location"]);
  });

  it("finds named tracks by stable and secondary identifiers with explicit missing-value handling",()=>{
    const aircraft={...fixture.aircraft[0],callsign:"  ",registration:"N123AB",icao24:"a1b2c3",type:"A320",observed_at:new Date(now).toISOString()};
    const vessel={...fixture.vessels[0],name:"HARBOR ONE",mmsi:"123456789",callsign:"SHIP7",imo:1234567,ship_type_name:"Cargo",observed_at:new Date(now).toISOString()};
    const rows=earthMarkers({...base,aircraft:[aircraft],vessels:[vessel]});
    const ac=rows.find(row=>row.kind==="aircraft")!,ship=rows.find(row=>row.kind==="vessel")!;
    expect(ac.name).toBe("N123AB");expect(ac.details).toContainEqual(["Callsign","Unknown"]);
    for(const identifier of ["n123ab","a1b2c3","a320"])expect(earthMarkerSearchText(ac)).toContain(identifier);
    for(const identifier of ["harbor one","123456789","ship7","1234567"])expect(earthMarkerSearchText(ship)).toContain(identifier);
    expect(ship.details).toContainEqual(["Reported vessel type","Cargo"]);
    const missing=earthMarkers({...base,vessels:[{...vessel,imo:0}]}).find(row=>row.kind==="vessel")!;
    expect(missing.details).toContainEqual(["IMO","Unknown"]);expect(missing.searchTerms).not.toContain("Unknown");
    const source=new Cesium.CustomDataSource();syncEarthEntities(source,[{...ship,name:"A".repeat(200)}]);
    expect(source.entities.values[0].label!.text!.getValue(Cesium.JulianDate.now())).toContain("MMSI 123456789");
  });

  it.each([
    ["894F5D","ICAO"],["a1B2c3","ICAO"],["~894F5D","Non-ICAO address"],["~abcdef","Non-ICAO address"],
    ["demo00","Source ID"],["abc1234","Source ID"],["~abc12","Source ID"],[" 894F5D ","Source ID"],
  ])("labels provider address %s as %s without rewriting its identity or position",(rawId,label)=>{
    const aircraft={...fixture.aircraft[0],icao24:rawId,callsign:"SYNTHETIC IDENTIFIER CHECK",observed_at:new Date(now).toISOString()};
    const marker=earthMarkers({...base,aircraft:[aircraft]}).find(row=>row.kind==="aircraft")!;
    expect(marker.identifier).toBe(`${label} ${rawId}`);expect(marker.details).toContainEqual([label,rawId]);
    expect(marker.id).toBe(`aircraft-${rawId}`);expect(marker.searchTerms).toContain(rawId);
    expect(earthMarkerSearchText(marker)).toContain(rawId.toLowerCase());expect(aircraft.icao24).toBe(rawId);
    expect([marker.lat,marker.lon,marker.height]).toEqual([aircraft.lat,aircraft.lon,0]);
    if(label!=="ICAO")expect(marker.details.some(([name])=>name==="ICAO")).toBe(false);
    const source=new Cesium.CustomDataSource();syncEarthEntities(source,[marker]);const entity=source.entities.getById(`aircraft-${rawId}`)!;
    expect(entity.label!.text!.getValue(Cesium.JulianDate.now())).toContain(`${label} ${rawId}`);
    syncEarthEntities(source,[{...marker,name:"CORRECTED CALLSIGN"}]);expect(source.entities.getById(`aircraft-${rawId}`)).toBe(entity);
  });

  it("never inserts source text or arbitrary colors into icon markup",()=>{
    const unsafe=report({summary:'<script>alert(1)</script>',military_subtype:'airstrike"/><image href="https://outside.invalid"/>'});
    const image=earthSymbolImage(earthSymbol(unsafe),'red" onload="alert(1)');
    const doc=new DOMParser().parseFromString(decodeURIComponent(image.split(",")[1]),"image/svg+xml");
    expect(doc.querySelector("parsererror,script,image,foreignObject")).toBeNull();expect(doc.querySelector("[onload],[onclick]")).toBeNull();
    expect(doc.documentElement.tagName).toBe("svg");expect(doc.documentElement.textContent).not.toContain("alert");
    for(const id of Object.keys(EARTH_SYMBOLS) as Array<keyof typeof EARTH_SYMBOLS>){
      const svg=new DOMParser().parseFromString(decodeURIComponent(earthSymbolImage(id,"#aabbcc").split(",")[1]),"image/svg+xml");
      expect(svg.querySelector("parsererror")).toBeNull();
    }
  });

  it.each([["A0","emitter_unknown"],["B0","emitter_unknown"],["C0","emitter_unknown"],["C1","ground"],["C2","ground"],["C3","obstacle"]])("uses only reported %s category for the neutral %s glyph",(category,symbol)=>{
    const aircraft={...fixture.aircraft[0],icao24:"~894f5d",callsign:"SYNTHETIC",category,heading:36.56,on_ground:true,observed_at:new Date(now-60000).toISOString()};
    const marker=earthMarkers({...base,aircraft:[aircraft]}).find(row=>row.kind==="aircraft")!;
    expect(marker.kind).toBe("aircraft");expect(marker.positionState).toBe("last_known");expect(marker.emitterCategory).toBe(category);expect(earthSymbol(marker)).toBe(symbol);
    expect(marker.details.find(([key])=>key==="Reported emitter category")?.[1]).toMatch(new RegExp(`^${category} · `));
    if(["A0","B0","C0"].includes(category)){
      expect(earthMarkerLabel(marker)).toContain("ADS-B emitter · type unspecified");
      expect(earthMarkerLabel(marker)).not.toMatch(/Aircraft|Ground emitter|Obstruction/);
      expect(marker.details).toContainEqual(["Reported emitter category",`${category} · No emitter category information`]);
      expect(earthSymbolImage(earthSymbol(marker),marker.color)).not.toBe(earthSymbolImage("ground",marker.color));
      expect(earthSymbolImage(earthSymbol(marker),marker.color)).not.toBe(earthSymbolImage("aircraft",marker.color));
    }
    const source=new Cesium.CustomDataSource();syncEarthEntities(source,[marker]);const entity=source.entities.getById("aircraft-~894f5d")!,time=Cesium.JulianDate.now();
    expect(entity.properties!.getValue(time).directionShown).toBe(false);expect(entity.billboard!.rotation!.getValue(time)).toBe(0);expect(entity.billboard!.alignedAxis!.getValue(time)).toEqual(Cesium.Cartesian3.ZERO);
    expect(entity.position!.getValue(time)).toEqual(Cesium.Cartesian3.fromDegrees(aircraft.lon,aircraft.lat,0));
    expect(decodeURIComponent(entity.billboard!.image!.getValue(time))).toContain('stroke-dasharray="3 2"');
    expect(applyEarthHorizon(source,Cesium.Cartesian3.fromDegrees(aircraft.lon,aircraft.lat,2000000))).toBe(1);
    expect(applyEarthHorizon(source,Cesium.Cartesian3.fromDegrees(aircraft.lon-180,-aircraft.lat,2000000))).toBe(0);
    for(const other of [undefined,"","A3","C4","C2 "]){
      const unclassified=earthMarkers({...base,aircraft:[{...aircraft,category:other,callsign:"SECRTY02",aircraft_category:"ground"}]}).find(row=>row.kind==="aircraft")!;
      expect(earthSymbol(unclassified)).toBe("aircraft");
    }
  });

  it.each(["toString","valueOf","__proto__"])("keeps unexpected emitter category %s raw without inherited object properties",category=>{
    const marker=earthMarkers({...base,aircraft:[{...fixture.aircraft[0],category,observed_at:new Date(now).toISOString()}]}).find(row=>row.kind==="aircraft")!;
    expect(marker.details).toContainEqual(["Reported emitter category",category]);expect(earthSymbol(marker)).toBe("aircraft");
  });

  it("provides a native expandable text legend with decorative icons and explicit interpretation limits",()=>{
    const host=document.createElement("div");host.innerHTML=renderToStaticMarkup(<EarthSymbolLegend/>);
    expect(host.querySelector("details:not([open]) > summary")?.textContent).toBe("Symbols and identifiers");
    expect(host.querySelectorAll('ul[aria-label="Earth symbol meanings"] li')).toHaveLength(18);
    expect([...host.querySelectorAll("img")].every(img=>img.alt===""&&img.src.startsWith("data:image/svg+xml"))).toBe(true);
    expect(host.textContent).toContain("not live observations");expect(host.textContent).toContain("not a verified impact");expect(host.textContent).toContain("direction unknown");
    expect(host.textContent).toContain("Dashed borders mark last-known or recorded tracks");
    expect(host.textContent).toContain("Bracket frame / AREA REF");
  });
});
