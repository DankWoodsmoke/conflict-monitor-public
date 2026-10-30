#!/bin/bash
set -e
# Preserve the upstream image's core, topology and Tiger extension profile.
for db in template_postgis "$POSTGRES_DB"; do
    if [ "$db" = template_postgis ]; then
        psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres -c 'CREATE DATABASE template_postgis IS_TEMPLATE true;'
    fi
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" <<'SQL'
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;
CREATE EXTENSION IF NOT EXISTS postgis_tiger_geocoder;
SQL
done
