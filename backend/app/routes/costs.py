"""GET /costs — live cost transparency endpoint for truthevades.com."""
from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import text

from app.db import async_session

router = APIRouter(prefix="/costs", tags=["costs"])

def _float(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except Exception:
        return 0.0


@router.get("/summary")
async def cost_summary():
    """
    Returns true average cost per day since launch, blending:
      - first_month_override  : actual all-in spend for the build+launch phase
      - fixed monthly costs   : server, X API, speech API (prorated daily)
      - tracked Claude API    : logged per-call in usage_log after go-live

    avg_per_day = total_spend_since_launch / days_since_launch
    """
    async with async_session() as session:
        # ── Config ───────────────────────────────────────────────────────────
        cfg_rows = await session.execute(text("SELECT key, value FROM cost_config"))
        cfg = {row.key: row.value for row in cfg_rows}

        now = datetime.now(timezone.utc)

        launch_dt = datetime.fromisoformat(
            cfg.get("launch_date", "2026-03-09")
        ).replace(tzinfo=timezone.utc)
        days_running = max(1, (now - launch_dt).days)

        # The "first month" covers launch → first_month_end_date at all-in cost
        override_total  = _float(cfg.get("first_month_override", "0"))
        override_end_str = cfg.get("first_month_end_date", "2026-04-01")
        override_end_dt = datetime.fromisoformat(override_end_str).replace(tzinfo=timezone.utc)

        # ── Fixed ongoing monthly costs (post-override period) ────────────────
        monthly_fixed = (
            _float(cfg.get("monthly_hetzner"))
            + _float(cfg.get("monthly_speech_api"))
            + _float(cfg.get("monthly_x_api"))
            + _float(cfg.get("monthly_claude_sub"))
        )
        daily_fixed = monthly_fixed / 30.0

        # Days after the override window ended (may be 0 if still in first month)
        post_override_days = max(0, (now - override_end_dt).days)
        post_override_fixed = post_override_days * daily_fixed

        # ── Tracked Claude API costs (only accrued after logging was added) ───
        total_tracked = await session.execute(text(
            "SELECT SUM(cost_usd) FROM usage_log"
        ))
        cost_value = total_tracked.scalar()
        total_claude_usd = _float(cost_value)

        # Per-operation breakdown
        op_rows = await session.execute(text(
            "SELECT operation, model, "
            "  SUM(input_tokens) as input_tokens, "
            "  SUM(output_tokens) as output_tokens, "
            "  SUM(cost_usd) as cost_usd, "
            "  COUNT(*) as calls "
            "FROM usage_log "
            "GROUP BY operation, model "
            "ORDER BY cost_usd DESC"
        ))
        ops = [
            {
                "operation": row.operation,
                "model":     row.model,
                "calls":     int(row.calls),
                "input_tokens":  int(row.input_tokens),
                "output_tokens": int(row.output_tokens),
                "cost_usd":  round(_float(row.cost_usd), 4) if row.cost_usd is not None else None,
            }
            for row in op_rows
        ]

        # ── True total spend & average ────────────────────────────────────────
        # first_month_override covers everything (Claude API, X API, Hetzner,
        # speech, subscriptions) for the build + launch phase.
        # After that: prorated fixed + live-tracked Claude API.
        total_spend = override_total + post_override_fixed + total_claude_usd
        avg_per_day = round(total_spend / days_running, 2)
        avg_per_month = round(avg_per_day * 30, 2)

        # ── Last 7 days trend (tracked API only) ─────────────────────────────
        trend_rows = await session.execute(text(
            "SELECT DATE(created_at) as day, SUM(cost_usd) as cost_usd "
            "FROM usage_log "
            "WHERE created_at >= NOW() - INTERVAL '7 days' "
            "GROUP BY day ORDER BY day"
        ))
        trend = [
            {"date": str(row.day), "claude_api_usd": round(_float(row.cost_usd), 4) if row.cost_usd is not None else None}
            for row in trend_rows
        ]

        return {
            "measurement_status": "configured_estimate_partial" if cfg else "unconfigured",
            "billing_completeness": "unverified; null-cost calls and untracked charges may exist",
            "pricing_verified": False,
            "avg_per_day_usd":   avg_per_day if cfg else None,
            "avg_per_month_usd": avg_per_month if cfg else None,
            "days_running":      days_running,
            "launch_date":       cfg.get("launch_date"),
            "total_spend_usd":   round(total_spend, 2) if cfg else None,
            "breakdown": {
                "first_month": {
                    "total":    override_total,
                    "end_date": override_end_str,
                    "note":     "All-in: build phase, APIs, subscriptions, hosting",
                },
                "fixed_monthly": {
                    "server_hosting": _float(cfg.get("monthly_hetzner")),
                    "speech_api":     _float(cfg.get("monthly_speech_api")),
                    "x_api":          _float(cfg.get("monthly_x_api")),
                    "claude_sub":     _float(cfg.get("monthly_claude_sub")),
                    "total":          round(monthly_fixed, 2),
                    "per_day":        round(daily_fixed, 2),
                },
                "claude_api_tracked": {
                    "total_usd":  round(total_claude_usd, 4) if cost_value is not None else None,
                    "operations": ops,
                },
            },
            "trend_7d": trend,
            "currency": "USD",
        }
