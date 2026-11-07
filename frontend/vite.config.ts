import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import cesium from "vite-plugin-cesium";
import {createHash} from "node:crypto";
import {readFileSync,readdirSync} from "node:fs";
import {dirname,join,relative} from "node:path";
import {fileURLToPath} from "node:url";

const root=dirname(fileURLToPath(import.meta.url));
function sourceFiles(folder:string):string[]{return readdirSync(folder,{withFileTypes:true}).flatMap(entry=>entry.isDirectory()?sourceFiles(join(folder,entry.name)):[join(folder,entry.name)]);}
// Reproducible across Windows/Linux; no paths, timestamps, credentials or Git state enter the bundle.
const sourceHash=createHash("sha256");
for(const file of [...sourceFiles(join(root,"src")),...sourceFiles(join(root,"tools")),...sourceFiles(join(root,"public")),...['package.json','package-lock.json','vite.config.ts','tsconfig.json'].map(name=>join(root,name))].sort((a,b)=>relative(root,a).replaceAll('\\','/').localeCompare(relative(root,b).replaceAll('\\','/'),'en'))){
  sourceHash.update(relative(root,file).replaceAll('\\','/')+'\0').update(readFileSync(file)).update('\0');
}
const buildId=sourceHash.digest("hex");

export default defineConfig({
  worker: { format: "es" },
  build: { target: "esnext" },
  define:{__APP_BUILD_ID__:JSON.stringify(buildId.slice(0,12))},
  plugins: [react(), cesium(),{name:"inspectable-build-identity",generateBundle(){this.emitFile({type:"asset",fileName:"build.json",source:JSON.stringify({build_id:buildId.slice(0,12),frontend_source_sha256:buildId,scope:"frontend/src, frontend/tools, frontend/public and frontend package/build configuration"})+"\n"});}}],
  server: {
    host: "127.0.0.1",
    port: 5173,
    allowedHosts: ["localhost"],
    // Polling required for Docker volumes on Windows (WSL2 inotify doesn't propagate)
    watch: {
      usePolling: true,
      interval: 1000,
    },
    proxy: {
      // Preserve the page host so the backend can verify same-origin WebSockets,
      // exactly as the production nginx proxy does. Do not rewrite Origin.
      "/api": { target: process.env.API_PROXY_TARGET || "http://127.0.0.1:8000", changeOrigin: false, ws: true, rewrite: path => path.replace(/^\/api/, "") },
      // Proxy adsb.lol V2 API to avoid CORS issues
      "/adsb-api": {
        target: "https://api.adsb.lol",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/adsb-api/, ""),
        secure: true,
      },
    },
  },
});
