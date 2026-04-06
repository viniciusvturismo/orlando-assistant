"""
context_builder.py — Constrói o DecisionContext a partir dos dados do grupo e visita.

O DecisionContext é o objeto que o scoring engine consome. Ele:
  - Calcula os pesos finais (perfil + situação) uma única vez
  - Serializa estados do grupo em strings simples
  - Resolve o time_of_day a partir do datetime atual
  - Pré-computa must_do_areas para uso no _is_route_detour das penalidades

O context_builder NÃO acessa banco de dados nem APIs externas.
Recebe tudo pronto e monta a estrutura de decisão.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..domain.models import Group, GroupPreferences, OperationalContext
from ..domain.enums import TimeOfDay
from .weights import DimensionWeights, get_weights, get_weight_reason


@dataclass
class DecisionContext:
    """
    Snapshot imutável com tudo que o scoring engine precisa.
    Criado pelo build_decision_context() e passado para todas as funções de score.
    """
    group_id: str
    profile_id: str
    weights: DimensionWeights
    weight_reason: str                  # por que esses pesos foram escolhidos

    current_location_area: str
    current_datetime: datetime
    time_of_day: TimeOfDay
    hours_until_close: float

    done_attractions: list[str]
    closed_attractions: list[str]
    queue_snapshot: dict[str, int]
    active_shows: list                  # list[ShowSlot] do OperationalContext

    max_queue_minutes: int
    avoid_types: list[str]
    must_do_attractions: list[str]
    must_do_areas: set[str]             # áreas das must-do pendentes — pré-computado

    active_states: list[str]
    filter_override: Optional[object]   # FilterOverride ou dict ou None
    min_child_height: Optional[int]
    allow_group_split: bool
    show_interest: bool

    park_close_time: datetime
    weather: Optional[str]
    members: list = field(default_factory=list)


def build_decision_context(
    group: Group,
    preferences: GroupPreferences,
    context: OperationalContext,
    park_open_hour: int = 9,
    park_close_hour: int = 22,
    attraction_areas: Optional[dict[str, str]] = None,
) -> DecisionContext:
    """
    Constrói o DecisionContext. Os pesos são calculados aqui e NÃO mudam durante o scoring.

    Args:
        group:           entidade do grupo com membros
        preferences:     preferências e prioridades do grupo
        context:         contexto operacional atual (filas, localização, estados)
        park_open_hour:  hora de abertura do parque
        park_close_hour: hora de fechamento
        attraction_areas: mapa {attraction_id: area} para resolver must_do_areas
                          Se None, must_do_areas será vazio (sem penalidade de desvio)
    """
    now = context.current_datetime
    time_of_day = _classify_time_of_day(now, park_open_hour, park_close_hour)

    close_dt = now.replace(hour=park_close_hour, minute=0, second=0, microsecond=0)
    hours_until_close = max(0.0, (close_dt - now).total_seconds() / 3600)

    active_states = [s.value if hasattr(s, "value") else str(s) for s in context.active_states]

    weights = get_weights(
        profile_id=group.profile_id or "P4",
        active_states=active_states,
        hours_until_close=hours_until_close,
    )
    weight_reason = get_weight_reason(
        profile_id=group.profile_id or "P4",
        active_states=active_states,
        hours_until_close=hours_until_close,
    )

    # Pré-computa as áreas das must-do pendentes para o cálculo de desvio de rota
    must_do_areas = _resolve_must_do_areas(
        must_do=preferences.must_do_attractions,
        done=context.done_attractions,
        area_map=attraction_areas or {},
    )

    return DecisionContext(
        group_id=group.group_id,
        profile_id=group.profile_id or "P4",
        weights=weights,
        weight_reason=weight_reason,
        current_location_area=context.current_location_area,
        current_datetime=now,
        time_of_day=time_of_day,
        hours_until_close=hours_until_close,
        done_attractions=list(context.done_attractions),
        closed_attractions=list(context.closed_attractions),
        queue_snapshot=dict(context.queue_snapshot),
        active_shows=list(context.active_shows),
        max_queue_minutes=preferences.max_queue_minutes,
        avoid_types=list(preferences.avoid_types),
        must_do_attractions=list(preferences.must_do_attractions),
        must_do_areas=must_do_areas,
        active_states=active_states,
        filter_override=context.filter_override,
        min_child_height=group.min_child_height,
        allow_group_split=preferences.allow_group_split,
        show_interest=preferences.show_interest,
        park_close_time=close_dt,
        weather=context.weather.value if context.weather else None,
        members=list(group.members),
    )


def _classify_time_of_day(dt: datetime, open_hour: int, close_hour: int) -> TimeOfDay:
    hour = dt.hour
    if hour <= open_hour:
        return TimeOfDay.ROPE_DROP
    if hour < 11:
        return TimeOfDay.MORNING
    if hour < 13:
        return TimeOfDay.MIDDAY
    if hour < 16:
        return TimeOfDay.AFTERNOON
    if hour < 19:
        return TimeOfDay.EVENING
    return TimeOfDay.NIGHT


def _resolve_must_do_areas(
    must_do: list[str],
    done: list[str],
    area_map: dict[str, str],
) -> set[str]:
    """Retorna o conjunto de áreas das must-do ainda pendentes."""
    pending = set(must_do) - set(done)
    return {area_map[a] for a in pending if a in area_map}
