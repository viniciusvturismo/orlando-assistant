"""
response_generator.py — Entry point do gerador de resposta.

FLUXO:
  1. Assembler determinístico (sempre executado, sempre produz resposta)
  2. LLM polish (opcional, ativado quando USE_LLM=True e chave disponível)
     → recebe a mensagem do assembler como rascunho e pede refinamento
     → nunca descarta a estrutura — apenas melhora o texto
     → se falhar, retorna o texto do assembler sem modificação

A separação garante que o sistema nunca fica sem resposta.
O LLM é um "polidor", não o gerador principal.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from ..domain.models import Recommendation
from ..domain.models.group import Group, GroupPreferences
from ..domain.models.context import OperationalContext
from ..domain.enums import IntentType
from .response_assembler import (
    assemble_get_rec, assemble_check_in, assemble_mark_done,
    assemble_eval_queue, assemble_update_state, assemble_question,
)
from .response_templates import (
    attraction_name, end_of_day_prefix, state_acknowledgment,
)
from .fallback_templates import build_fallback_message

logger = logging.getLogger(__name__)

import os as _os
USE_LLM = _os.environ.get("USE_LLM", "true").lower() not in ("false", "0", "no")
# Overridden by USE_LLM env var — set USE_LLM=false to disable LLM polish
MAX_CHARS = 480               # limite máximo da mensagem final


def generate_response(
    recommendation: Recommendation,
    group: Group,
    context: OperationalContext,
    intent: str = "GET_REC",
    nlu_extras: Optional[dict] = None,
) -> str:
    """
    Gera mensagem final de WhatsApp em PT-BR.

    Args:
        recommendation: objeto de recomendação com primary, secondary e scores
        group:          grupo visitante com membros e perfil
        context:        contexto operacional atual
        intent:         intenção NLU que originou esta resposta
        nlu_extras:     dados extras extraídos pelo NLU (sentiment, attraction_slug, etc.)

    Retorna sempre uma string válida — nunca propaga exceções.
    """
    extras = nlu_extras or {}

    try:
        # 1. Assembler determinístico — gera a mensagem base
        assembled = _assemble_by_intent(
            intent=intent,
            recommendation=recommendation,
            group=group,
            context=context,
            extras=extras,
        )

        if not assembled:
            return build_fallback_message(recommendation)

        # 2. LLM polish (opcional)
        if USE_LLM:
            polished = _try_llm_polish(assembled, recommendation, group, context, intent)
            if polished:
                return _enforce_limits(polished)

        return _enforce_limits(assembled)

    except Exception as e:
        logger.error("response_generator_failed rec=%s error=%s", recommendation.recommendation_id, e, exc_info=True)
        return build_fallback_message(recommendation)


# ─────────────────────────────────────────────────────────────────────────────
# ROTEAMENTO POR INTENÇÃO
# ─────────────────────────────────────────────────────────────────────────────

def _assemble_by_intent(
    intent: str,
    recommendation: Recommendation,
    group: Group,
    context: OperationalContext,
    extras: dict,
) -> str:
    active_states = [s.value if hasattr(s, "value") else s for s in context.active_states]
    hours = context.hours_until_close()
    profile_id = group.profile_id.value if group.profile_id else "P4"

    # Prefixo situacional compartilhado entre intents
    situational_prefix = _build_situational_prefix(active_states, hours)

    if intent == "CHECK_IN":
        return assemble_check_in(group)

    if intent == "MARK_DONE":
        attraction_slug = extras.get("attraction_slug")
        sentiment = extras.get("sentiment")
        if attraction_slug:
            return assemble_mark_done(recommendation, group, context, attraction_slug, sentiment)
        return assemble_get_rec(recommendation, group, context, prefix=situational_prefix)

    if intent == "EVAL_QUEUE":
        reported_wait = extras.get("reported_wait_minutes")
        max_queue = getattr(
            context, "_preferences_max_queue", group.min_child_height and 45 or 45
        )
        if reported_wait is not None:
            return assemble_eval_queue(recommendation, group, context, reported_wait, max_queue)
        return assemble_get_rec(recommendation, group, context, prefix=situational_prefix)

    if intent == "UPDATE_STATE":
        return assemble_update_state(active_states, recommendation, group, context)

    if intent == "QUESTION":
        attraction_slug = extras.get("attraction_slug")
        aspect = extras.get("question_aspect")
        attraction_data = extras.get("attraction_data", {})
        current_wait = extras.get("current_wait")
        if attraction_slug:
            return assemble_question(attraction_slug, aspect, attraction_data, current_wait)

    # GET_REC, FILTER_REQ, UPDATE_LOC e fallback
    return assemble_get_rec(recommendation, group, context, prefix=situational_prefix)


def _build_situational_prefix(active_states: list[str], hours_until_close: float) -> Optional[str]:
    """Prefixo situacional que aparece antes da recomendação principal."""
    eod = end_of_day_prefix(hours_until_close)
    if eod:
        return eod
    comfort = {"tired", "hungry", "hot", "cranky", "needs_rest"}
    if set(active_states) & comfort:
        return state_acknowledgment(active_states)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# LLM POLISH — opcional, melhora o texto sem mudar a estrutura
# ─────────────────────────────────────────────────────────────────────────────

_POLISH_PROMPT = """Você é o assistente de parques da Disney para famílias brasileiras.

