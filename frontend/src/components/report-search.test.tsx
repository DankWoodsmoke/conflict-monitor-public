import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LiveFeed } from "./LiveFeed";
import { useReportFilters } from "../hooks/useReportFilters";
import { buildShowcase } from "../lib/showcase";
import type { ConflictEvent } from "../types/event";

let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  vi.useFakeTimers();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});

afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  vi.useRealTimers();
});

function report(id: number, changes: Partial<ConflictEvent> = {}): ConflictEvent {
  return {
    ...buildShowcase(Date.now()).events[0],
    id, summary: `Report ${id}`, raw_text: "Original source body",
    channel_name: "publisher", location_name: "", source: "rss_fixture",
    ...changes,
  };
}

async function search(value: string) {
  const input = host.querySelector<HTMLInputElement>('[aria-label="Search loaded reports"]')!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

async function click(label: string) {
  const button = [...host.querySelectorAll("button")].find(node => node.textContent === label)!;
  expect(button).toBeDefined();
  await act(async () => button.click());
}

describe("report discovery", () => {
  it("exposes search before filters and matches trimmed full phrases in preserved text", async () => {
    const events = [report(1, { raw_text: "The vessel entered the southern harbor overnight." }), report(2)];
    await act(async () => root.render(<LiveFeed events={events} allEvents={[...events, report(3)]} />));
    expect(host.querySelector('.report-filter-panel')).toBeNull();
    expect(host.querySelector('[aria-label="Search loaded reports"]')).not.toBeNull();
    await search("  SOUTHERN HARBOR  ");
    expect([...host.querySelectorAll('.report-summary')].map(node => node.textContent)).toEqual(["Report 1"]);
    expect(host.querySelector('.report-search-coverage')?.textContent).toBe("1 of 2 loaded reports in this window");
  });

  it.each([
    ["ورد التقرير من بيروت اليوم", " بيروت "],
    ["A report from Café Square", "CAFE\u0301"],
  ])("matches Unicode source text without changing the report (%s)", async (raw_text, query) => {
    const event = report(1, { raw_text });
    await act(async () => root.render(<LiveFeed events={[event, report(2)]} />));
    await search(query);
    expect(host.querySelectorAll('.intel-card')).toHaveLength(1);
    expect(event.raw_text).toBe(raw_text);
  });

  it("treats whitespace as no search and identifies a filtered empty result", async () => {
    await act(async () => root.render(<LiveFeed events={[report(1)]} />));
    await search("   ");
    expect(host.querySelectorAll('.intel-card')).toHaveLength(1);
    expect([...host.querySelectorAll('button')].some(button => button.textContent === "FILTER")).toBe(true);
    await search("no match");
    expect(host.textContent).toContain("No reports match active filters");
    expect(host.querySelector('.report-search-coverage')?.textContent).toBe("0 of 1 loaded reports in this window");
  });

  it("clears only the query and restores search focus while preserving source filters", async () => {
    await act(async () => root.render(<LiveFeed events={[report(1), report(2, { source: "telegram" })]} />));
    await click("FILTER");
    await click("RSS");
    await search("no match");
    await act(async () => host.querySelector<HTMLButtonElement>('[aria-label="Clear report search"]')!.click());
    expect(host.querySelectorAll('.intel-card')).toHaveLength(1);
    expect(document.activeElement).toBe(host.querySelector('[aria-label="Search loaded reports"]'));
    expect(host.querySelector('[aria-label="Clear report search"]')).toBeNull();
  });

  it("retains query and source criteria when the workspace remounts a feed", async () => {
    const events = [report(1), report(2, { source: "telegram" })];
    function Workspace() {
      const filters = useReportFilters();
      const [open, setOpen] = useState(true);
      return <><button onClick={() => setOpen(value => !value)}>Switch workspace</button>
        {open && <LiveFeed events={events} filters={filters} />}</>;
    }
    await act(async () => root.render(<Workspace />));
    await search("Original source");
    await click("FILTER (1)");
    await click("RSS");
    await click("Switch workspace");
    expect(host.querySelector('.report-feed')).toBeNull();
    await click("Switch workspace");
    expect(host.querySelector<HTMLInputElement>('[aria-label="Search loaded reports"]')?.value).toBe("Original source");
    expect(host.querySelectorAll('.intel-card')).toHaveLength(1);
    expect(host.textContent).toContain("FILTER (2)");
    await click("FILTER (2)");
    await click("✕ CLEAR");
    expect(host.querySelectorAll('.intel-card')).toHaveLength(2);
  });

  it("discloses the existing render cap without claiming hidden matches are displayed", async () => {
    await act(async () => root.render(<LiveFeed events={Array.from({ length: 601 }, (_, index) => report(index + 1))} />));
    expect(host.querySelectorAll('.intel-card')).toHaveLength(600);
    expect(host.querySelector('.report-search-coverage')?.textContent).toBe("601 of 601 loaded reports in this window · first 600 displayed");
  });
});
