import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

from ...domain.models import OperationalContext, FilterOverride
from ...domain.enums import WeatherCondition, GroupStateType
from ..database.connection import get_connection

CONTEXT_TTL_HOURS = 24


class ContextRepository:

    def create(self, context: OperationalContext) -> OperationalContext:
        expires_at = context.current_datetime + timedelta(hours=CONTEXT_TTL_HOURS)
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO operational_contexts
                   (context_id, group_id, current_park_id, current_datetime,
                    current_location_area, queue_snapshot, queue_snapshot_at,
                    done_attractions, closed_attractions, active_states,
                    filter_override, weather, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    context.context_id, context.group_id, context.current_park_id,
                    context.current_datetime.isoformat(), context.current_location_area,
                    json.dumps(context.queue_snapshot),
                    context.queue_snapshot_at.isoformat() if context.queue_snapshot_at else None,
                    json.dumps(context.done_attractions),
                    json.dumps(context.closed_attractions),
                    json.dumps([s.value if hasattr(s, "value") else s for s in context.active_states]),
                    json.dumps(self._serialize_filter(context.filter_override)),
                    context.weather.value if context.weather else None,
                    expires_at.isoformat(),
                ),
            )
        context.expires_at = expires_at
        return context

    def get_active(self, group_id: str) -> Optional[OperationalContext]:
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            row = conn.execute(
                """SELECT * FROM operational_contexts
                   WHERE group_id = ? AND (expires_at IS NULL OR expires_at > ?)
                   ORDER BY current_datetime DESC LIMIT 1""",
                (group_id, now),
            ).fetchone()
            if not row:
                return None
            return self._hydrate(dict(row))

    def patch_location(self, context_id: str, location_area: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE operational_contexts SET current_location_area = ? WHERE context_id = ?",
                (location_area, context_id),
            )

    def add_done_attraction(self, context_id: str, attraction_id: str) -> None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT done_attractions FROM operational_contexts WHERE context_id = ?",
                (context_id,),
            ).fetchone()
            if not row:
                return
            done = json.loads(row["done_attractions"])
            if attraction_id not in done:
                done.append(attraction_id)
            conn.execute(
                "UPDATE operational_contexts SET done_attractions = ? WHERE context_id = ?",
                (json.dumps(done), context_id),
            )

    def update_queues(self, context_id: str, queue_snapshot: dict[str, int]) -> None:
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute(
                """UPDATE operational_contexts
                   SET queue_snapshot = ?, queue_snapshot_at = ?
                   WHERE context_id = ?""",
                (json.dumps(queue_snapshot), now, context_id),
            )

    def update_states(self, context_id: str, states: list[str]) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE operational_contexts SET active_states = ? WHERE context_id = ?",
                (json.dumps(states), context_id),
            )

    def _hydrate(self, row: dict) -> OperationalContext:
        filter_raw = json.loads(row["filter_override"]) if row["filter_override"] else None
        filter_override = None
        if filter_raw:
            filter_override = FilterOverride(
                intensity=filter_raw.get("intensity"),
                environment=filter_raw.get("environment"),
                max_queue_minutes=filter_raw.get("max_queue_minutes"),
                for_all_members=filter_raw.get("for_all_members", False),
            )

        states_raw = json.loads(row["active_states"])
        active_states = []
        for s in states_raw:
            try:
                active_states.append(GroupStateType(s))
            except ValueError:
                pass

        return OperationalContext(
            context_id=row["context_id"],
            group_id=row["group_id"],
            current_park_id=row["current_park_id"],
            current_datetime=datetime.fromisoformat(row["current_datetime"]),
            current_location_area=row["current_location_area"],
            queue_snapshot=json.loads(row["queue_snapshot"]),
            queue_snapshot_at=datetime.fromisoformat(row["queue_snapshot_at"]) if row["queue_snapshot_at"] else None,
            done_attractions=json.loads(row["done_attractions"]),
            closed_attractions=json.loads(row["closed_attractions"]),
            active_states=active_states,
            filter_override=filter_override,
            weather=WeatherCondition(row["weather"]) if row["weather"] else None,
            expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
        )

    def _serialize_filter(self, f: Optional[FilterOverride]) -> Optional[dict]:
        if not f:
            return None
        return {
            "intensity": f.intensity,
            "environment": f.environment,
            "max_queue_minutes": f.max_queue_minutes,
            "for_all_members": f.for_all_members,
        }


def get_context_repository() -> ContextRepository:
    return ContextRepository()
