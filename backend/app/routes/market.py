"""Live market data endpoint — fetches key economic indicators every 5 minutes.

Indicators are chosen specifically for Iran-Israel-US conflict relevance:
  - Brent Crude  — most sensitive to Hormuz disruption
  - WTI Crude    — US benchmark
  - Gold         — safe-haven demand spike indicator
  - VIX          — equity fear gauge (spikes on escalation)
  - USD/ILS      — Israeli Shekel stress (weakens under war pressure)
  - S&P 500      — broad market risk-off signal
  - ITA          — iShares US Defense & Aerospace ETF
  - NG=F         — Natural Gas (pipeline / energy weapon)
  - TLT          — 20yr Treasury (capital flight / rate stress)

Uses yfinance (no API key required).
"""

import asyncio
import logging
import math
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

import yfinance as yf
from fastapi import APIRouter, HTTPException, Query
from app.config import settings

router = APIRouter(prefix="/market", tags=["market"])
logger = logging.getLogger(__name__)

# ── Cache ─────────────────────────────────────────────────────────────────────
_cache: list[dict] | None = None
_cache_ts: float = 0
CACHE_TTL = 300  # 5 minutes

HIST_CACHE_TTL = 3600  # 1 hour — daily data doesn't need frequent refresh
FAILURE_COOLDOWN = 30
MAX_REFRESH_TASKS = 4

SYMBOLS = ["BZ=F", "CL=F", "GC=F", "^VIX", "ILS=X", "^GSPC", "ITA", "NG=F", "TLT"]

SYMBOL_META = {
    "BZ=F":  {"name": "BRENT",    "unit": "$/bbl",  "category": "oil",    "label": "Hormuz Risk Premium"},
    "CL=F":  {"name": "WTI",      "unit": "$/bbl",  "category": "oil",    "label": "US Energy Benchmark"},
    "GC=F":  {"name": "GOLD",     "unit": "$/oz",   "category": "metal",  "label": "Safe-Haven Demand"},
    "^VIX":  {"name": "VIX",      "unit": "",       "category": "fear",   "label": "Market Fear Index"},
    "ILS=X": {"name": "USD/ILS",  "unit": "",       "category": "fx",     "label": "Shekel Stress"},
    "^GSPC": {"name": "S&P 500",  "unit": "",       "category": "equity", "label": "Risk-Off Signal"},
    "ITA":   {"name": "DEFENSE",  "unit": "$/sh",   "category": "defense","label": "Defense Sector (ETF)"},
    "NG=F":  {"name": "NAT GAS",  "unit": "$/mmbtu","category": "energy", "label": "Energy Weapon Risk"},
    "TLT":   {"name": "T-BONDS",  "unit": "$/sh",   "category": "rates",  "label": "Capital Flight Indicator"},
}

_executor: ThreadPoolExecutor | None = None
_provider_slots = asyncio.Semaphore(2)
_provider_jobs = set()
_stopping = False


async def _run_provider(function, *args):
    """Keep at most two executor jobs, including jobs whose awaiters cancel.

    Python cannot kill an executing provider thread. Its permit is retained
    until the actual job finishes, so request timeouts cannot grow a hidden
    executor queue. Shutdown cancels pending async work and does not wait for
    uninterruptible provider I/O; process termination may still wait on threads.
    """
    global _executor
    slots = _provider_slots
    await slots.acquire()
    loop = asyncio.get_running_loop()
    try:
        # A restarted lifespan can inherit still-running threads from an old
        # loop/executor. They count against the same physical work limit.
        while sum(not job.done() for job in tuple(_provider_jobs)) >= 2:
            await asyncio.sleep(.05)
        if _stopping:
            raise RuntimeError("Market service is stopping")
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="market_provider")
        job = _executor.submit(function, *args)
    except BaseException:
        slots.release()
        raise
    _provider_jobs.add(job)
    def finished(done):
        def release():
            _provider_jobs.discard(done)
            slots.release()
        try:
            loop.call_soon_threadsafe(release)
        except RuntimeError:
            _provider_jobs.discard(done)
    job.add_done_callback(finished)
    return await asyncio.shield(asyncio.wrap_future(job, loop=loop))


