"""
bonuses.py — Bônus e penalidades aplicados sobre o score base.

CALIBRAÇÃO:
  Constantes nomeadas no topo — ajuste aqui, não no código.
  Cap: bônus máximo = BONUS_CAP, penalidade máxima = PENALTY_CAP.

HISTÓRICO DE MUDANÇAS:
  v1.1 — Adicionado BONUS_RARE_WINDOW: must-do com fila muito abaixo do histórico
          recebe bônus adicional de urgência (correção F1).
       — must_do_tight_queue: flag retornada quando must-do com fila ≥ 85% do limite,
          para o assembler gerar texto honesto (correção F3).
       — split_height_warning: flag quando allow_split + min_child_height < min_height_cm,
          para o assembler personalizar a nota de rider swap (correção F4).
"""

from dataclasses import dataclass, field
from ..domain.models import Attraction
from ..domain.enums import TimeOfDay
from .context_builder import DecisionContext
from .score_dimensions import estimate_walk_minutes

# ── Limites ────────────────────────────────────────────────────────────────────
BONUS_CAP   = 20.0   # aumentado de 15 → 20 para acomodar o novo bônus de janela
PENALTY_CAP = 20.0

# ── Valores de bônus individuais ──────────────────────────────────────────────
BONUS_MUST_DO        = 15.0  # atração está em must_do_attractions
BONUS_RARE_LOW_QUEUE =  8.0  # fila excepcionalmente curta para atração icônica (≤15 min)
BONUS_PARK_ICON      =  6.0  # atração icônica ainda não realizada
BONUS_SHOW_WINDOW    = 10.0  # show começa em janela ideal
BONUS_RARE_WINDOW    = 10.0  # NOVO v1.1: must-do com fila < 40% do histórico do período

# ── Valores de penalidade individuais ─────────────────────────────────────────
PENALTY_LONG_WALK_QUEUE  = 10.0
PENALTY_YOUNG_CHILD_HIGH =  8.0
PENALTY_ROUTE_DETOUR     =  6.0
PENALTY_OUTDOOR_HEAT     =  5.0
PENALTY_SHORT_LONG_QUEUE =  8.0

# Limiar de "janela rara": fila atual abaixo deste % do histórico → bônus
RARE_WINDOW_THRESHOLD = 0.40

# Limiar de "fila no limite": fila atual acima deste % do max → texto honesto
TIGHT_QUEUE_THRESHOLD = 0.85


@dataclass
class BonusResult:
    """Resultado detalhado dos bônus/penalidades com flags para o assembler."""
    bonus: float
    penalty: float
    # Flags para o assembler de mensagens
    rare_window: bool = False          # must-do com fila excepcionalmente boa
    must_do_tight_queue: bool = False  # must-do mas fila está no limite do tolerado
    split_height_warning: bool = False # allow_split com criança abaixo da altura mínima
    split_child_height: int = 0        # altura da criança bloqueada
    split_min_height: int = 0          # altura mínima da atração


