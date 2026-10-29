import { nowMs } from "../lib/clock";
import { hasMultipleReports } from "../utils/verification";
/**
 * SignalPanel — replaces EscalationGauge
 *
 * Shows three factual dimensions of the current event stream, with no
 * editorial interpretation baked in:
 *
 *   1. Frequency sparkline — event volume per hour, last 24 h
 *      Lets the analyst see activity rhythms and surges without
 *      labelling them "ELEVATED" or "CRITICAL".
 *
 *   2. Event-type composition bar — Military / Diplomatic / Economic / Cyber
 *      Factual breakdown of what kinds of events are being reported.
 *
 *   3. Data-quality stats
 *      • MULTI-SRC  — % of events with multiple source records; independence unassessed
 *                     (the real confidence signal; more is more reliable)
 *      • SOURCES    — distinct channels contributing to current window
 *      • EVENTS     — raw count
 */

import { useMemo } from "react";
import type { ConflictEvent } from "../types/event";

const SPARKLINE_HOURS = 24;
const BAR_COUNT = 24;

const TYPE_COLORS: Record<string, string> = {
  military:   "var(--accent-red)",
  diplomatic: "var(--accent-blue)",
  economic:   "var(--accent-yellow)",
  cyber:      "var(--accent-purple)",
  humanitarian: "var(--accent-green)",
  protest:    "#a0a0c0",
};

const TYPE_LABELS: Record<string, string> = {
  military:   "MIL",
  diplomatic: "DIP",
  economic:   "ECO",
  cyber:      "CYB",
  humanitarian: "HUM",
  protest:    "PRO",
};

interface SignalPanelProps {
  events: ConflictEvent[];
}

