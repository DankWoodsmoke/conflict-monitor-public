/**
 * CesiumJS 1.139.1 / @cesium/engine 23.0.1 compatibility guard.
 * Upstream: https://github.com/CesiumGS/cesium/blob/1.139/packages/engine/Source/Scene/Material.js
 * Apache-2.0 source/bundle notices remain intact. Only the two instanceof checks
 * are guarded when OffscreenCanvas is absent (Windows WebKit has working WebGL2).
 * No constructor/global is fabricated. A future dependency shape must be reviewed.
 */
import {readFileSync,writeFileSync} from "node:fs";
import {createHash} from "node:crypto";
import {resolve} from "node:path";
import {fileURLToPath} from "node:url";
import assert from "node:assert/strict";

const root=fileURLToPath(new URL("../",import.meta.url));
const files=[
 {path:"node_modules/@cesium/engine/Source/Scene/Material.js",before:"5011e0ea5d0bf5b6467c03797de8a111f6aef658a6d39a83acf8b72430fbd3c1",after:"a693e34c81949728faf752456a526c479cd79cee614ea62d3b92d9b7f0943e37"},
 {path:"node_modules/cesium/Build/Cesium/Cesium.js",before:"64a3507201bf3c24f740803ccbab0fa62b708db52c26bc339c98c5f280aed5ed",after:"849926bc0cc83889a70d66e2a5a012258738e6c873d2da0da0dacd8b166a2ec7"},
 {path:"node_modules/cesium/Build/CesiumUnminified/Cesium.js",before:"857ad53acf5e90e70cb519e3c0b3c10945dc1b11c078ef69e2dcb59b67a6be91",after:"89dd1a1d4cae001318b42bae0b51544b90e6c22c55f97a502b00b546b6fd6442"},
];
const sha=value=>createHash("sha256").update(value).digest("hex");
function versions(cesium,engine){if(cesium!=="1.139.1"||engine!=="23.0.1")throw new Error("Unreviewed Cesium version; compatibility patch requires review");}
function transform(source,file){
 const hash=sha(source);if(hash===file.after)return source;
 if(hash!==file.before)throw new Error(`Unreviewed Cesium file: ${file.path}`);
 const matches=[...source.matchAll(/instanceof OffscreenCanvas/g)];
 if(matches.length!==2)throw new Error(`Unexpected guard count: ${file.path}`);
 let patched=source;
 for(const match of matches.reverse()){
   const name=source.slice(Math.max(0,match.index-80),match.index).match(/([A-Za-z_$][\w$]*) $/)?.[1];
   if(!name)throw new Error(`Unexpected guard shape: ${file.path}`);
   const start=match.index-name.length-1,end=match.index+"instanceof OffscreenCanvas".length;
   patched=patched.slice(0,start)+`(typeof OffscreenCanvas !== "undefined" && ${name} instanceof OffscreenCanvas)`+patched.slice(end);
 }
 if(sha(patched)!==file.after)throw new Error(`Patched hash mismatch: ${file.path}`);
 return patched;
}
export function patchCesium({check=false,selfTest=false}={}){
 versions(JSON.parse(readFileSync(resolve(root,"node_modules/cesium/package.json"))).version,JSON.parse(readFileSync(resolve(root,"node_modules/@cesium/engine/package.json"))).version);
 // Validate every input before changing any dependency file.
 const plan=files.map(file=>{const source=readFileSync(resolve(root,file.path),"utf8");return {file,source,patched:transform(source,file)};});
 if(selfTest){
   assert.throws(()=>versions("0.0.0","23.0.1"),/Unreviewed/);
   for(const {file,patched} of plan){assert.equal(transform(patched,file),patched);assert.throws(()=>transform(patched+"\nunknown-change",file),/Unreviewed/);}
 }
 for(const {file,source,patched} of plan){
   if(check&&source!==patched)throw new Error(`Cesium patch missing: ${file.path}`);
   if(!check&&source!==patched)writeFileSync(resolve(root,file.path),patched);
   console.log(`${file.path} SHA256 ${file.after}`);
 }
 console.log(`Cesium OffscreenCanvas guards verified${selfTest?"; idempotence and unknown-version/file rejection passed":""}`);
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))patchCesium({check:process.argv.includes("--check"),selfTest:process.argv.includes("--self-test")});
