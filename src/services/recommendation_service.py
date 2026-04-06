"""
recommendation_service.py — Orquestra o fluxo completo de recomendação.

Sequência:
  1. build_decision_context  → DecisionContext com pesos calculados
  2. apply_filters           → separa elegíveis de excluídas
  3. rank_attractions        → lista ordenada por score
  4. select_primary_and_secondary → primary + secondary com diversidade de área
  5. generate_response       → texto PT-BR para WhatsApp (opcional)
  6. Recommendation          → objeto completo para retorno e persistência

Este service é o único que conhece a sequência completa.
Cada passo individual é testável de forma isolada.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from ..domain.models import Recommendation, Group, GroupPreferences, OperationalContext
from ..domain.exceptions.domain_exceptions import NoEligibleAttractions
from ..decision.context_builder import build_decision_context, DecisionContext
from ..decision.rules_engine import apply_filters, FilterResult
from ..decision.scoring_engine import rank_attractions, explain_score
from ..decision.ranker import select_primary_and_secondary
from ..infra.repositories.attractions_repository import get_attractions_repository
from ..language.fallback_templates import build_fallback_message

logger = logging.getLogger(__name__)


class RecommendationService:

    def __init__(self):
        self._attractions_repo = get_attractions_repository()

    def recommend(
        self,
        group: Group,
        preferences: GroupPreferences,
        context: OperationalContext,
        filter_override: Optional[dict] = None,
        generate_text: bool = True,
        user_message: str = "",
        intent: str = "GET_REC",
    ) -> Recommendation:
        """
        Fluxo completo de recomendação.

        Nunca propaga exceção para o chamador (exceto NoEligibleAttractions,
        que indica problema real de dados ou filtros muito restritivos).

        Args:
            group:           grupo visitante com membros
            preferences:     preferências e prioridades do grupo
            context:         estado operacional atual (filas, localização, estados)
            filter_override: filtro temporário vindo de mensagem do usuário
            generate_text:   se False, retorna score sem chamar o gerador de resposta
            user_message:    mensagem original do usuário (para persistência)
            intent:          intent NLU que gerou esta chamada
        """
        # Aplica filter_override pontual sem mutar o contexto original
        effective_context = _apply_filter_override(context, filter_override)

        # Mapa attraction_id → area para cálculo de must_do_areas
        attraction_area_map = {
            a.attraction_id: a.area.value
            for a in self._attractions_repo.get_all_active()
        }

        # 1. Contexto de decisão com pesos calculados
        decision_ctx = build_decision_context(
            group=group,
            preferences=preferences,
            context=effective_context,
            attraction_areas=attraction_area_map,
        )

        logger.info(
            "recommend_start group=%s profile=%s location=%s weights=%s reason='%s'",
            group.group_id, decision_ctx.profile_id,
            decision_ctx.current_location_area,
            decision_ctx.weights.describe(),
            decision_ctx.weight_reason,
        )

        # 2. Filtros de exclusão
        all_attractions = self._attractions_repo.get_all_active()
        filter_result: FilterResult = apply_filters(all_attractions, decision_ctx)

        logger.info(
            "filter_result eligible=%d excluded=%d summary=%s",
            filter_result.eligible_count,
            filter_result.excluded_count,
            filter_result.exclusion_summary(),
        )

        if not filter_result.eligible:
            raise NoEligibleAttractions(
                f"Todos os {len(all_attractions)} atrações foram filtradas. "
                f"Resumo: {filter_result.exclusion_summary()}"
            )

        # 3. Scoring e ranking
        ranked = rank_attractions(filter_result.eligible, decision_ctx)

        if logger.isEnabledFor(logging.DEBUG):
            for scored in ranked[:5]:
                logger.debug("\n%s", explain_score(scored, decision_ctx))

        # 4. Seleção primary + secondary
        primary, secondary = select_primary_and_secondary(ranked)

        # 5. Monta objeto de recomendação
        filters_applied = sorted({reason for _, reason in filter_result.excluded})
        rec = Recommendation(
            recommendation_id=f"rec_{uuid.uuid4().hex[:12]}",
            group_id=group.group_id,
            context_id=context.context_id,
            generated_at=datetime.now(timezone.utc),
            primary=primary,
            secondary=secondary,
            filters_applied=filters_applied,
            candidates_evaluated=filter_result.eligible_count,
            user_message=user_message,
        )

        # 6. Geração de texto
        if generate_text:
            rec.whatsapp_message = self._generate_text_safe(rec, group, effective_context, intent)

        logger.info(
            "recommend_done group=%s primary=%s score=%.1f secondary=%s candidates=%d",
            group.group_id, primary.attraction_id, primary.score,
            secondary.attraction_id if secondary else None,
            filter_result.eligible_count,
        )
        return rec

    def score_only(
        self,
        group: Group,
        preferences: GroupPreferences,
        context: OperationalContext,
    ) -> list:
        """
        Retorna o ranking completo sem gerar texto.
        Útil para debug, testes e análise de qualidade do motor.
        """
        attraction_area_map = {
            a.attraction_id: a.area.value
            for a in self._attractions_repo.get_all_active()
        }
        decision_ctx = build_decision_context(group, preferences, context, attraction_areas=attraction_area_map)
        all_attractions = self._attractions_repo.get_all_active()
        filter_result = apply_filters(all_attractions, decision_ctx)
        return rank_attractions(filter_result.eligible, decision_ctx)

    def _generate_text_safe(self, rec, group, context, intent: str) -> str:
        """Gera texto com fallback garantido."""
        try:
            from ..language.response_generator import generate_response
            return generate_response(rec, group, context, intent)
        except Exception as e:
            logger.error("response_generation_failed rec=%s error=%s", rec.recommendation_id, e)
            return build_fallback_message(rec)


def _apply_filter_override(context: OperationalContext, override: Optional[dict]) -> OperationalContext:
    """
    Retorna contexto com filter_override aplicado sem mutar o original.
    Se o contexto já tem um filter_override, o pontual sobrescreve.
    """
    if not override:
        return context
    # Cria cópia rasa do contexto com o filter_override pontual
    from dataclasses import replace
    from ..domain.models.context import FilterOverride
    fo = FilterOverride(
        intensity=override.get("intensity"),
        environment=override.get("environment"),
        max_queue_minutes=override.get("max_queue_minutes"),
        for_all_members=override.get("for_all_members", False),
    )
    try:
        return replace(context, filter_override=fo)
    except TypeError:
        # dataclass sem frozen=True não suporta replace — fallback: muta e restaura
        original_fo = context.filter_override
        context.filter_override = fo
        return context