export function SignalPanel({ events }: SignalPanelProps) {
  const { buckets, maxBucket, typeCounts, multiConfirmed, sourceCount } = useMemo(() => {
    const now = nowMs();
    const buckets = new Array(BAR_COUNT).fill(0);
    const typeCounts: Record<string, number> = {};
    let multiConfirmed = 0;
    const sources = new Set<string>();

    for (const e of events) {
      // Sparkline — bucket into last-24h hourly slots
      const hoursAgo = (now - new Date(e.timestamp).getTime()) / 3_600_000;
      if (hoursAgo >= 0 && hoursAgo < SPARKLINE_HOURS) {
        const slot = BAR_COUNT - 1 - Math.floor(hoursAgo);
        if (slot >= 0) buckets[slot]++;
      }

      // Type counts (all events in current filter window)
      const t = e.event_type ?? "unclassified";
      typeCounts[t] = (typeCounts[t] ?? 0) + 1;

      // Multi-source confirmation
      if (hasMultipleReports(e)) multiConfirmed++;

      // Active sources
      if (e.channel_name) sources.add(e.channel_name);
    }

    return {
      buckets,
      maxBucket: Math.max(...buckets, 1),
      typeCounts,
      multiConfirmed,
      sourceCount: sources.size,
    };
  }, [events]);

  const total = events.length;
  const confirmPct = total > 0 ? Math.round((multiConfirmed / total) * 100) : 0;

  // Color of the multi-src stat — purely a data quality indicator
  const confirmColor =
    confirmPct >= 50
      ? "var(--accent-green)"
      : confirmPct >= 20
      ? "var(--accent-yellow)"
      : "var(--text-secondary)";

  // Peak hour label for tooltip
  const peakIdx = buckets.indexOf(Math.max(...buckets));
  const peakHoursAgo = BAR_COUNT - 1 - peakIdx;

  const typeEntries = Object.entries(typeCounts).sort((a, b) => b[1] - a[1]);

  return (
    <div
      className="panel"
      style={{
        display: "flex",
        flexDirection: "column",
        padding: "12px 14px",
        height: "100%",
        gap: 10,
        boxShadow: "0 0 1px var(--border-glow)",
      }}
    >
      {/* ── Header ── */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexShrink: 0,
        }}
      >
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            letterSpacing: 2,
            color: "var(--text-secondary)",
            textTransform: "uppercase",
          }}
        >
          Signal Activity
        </span>
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            color: "var(--text-secondary)",
            opacity: 0.5,
          }}
        >
          LAST {SPARKLINE_HOURS}H
        </span>
      </div>

      {/* ── Sparkline ── */}
      <div
        title={
          maxBucket > 0
            ? `Peak: ${Math.max(...buckets)} events ~${peakHoursAgo}h ago`
            : "No events in last 24h"
        }
        style={{
          display: "flex",
          alignItems: "flex-end",
          gap: 2,
          height: 52,
          flexShrink: 0,
        }}
      >
        {buckets.map((count, i) => {
          const isCurrent = i === BAR_COUNT - 1;
          const heightPx = count > 0 ? Math.max((count / maxBucket) * 48, 3) : 1;
          const opacity = count === 0 ? 0.15 : isCurrent ? 1 : 0.55 + (count / maxBucket) * 0.45;
          return (
            <div
              key={i}
              title={`${count} event${count !== 1 ? "s" : ""} · ${BAR_COUNT - 1 - i}h ago`}
              style={{
                flex: 1,
                height: heightPx,
                background: isCurrent
                  ? "var(--accent-blue)"
                  : count > 0
                  ? "rgba(88,166,255,0.7)"
                  : "var(--border)",
                borderRadius: 1,
                opacity,
                transition: "height 0.4s ease",
                boxShadow:
                  isCurrent && count > 0
                    ? "0 0 6px rgba(88,166,255,0.7)"
                    : "none",
              }}
            />
          );
        })}
      </div>

      {/* ── Event-type composition bar ── */}
      {total > 0 && (
        <div style={{ flexShrink: 0 }}>
          {/* Stacked bar */}
          <div
            style={{
              display: "flex",
              height: 5,
              borderRadius: 3,
              overflow: "hidden",
              gap: 1,
              marginBottom: 6,
            }}
          >
            {typeEntries.map(([type, count]) => {
              const pct = (count / total) * 100;
              return (
                <div
                  key={type}
                  title={`${type}: ${count} (${Math.round(pct)}%)`}
                  style={{
                    width: `${pct}%`,
                    background: TYPE_COLORS[type] ?? "var(--text-secondary)",
                    transition: "width 0.5s ease",
                    flexShrink: 0,
                  }}
                />
              );
            })}
          </div>

          {/* Type legend — compact dots */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: "3px 8px" }}>
            {typeEntries.map(([type, count]) => {
              const pct = Math.round((count / total) * 100);
              return (
                <span
                  key={type}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 4,
                    fontFamily: "var(--font-mono)",
                    fontSize: 11,
                    color: "var(--text-secondary)",
                  }}
                >
                  <span
                    style={{
                      width: 5,
                      height: 5,
                      borderRadius: "50%",
                      background: TYPE_COLORS[type] ?? "var(--text-secondary)",
                      display: "inline-block",
                      flexShrink: 0,
                    }}
                  />
                  {TYPE_LABELS[type] ?? type.slice(0, 3).toUpperCase()}{" "}
                  <span style={{ opacity: 0.7 }}>{pct}%</span>
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Stats footer ── */}
      <div
        style={{
          marginTop: "auto",
          borderTop: "1px solid var(--border)",
          paddingTop: 8,
          display: "flex",
          flexDirection: "column",
          gap: 5,
          flexShrink: 0,
        }}
      >
        {(
          [
            {
              label: "EVENTS",
              value: total.toLocaleString(),
              color: "var(--text-primary)",
              title: "Total events in current filter window",
            },
            {
              label: "MULTI-SRC",
              value: `${confirmPct}%`,
              color: confirmColor,
              title: `${multiConfirmed} of ${total} events with multiple source records; independence unassessed`,
            },
            {
              label: "SOURCES",
              value: sourceCount.toString(),
              color: "var(--accent-blue)",
              title: "Distinct reporting channels in current window",
            },
          ] as const
        ).map(({ label, value, color, title }) => (
          <div
            key={label}
            title={title}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              cursor: "default",
            }}
          >
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 11,
                letterSpacing: 1.5,
                color: "var(--text-secondary)",
              }}
            >
              {label}
            </span>
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 12,
                fontWeight: 700,
                color,
              }}
            >
              {value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
