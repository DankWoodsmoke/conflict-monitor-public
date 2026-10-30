import {describe,expect,it} from "vitest";
import {recentReports,sourceFamilyCounts,sourceAge,reportImageryLinks} from "./reportPresentation";
import {buildShowcase} from "./showcase";
const clock=Date.parse("2026-10-29T06:00:00Z"),base=buildShowcase(clock).events[0];
describe("source presentation boundaries",()=>{
 it("orders recent source records by source time and excludes invalid, future and expired timestamps without scoring them",()=>{
  const rows=[{...base,id:1,timestamp:new Date(clock-3600000).toISOString(),severity:10},{...base,id:2,timestamp:new Date(clock-1000).toISOString(),severity:0},{...base,id:3,timestamp:"invalid"},{...base,id:4,timestamp:new Date(clock+1000).toISOString()},{...base,id:5,timestamp:new Date(clock-5*3600000).toISOString()}];
  expect(recentReports(rows,clock,4).map(e=>e.id)).toEqual([2,1]);expect(rows[1].severity).toBe(0);
 });
 it("accounts for every loaded source family without calling sensor or unknown records RSS",()=>{
  const rows=["telegram","rss_x_fixture","x_fixture","rss_fixture","satellite_firms","unknown"].map((source,id)=>({...base,id,source,event_type:"unclassified" as const}));
  expect(sourceFamilyCounts(rows)).toEqual({telegram:1,x:2,rss:1,sensor:1,other:1});
 });
 it.each([[0,0],[-33.9,151.2],[90,-180]])("retains valid zero and signed imagery coordinates (%s,%s)",(lat,lon)=>{
  const links=reportImageryLinks({...base,lat,lon});expect(links.google).toContain(`${lat.toFixed(5)},${lon.toFixed(5)}`);expect(links.worldview).toContain("&t=");expect(links.copernicus).toContain(`lat=${lat.toFixed(4)}`);
 });
 it("rejects invalid coordinates and leaves a bad acquisition date unknown rather than guessing today",()=>{
  expect(reportImageryLinks({...base,lat:91,lon:0})).toEqual({google:null,worldview:null,copernicus:null});
  expect(reportImageryLinks({...base,lat:-25,lon:80})).toEqual({google:null,worldview:null,copernicus:null});
  const links=reportImageryLinks({...base,lat:0,lon:0,timestamp:"invalid"});expect(links.google).toBeTruthy();expect(links.worldview).toBeNull();
 });
 it("never prints a negative or NaN source age",()=>{expect(sourceAge("invalid",clock)).toBe("Time unknown");expect(sourceAge(new Date(clock+1).toISOString(),clock)).toBe("Future source time");expect(sourceAge(new Date(clock-60000).toISOString(),clock)).toBe("1m");});
});
