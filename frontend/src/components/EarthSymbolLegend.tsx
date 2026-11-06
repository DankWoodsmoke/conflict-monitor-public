import {EARTH_SYMBOLS,earthSymbolImage,type EarthSymbolId} from "../lib/earthSymbols";

const examples:Array<{symbol:EarthSymbolId;color:string;label?:string}>=[
  {symbol:"aircraft",color:"#8fd3f5"},
  {symbol:"vessel",color:"#79d6c5"},
  {symbol:"aircraft_unknown",color:"#8fd3f5"},
  {symbol:"vessel_unknown",color:"#79d6c5"},
  {symbol:"ground",color:"#8fd3f5"},
  {symbol:"obstacle",color:"#8fd3f5"},
  {symbol:"airstrike",color:"#f27c74",label:"Airstrike / explosion claim · unverified"},
  {symbol:"military",color:"#f27c74"},
  {symbol:"thermal",color:"#f1b16e"},
  {symbol:"report",color:"#c3d6de"},
  {symbol:"diplomatic",color:"#77b9eb"},
  {symbol:"economic",color:"#dcb969"},
  {symbol:"humanitarian",color:"#91d0ad"},
  {symbol:"cyber",color:"#bf9bea"},
  {symbol:"protest",color:"#d7a5cf"},
  {symbol:"reference",color:"#adb4c4"},
  {symbol:"navigation",color:"#c7a4e8"},
];

export function EarthSymbolLegend(){
  return <details className="earth-symbol-legend">
    <summary>Symbols and identifiers</summary>
    <p>Shapes identify the stored report category or tracked object. They do not establish truth, ownership or precise impact location. These examples are a legend, not live observations.</p>
    <p>Aircraft use wings and a tail; vessels use a hull. A question badge means direction is unknown: those side-profile icons stay fixed. Track labels include Aircraft or Vessel alongside the source identifier.</p>
    <ul aria-label="Earth symbol meanings">{examples.map(({symbol,color,label})=><li key={symbol}>
      <img src={earthSymbolImage(symbol,color)} width={32} height={32} alt=""/>
      <span><strong>{label||EARTH_SYMBOLS[symbol].label}</strong><small>{EARTH_SYMBOLS[symbol].description}</small></span>
    </li>)}</ul>
    <div className="earth-symbol-history"><img src={earthSymbolImage("vessel","#9aabb8",true)} width={32} height={32} alt=""/><span>Hollow, dashed tracks are last known or recorded. They do not move between observations.</span></div>
    <div className="earth-symbol-history"><img src={earthSymbolImage("report","#c3d6de",false,true)} width={32} height={32} alt=""/><span>Bracket frame / AREA REF: city, region, country or unassessed precision. The supplied anchor is not an exact impact location; no uncertainty radius is invented.</span></div>
    <p>The burst requires both a specific airstrike/explosion label and source-reviewed asserted stance. Current live feeds do not supply that review metadata; equipment names or automatic model extraction alone remain neutral.</p>
    <p>Search by callsign, registration, ICAO address, vessel name, MMSI or available IMO. Identifiers remain visible in details even when labels are hidden at regional zoom.</p>
  </details>;
}
