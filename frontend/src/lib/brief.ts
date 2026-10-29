export function briefScore(brief:any):number|null{
 const score=brief?.escalation_score;
 return typeof score==="number"&&Number.isFinite(score)&&score>=0&&score<=100?score:null;
}
export function briefIndexLabel(brief:any):string{
 const score=briefScore(brief);return score===null?"UNASSESSED":`${score}/100`;
}
export function isSourceDigest(brief:any):boolean{
 return brief?.trigger==="source_digest"||["source_digest","attributed_source_digest"].includes(brief?.analysis_status);
}
