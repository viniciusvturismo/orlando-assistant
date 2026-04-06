import uuid
from datetime import datetime
from typing import Optional

from ..domain.models import OperationalContext, FilterOverride
from ..domain.enums import WeatherCondition, GroupStateType
from ..domain.exceptions.domain_exceptions import NoContextActive, ContextExpired
from ..infra.repositories.context_repository import get_context_repository


class ContextService:

    def __init__(self):
        self._repo = get_context_repository()

    def create_context(
        self,
        group_id: str,
        park_id: str,
        location_area: str,
        queue_snapshot: dict[str, int],
        done_attractions: Optional[list[str]] = None,
        closed_attractions: Optional[list[str]] = None,
        weather: Optional[str] = None,
        group_states: Optional[list[str]] = None,
        filter_override: Optional[dict] = None,
    ) -> OperationalContext:
        context_id = f"ctx_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        fo = None
        if filter_override:
            fo = FilterOverride(
                intensity=filter_override.get("intensity"),
                environment=filter_override.get("environment"),
                max_queue_minutes=filter_override.get("max_queue_minutes"),
                for_all_members=filter_override.get("for_all_members", False),
            )

        states = []
        for s in (group_states or []):
            try:
                states.append(GroupStateType(s))
            except ValueError:
                pass

        context = OperationalContext(
            context_id=context_id,
            group_id=group_id,
            current_park_id=park_id,
            current_datetime=now,
            current_location_area=location_area,
            queue_snapshot=queue_snapshot,
            queue_snapshot_at=now,
            done_attractions=done_attractions or [],
            closed_attractions=closed_attractions or [],
            active_states=states,
            filter_override=fo,
            weather=WeatherCondition(weather) if weather else None,
        )

        return self._repo.create(context)

    def get_active_context(self, group_id: str) -> OperationalContext:
        ctx = self._repo.get_active(group_id)
        if not ctx:
            raise NoContextActive(group_id)
        return ctx

    def update_location(self, group_id: str, location_area: str) -> OperationalContext:
        ctx = self.get_active_context(group_id)
        self._repo.patch_location(ctx.context_id, location_area)
        ctx.current_location_area = location_area
        return ctx

    def mark_attraction_done(self, group_id: str, attraction_id: str) -> OperationalContext:
        ctx = self.get_active_context(group_id)
        self._repo.add_done_attraction(ctx.context_id, attraction_id)
        if attraction_id not in ctx.done_attractions:
            ctx.done_attractions.append(attraction_id)
        return ctx

    def update_queues(self, group_id: str, queue_snapshot: dict[str, int]) -> OperationalContext:
        ctx = self.get_active_context(group_id)
        self._repo.update_queues(ctx.context_id, queue_snapshot)
        ctx.queue_snapshot = queue_snapshot
        return ctx

    def apply_group_states(self, group_id: str, new_states: list[str]) -> OperationalContext:
        ctx = self.get_active_context(group_id)
        existing = [s.value if hasattr(s, "value") else s for s in ctx.active_states]
        merged = list(set(existing + new_states))
        self._repo.update_states(ctx.context_id, merged)
        return ctx
