/**
 * Report-only position admission. Coordinate usability is not verification.
 *
 * The recovered application used this exact pair for unresolved reports. It is
 * geographically valid and must remain usable by independent track/search
 * coordinate policies; only report plotting/citation links exclude it here.
 */
export const LEGACY_UNKNOWN_REPORT_POSITION = Object.freeze({lat: -25, lon: 80});

export type ReportPositionInput = {lat?: unknown; lon?: unknown};
export type UsableReportPosition = {lat: number; lon: number};

export function hasUsableReportCoordinates<T extends ReportPositionInput>(
  report: T | null | undefined,
): report is T & UsableReportPosition {
  if (report == null) return false;
  const {lat, lon} = report;
  return typeof lat === "number" && typeof lon === "number" &&
    Number.isFinite(lat) && Number.isFinite(lon) &&
    lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180 &&
    !(lat === LEGACY_UNKNOWN_REPORT_POSITION.lat && lon === LEGACY_UNKNOWN_REPORT_POSITION.lon);
}
