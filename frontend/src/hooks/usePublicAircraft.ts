import {API_BASE} from "../lib/runtime";
import type {Aircraft} from "./useTracking";
import {validPublicAircraft} from "../lib/publicData";
import {usePublicationPoll} from "./usePublicationPoll";

export type PublicAircraft={status:string;batch_id:string|null;published_at:string|null;aircraft:Aircraft[];download_url:string|null;
 source_records?:number;filtered_records?:number;provider_snapshot_at?:string};
export function usePublicAircraft(enabled:boolean){
 const result=usePublicationPoll(`${API_BASE}/publication/aircraft`,15000,enabled,validPublicAircraft);
 return {...result,aircraft:result.failed?[]:result.data?.aircraft??[]};
}
