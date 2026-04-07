"""
message_router.py — Roteador de mensagens (canal → handlers de domínio).

RESPONSABILIDADE:
  Receber InboundMessage, acionar NLU, delegar ao handler correto
  e retornar OutboundMessage. Orquestra mas não executa lógica de domínio.

CONTRATO COM O CANAL:
  Entrada : InboundMessage  (de qualquer canal)
  Saída   : OutboundMessage (para qualquer canal)
  Garantia: NUNCA propaga exceção. Erros viram OutboundMessage com fallback_used=True.

ADICIONANDO UM NOVO INTENT:
  1. Declare o handler: async def _handle_<intent>(inbound, nlu) -> HandlerResult
  2. Registre em _HANDLERS
  3. Adicione ao test_message_router.py
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from ..language.nlu import interpret_message
from ..language.fallback_templates import (
    build_clarification_message, build_checkin_prompt, build_error_message,
)
from ..domain.enums import IntentType
from .contracts import InboundMessage, OutboundMessage, ChannelType, DeliveryStatus

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# RESULTADO DE HANDLER — o que cada handler devolve ao router
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class HandlerResult:
    """
    O que cada handler de intent retorna.
    O router converte isso em OutboundMessage.
    """
    text:              str
    intent_handled:    str    = ""
    recommendation_id: Optional[str] = None
    used_llm:          bool   = False
    needs_followup:    bool   = False
    location_updated:  Optional[str] = None   # nova área, se UPDATE_LOC foi processado


# ─────────────────────────────────────────────────────────────────────────────
# ROUTER PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

class MessageRouter:
    """
    Orquestra o fluxo de uma mensagem recebida até a resposta final.

    Fluxo interno:
      InboundMessage
        → NLU (interpret_message)
        → handler por intent
        → HandlerResult
        → OutboundMessage
    """

    async def route(self, inbound: InboundMessage) -> OutboundMessage:
        """
        Ponto de entrada principal. Nunca propaga exceção.
        """
        # Contexto de sessão para o NLU
        # Busca o parque do grupo no banco
        _park_name = "Orlando"
        if inbound.group_id:
            try:
                from ..infra.database.connection import get_connection
                with get_connection() as _conn:
                    _row = _conn.execute(
                        "SELECT park_id FROM groups WHERE group_id = ?",
                        (inbound.group_id,)
                    ).fetchone()
                    if _row and _row["park_id"]:
                        _park_id = _row["park_id"]
                        _park_names = {
                            "magic_kingdom": "Magic Kingdom",
                            "epcot": "EPCOT",
                            "hollywood_studios": "Hollywood Studios",
                            "animal_kingdom": "Animal Kingdom",
                            "universal_studios": "Universal Studios Florida",
                            "islands_of_adventure": "Islands of Adventure",
                            "epic_universe": "Epic Universe",
                            "seaworld": "SeaWorld Orlando",
                            "busch_gardens": "Busch Gardens Tampa Bay",
                        }
                        _park_name = _park_names.get(_park_id, "Orlando")
            except Exception:
                pass

        session_ctx = {
            "park": _park_name,
            "group_id": inbound.group_id or "novo",
            "channel": inbound.channel.value,
        }

        # ── Interpretação ──────────────────────────────────────────────────
        nlu = interpret_message(inbound.raw_text, session_ctx)

        logger.debug(
            "nlu phone=%s intent=%s conf=%.2f location=%s attraction=%s states=%s",
            inbound.phone, nlu.intent.value, nlu.confidence,
            nlu.location_zone, nlu.attraction_slug, nlu.group_state,
        )

        # ── Clarificação necessária ────────────────────────────────────────
        if nlu.needs_clarification:
            return self._build_outbound(
                inbound=inbound,
                text=build_clarification_message(nlu.clarification_question),
                intent="CLARIFICATION",
                needs_followup=True,
            )

        # ── Novo usuário ───────────────────────────────────────────────────
        if inbound.is_new_user:
            result = await _handle_new_user(inbound, nlu)
            return self._build_outbound(inbound, **result.__dict__)

        # ── Roteamento por intent ──────────────────────────────────────────
        handler = _HANDLERS.get(nlu.intent, _handle_unknown)
        try:
            result = await handler(inbound, nlu)
        except Exception as e:
            logger.error(
                "handler_failed intent=%s phone=%s error=%s",
                nlu.intent.value, inbound.phone, e, exc_info=True,
            )
            return self._build_outbound(
                inbound=inbound,
                text=build_error_message(),
                intent=nlu.intent.value,
                fallback_used=True,
            )

        return self._build_outbound(inbound, **result.__dict__)

    def _build_outbound(
        self,
        inbound: InboundMessage,
        text: str,
        intent_handled: str = "",
        recommendation_id: Optional[str] = None,
        used_llm: bool = False,
        fallback_used: bool = False,
        needs_followup: bool = False,
        location_updated: Optional[str] = None,
        **_,
    ) -> OutboundMessage:
        return OutboundMessage(
            to_phone=inbound.phone,
            channel=inbound.channel,
            text=text,
            intent_handled=intent_handled,
            recommendation_id=recommendation_id,
            used_llm=used_llm,
            fallback_used=fallback_used,
            needs_followup=needs_followup,
            delivery_status=DeliveryStatus.QUEUED,
        )


# ─────────────────────────────────────────────────────────────────────────────
# HANDLERS POR INTENT
# Cada função: async (inbound, nlu) -> HandlerResult
# Nunca propaga exceção — trata internamente ou deixa o router tratar.
# ─────────────────────────────────────────────────────────────────────────────

async def _handle_new_user(inbound: InboundMessage, nlu) -> HandlerResult:
    from ..services.group_service import GroupService
    from .session_manager import get_session_manager

    service = GroupService()
    group, _ = service.get_or_create(whatsapp_number=inbound.phone)

    get_session_manager().register(inbound.phone, group.group_id)

    if nlu.members_mentioned:
        from ..domain.models import Member
        members = [Member(role=m.role, age=m.age, height_cm=m.height_cm)
                   for m in nlu.members_mentioned]
        service.update_members(group.group_id, members)

    # Pega o nome do parque para a mensagem de boas-vindas
    _welcome_park = "Orlando"
    try:
        from ..infra.database.connection import get_connection
        with get_connection() as _conn:
            _row = _conn.execute(
                "SELECT park_id FROM groups WHERE group_id = ?",
                (group.group_id,)
            ).fetchone()
            if _row:
                _pid = _row["park_id"]
                _pmap = {
                    "magic_kingdom": "Magic Kingdom",
                    "epcot": "EPCOT",
                    "hollywood_studios": "Hollywood Studios",
                    "animal_kingdom": "Animal Kingdom",
                    "universal_studios": "Universal Studios Florida",
                    "islands_of_adventure": "Islands of Adventure",
                    "epic_universe": "Epic Universe",
                    "seaworld": "SeaWorld Orlando",
                    "busch_gardens": "Busch Gardens Tampa Bay",
                }
                _welcome_park = _pmap.get(_pid, "Orlando")
    except Exception:
        pass

    return HandlerResult(
        text=build_checkin_prompt(_welcome_park),
        intent_handled="CHECK_IN",
        needs_followup=True,
    )


async def _handle_checkin(inbound: InboundMessage, nlu) -> HandlerResult:
    from ..services.group_service import GroupService
    from ..domain.models import Member

    service = GroupService()
    if nlu.members_mentioned:
        members = [Member(role=m.role, age=m.age, height_cm=m.height_cm)
                   for m in nlu.members_mentioned]
        service.update_members(inbound.group_id, members)

    return HandlerResult(
        text=build_checkin_prompt(),
        intent_handled="CHECK_IN",
        needs_followup=True,
    )


async def _handle_get_rec(inbound: InboundMessage, nlu) -> HandlerResult:
    from ..services.group_service import GroupService
    from ..services.context_service import ContextService
    from ..services.recommendation_service import RecommendationService
    from ..domain.exceptions.domain_exceptions import NoContextActive, GroupSetupIncomplete

    gs = GroupService()
    cs = ContextService()
    rs = RecommendationService()

    try:
        group = gs.get_by_id(inbound.group_id)
        gs.assert_setup_complete(group)
        prefs = gs.get_preferences(inbound.group_id)
        context = cs.get_active_context(inbound.group_id)
    except GroupSetupIncomplete:
        return HandlerResult(
            text="Ainda precisamos configurar o perfil de vocês. Me conta quem está no grupo e as idades!",
            intent_handled="GET_REC",
            needs_followup=True,
        )
    except NoContextActive:
        return HandlerResult(
            text="Para recomendar, preciso saber onde vocês estão no parque agora. Me conta!",
            intent_handled="GET_REC",
            needs_followup=True,
        )

    # Atualiza localização se NLU extraiu uma
    location_updated = None
    if nlu.location and nlu.location.zone:
        cs.update_location(inbound.group_id, nlu.location.zone)
        context.current_location_area = nlu.location.zone
        location_updated = nlu.location.zone

    rec = rs.recommend(
        group=group,
        preferences=prefs,
        context=context,
        filter_override=nlu.filter_override,
        generate_text=True,
        user_message=nlu.raw_message,
        intent=nlu.intent.value,
    )

    return HandlerResult(
        text=rec.whatsapp_message or build_error_message(),
        intent_handled="GET_REC",
        recommendation_id=rec.recommendation_id,
        location_updated=location_updated,
    )


async def _handle_eval_queue(inbound: InboundMessage, nlu) -> HandlerResult:
    if nlu.attraction_ref and nlu.attraction_ref.slug and nlu.reported_wait_minutes is not None:
        from ..services.context_service import ContextService
        try:
            ctx = ContextService().get_active_context(inbound.group_id)
            updated = {**ctx.queue_snapshot, nlu.attraction_ref.slug: nlu.reported_wait_minutes}
            ContextService().update_queues(inbound.group_id, updated)
        except Exception:
            pass
    return await _handle_get_rec(inbound, nlu)


async def _handle_update_loc(inbound: InboundMessage, nlu) -> HandlerResult:
    if nlu.location and nlu.location.zone:
        try:
            from ..services.context_service import ContextService
            ContextService().update_location(inbound.group_id, nlu.location.zone)
        except Exception:
            pass
        return await _handle_get_rec(inbound, nlu)
    return HandlerResult(
        text="Entendido! Me conta mais sobre onde vocês estão.",
        intent_handled="UPDATE_LOC",
        needs_followup=True,
    )


async def _handle_update_state(inbound: InboundMessage, nlu) -> HandlerResult:
    if nlu.group_state:
        try:
            from ..services.context_service import ContextService
            ContextService().apply_group_states(inbound.group_id, nlu.group_state)
        except Exception:
            pass

    comfort_states = {"tired", "hungry", "hot", "needs_rest", "cranky"}
    is_comfort = bool(set(nlu.group_state) & comfort_states)

    if "hungry" in nlu.group_state:
        return HandlerResult(
            text=(
                "Hora de recarregar! 🍕\n\n"
                "Procura um lugar com AC pra comer tranquilo. "
                "Quando estiverem prontos, me avisa que sugiro o próximo."
            ),
            intent_handled="UPDATE_STATE",
            needs_followup=True,
        )

    if is_comfort:
        return await _handle_get_rec(inbound, nlu)

    return await _handle_get_rec(inbound, nlu)


async def _handle_filter_req(inbound: InboundMessage, nlu) -> HandlerResult:
    return await _handle_get_rec(inbound, nlu)


async def _handle_mark_done(inbound: InboundMessage, nlu) -> HandlerResult:
    if nlu.attraction_ref and nlu.attraction_ref.slug:
        try:
            from ..services.context_service import ContextService
            ContextService().mark_attraction_done(inbound.group_id, nlu.attraction_ref.slug)
        except Exception:
            pass

    result = await _handle_get_rec(inbound, nlu)

    # Prefixa com acuse de sentimento se houver
    prefix = ""
    if nlu.sentiment == "positive":
        prefix = "🎢 Anotei! "
    elif nlu.sentiment == "negative":
        prefix = "Anotei — vamos pular essa da próxima vez. "

    if prefix:
        result.text = prefix + result.text
    result.intent_handled = "MARK_DONE"
    return result


async def _handle_question(inbound: InboundMessage, nlu) -> HandlerResult:
    if not (nlu.attraction_ref and nlu.attraction_ref.slug):
        return HandlerResult(
            text="Qual atração você quer saber? Me fala o nome!",
            intent_handled="QUESTION",
            needs_followup=True,
        )

    from ..infra.repositories.attractions_repository import get_attractions_repository
    from ..language.response_assembler import assemble_question

    repo = get_attractions_repository()
    attraction = repo.get_by_id(nlu.attraction_ref.slug)
    if not attraction:
        return HandlerResult(
            text=f"Não encontrei informações sobre '{nlu.attraction_ref.raw}'. Pode confirmar o nome?",
            intent_handled="QUESTION",
            needs_followup=True,
        )

    aspect = nlu.question_aspect.value if nlu.question_aspect else None
    text = assemble_question(
        attraction.attraction_id,
        aspect,
        {
            "min_height_cm": attraction.min_height_cm,
            "tags": attraction.tags,
            "intensity": attraction.intensity.value,
            "duration_minutes": attraction.duration_minutes,
            "description_pt": attraction.description_pt,
            "strategic_notes": attraction.strategic_notes,
            "avg_wait_by_period": attraction.avg_wait_by_period,
        },
    )
    return HandlerResult(text=text, intent_handled="QUESTION")


async def _handle_unknown(inbound: InboundMessage, nlu) -> HandlerResult:
    return HandlerResult(
        text="Pode me contar onde vocês estão ou o que querem fazer agora? Assim consigo ajudar melhor!",
        intent_handled="UNKNOWN",
        needs_followup=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# TABELA DE ROTEAMENTO
# ─────────────────────────────────────────────────────────────────────────────

_HANDLERS = {
    IntentType.CHECK_IN:     _handle_checkin,
    IntentType.GET_REC:      _handle_get_rec,
    IntentType.EVAL_QUEUE:   _handle_eval_queue,
    IntentType.UPDATE_LOC:   _handle_update_loc,
    IntentType.UPDATE_STATE: _handle_update_state,
    IntentType.FILTER_REQ:   _handle_filter_req,
    IntentType.MARK_DONE:    _handle_mark_done,
    IntentType.QUESTION:     _handle_question,
    IntentType.UNKNOWN:      _handle_unknown,
}
