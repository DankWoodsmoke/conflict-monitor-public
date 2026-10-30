import {useEffect,useRef} from "react";

/** A foreground overlay owns Escape and focus until it closes. */
export function useModalFocus(open:boolean,onClose:()=>void){
 const ref=useRef<HTMLDivElement>(null),closeRef=useRef(onClose);closeRef.current=onClose;
 useEffect(()=>{
  if(!open)return;
  const prior=document.activeElement as HTMLElement|null,dialog=ref.current;
  const covered:Element[]=[];let branch:Element|null=dialog;
  while(branch?.parentElement){for(const sibling of Array.from(branch.parentElement.children)){if(sibling!==branch&&!sibling.hasAttribute("inert")){sibling.setAttribute("inert","");covered.push(sibling);}}if(branch.parentElement===document.body)break;branch=branch.parentElement;}
  const controls=()=>Array.from(dialog?.querySelectorAll<HTMLElement>('button,a[href],summary,input,select,textarea,video[controls],[tabindex="0"]')||[]).filter(node=>{
   if(node.matches(':disabled')||node.closest('[hidden],[inert]')||!node.getClientRects().length)return false;
   // Closed details can retain layout rectangles for descendants that cannot
   // receive focus. Only their own direct summary remains in the tab order.
   for(let parent=node.parentElement;parent;parent=parent.parentElement){
    if(parent.tagName==='DETAILS'&&!parent.hasAttribute('open')){
     const summary=Array.from(parent.children).find(child=>child.tagName==='SUMMARY');
     if(!summary?.contains(node))return false;
    }
   }
   if(typeof node.checkVisibility==='function'&&!node.checkVisibility())return false;
   const style=getComputedStyle(node);return style.visibility!=='hidden'&&style.display!=='none';
  });
  (dialog?.querySelector<HTMLElement>('[data-modal-close]')||dialog)?.focus();
  const keyboard=(event:KeyboardEvent)=>{
   if(event.key==="Escape"){event.preventDefault();event.stopImmediatePropagation();closeRef.current();return;}
   if(event.key!=="Tab")return;const all=controls(),first=all[0],last=all[all.length-1];
   if(!first){event.preventDefault();dialog?.focus();return;}
   if(event.shiftKey&&(document.activeElement===first||!dialog?.contains(document.activeElement))){event.preventDefault();last.focus();}
   else if(!event.shiftKey&&(document.activeElement===last||!dialog?.contains(document.activeElement))){event.preventDefault();first.focus();}
  };
  window.addEventListener("keydown",keyboard,true);return()=>{window.removeEventListener("keydown",keyboard,true);covered.forEach(node=>node.removeAttribute("inert"));if(prior?.isConnected)prior.focus();};
 },[open]);
 return ref;
}
