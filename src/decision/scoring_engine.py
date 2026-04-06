"""
scoring_engine.py — Motor de score principal.

v1.1 — AttractionScore agora carrega BonusResult.flags para o assembler:
  - rare_window:          must-do com janela de fila excepcional
  - must_do_tight_queue:  must-do mas fila no limite do tolerado → texto honesto
  - split_height_warning: allow_split com criança abaixo da altura mínima
"""

import logging
from typing import Optional
from ..domain.models import Attraction, AttractionScore, ScoreBreakdown
from .context_builder import DecisionContext
from .score_dimensions import (
    d1_queue_score, d2_proximity_score, d3_profile_score,
    d4_time_score, d5_strategy_score, estimate_walk_minutes,
)
from .bonuses import calculate_bonus_result

logger = logging.getLogger(__name__)

_REASON_LABELS = {
    "must_do":        "Atração prioritária do grupo",
    "low_queue":      "Fila excepcionalmente boa agora",
    "profile_match":  "Combina perfeitamente com o perfil",
    "show_window":    "Janela ideal para o show",
    "strategic_route":"Posição estratégica na rota",
    "end_of_day":     "Última oportunidade antes de fechar",
    "weather_refuge": "Indoor — ótimo com esse calor",
    "rare_window":    "Janela rara — fila muito abaixo do normal",
}


def score_attraction(attraction: Attraction, ctx: DecisionContext) -> AttractionScore:
    """Calcula o score completo de uma atração. Função pura."""
    w = ctx.weights

    raw_d1 = d1_queue_score(attraction, ctx)
    raw_d2 = d2_proximity_score(attraction, ctx)
    raw_d3 = d3_profile_score(attraction, ctx)
    raw_d4 = d4_time_score(attraction, ctx)
    raw_d5 = d5_strategy_score(attraction, ctx)

    d1 = round(raw_d1 * w.d1_queue, 3)
    d2 = round(raw_d2 * w.d2_proximity, 3)
    d3 = round(raw_d3 * w.d3_profile, 3)
    d4 = round(raw_d4 * w.d4_time, 3)
    d5 = round(raw_d5 * w.d5_strategy, 3)
    base_score = d1 + d2 + d3 + d4 + d5

    br = calculate_bonus_result(attraction, ctx, base_score)
    final_score = round(max(0.0, min(100.0, base_score + br.bonus - br.penalty)), 2)

    current_wait = ctx.queue_snapshot.get(
        attraction.attraction_id,
        attraction.historical_wait(ctx.time_of_day.value),
    )
    walk = estimate_walk_minutes(ctx.current_location_area, attraction.area.value)
    primary_reason = _determine_primary_reason(attraction, ctx, raw_d1, raw_d3, raw_d5, br)
    supporting = _determine_supporting_reasons(attraction, ctx, raw_d2, raw_d4, current_wait, br)
    context_note, trade_off = _build_notes(attraction, ctx, walk, current_wait, br)

    scored = AttractionScore(
        attraction_id=attraction.attraction_id,
        name=attraction.name,
        score=final_score,
        current_wait=current_wait,
        walk_minutes=walk,
        primary_reason=primary_reason,
        supporting_reasons=supporting,
        context_note=context_note,
        trade_off=trade_off,
        score_breakdown=ScoreBreakdown(
            d1_queue=round(d1, 2),
            d2_proximity=round(d2, 2),
            d3_profile=round(d3, 2),
            d4_time=round(d4, 2),
            d5_strategy=round(d5, 2),
            bonuses=round(br.bonus, 2),
            penalties=round(br.penalty, 2),
        ),
    )

    # Propaga flags do BonusResult como metadado extra no AttractionScore
    # Usando __dict__ para evitar modificar o dataclass (compatível com MVP)
    scored._rare_window = br.rare_window
    scored._must_do_tight_queue = br.must_do_tight_queue
    scored._split_height_warning = br.split_height_warning
    scored._split_child_height = br.split_child_height
    scored._split_min_height = br.split_min_height

    return scored


def rank_attractions(attractions: list[Attraction], ctx: DecisionContext) -> list[AttractionScore]:
    """Pontua e ordena todas as atrações elegíveis. Função pura."""
    if not attractions:
        return []
    scored = [score_attraction(a, ctx) for a in attractions]
    ranked = sorted(scored, key=lambda s: s.score, reverse=True)
    logger.debug(
        "ranking top3=%s weights=%s",
        [(s.attraction_id, s.score) for s in ranked[:3]],
        ctx.weights.describe(),
    )
    return ranked


