"""Inherited editorial hypotheses, deliberately separate from current evidence.

The original curated summaries are retained for continuity. Their quotations,
attribution and factual accuracy have not been independently verified here.
They are optional lenses to test, not structural laws or proof of current events.
No network request, refresh clock, subscriber count, or automatic cache is used.
"""
import copy
import json
import logging

logger = logging.getLogger("app.services.predictive_history")

CURATED_FRAMEWORKS = [
    {
        "episode": 16,
        "title": "Pax Judaica Rising",
        "video_id": "mk4vcHtawSo",
        "published": "2026-03-26",
        "law": "PAX JUDAICA RISING",
        "summary": (
            "Israel is the primary structural beneficiary of the US-Iran war. "
            "While great powers exhaust each other, Israel achieves regional hegemony "
            "without direct involvement. The silent beneficiary always wins the endgame. "
            "Shifting power dynamics alter global oil markets and elevate a new regional superpower."
        ),
        "application": (
            "Assess which actor gains RELATIVE power as others deplete resources and credibility. "
            "The structurally positioned beneficiary shapes events without appearing to."
        ),
        "key_prediction": "Israeli regional hegemony (Pax Judaica) emerges as Iran is degraded and US credibility is spent.",
    },
    {
        "episode": 15,
        "title": "The Return of History",
        "video_id": "zAer-Mqe7tQ",
        "law": "RETURN OF HISTORY",
        "summary": (
            "The 'End of History' liberal order is terminating. Suppressed historical conflicts — "
            "ethnic, religious, civilizational — reassert when hegemonic order weakens. "
            "Ottoman successor rivalries, Persian-Arab tensions, and Sunni-Shia fault lines "
            "are re-activating as US hegemony retreats."
        ),
        "application": (
            "Identify which suppressed historical conflict is reasserting itself. "
            "The deeper the historical grievance, the more violent the reassertion."
        ),
        "key_prediction": "Civilizational and sectarian conflicts suppressed by US hegemony re-emerge across the Middle East.",
    },
    {
        "episode": 14,
        "title": "The Law of Proximity",
        "video_id": "nOQqGy4boBY",
        "law": "LAW OF PROXIMITY",
        "summary": (
            "Geographic proximity maximises the security dilemma. The closer two states, "
            "the more zero-sum their relationship. Distant threats are mediated; proximate threats "
            "are existential. Israel-Iran conflict is mediated through a proxy belt "
            "(Lebanon-Syria-Iraq-Yemen) that collapses distance into intimacy."
        ),
        "application": (
            "Map the proxy chain between distant adversaries. Each proxy layer adds escalation "
            "friction but also escalation pathways. Destruction of the proxy belt forces direct confrontation."
        ),
        "key_prediction": "Dismantling the Shia Crescent (Hezbollah, Iraq PMF, Houthis) forces direct Iran-Israel confrontation.",
    },
    {
        "episode": 13,
        "title": "Epstein's World",
        "video_id": "EBWTRvjZ1dw",
        "law": "EPSTEIN NETWORKS",
        "summary": (
            "Intelligence networks, elite blackmail, and hidden financial flows are the shadow "
            "infrastructure of geopolitics. Publicly stated policies diverge systematically "
            "from actual actor behaviour when hidden leverage is in play. "
            "Inexplicable non-moves (expected escalations that don't happen) signal Epstein dynamics."
        ),
        "application": (
            "When a structurally compelled move doesn't happen, ask: who has leverage over the actor? "
            "Intelligence coercion, financial exposure, or elite network protection explains "
            "the gap between expected and observed behaviour."
        ),
        "key_prediction": "Hidden leverage networks constrain overt escalation even when structural logic demands it.",
    },
    {
        "episode": 12,
        "title": "The Law of Eschatological Convergence",
        "law": "ESCHATOLOGICAL CONVERGENCE",
        "summary": (
            "Religious end-times frameworks across civilizations are converging on the same "
            "geographic focal point — Jerusalem and the Temple Mount. When eschatological "
            "timelines align, actors accept catastrophic rational-choice losses for divine mandate. "
            "Jewish messianism, Shia 12th Imam theology, and evangelical Christian Zionism "
            "all converge on the same prophetic trigger geography."
        ),
        "application": (
            "Eschatological actors cannot be deterred by rational cost-benefit calculation. "
            "Identify when religious-mandate logic has captured decision-making — "
            "these actors are structurally compelled toward actions that appear irrational."
        ),
        "key_prediction": "Jerusalem/Temple Mount control becomes a non-negotiable trigger point across multiple civilizational actors.",
    },
    {
        "episode": 11,
        "title": "The Law of Escalation",
        "law": "LAW OF ESCALATION",
        "summary": (
            "Conflicts escalate in predictable game-theoretic steps until reaching equilibrium. "
            "Each actor must respond to the last escalation or permanently lose deterrence credibility. "
            "Equilibrium is reached only when one side loses capacity or political will to respond. "
            "Premature ceasefires without structural resolution produce escalation resumption."
        ),
        "application": (
            "Map the escalation ladder. Identify which rung each actor is currently on and "
            "what the next unavoidable rung is. The actor with the most rungs remaining wins. "
            "Asymmetric escalation (nuclear vs conventional) is the trump card."
        ),
        "key_prediction": "Escalation continues until one side crosses a capacity threshold — nuclear ambiguity is the ceiling.",
    },
    {
        "episode": 10,
        "title": "The Empire Trap",
        "law": "EMPIRE TRAP",
        "summary": (
            "Empires become trapped by the cost of maintaining their periphery. "
            "Each intervention to stabilise a failing proxy creates new dependencies "
            "and new instability vectors. The empire cannot withdraw without losing credibility, "
            "cannot stay without haemorrhaging resources — an inescapable structural trap."
        ),
        "application": (
            "Assess whether the hegemon is caught in the empire trap. "
            "Signs: escalating costs, diminishing returns, inability to define victory. "
            "Trapped empires are forced into desperate escalation or face disorderly retreat."
        ),
        "key_prediction": "US faces the empire trap in the Middle East — continuation costs credibility; withdrawal costs hegemony.",
    },
]



def local_framework_context() -> dict:
    """Return an isolated, honestly labelled copy of the inherited framework."""
    frameworks = copy.deepcopy(CURATED_FRAMEWORKS)
    for framework in frameworks:
        video_id = framework.get("video_id")
        framework["source_pointer"] = (
            f"https://www.youtube.com/watch?v={video_id}" if video_id else
            "https://www.youtube.com/@PredictiveHistory"
        )
        framework["provenance_status"] = "inherited_unverified_editorial_summary"
    return {
        "mode": "local_curated_hypotheses",
        "fetched_at": None,
        "fetch_succeeded": False,
        "frameworks": frameworks,
        "limitations": [
            "These inherited summaries are not verified transcripts or current observations.",
            "Titles, dates, attribution and quoted claims require source review before reliance.",
            "The word law is inherited editorial wording, not an established causal law.",
            "No framework establishes an actor's motivation, intent or future behavior.",
        ],
    }


async def refresh_cache() -> dict:
    """Compatibility entry point: local copy only, without network or disk I/O."""
    return local_framework_context()


async def get_game_theory_context() -> str:
    return json.dumps(local_framework_context(), ensure_ascii=False)


async def start_predictive_history_refresher() -> None:
    """Compatibility entry point; automatic external fetching is disabled."""
    logger.info("Predictive History: local unverified hypotheses; automatic fetching disabled")
