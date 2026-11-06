import type {EarthMarker} from "./earth";

export type EarthSymbolId="aircraft"|"aircraft_unknown"|"emitter_unknown"|"ground"|"obstacle"|"vessel"|"vessel_unknown"|"airstrike"|"explosion"|"military"|"diplomatic"|"economic"|"cyber"|"humanitarian"|"protest"|"thermal"|"reference"|"navigation"|"report";
type SymbolDefinition={label:string;description:string;path:string;detailPath?:string};
/** Fixed, application-owned artwork. Source text never becomes SVG markup. */
export const EARTH_SYMBOLS:Record<EarthSymbolId,SymbolDefinition>={
  aircraft:{label:"Aircraft position",description:"Aircraft silhouette follows the reported direction; track or heading basis may be unknown.",path:"M16 2 C17 2 18 4 18 6 L18 11 L31 20 L31 23 L18 18 L18 25 L23 29 L23 31 L16 28 L9 31 L9 29 L14 25 L14 18 L1 23 L1 20 L14 11 L14 6 C14 4 15 2 16 2 Z"},
  aircraft_unknown:{label:"Aircraft · direction unknown",description:"Fixed side-profile aircraft with a tail and wing is an identifier. Its nose does not indicate a reported travel direction.",path:"M2 17 L7 17 L4 8 L8 8 L14 17 L25 17 Q29 17 30 20 L20 22 L13 30 L9 30 L13 22 L5 22 Z"},
  emitter_unknown:{label:"ADS-B emitter · type unspecified",description:"A0, B0 and C0 provide no emitter category information. The neutral diamond does not establish an aircraft, vehicle or obstruction, and does not imply direction.",path:"M16 5 L27 16 L16 27 L5 16 Z M13 12 Q13 9 16 9 Q20 9 20 13 Q20 15 16 17 V19 M16 22 V23"},
  ground:{label:"Ground emitter · reported",description:"Explicit ADS-B category C1–C2 reports a surface vehicle. No ownership or active emergency is inferred; the icon is not directional.",path:"M7 10 H25 V23 H7 Z M4 27 H28 M11 23 V27 M21 23 V27 M11 14 H21 M11 18 H21"},
  obstacle:{label:"Obstruction · reported",description:"Explicit ADS-B category C3 reports a fixed ground or tethered obstruction. This is not an independently surveyed obstacle or directional track.",path:"M16 7 L8 27 H24 Z M11 19 H21 M9 24 H23 M16 7 V3 M12 3 H20 M4 28 H28"},
  vessel:{label:"Vessel position",description:"Pointed bow and flat stern follow the reported direction; inspect details for true heading versus course.",path:"M16 2 C21 6 24 10 24 16 L22 29 H10 L8 16 C8 10 11 6 16 2 Z M12 14 H20 V22 H12 Z"},
  vessel_unknown:{label:"Vessel · direction unknown",description:"Fixed side-profile hull and waves identify a vessel without implying a heading or sea condition.",path:"M2 18 H30 L25 26 H8 Z",detailPath:"M8 18 V11 H24 V18 M13 11 V7 H20 V11 M3 29 Q6 26 9 29 T15 29 T21 29 T27 29"},
  airstrike:{label:"Airstrike claim · unverified",description:"Explicit airstrike label with source-reviewed assertion stance; not a verified impact or location.",path:"M16 3 L19 11 L25 6 L23 14 L30 15 L23 19 L27 27 L19 23 L15 31 L13 23 L5 27 L9 19 L2 16 L10 13 L7 5 L14 10 Z"},
  explosion:{label:"Explosion claim · unverified",description:"Explicit explosion label with source-reviewed assertion stance; cause, actor and factual accuracy remain unverified.",path:"M16 3 L19 11 L25 6 L23 14 L30 15 L23 19 L27 27 L19 23 L15 31 L13 23 L5 27 L9 19 L2 16 L10 13 L7 5 L14 10 Z"},
  military:{label:"Military report",description:"Stored military category; the symbol does not assert a strike, weapon or combatant identity.",path:"M16 6 L25 10 L23 21 L16 27 L9 21 L7 10 Z M16 12 L16 19 M16 22 L16 23"},
  diplomatic:{label:"Diplomatic report",description:"Stored diplomatic category; no agreement or outcome is inferred.",path:"M7 8 L25 8 L25 21 L16 21 L10 26 L10 21 L7 21 Z M11 13 L21 13 M11 17 L18 17"},
  economic:{label:"Economic report",description:"Stored economic category; not a measured market move or forecast.",path:"M7 25 L7 19 L11 19 L11 25 Z M14 25 L14 13 L18 13 L18 25 Z M21 25 L21 7 L25 7 L25 25 Z"},
  cyber:{label:"Cyber report",description:"Stored cyber category; attribution and cause remain unverified.",path:"M10 10 L22 10 L22 22 L10 22 Z M14 14 L18 14 L18 18 L14 18 Z M13 6 L13 10 M19 6 L19 10 M13 22 L13 26 M19 22 L19 26 M6 13 L10 13 M6 19 L10 19 M22 13 L26 13 M22 19 L26 19"},
  humanitarian:{label:"Humanitarian report",description:"Stored humanitarian category; no verified aid delivery or casualty count is inferred.",path:"M12 7 L20 7 L20 12 L25 12 L25 20 L20 20 L20 25 L12 25 L12 20 L7 20 L7 12 L12 12 Z"},
  protest:{label:"Public assembly report",description:"Stored protest category; no crowd size or intent is inferred.",path:"M13 10 A3 3 0 1 0 19 10 A3 3 0 1 0 13 10 M6 13 A2 2 0 1 0 10 13 A2 2 0 1 0 6 13 M22 13 A2 2 0 1 0 26 13 A2 2 0 1 0 22 13 M11 26 V22 Q11 17 16 17 Q21 17 21 22 V26 M3 24 V21 Q3 17 8 17 Q10 17 11 19 M29 24 V21 Q29 17 24 17 Q22 17 21 19"},
  thermal:{label:"Thermal observation / report",description:"Thermal anomaly or fire report; it does not establish a strike, weapon, actor or casualties.",path:"M17 5 Q20 12 18 15 Q23 13 23 10 Q29 21 22 26 Q16 30 10 25 Q5 19 11 12 Q10 18 14 18 Q12 11 17 5 Z"},
  reference:{label:"Reference location",description:"Inherited approximate infrastructure point; source, survey date and current status are unverified.",path:"M7 8 L25 8 L25 26 L7 26 Z M12 12 L14 12 L14 15 L12 15 Z M18 12 L20 12 L20 15 L18 15 Z M12 19 L14 19 L14 22 L12 22 Z M18 19 L20 19 L20 22 L18 22 Z"},
  navigation:{label:"Navigation-quality candidate",description:"A position-quality cluster, not a confirmed interference or jamming location.",path:"M16 6 L16 10 M16 22 L16 26 M6 16 L10 16 M22 16 L26 16 M11 16 A5 5 0 1 0 21 16 A5 5 0 1 0 11 16"},
  report:{label:"Unclassified report",description:"A report with usable stored coordinates; no incident type or factual verification is inferred.",path:"M9 6 L20 6 L25 11 L25 26 L9 26 Z M20 6 L20 12 L25 12 M13 16 L21 16 M13 21 L19 21"},
};

