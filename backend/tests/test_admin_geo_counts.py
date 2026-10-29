"""Execute the admin diagnostic's real SQL predicates over controlled rows."""
import sqlite3
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import sqlite

from app.routes.events import geo_stats


@pytest.mark.asyncio
async def test_geo_diagnostic_counts_pairs_and_ranges_and_only_excludes_exact_legacy_placeholder():
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE events (id INTEGER,lat REAL,lon REAL)")
    connection.executemany("INSERT INTO events VALUES (?,?,?)", [
        (1, 0, 0), (2, -25, 0), (3, -25, 80), (4, 31, None), (5, 91, 45), (6, None, None)])
    class Session:
        async def execute(self, query):
            # Same SQLAlchemy expression; only numeric/null predicate execution
            # uses SQLite here, not geometry or a substitute PostGIS qualification.
            statement = query.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True})
            count = connection.execute(str(statement)).fetchone()[0]
            return SimpleNamespace(scalar_one=lambda: count)
    try:
        result = await geo_stats(Session())
        assert result == {"total": 6, "geolocated": 2, "unknown_location": 4, "geo_rate": "33.3%"}
    finally:
        connection.close()
