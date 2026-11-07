import {act} from "react";
import {createRoot,type Root} from "react-dom/client";
import {beforeEach,afterEach,describe,it,expect,vi} from "vitest";
import {LiveFeed} from "./LiveFeed";
import {TimelineScrubber} from "./TimelineScrubber";
import {buildShowcase} from "../lib/showcase";
import {assessedSeverity,severityLabel,hasCriticalAlertStyle} from "../lib/events";
import type {ConflictEvent} from "../types/event";
import {briefScore,briefLevel} from "../lib/brief";

let host:HTMLDivElement,root:Root;
beforeEach(()=>{(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;vi.useFakeTimers();host=document.createElement("div");document.body.append(host);root=createRoot(host);});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.useRealTimers();});
function modelReport():ConflictEvent{
 const e={...buildShowcase(Date.now()).events[0],synthetic:false,severity:9,summary:"Source-bound model estimate"};
 return {...e,evidence:{...e.evidence!,assessment:{status:"model_estimate",event_type:e.event_type,severity:9,severity_label:"critical",basis:"source_bound_model_extraction",review_status:"unreviewed",confirmed:false,critical_alert_eligible:false,model:"fixture-model",rubric_version:"fixture-v1",source_sha256:"a".repeat(64),limitations:[]}}};
}
describe("assessment provenance and alert semantics",()=>{
 it("does not promote old escalation metadata to current critical or wartime levels",()=>{
  expect(briefScore({escalation_score:99,escalation_level:"WARTIME"})).toBeNull();
  expect(briefLevel({escalation_score:99,escalation_level:"WARTIME"})).toBe("UNASSESSED");
  expect(briefScore({synthetic:true,escalation_score:99})).toBe(99);
  expect(briefLevel({synthetic:true,escalation_level:"CRITICAL"})).toBe("CRITICAL");
 });
 it("keeps old 9/10 values visible without ranking or critical styling",async()=>{
  const e={...modelReport(),evidence:undefined,summary:"Old metadata",classification_status:"legacy_unknown" as const};
  expect(assessedSeverity(e)).toBeNull();expect(severityLabel(e)).toBe("LEGACY 9/10 · UNREVIEWED");expect(hasCriticalAlertStyle(e)).toBe(false);
  await act(async()=>root.render(<LiveFeed events={[e]}/>));
  expect(host.querySelector('.intel-card-crit')).toBeNull();expect(host.textContent).toContain("LEGACY 9/10 · UNREVIEWED");
 });
 it("can rank a source-bound model estimate while keeping critical alerts unqualified",async()=>{
  const model=modelReport(),old={...model,id:2,summary:"Legacy excluded by threshold",evidence:undefined},raw={...model,id:3,severity:0,summary:"Unscored source",classification_status:"not_requested" as const};
  expect(assessedSeverity(model)).toBe(9);expect(hasCriticalAlertStyle(model)).toBe(false);
  await act(async()=>root.render(<LiveFeed events={[model,old,raw]}/>));
  expect(host.querySelectorAll('.intel-card-crit')).toHaveLength(0);
  await act(async()=>[...host.querySelectorAll('button')].find(b=>b.textContent==='FILTER')!.click());
  await act(async()=>host.querySelector<HTMLButtonElement>('[aria-label="Scored severity 9/10 and above"]')!.click());
  expect(host.querySelectorAll('.intel-card')).toHaveLength(1);expect(host.textContent).toContain("MODEL 9/10 · UNREVIEWED");
  expect(host.textContent).not.toContain(old.summary);expect(host.textContent).not.toContain(raw.summary);
 });
 it("keeps coverage and filter disclosures mutually exclusive without resetting the selected threshold",async()=>{
  await act(async()=>root.render(<LiveFeed events={[modelReport()]}/>));
  const coverage=host.querySelector<HTMLDetailsElement>('.assessment-coverage')!;
  await act(async()=>{coverage.open=true;coverage.dispatchEvent(new Event('toggle'));});
  await act(async()=>[...host.querySelectorAll('button')].find(b=>b.textContent==='FILTER')!.click());
  expect(coverage.open).toBe(false);expect(host.querySelector('.report-filter-panel')).not.toBeNull();
  await act(async()=>host.querySelector<HTMLButtonElement>('[aria-label="Scored severity 9/10 and above"]')!.click());
  await act(async()=>{coverage.open=true;coverage.dispatchEvent(new Event('toggle'));});
  expect(host.querySelector('.report-filter-panel')).toBeNull();expect(host.textContent).toContain('FILTER (1)');
  expect(host.querySelectorAll('.intel-card')).toHaveLength(1);
 });
 it.each([NaN,Infinity,-1,11,9.5])("rejects invalid rating %s",score=>{
  expect(assessedSeverity({...modelReport(),severity:score})).toBeNull();
 });
 it.each(["source_sha256","model","rubric_version"])("does not rank a model estimate missing %s",key=>{
  const e=modelReport();(e.evidence!.assessment! as any)[key]="";expect(assessedSeverity(e)).toBeNull();
 });
 it("does not count an invalid coordinate or legacy sentinel as a mapped report",async()=>{
  const e=modelReport();const invalid=[{...e,lat:-25,lon:80},{...e,id:2,lat:NaN},{...e,id:3,lon:181},{...e,id:4,lat:null,lon:null}];
  await act(async()=>root.render(<TimelineScrubber allEvents={invalid} timeRange={null} activeRange={null} onRangeChange={()=>{}}/>));
  expect(host.querySelector('.timeline-stats')?.textContent).toContain("0 / 0 MAPPED REPORTS");
 });
 it("includes six in high estimates while excluding legacy scores from the tally",async()=>{
  const e=modelReport();e.severity=6;e.evidence!.assessment!.severity=6;e.evidence!.assessment!.severity_label="high";
  await act(async()=>root.render(<TimelineScrubber allEvents={[e,{...e,id:2,severity:10,evidence:undefined}]} timeRange={null} activeRange={null} onRangeChange={()=>{}}/>));
  expect(host.querySelector('.timeline-stats')?.textContent).toContain("1 HIGH ESTIMATES");
 });
});