export function hasReportedDirection(marker:Pick<EarthMarker,"heading">){
  return typeof marker.heading==="number"&&Number.isFinite(marker.heading)&&marker.heading>=0&&marker.heading<360;
}

export function earthSymbol(marker:EarthMarker):EarthSymbolId{
  if(marker.kind==="aircraft"){
    if(["A0","B0","C0"].includes(marker.emitterCategory||""))return "emitter_unknown";
    if(["C1","C2"].includes(marker.emitterCategory||""))return "ground";
    if(marker.emitterCategory==="C3")return "obstacle";
    return hasReportedDirection(marker)?"aircraft":"aircraft_unknown";
  }
  if(marker.kind==="vessel")return hasReportedDirection(marker)?"vessel":"vessel_unknown";
  if(marker.kind!=="report")return marker.kind;
  const event=marker.report;
  if(!event)return "report";
  if(event.event_type==="thermal_anomaly")return "thermal";
  if(["invalid","unavailable","not_requested"].includes(event.classification_status||""))return "report";
  // Equipment/subtype labels (missile, drone, naval, artillery) do not assert an impact.
  // Do not read summary keywords: they may be quoted, denied, historical or hypothetical.
  if(event.event_type==="military"&&event.classification_status==="extracted"&&event.claim_stance==="asserted"&&event.claim_stance_basis==="source_review"){
    if(event.military_subtype==="airstrike")return "airstrike";
    if(event.military_subtype==="explosion")return "explosion";
  }
  return ["military","diplomatic","economic","cyber","humanitarian","protest"].includes(event.event_type)?event.event_type as EarthSymbolId:"report";
}

