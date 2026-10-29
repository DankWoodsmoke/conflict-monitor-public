export interface ConflictEvent {
  id: number;
  synthetic?: boolean;
  classification_status?: "extracted" | "unavailable" | "invalid" | "legacy_unknown" | "not_requested";
  geolocation_precision?: "unknown" | "country" | "region" | "city" | "site" | "sensor_pixel";
  evidence?: {
    status: "unassessed" | "reported" | "multiple_reports" | "sensor_observation";
    unique_source_count: number;
    source_networks: string[];
    independent_origin_count: number | null;
    independence_status: "unassessed";
    verification_basis: string;
    limitations: string[];
  };
  reports?: Array<Record<string, unknown>>;
  source: string;
  channel_name: string;
  raw_text: string;
  summary: string;
  event_type: "military" | "diplomatic" | "economic" | "cyber" | "humanitarian" | "protest" | "thermal_anomaly" | "unclassified";
  severity: number;
  lat: number | null;
  lon: number | null;
  timestamp: string;
  created_at: string;
  report_count?: number;
  reporting_channels?: string;
  location_name?: string;
  telegram_message_id?: number | null;
  source_url?: string;
  source_reliability?: number | null;
  military_subtype?: string;   // airstrike | missile | drone | naval | artillery | ground | assassination
  actor?: string;              // IDF | IRGC | Hezbollah | Houthi | US military | etc.
  casualties?: string;         // "3 killed, 12 injured" or empty
  anomaly_score?: number;      // 0-10, 0 = routine
  anomaly_analysis?: string;   // analyst reasoning for why this is anomalous
  confirmed_networks?: string; // legacy publisher grouping; does not establish independent origins
}

export interface EventWSMessage {
  type: "new_event";
  event: ConflictEvent;
}
