# Location review and plotting boundaries

The location of a publisher, a quoted official, a military organization or a
destination is not automatically the location of an incident. The inherited
geocoder previously mapped bare `IDF`, `IRGC` and `CENTCOM` to headquarters,
selected Damascus from `Beirut or Damascus`, mapped `north of Tehran` to the
city center and mapped bare `Natanz` to a nuclear facility. These behaviors were
reproduced before the repair; their outputs remain in the private audit.

Automatic lookup now rejects actor aliases, ambiguous locality/facility names,
relative descriptions and partial/multiple-place sentences. Exact local names
remain **unverified reference points**. The recovered table contains no
independently qualified survey date, source identifier or accuracy radius.
A ranked external search with multiple results stays unresolved. The old
rectangular water heuristic is not used as a coordinate validator.

`GET /events/{id}/location-candidates` performs a bounded local name scan of
preserved text. It makes no model or external geocoding request and writes
nothing. Each mention carries the original source hash, exact Unicode and
UTF-16 spans, a version hash for the inherited gazetteer, and explicit unknown
incident relationship/precision. Bare ambiguous aliases have no proposed
coordinate. A 24,000-character size limit and 24-mention result limit are
reported explicitly. The primarily English name inventory is incomplete.

Matching excludes markup attributes, comments, script/style bodies and URL tokens
without rewriting the preserved source or changing offsets. Image metadata and
place names embedded in links must not become report-prose candidates. Ambiguous
or unterminated markup is suppressed conservatively and the review displays an
incomplete-coverage notice. HTML entities are not decoded into invented source
spans. This is a bounded lexical review aid, not a full browser rendering model.

The source's **Evidence & provenance → Review place mentions** control checks
the returned source hash and browser spans before displaying source context.
It does not plot, accept, publish or verify a candidate. A denial, quotation,
departure and destination remain visible in the original wording. Changed
source bytes invalidate the old review. This is a review aid, not a trained
geolocation model or an incident-location acceptance workflow.

The next qualification step is a held-out, reviewed corpus covering ambiguous
places, multiple events, denials, relative areas, multilingual spellings and
incident versus publication times. Public incident positions need explicit
provenance and a separate acceptance record. Existing raw reports and historical
sentinels must be preserved; missing coordinates must not be filled merely to
make the Earth view busier.

## External geocoding

External lookup remains disabled by default. The public Nominatim service has
an application-wide one-request-per-second maximum, requires identification,
attribution and caching, discourages recurring bulk geocoding and forbids
systematic scraping. Regularly scheduled scripts and runs longer than a day
are restricted to four requests per minute, with a single machine/thread and
cached results. It is not an unrestricted production backfill service, and the
automatic collector adapter refuses its public hostname before any request.
Choose an operator-controlled service or qualified data extract for bulk work;
do not send private source text. See the [OSMF usage policy](https://operations.osmfoundation.org/policies/nominatim/).

Search ordering is a candidate ranking, not a proof of incident location. The
adapter requests several matches and refuses ambiguity instead of taking the
first result; failed requests also consume its rate interval. Returned place
coordinates and bounds need an explicit precision/relationship review. See the
[Nominatim search reference](https://nominatim.org/release-docs/latest/api/Search/).
