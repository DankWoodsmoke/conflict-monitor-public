import {useCallback,useEffect,useRef,useState} from "react";
import {SHOWCASE} from "../lib/runtime";

/** Only the explicitly public, browser-restricted Maps key belongs in this response. */
export interface EarthProviderConfig {
  google_earth_enabled?:unknown;
  google_maps_browser_key?:unknown;
}

export function useEarthProvider(){
  const [googleKey,setGoogleKey]=useState<string>(()=>import.meta.env.VITE_GOOGLE_MAPS_KEY||"");
  const [googleEnabled,setGoogleEnabled]=useState(()=>new URLSearchParams(window.location.search).get("earth")==="google"||(!SHOWCASE&&!!import.meta.env.VITE_GOOGLE_MAPS_KEY));
  const manualRef=useRef(false);
  const applyManual=useCallback((key:string,enabled:boolean)=>{
    manualRef.current=true;setGoogleKey(key.trim());setGoogleEnabled(enabled);
  },[]);
  const applyServerConfig=useCallback((config:EarthProviderConfig)=>{
    if(SHOWCASE||manualRef.current||config.google_earth_enabled!==true||typeof config.google_maps_browser_key!=="string")return;
    const key=config.google_maps_browser_key.trim();
    if(key){setGoogleKey(key);setGoogleEnabled(true);}
  },[]);
  useEffect(()=>{
    const receive=(event:Event)=>{
      const detail=(event as CustomEvent).detail;
      if(typeof detail?.key==="string")applyManual(detail.key,detail.enabled===true);
    };
    window.addEventListener("cm-earth-provider",receive);
    return()=>window.removeEventListener("cm-earth-provider",receive);
  },[applyManual]);
  return {googleKey,googleEnabled,applyManual,applyServerConfig};
}