def calculate_bonus_result(
    attraction: Attraction,
    ctx: DecisionContext,
    base_score: float,
) -> BonusResult:
    """
    Calcula bônus e penalidades com flags para o assembler.
    Versão completa — use esta nos novos fluxos.
    """
    bonus = 0.0
    rare_window = False
    must_do_tight_queue = False
    split_height_warning = False
    split_child_height = 0
    split_min_height = 0

    # ── Bônus ─────────────────────────────────────────────────────────────────

    is_must_do = attraction.attraction_id in ctx.must_do_attractions

    if is_must_do:
        bonus += BONUS_MUST_DO

        # v1.1 — BONUS_RARE_WINDOW: must-do com fila muito abaixo do histórico
        # Corrige F1: Mine Train com 15 min no rope drop (histórico 20 min) não
        # recebia bônus extra. Agora recebe se fila < 40% do histórico.
        current_wait = ctx.queue_snapshot.get(attraction.attraction_id)
        historical = attraction.historical_wait(ctx.time_of_day.value)
        if current_wait is not None and historical > 0:
            ratio = current_wait / historical
            if ratio < RARE_WINDOW_THRESHOLD:
                bonus += BONUS_RARE_WINDOW
                rare_window = True

        # v1.1 — must_do_tight_queue flag: must-do mas fila está quase no limite
        # Corrige F3: assembler usa isso para gerar texto honesto em vez de "fila favorável"
        max_q = ctx.max_queue_minutes
        wait = current_wait if current_wait is not None else historical
        if wait >= max_q * TIGHT_QUEUE_THRESHOLD:
            must_do_tight_queue = True

    current_wait = ctx.queue_snapshot.get(attraction.attraction_id, 999)
    if current_wait <= 15 and attraction.is_icon():
        bonus += BONUS_RARE_LOW_QUEUE

    if attraction.is_icon() and attraction.attraction_id not in ctx.done_attractions:
        bonus += BONUS_PARK_ICON

    # Show window
    walk = estimate_walk_minutes(ctx.current_location_area, attraction.area.value)
    for show in ctx.active_shows:
        if show.attraction_id == attraction.attraction_id:
            mins_until = show.minutes_until(ctx.current_datetime)
            if walk + 5 <= mins_until <= 40:
                bonus += BONUS_SHOW_WINDOW
                break

    bonus = round(min(bonus, BONUS_CAP), 2)

    # ── Penalidades ───────────────────────────────────────────────────────────

    penalty = 0.0
    current_wait_for_penalty = ctx.queue_snapshot.get(attraction.attraction_id, 0)

    if walk > 12 and current_wait_for_penalty > 25:
        penalty += PENALTY_LONG_WALK_QUEUE

    if attraction.duration_minutes <= 2 and current_wait_for_penalty > 25:
        penalty += PENALTY_SHORT_LONG_QUEUE

    if ctx.min_child_height is not None and ctx.min_child_height < 95:
        if attraction.intensity.value in ("high", "extreme"):
            penalty += PENALTY_YOUNG_CHILD_HIGH

    if _is_route_detour(attraction, ctx):
        penalty += PENALTY_ROUTE_DETOUR

    if not attraction.is_indoor and ctx.weather == "sunny":
        if ctx.time_of_day in (TimeOfDay.MIDDAY, TimeOfDay.AFTERNOON):
            penalty += PENALTY_OUTDOOR_HEAT

    penalty = round(min(penalty, PENALTY_CAP), 2)

    # ── v1.1 — split_height_warning flag ──────────────────────────────────────
    # Corrige F4: quando allow_group_split=True e criança está abaixo da altura mínima,
    # o assembler precisa de dados concretos para personalizar a nota de rider swap.
    if ctx.allow_group_split and ctx.min_child_height is not None:
        if attraction.min_height_cm > 0 and ctx.min_child_height < attraction.min_height_cm:
            split_height_warning = True
            split_child_height = ctx.min_child_height
            split_min_height = attraction.min_height_cm

    return BonusResult(
        bonus=bonus,
        penalty=penalty,
        rare_window=rare_window,
        must_do_tight_queue=must_do_tight_queue,
        split_height_warning=split_height_warning,
        split_child_height=split_child_height,
        split_min_height=split_min_height,
    )


def calculate_bonuses(attraction: Attraction, ctx: DecisionContext, base_score: float) -> float:
    """Interface simplificada — mantém compatibilidade com scoring_engine."""
    return calculate_bonus_result(attraction, ctx, base_score).bonus


def calculate_penalties(attraction: Attraction, ctx: DecisionContext) -> float:
    """Interface simplificada — mantém compatibilidade com scoring_engine."""
    return calculate_bonus_result(attraction, ctx, 0.0).penalty


def _is_route_detour(attraction: Attraction, ctx: DecisionContext) -> bool:
    if not ctx.must_do_attractions:
        return False
    remaining = {a for a in ctx.must_do_attractions if a not in ctx.done_attractions}
    if not remaining:
        return False
    if not ctx.must_do_areas:
        return False
    return attraction.area.value not in ctx.must_do_areas
