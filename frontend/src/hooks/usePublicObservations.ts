import {API_BASE} from "../lib/runtime";
import type {ThermalObservation} from "../lib/earth";
import {validPublicObservations} from "../lib/publicData";
import {usePublicationPoll} from "./usePublicationPoll";

export type PublicObservations={status:string;last_attempt_status:string;published_at:string|null;batch_id:string|null;
 source_rows?:number;regional_rows?:number;eligible_count:number;displayed_count:number;filtered_rows?:number;
 minimum_frp_mw:number;hotspots:ThermalObservation[];citation_url:string;disclaimer_url:string;attribution:string;download_url?:string|null};

export function usePublicObservations(enabled:boolean){
 const result=usePublicationPoll(`${API_BASE}/publication/observations`,60000,enabled,validPublicObservations);
 return {...result,hotspots:result.failed?[]:result.data?.hotspots??[]};
}
