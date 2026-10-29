export type ViewMode="earth"|"media"|"sitrep";
/** Earlier bookmarks remain useful without retaining two competing spatial views. */
export function workspaceView(value:string|null):ViewMode{return value==="media"||value==="sitrep"?value:"earth";}
