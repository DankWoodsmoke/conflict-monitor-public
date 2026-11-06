# Local analysis of a selected report

The feed and selected Earth report can expose **Analyze this report locally**.
Expanding the control checks local-tool configuration. Only its explicit analysis
button starts inference, and that operation requires the operator key.

The existing stock local Qwen extraction path proposes a conflict-topic label,
linguistic stance and literal place, actor and quantity mentions. The full source
remains inspectable; the model receives at most its first 2,500 characters. A
separate deterministic place-name review supplies exact source context. Neither
kind of place mention establishes an incident location. The result assigns no
severity, creates no critical alert, changes no Event fields and adds no markers.
These are unreviewed proposals, not factual or multilingual semantic verification.
This path does not call GOOL or a paid provider.

## Source and request binding

`POST /report-analysis/{event_id}` accepts only
`{"expected_source_sha256":"<64 lowercase hexadecimal characters>"}` with
`X-Admin-Key`. It requires a real, recent, cited raw source, up to 12,000
characters, within the configured briefing age window. Generated summaries are
not substituted for missing source text. Known Telegram sources/citations or
retained Telegram report provenance are rejected before inference; this does not
grant blanket permission to process other publishers' content.

The `202` response supplies a UUID `job_id` and
`status_url=/report-analysis/jobs/{job_id}`. Poll that exact path with the same
administrative authorization. A successful job has `status=available` and a
`result` with the frozen source, model labels, literal spans, place review,
source/excerpt hashes, model digest and prompt identity. Unicode code-point and
UTF-16 offsets identify the same literal source text.

The service checks source text, citation, publication time, canonical platform,
display-name inputs and retained report provenance before work, after inference
and when reading a completed result. Changed sources return `source_changed`;
newly restricted provenance returns `source_permission_required`, withholding
the result. Other terminal outcomes are `failed` or `cancelled`; failed work
never substitutes a prior job's output. The client also validates its selected
source and request identity and retires pending requests on selection change.

The server shares the existing local-analysis lock and runtime task. A concurrent
batch/selected analysis is rejected with `409`, rather than starting overlapping
inference. The local-call ledger records the attempt separately from paid usage.
The global batch `analysis.json` artifact is not overwritten by this path.

## Retention and deployment limits

Job results are held in process memory for at most one hour after admission,
with up to 16 records retained. Completed results may be evicted sooner when
the bounded registry fills. Restarting the API removes the registry; expired or
missing jobs return `404`. Use the existing single API process for this path;
multiple workers would require a shared job store before these results could be
routed reliably. The UI clears a result at expiry and revalidates it on reopening.
Viewing or polling never restarts inference automatically.

The input has not been permanently classified. Reports mode can still show
`unclassified`/unscored records after a useful local proposal. Source retention,
public display rights, multilingual accuracy and qualified critical alerting
remain separate concerns. An installed/configured model is not proof of a
successful current inference; bind any live-execution claim to its specific
qualification receipt.
