import {defineConfig} from "@playwright/test";

export default defineConfig({
 testDir:"./e2e",testMatch:"**/*.pw.ts",fullyParallel:false,workers:1,
 timeout:45000,expect:{timeout:15000},reporter:"list",
 outputDir:"../artifacts/browser-tests",
 webServer:process.env.CM_BASE_URL?undefined:{command:"npm run preview -- --port 5188 --strictPort",url:"http://127.0.0.1:5188",reuseExistingServer:true,timeout:30000},
 use:{baseURL:process.env.CM_BASE_URL||"http://127.0.0.1:5188",channel:"chrome",
  viewport:{width:1440,height:1000},headless:true,trace:"off",video:"off",screenshot:"off",
  launchOptions:{args:["--enable-unsafe-swiftshader"]}},
});