const images=new Map<string,string>();
export function isAreaReference(marker:EarthMarker){
  return marker.kind==="report"&&marker.report?.geolocation_precision!=="site"&&marker.report?.geolocation_precision!=="sensor_pixel";
}

export function earthSymbolImage(symbol:EarthSymbolId,color:string,historical=false,areaReference=false):string{
  const safeColor=/^#[0-9a-f]{6}$/i.test(color)?color:"#c3d6de";
  const key=`${symbol}|${safeColor}|${historical}|${areaReference}`;
  const cached=images.get(key);if(cached)return cached;
  const definition=EARTH_SYMBOLS[symbol]||EARTH_SYMBOLS.report;
  const fill=!historical&&["aircraft","aircraft_unknown","vessel","vessel_unknown","airstrike","explosion","thermal","humanitarian","economic"].includes(symbol)?safeColor:"none";
  const unknown=symbol==="aircraft_unknown"||symbol==="vessel_unknown";
  const frame=areaReference?`<rect x="-2" y="-2" width="36" height="36" rx="4" fill="#07121d" fill-opacity=".94"/><path d="M6 -2 H-2 V6 M26 -2 H34 V6 M34 26 V34 H26 M6 34 H-2 V26" fill="none" stroke="${safeColor}" stroke-width="2"/>`:`<circle cx="16" cy="16" r="18" fill="#07121d" fill-opacity=".94" stroke="${safeColor}" stroke-width="1.7"${historical?' stroke-dasharray="3 2"':""}/>`;
  const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="-4 -4 40 40">${frame}<path d="${definition.path}" fill="${fill}" fill-rule="evenodd" stroke="${safeColor}" stroke-width="1.35" stroke-linejoin="round" stroke-linecap="round"/>${definition.detailPath?`<path d="${definition.detailPath}" fill="none" stroke="${safeColor}" stroke-width="1.5" stroke-linecap="round"/>`:""}${unknown?'<circle cx="27" cy="5" r="6" fill="#07121d" stroke="#d8e5ed"/><path d="M25 3 Q25 0 28 1 Q31 3 27 5 L27 6 M27 8 L27 8.1" fill="none" stroke="#d8e5ed" stroke-width="1.5" stroke-linecap="round"/>':""}</svg>`;
  const image=`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  // Palette/type variants are normally finite; bounded even for malformed external colors.
  if(images.size>=128)images.delete(images.keys().next().value!);
  images.set(key,image);return image;
}

export function earthMarkerLabel(marker:EarthMarker){
  const symbol=earthSymbol(marker);
  const kind=marker.kind==="aircraft"?(symbol==="emitter_unknown"?"ADS-B emitter · type unspecified":symbol==="ground"?"Ground emitter":symbol==="obstacle"?"Obstruction":"Aircraft"):marker.kind==="vessel"?"Vessel":"";
  const identity=[marker.identifier,kind,marker.name!==marker.identifier?marker.name:null].filter(Boolean).join(" · ");
  return `${marker.positionState==="last_known"?"LAST KNOWN · ":marker.positionState==="recorded"?"RECORDED · ":isAreaReference(marker)?"AREA REF · ":""}${identity}`;
}

export function earthMarkerSearchText(marker:EarthMarker){
  return [marker.id,marker.name,marker.identifier,...(marker.searchTerms||[]),marker.report?.location_name].filter(Boolean).join(" ").toLowerCase();
}