Receba o RASCUNHO abaixo — uma mensagem de WhatsApp já estruturada — e refine o texto:
- Mantenha EXATAMENTE os 4 blocos: ✅ opção principal, 🔄 alternativa, 💡 motivo, 📍 orientação
- Melhore a naturalidade do PT-BR sem alterar os dados (nome, fila, tempo de caminhada)
- Tom: amigo que conhece o parque — direto, humano, sem exagero
- Máximo 8 linhas, máximo 320 caracteres
- Não invente informações que não estão no rascunho
- Não use negrito, itálico ou markdown
- Retorne APENAS o texto final da mensagem, sem explicações

RASCUNHO:
{draft}

CONTEXTO:
{context}"""


def _try_llm_polish(
    draft: str,
    rec: Recommendation,
    group: Group,
    context: OperationalContext,
    intent: str,
) -> Optional[str]:
    """Tenta polir o rascunho com LLM. Retorna None em qualquer falha."""
    try:
        from ..infra.external.claude_client import get_claude_client

        prompt_path = Path(__file__).parent / "prompts" / "response_prompt.txt"
        system_prompt = (
            prompt_path.read_text(encoding="utf-8")
            if prompt_path.exists()
            else _POLISH_PROMPT
        )

        context_summary = _build_context_summary(rec, group, context, intent)
        user_content = _POLISH_PROMPT.format(draft=draft, context=context_summary)

        polished = get_claude_client().complete(
            system_prompt=system_prompt if prompt_path.exists() else
                "Você é um assistente de parques da Disney. Refine a mensagem de WhatsApp mantendo estrutura e dados.",
            user_message=user_content,
            max_tokens=350,
        )

        polished = polished.strip()
        if len(polished) < 20:  # resposta suspeita
            return None

        logger.debug("llm_polish applied len_before=%d len_after=%d", len(draft), len(polished))
        return polished

    except Exception as e:
        logger.debug("llm_polish_skipped reason=%s", e)
        return None


def _build_context_summary(rec: Recommendation, group: Group, ctx: OperationalContext, intent: str) -> str:
    """Resumo compacto do contexto para o prompt do LLM."""
    profile_id = group.profile_id.value if group.profile_id else "P4"
    members = group.members
    adults = sum(1 for m in members if m.role == "adult")
    children = [m for m in members if m.role == "child"]
    ages = [str(c.age) for c in children if c.age]
    states = [s.value if hasattr(s, "value") else s for s in ctx.active_states]

    return json.dumps({
        "intent": intent,
        "profile": profile_id,
        "members": f"{adults} adultos" + (f", crianças {','.join(ages)} anos" if ages else ""),
        "location": ctx.current_location_area,
        "time": ctx.current_datetime.strftime("%H:%M"),
        "weather": ctx.weather.value if ctx.weather else "unknown",
        "active_states": states,
        "primary_reason": rec.primary.primary_reason,
        "hours_until_close": ctx.hours_until_close(),
    }, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# UTILITÁRIOS
# ─────────────────────────────────────────────────────────────────────────────

def _enforce_limits(text: str) -> str:
    """Garante que a mensagem respeita os limites de tamanho."""
    if len(text) <= MAX_CHARS:
        return text

    # Trunca na última linha que cabe
    lines = text.split("\n")
    result = []
    total = 0
    for line in lines:
        if total + len(line) + 1 > MAX_CHARS:
            break
        result.append(line)
        total += len(line) + 1

    return "\n".join(result).rstrip()