def _fetch_quotes_sync() -> list[dict]:
    """Synchronous yfinance fetch — run in thread pool to avoid blocking event loop."""
    tickers = yf.Tickers(" ".join(SYMBOLS))
    out = []
    for sym in SYMBOLS:
        try:
            t = tickers.tickers[sym]
            fi = t.fast_info
            price = fi.last_price
            prev_close = fi.previous_close
            if price is None or not math.isfinite(float(price)):
                continue
            if prev_close and math.isfinite(float(prev_close)):
                change_abs = price - prev_close
                change_pct = (change_abs / prev_close) * 100
            else:
                change_abs = None
                change_pct = None

            meta = SYMBOL_META.get(sym, {"name": sym, "unit": "", "category": "other"})
            out.append({
                "symbol":     sym,
                "name":       meta["name"],
                "unit":       meta["unit"],
                "category":   meta["category"],
                "price":      round(float(price), 2),
                "change_pct": round(float(change_pct), 2) if change_pct is not None else None,
                "change_abs": round(float(change_abs), 2) if change_abs is not None else None,
                "market_state": "unknown",
                "observation_time": None,
                "source": "Yahoo Finance via yfinance",
            })
        except Exception as e:
            logger.debug("Skip %s: %s", sym, e)
    return out


async def _fetch_quotes() -> list[dict]:
    return await _run_provider(_fetch_quotes_sync)


_quote_task: asyncio.Task | None = None
_history_tasks: dict[int, asyncio.Task] = {}
_hist_by_days: dict[int, tuple[float, dict]] = {}
_quote_retry_at = 0.0
_history_retry_at: dict[int, float] = {}


def _active_refresh_count():
    return int(_quote_task is not None and not _quote_task.done()) + sum(
        not task.done() for task in _history_tasks.values())


def _observe_completion(task):
    # Request timeouts leave shared work running; retrieve eventual exceptions.
    if not task.cancelled():
        task.exception()


async def _refresh_quotes():
    global _cache, _cache_ts, _quote_retry_at
    try:
        fresh = await _fetch_quotes()
        if not fresh:
            raise ValueError("Provider returned no valid market observations")
        _cache, _cache_ts = fresh, time.monotonic()
        _quote_retry_at = 0
    except Exception:
        _quote_retry_at = time.monotonic() + FAILURE_COOLDOWN
        raise


@router.get("")
async def get_market_data():
    """Bounded single-flight provider refresh; no network while disabled."""
    global _quote_task
    now = time.monotonic()
    if not settings.live_ingestion_enabled or _stopping:
        return {"data": [], "stale": True, "status": "disabled", "cached_ago": -1}
    if _cache is not None and now - _cache_ts < CACHE_TTL:
        return {"data": _cache, "stale": False, "status": "cached", "cached_ago": int(now - _cache_ts)}
    if (_quote_task is None or _quote_task.done()) and now >= _quote_retry_at and _active_refresh_count() < MAX_REFRESH_TASKS:
        _quote_task = asyncio.create_task(_refresh_quotes())
        _quote_task.add_done_callback(_observe_completion)
    try:
        if _quote_task is not None and not _quote_task.done():
            await asyncio.wait_for(asyncio.shield(_quote_task), timeout=1.5)
    except asyncio.TimeoutError:
        pass
    except Exception:
        logger.warning("Market refresh failed; retaining last good snapshot")
    age = int(time.monotonic() - _cache_ts) if _cache is not None else -1
    return {"data": _cache or [], "stale": age < 0 or age >= CACHE_TTL,
            "status": "loading" if _quote_task and not _quote_task.done() else "cached" if _cache else "unavailable",
            "cached_ago": age, "retry_after": max(1, math.ceil(_quote_retry_at - time.monotonic())) if age < 0 or age >= CACHE_TTL else 0,
            "source": "Yahoo Finance via yfinance", "pricing_verified": False}


