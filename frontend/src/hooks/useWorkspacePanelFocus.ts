import {useEffect,useLayoutEffect,useRef} from "react";
import type {ViewMode} from "../lib/workspace";

/** Panel transitions own focus; data refreshes and camera updates do not. */
export function useWorkspacePanelFocus(mode:ViewMode,onClose:()=>void){
  const panelRef=useRef<HTMLElement>(null),stageRef=useRef<HTMLDivElement>(null);
  const openerRef=useRef<HTMLElement|null>(null),previousMode=useRef<ViewMode>("earth");
  const closeRef=useRef(onClose);closeRef.current=onClose;
  useLayoutEffect(()=>{
    const prior=previousMode.current;previousMode.current=mode;
    if(mode!=="earth"){
      const active=document.activeElement as HTMLElement|null;
      if(active&&active!==document.body&&!panelRef.current?.contains(active))openerRef.current=active;
      panelRef.current?.querySelector<HTMLButtonElement>('button[data-panel-close]')?.focus();
    }else if(prior!=="earth"){
      const target=openerRef.current?.isConnected?openerRef.current:document.querySelector<HTMLButtonElement>('nav[aria-label="Workspace views"] button');
      target?.focus();openerRef.current=null;
    }
  },[mode]);
  useEffect(()=>{
    if(mode==="earth")return;
    const key=(event:KeyboardEvent)=>{
      if(event.key==="Escape"&&!event.defaultPrevented&&!document.querySelector('[role="dialog"]')){event.preventDefault();closeRef.current();}
    };
    window.addEventListener("keydown",key);return()=>window.removeEventListener("keydown",key);
  },[mode]);
  return {panelRef,stageRef};
}
