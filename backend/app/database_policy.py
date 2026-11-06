"""Explicit database surfaces shared by bootstrap, readiness and qualification."""

PUBLIC_ROLE = "monitor_public"
PUBLIC_REPORT_TABLES = frozenset({"public_observation_batches", "public_aircraft_batches"})
# Prior exact SELECT-only reader profile, recognized only while revoking it.
LEGACY_PUBLIC_REPORT_TABLES = frozenset({"events", "event_delivery_state", "event_deliveries"})
# PostGIS exposes these to PUBLIC by default. Preserve private-reader access
# explicitly when installing the more restrictive public login.
POSTGIS_REFERENCE_TABLES = frozenset({
    ("public", "geometry_columns"), ("public", "geography_columns"), ("public", "spatial_ref_sys"),
    ("topology", "topology"), ("topology", "layer"),
    *{("tiger", name) for name in ("geocode_settings", "geocode_settings_default", "loader_platform",
        "loader_variables", "loader_lookuptables", "pagc_gaz", "pagc_lex", "pagc_rules")},
})
POSTGIS_REFERENCE_SEQUENCES = frozenset({("topology", "topology_id_seq")})
PUBLIC_BLOCKED_STORAGE_FUNCTIONS = frozenset({
    "lo_creat", "lo_create", "lo_from_bytea", "lo_import", "lo_put", "lowrite",
    "lo_unlink", "lo_truncate", "lo_truncate64",
})