def _determine_primary_reason(
    attraction: Attraction,
    ctx: DecisionContext,
    raw_d1: float,
    raw_d3: float,
    raw_d5: float,
    br,
) -> str:
    if attraction.attraction_id in ctx.must_do_attractions:
        # v1.1: se foi janela rara, o motivo específico é mais informativo
        if br.rare_window:
            return "rare_window"
        return "must_do"
    if ctx.hours_until_close <= 2.0:
        return "end_of_day"
    if ctx.weather in ("sunny", "rainy") and attraction.is_indoor:
        return "weather_refuge"
    if raw_d1 >= 75:
        return "low_queue"
    if raw_d3 >= 85:
        return "profile_match"
    if raw_d5 >= 75:
        return "strategic_route"
    scores = {"low_queue": raw_d1, "profile_match": raw_d3, "strategic_route": raw_d5}
    return max(scores, key=scores.get)


def _determine_supporting_reasons(
    attraction: Attraction,
    ctx: DecisionContext,
    raw_d2: float,
    raw_d4: float,
    current_wait: int,
    br,
) -> list[str]:
    reasons = []
    if raw_d2 >= 80:
        reasons.append("nearby")
    if raw_d4 >= 95:
        reasons.append("best_time_now")
    if attraction.is_indoor and ctx.weather == "sunny":
        reasons.append("indoor_ac")
    if current_wait <= 10:
        reasons.append("very_short_queue")
    # v1.1: rider swap como razão de apoio só quando split_height_warning ativo
    if br.split_height_warning:
        reasons.append("rider_swap_split")
    elif attraction.rider_swap and ctx.min_child_height is not None:
        reasons.append("rider_swap_available")
    return reasons[:3]


def _build_notes(
    attraction: Attraction,
    ctx: DecisionContext,
    walk: int,
    current_wait: int,
    br,
) -> tuple[Optional[str], Optional[str]]:
    # v1.1: suprime context_note quando informação é redundante com a fila atual
    # Correção F2: não repetir "fila quase sempre baixa" quando já exibimos a fila real
    context_note = None
    if attraction.strategic_notes:
        historical = attraction.historical_wait(ctx.time_of_day.value)
        # Suprime nota de "fila baixa" quando fila atual já é boa e nota não acrescenta
        note_lower = attraction.strategic_notes.lower()
        is_redundant_queue_note = (
            any(kw in note_lower for kw in ["fila quase sempre", "sem fila", "fila curta"])
            and current_wait <= historical * 0.7
        )
        if not is_redundant_queue_note:
            context_note = attraction.strategic_notes.split(".")[0].strip() or None

    trade_off = None
    if walk > 10 and current_wait < 20:
        trade_off = f"um pouco distante ({walk} min a pé), mas fila excepcionalmente boa"
    elif current_wait > 35 and attraction.attraction_id in ctx.must_do_attractions:
        trade_off = f"fila de {current_wait} min, mas é prioridade de vocês"
    elif not attraction.is_indoor and ctx.weather == "sunny":
        trade_off = "atração outdoor — leve protetor solar e água"

    return context_note, trade_off


def explain_score(scored: AttractionScore, ctx: DecisionContext) -> str:
    bd = scored.score_breakdown
    if not bd:
        return f"{scored.attraction_id}: score={scored.score}"
    flags = []
    if getattr(scored, '_rare_window', False): flags.append("RARE_WINDOW")
    if getattr(scored, '_must_do_tight_queue', False): flags.append("TIGHT_QUEUE")
    if getattr(scored, '_split_height_warning', False):
        flags.append(f"SPLIT({scored._split_child_height}<{scored._split_min_height}cm)")
    lines = [
        f"Atração: {scored.name} → {scored.score}/100  flags={flags}",
        f"Pesos: {ctx.weights.describe()}  [{ctx.weight_reason}]",
        f"  D1={bd.d1_queue:.1f} D2={bd.d2_proximity:.1f} D3={bd.d3_profile:.1f} "
        f"D4={bd.d4_time:.1f} D5={bd.d5_strategy:.1f} +{bd.bonuses:.1f} -{bd.penalties:.1f}",
        f"  Motivo: {scored.primary_reason} | Apoio: {scored.supporting_reasons}",
    ]
    if scored.trade_off:
        lines.append(f"  Trade-off: {scored.trade_off}")
    return "\n".join(lines)