def _fetch_history_sync(symbols: list[str], days: int) -> dict:
    """Fetch daily OHLCV history for each symbol. Returns {symbol: [{date,close},...]}"""
    end   = datetime.utcnow()
    start = end - timedelta(days=days + 5)   # small buffer for weekends/holidays
    result: dict = {}
    for sym in symbols:
        try:
            df = yf.download(sym, start=start.strftime("%Y-%m-%d"),
                             end=end.strftime("%Y-%m-%d"),
                             interval="1d", progress=False, auto_adjust=True)
            if df.empty:
                continue
            # df has a MultiIndex or flat columns depending on yfinance version
            close_col = "Close"
            if hasattr(df.columns, "levels"):
                df.columns = df.columns.droplevel(1)
            closes = df[close_col].dropna()
            series = [
                {"date": str(ts.date()), "close": round(float(v), 4)}
                for ts, v in closes.items() if math.isfinite(float(v))
            ][-days:]   # keep at most `days` points
            if series:
                result[sym] = series
        except Exception as e:
            logger.debug("History skip %s: %s", sym, e)
    return result


async def _refresh_history(days: int):
    try:
        fresh = await _run_provider(_fetch_history_sync, SYMBOLS, days)
        if not fresh:
            raise ValueError("No market history available")
        if days not in _hist_by_days and len(_hist_by_days) >= 8:
            oldest = min(_hist_by_days, key=lambda key: _hist_by_days[key][0])
            _hist_by_days.pop(oldest)
        _hist_by_days[days] = (time.monotonic(), fresh)
        _history_retry_at.pop(days, None)
    except Exception:
        _history_retry_at[days] = time.monotonic() + FAILURE_COOLDOWN
        raise


@router.get("/history")
async def get_market_history(days: int = Query(default=30, ge=5, le=90)):
    if not isinstance(days, int) or not 5 <= days <= 90:
        raise HTTPException(422, "History days must be between 5 and 90")
    if not settings.live_ingestion_enabled or _stopping:
        return {"history": {}, "meta": SYMBOL_META, "status": "disabled", "stale": True, "cached_ago": -1}
    now = time.monotonic()
    stamp, cached = _hist_by_days.get(days, (0, {}))
    if not cached or now - stamp >= HIST_CACHE_TTL:
        task = _history_tasks.get(days)
        if (task is None or task.done()) and now >= _history_retry_at.get(days, 0) and _active_refresh_count() < MAX_REFRESH_TASKS:
            task = asyncio.create_task(_refresh_history(days), name=f"market_history_{days}")
            _history_tasks[days] = task
            def finished(done):
                _observe_completion(done)
                if _history_tasks.get(days) is done:
                    _history_tasks.pop(days, None)
            task.add_done_callback(finished)
        try:
            if task is not None and not task.done():
                await asyncio.wait_for(asyncio.shield(task), timeout=1.5)
        except asyncio.TimeoutError:
            pass
        except Exception:
            logger.warning("Market history unavailable; retaining last good snapshot")
    stamp, cached = _hist_by_days.get(days, (0, {}))
    age = int(time.monotonic() - stamp) if stamp else -1
    return {"history": cached, "meta": SYMBOL_META, "cached_ago": age,
            "stale": age < 0 or age >= HIST_CACHE_TTL, "days_requested": days,
            "status": "loading" if days in _history_tasks and not _history_tasks[days].done() else "cached" if cached else "unavailable",
            "retry_after": max(1, math.ceil(_history_retry_at.get(days, 0) - time.monotonic())) if age < 0 or age >= HIST_CACHE_TTL else 0}


def start_market():
    global _stopping, _provider_slots
    _stopping = False
    # Async semaphores belong to one event loop; actual surviving jobs remain
    # tracked separately and also gate submission after a lifespan restart.
    _provider_slots = asyncio.Semaphore(2)


async def stop_market():
    """Cancel owned coroutines; executing provider threads remain unkillable."""
    global _stopping, _executor, _quote_task
    _stopping = True
    tasks = set(_history_tasks.values())
    if _quote_task is not None:
        tasks.add(_quote_task)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _history_tasks.clear()
    _quote_task = None
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)
        _executor = None
