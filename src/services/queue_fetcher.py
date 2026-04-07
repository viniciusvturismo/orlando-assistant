import logging
import urllib.request
import json
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

MK_ENTITY_ID = "75ea578a-adc8-4116-a54d-dccb60765ef9"
API_URL = f"https://api.themeparks.wiki/v1/entity/{MK_ENTITY_ID}/live"

ATTRACTION_NAME_MAP = {
    "seven dwarfs":         "seven_dwarfs_mine_train",
    "space mountain":       "space_mountain",
    "tron":                 "tron_lightcycle_run",
    "big thunder":          "big_thunder_mountain",
    "haunted mansion":      "haunted_mansion",
    "pirates of the caribbean": "pirates_of_the_caribbean",
    "peter pan":            "peter_pan_flight",
    "small world":          "its_a_small_world",
    "buzz lightyear":       "buzz_lightyear",
    "dumbo":                "dumbo",
    "tiana":                "tiana_bayou_adventure",
    "jungle cruise":        "jungle_cruise",
    "barnstormer":          "barnstormer",
    "tomorrowland speedway": "tomorrowland_speedway",
    "little mermaid":       "under_the_sea",
    "enchanted tales":      "enchanted_tales_belle",
    "liberty belle":        "liberty_belle_riverboat",
    "carousel of progress": "carousel_of_progress",
}


def fetch_live_queues() -> Optional[dict]:
    try:
        req = urllib.request.Request(API_URL, headers={"User-Agent": "OrlandoAssistant/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        logger.warning("queue_fetch_failed: %s", e)
        return None

    result = {}
    for item in data.get("liveData", []):
        if item.get("entityType") != "ATTRACTION":
            continue
        name = (item.get("name") or "").lower()
        status = item.get("status", "CLOSED")
        wait_time = (item.get("queue") or {}).get("STANDBY", {}).get("waitTime")
        slug = None
        for key, s in ATTRACTION_NAME_MAP.items():
            if key in name:
                slug = s
                break
        if not slug:
            continue
        if status == "OPERATING" and wait_time is not None:
            result[slug] = int(wait_time)
        elif status in ("CLOSED", "DOWN", "REFURBISHMENT"):
            result[slug] = 999

    logger.info("queue_fetch_ok attractions=%d", len(result))
    return result or None


def update_active_contexts(queue_snapshot: dict) -> int:
    try:
        from src.infra.database.connection import get_connection
        updated = 0
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT context_id, queue_snapshot FROM operational_contexts WHERE expires_at IS NULL OR expires_at > ?",
                (datetime.now(timezone.utc).isoformat(),)
            ).fetchall()
            for row in rows:
                existing = json.loads(row["queue_snapshot"] or "{}")
                merged = {**queue_snapshot, **existing}
                conn.execute(
                    "UPDATE operational_contexts SET queue_snapshot = ? WHERE context_id = ?",
                    (json.dumps(merged), row["context_id"])
                )
                updated += 1
        return updated
    except Exception as e:
        logger.error("queue_update_db_failed: %s", e)
        return 0


def run_queue_update() -> dict:
    started_at = datetime.now(timezone.utc)
    queues = fetch_live_queues()
    if queues is None:
        return {"success": False, "reason": "api_unavailable", "timestamp": started_at.isoformat()}
    updated = update_active_contexts(queues)
    return {
        "success": True,
        "attractions_fetched": len(queues),
        "contexts_updated": updated,
        "timestamp": started_at.isoformat(),
        "sample": {k: v for k, v in list(queues.items())[:5] if v < 999},
    }
