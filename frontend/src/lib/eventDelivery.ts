import type { ConflictEvent } from "../types/event";

export interface DeliveryCursor {
  epoch: string;
  after: string;
}

interface DeliveryChange {
  offset: string;
  event_id: number;
  action: "upsert" | "delete";
  event: ConflictEvent | null;
}

interface DeliveryPage {
  changes: DeliveryChange[];
  next_after: string;
  has_more: boolean;
}

const MAX_OFFSET = 9_223_372_036_854_775_807n;
const validEpoch = (value: unknown): value is string =>
  typeof value === "string" && /^[A-Za-z0-9_-]{1,128}$/.test(value);
const validOffset = (value: unknown): value is string =>
  typeof value === "string" && /^(0|[1-9]\d{0,18})$/.test(value) && BigInt(value) <= MAX_OFFSET;
const validId = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value > 0;
const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export function validReport(value: unknown): value is ConflictEvent {
  return record(value) && validId(value.id) &&
    typeof value.timestamp === "string" && Number.isFinite(Date.parse(value.timestamp));
}

export function readDeliveryBaseline(value: unknown, limit: number): DeliveryCursor & {events: ConflictEvent[]} {
  if (!record(value) || !validEpoch(value.epoch) || !validOffset(value.after) ||
      !Array.isArray(value.events) || value.events.length > limit || !value.events.every(validReport) ||
      new Set(value.events.map(event => event.id)).size !== value.events.length) {
    throw new Error("Invalid delivery baseline");
  }
  return { epoch: value.epoch, after: value.after, events: value.events };
}

export function readDeliveryPage(value: unknown, cursor: DeliveryCursor, limit: number): DeliveryPage {
  if (!record(value) || value.epoch !== cursor.epoch || !Array.isArray(value.changes) ||
      value.changes.length > limit || typeof value.has_more !== "boolean" ||
      (value.has_more && !value.changes.length)) {
    throw new Error("Invalid delivery page");
  }
  const changes: DeliveryChange[] = [];
  let previous = cursor.after;
  for (const change of value.changes) {
    if (!record(change) || !validOffset(change.offset) || BigInt(change.offset) <= BigInt(previous) ||
        !validId(change.event_id)) {
      throw new Error("Invalid delivery order");
    }
    const { offset, event_id, action, event } = change;
    if (action === "upsert" && validReport(event) && event.id === event_id) {
      changes.push({ offset, event_id, action, event });
    } else if (action === "delete" && event === null) {
      changes.push({ offset, event_id, action, event });
    } else {
      throw new Error("Invalid delivery change");
    }
    previous = offset;
  }
  if (value.next_after !== previous) throw new Error("Invalid delivery acknowledgement");
  return { changes, next_after: previous, has_more: value.has_more };
}

export function requiresDeliveryBaseline(value: unknown): boolean {
  if (!record(value) || !record(value.detail)) return false;
  const { code, reason } = value.detail;
  return code === "delivery_baseline_required" &&
    (reason === "epoch_changed" || reason === "cursor_expired" || reason === "cursor_ahead");
}
