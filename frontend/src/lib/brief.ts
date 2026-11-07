export function briefScore(brief:any):number|null{
 // No live calibrated escalation index is currently qualified. Legacy numbers
 // remain provenance metadata, not active conflict-state measurements.
 if(brief?.synthetic!==true)return null;
 const score=brief?.escalation_score;
 return typeof score==="number"&&Number.isFinite(score)&&score>=0&&score<=100?score:null;
}
export function briefLevel(brief:any):string{
 return brief?.synthetic===true&&["STABLE","ELEVATED","ESCALATING","CRITICAL","WARTIME"].includes(brief.escalation_level)?brief.escalation_level:"UNASSESSED";
}
export function briefIndexLabel(brief:any):string{
 const score=briefScore(brief);return score===null?"UNASSESSED":`${score}/100`;
}
export function isSourceDigest(brief:any):boolean{
 return brief?.trigger==="source_digest"||["source_digest","attributed_source_digest"].includes(brief?.analysis_status);
}
export function isArchivedSourceDigest(brief: {analysis_status?: string} | null | undefined): boolean {
  return brief?.analysis_status === "legacy_source_digest_unqualified";
}
