import {describe, expect, it} from "vitest";
import {validCoordinates} from "./earth";
import {hasUsableReportCoordinates} from "./reportPosition";

describe("report position admission", () => {
  it("rejects the exact inherited unknown placeholder without expanding it into an exclusion area", () => {
    expect(hasUsableReportCoordinates({lat: -25, lon: 80})).toBe(false);
    expect(hasUsableReportCoordinates({lat: -25.00001, lon: 80})).toBe(true);
    expect(hasUsableReportCoordinates({lat: -25, lon: 80.00001})).toBe(true);
  });

  it("retains signed and zero coordinates and geographic boundaries without assigning evidentiary precision", () => {
    for (const [lat, lon] of [[0, 0], [-0, 0], [-90, -180], [90, 180], [-33.9, 151.2]]) {
      const report = {lat, lon, geolocation_precision: "unknown", classification_status: "legacy_unknown"};
      const before = {...report};
      expect(hasUsableReportCoordinates(report)).toBe(true);
      expect(report).toEqual(before);
    }
  });

  it("rejects missing, nonnumeric, nonfinite and out-of-range values rather than coercing them", () => {
    for (const report of [undefined, null, {}, {lat: null, lon: 0}, {lat: 0, lon: null},
      {lat: "0", lon: 0}, {lat: 0, lon: false}, {lat: NaN, lon: 0}, {lat: 0, lon: Infinity},
      {lat: -91, lon: 0}, {lat: 91, lon: 0}, {lat: 0, lon: -181}, {lat: 0, lon: 181}]) {
      expect(hasUsableReportCoordinates(report)).toBe(false);
    }
  });

  it("does not redefine generic coordinates used by tracking and camera search", () => {
    expect(validCoordinates(-25, 80)).toBe(true);
    expect(hasUsableReportCoordinates({lat: -25, lon: 80})).toBe(false);
  });
});
