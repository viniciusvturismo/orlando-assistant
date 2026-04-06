"""
nlu.py — Interpretador de mensagens do WhatsApp.

ARQUITETURA EM DUAS CAMADAS:

  Camada 1 — Regras + heurísticas (sempre ativo):
    Rápido, determinístico, sem custo de API, sem latência.
    Cobre a maioria dos casos do cotidiano do parque.
    Resultado: NLUResult com confidence 0.0–0.98.

  Camada 2 — LLM fallback (opcional, quando confidence < CONFIDENCE_THRESHOLD):
    Acionado apenas para mensagens ambíguas ou fora do vocabulário.
    Usa Claude API com o nlu_prompt.txt de sistema.
    Requer ANTHROPIC_API_KEY no ambiente.

FLUXO:
  mensagem → rule_based_interpret()
    → se confidence >= CONFIDENCE_THRESHOLD: retorna resultado
    → se confidence < CONFIDENCE_THRESHOLD: chama llm_interpret()
      → se LLM falha: retorna resultado da camada 1 (graceful degradation)

CONFIGURAÇÃO:
  CONFIDENCE_THRESHOLD — abaixo disso aciona o LLM
  USE_LLM              — desativa o LLM completamente (útil em dev/testes)
"""

import logging
from typing import Optional

from ..domain.models import NLUResult, LocationHint, AttractionRef, MemberMention
from ..domain.enums import IntentType, QuestionAspect
from .nlu_knowledge import (
    normalize,
    resolve_area,
    resolve_attraction,
    extract_states,
    extract_filter_override,
    extract_members,
    extract_wait_minutes,
    extract_sentiment,
)
from .nlu_intent import classify_intent

logger = logging.getLogger(__name__)

# ── Configuração ───────────────────────────────────────────────────────────────
CONFIDENCE_THRESHOLD = 0.70  # abaixo disso, aciona LLM se disponível
USE_LLM = True               # desativar para testes sem API key


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def interpret_message(
    user_message: str,
    session_context: Optional[dict] = None,
) -> NLUResult:
    """
    Interpreta uma mensagem de WhatsApp e retorna NLUResult estruturado.

    Nunca propaga exceções — retorna UNKNOWN com needs_clarification=True
    em caso de falha completa.

    Args:
        user_message:    texto bruto recebido do WhatsApp
        session_context: dict com estado da sessão (park, location, profile, etc.)
                         Enriquece a interpretação mas não é obrigatório.
    """
    if not user_message or not user_message.strip():
        return _empty_result(user_message or "")

    try:
        result = rule_based_interpret(user_message, session_context)

        logger.info(
            "nlu_rule_based intent=%s confidence=%.2f matched=%s",
            result.intent.value,
            result.confidence,
            result.ambiguities,
        )

        # Aciona LLM se confiança baixa e LLM disponível
        if result.confidence < CONFIDENCE_THRESHOLD and USE_LLM:
            result = _try_llm_fallback(user_message, session_context, result)

        return result

    except Exception as e:
        logger.error("nlu_failed message='%s' error=%s", user_message[:60], e, exc_info=True)
        return NLUResult(
            intent=IntentType.UNKNOWN,
            confidence=0.0,
            raw_message=user_message,
            needs_clarification=True,
            clarification_question="Pode me contar onde vocês estão ou o que querem fazer agora?",
        )


# ─────────────────────────────────────────────────────────────────────────────
# CAMADA 1 — REGRAS E HEURÍSTICAS
# ─────────────────────────────────────────────────────────────────────────────

def rule_based_interpret(
    user_message: str,
    session_context: Optional[dict] = None,
) -> NLUResult:
    """
    Interpreta a mensagem usando regras, dicionários e heurísticas.
    Função pura — sem I/O. Testável sem mocks.

    Extração é independente da classificação de intenção:
    cada campo é extraído mesmo que a intenção seja incerta,
    pois pode ser usado para enriquecer o contexto.
    """
    norm = normalize(user_message)

    # 1. Classifica intenção
    classification = classify_intent(user_message)
    intent = classification.intent
    confidence = classification.confidence

    # 2. Extrai localização
    location = _extract_location(norm, user_message)

    # 3. Extrai referência de atração
    attraction_ref = _extract_attraction_ref(norm, user_message)

    # 4. Extrai estado do grupo
    group_state = extract_states(user_message)

    # 5. Extrai filtro/restrição momentânea
    filter_override = extract_filter_override(user_message)

    # 6. Extrai membros mencionados
    members_raw = extract_members(user_message)
    members_mentioned = [
        MemberMention(role=m["role"], age=m.get("age"), height_cm=m.get("height_cm"))
        for m in members_raw
    ]

    # 7. Extrai tempo de fila reportado
    reported_wait = extract_wait_minutes(user_message)

    # 8. Extrai aspecto de dúvida (só para QUESTION)
    question_aspect = _extract_question_aspect(norm) if intent == IntentType.QUESTION else None

    # 9. Extrai sentimento (relevante para MARK_DONE)
    sentiment = extract_sentiment(user_message) if intent == IntentType.MARK_DONE else None

    # 10. Detecta ambiguidades e necessidade de clarificação
    ambiguities, needs_clarification, clarification_q = _assess_ambiguities(
        intent, confidence, location, attraction_ref, classification,
    )

    return NLUResult(
        intent=intent,
        confidence=confidence,
        raw_message=user_message,
        location=location,
        attraction_ref=attraction_ref,
        group_state=group_state,
        filter_override=filter_override,
        members_mentioned=members_mentioned,
        reported_wait_minutes=reported_wait,
        question_aspect=question_aspect,
        sentiment=sentiment,
        ambiguities=ambiguities,
        needs_clarification=needs_clarification,
        clarification_question=clarification_q,
    )


# ── Extratores individuais ─────────────────────────────────────────────────────

def _extract_location(norm: str, original: str) -> Optional[LocationHint]:
    """
    Tenta resolver uma área do parque na mensagem.
    Retorna LocationHint apenas se encontrou algo concreto.
    """
    slug, ref_text = resolve_area(original)
    if slug:
        return LocationHint(zone=slug, ref_text=ref_text)

    # Segunda tentativa: área mencionada após "estamos na/no/em"
    import re
    match = re.search(r"estamos\s+(?:na|no|em|perto\s+da?o?)\s+(\w[\w\s]*)", norm)
    if match:
        slug2, ref2 = resolve_area(match.group(1))
        if slug2:
            return LocationHint(zone=slug2, ref_text=match.group(1).strip())

    return None


def _extract_attraction_ref(norm: str, original: str) -> Optional[AttractionRef]:
    """
    Tenta resolver uma atração mencionada na mensagem.
    Retorna AttractionRef com slug se identificada, ou com raw=texto se não.
    """
    slug, ref_text = resolve_attraction(original)
    if slug:
        return AttractionRef(slug=slug, raw=ref_text)

    # Se houve referência vaga ("aquela montanha russa famosa"), captura o texto
    import re
    vague = re.search(
        r"(montanha russa|brinquedo|atracao|atração|ride)\s+(\w[\w\s]*?)(?:\?|,|\.|\s+$)",
        norm
    )
    if vague:
        return AttractionRef(slug=None, raw=vague.group(0).strip())

    return None


def _extract_question_aspect(norm: str) -> Optional[QuestionAspect]:
    """Identifica o que o usuário quer saber sobre a atração."""
    import re

    if re.search(r"\b(molha|molhar|fica molhado|agua)\b", norm):
        return QuestionAspect.WETNESS
    if re.search(r"\b(altura|alto|centimetro|cm|mede)\b", norm):
        return QuestionAspect.HEIGHT_REQ
    if re.search(r"\b(assusta|medo|escuro|assustador|pesado)\b", norm):
        return QuestionAspect.SCARE_FACTOR
    if re.search(r"\b(quanto tempo|dura|demora|duracao|duração)\b", norm):
        return QuestionAspect.DURATION
    if re.search(r"\b(cadeirante|acessibilidade|deficiencia|deficiência)\b", norm):
        return QuestionAspect.ACCESSIBILITY
    if re.search(r"\b(forte|intensa|intenso|radical|enjoo|enjôo)\b", norm):
        return QuestionAspect.INTENSITY_INFO
    if re.search(r"\b(fila|espera|demora|minutos|quanto demora)\b", norm):
        return QuestionAspect.WAIT_ESTIMATE
    return None


def _assess_ambiguities(
    intent: IntentType,
    confidence: float,
    location: Optional[LocationHint],
    attraction_ref: Optional[AttractionRef],
    classification,
) -> tuple[list[str], bool, Optional[str]]:
    """
    Detecta ambiguidades e decide se clarificação é necessária.
    Retorna (ambiguities, needs_clarification, clarification_question).
    """
    ambiguities = []
    needs_clarification = False
    clarification_q = None

    if intent == IntentType.UNKNOWN:
        needs_clarification = True
        clarification_q = "Pode me contar onde vocês estão ou o que querem fazer agora?"
        return ambiguities, needs_clarification, clarification_q

    # Confiança muito baixa
    if confidence < 0.50:
        needs_clarification = True
        clarification_q = _build_clarification(intent, location, attraction_ref)
        ambiguities.append(f"confidence_low_{confidence:.2f}")

    # Intenção GET_REC sem localização — não bloqueia, mas sinaliza
    if intent == IntentType.GET_REC and not location:
        ambiguities.append("location_not_found")

    # EVAL_QUEUE sem atração identificada
    if intent == IntentType.EVAL_QUEUE and (not attraction_ref or not attraction_ref.slug):
        needs_clarification = True
        clarification_q = "Qual atração você quer saber se vale a pena?"
        ambiguities.append("attraction_not_identified")

    # QUESTION sem atração identificada
    if intent == IntentType.QUESTION and (not attraction_ref or not attraction_ref.slug):
        needs_clarification = True
        clarification_q = "Qual atração você quer saber?"
        ambiguities.append("question_target_unclear")

    # Mais de dois candidatos com score alto (ambiguidade real)
    top_scores = sorted(classification.scores.values(), reverse=True)
    if len(top_scores) >= 2 and top_scores[1] > 0 and top_scores[0] / top_scores[1] < 1.3:
        second_intent = [k for k, v in classification.scores.items() if v == top_scores[1]]
        if second_intent:
            ambiguities.append(f"also_could_be_{second_intent[0]}")

    return ambiguities, needs_clarification, clarification_q


def _build_clarification(
    intent: IntentType,
    location: Optional[LocationHint],
    attraction_ref: Optional[AttractionRef],
) -> str:
    """Gera pergunta de clarificação específica baseada na intenção e no que falta."""
    if intent == IntentType.GET_REC and not location:
        return "Onde vocês estão agora no parque?"
    if intent == IntentType.EVAL_QUEUE:
        return "Qual atração você quer avaliar a fila?"
    if intent == IntentType.QUESTION:
        return "Sobre qual atração você quer saber?"
    return "Pode me contar o que vocês precisam agora?"


# ─────────────────────────────────────────────────────────────────────────────
# CAMADA 2 — FALLBACK LLM
# ─────────────────────────────────────────────────────────────────────────────

def _try_llm_fallback(
    user_message: str,
    session_context: Optional[dict],
    rule_result: NLUResult,
) -> NLUResult:
    """
    Tenta enriquecer o resultado com LLM quando confiança é baixa.
    Se falhar, retorna o resultado da camada 1 sem modificação.
    """
    import json
    from pathlib import Path

    try:
        from ..infra.external.claude_client import get_claude_client

        prompt_path = Path(__file__).parent / "prompts" / "nlu_prompt.txt"
        system_prompt = (
            prompt_path.read_text(encoding="utf-8") if prompt_path.exists()
            else _minimal_llm_prompt()
        )

        user_content = _build_llm_input(user_message, session_context, rule_result)
        raw = get_claude_client().complete(system_prompt, user_content, max_tokens=600)
        llm_result = _parse_llm_response(raw, user_message)

        # Merge: LLM preenche o que as regras não conseguiram
        return _merge_results(rule_result, llm_result)

    except Exception as e:
        logger.warning("llm_fallback_failed error=%s — using rule result", e)
        return rule_result


def _build_llm_input(message: str, ctx: Optional[dict], rule_result: NLUResult) -> str:
    """Monta o prompt de usuário com contexto de sessão e resultado das regras."""
    parts = []
    if ctx:
        parts.append("CONTEXTO DA SESSÃO:")
        for k, v in ctx.items():
            parts.append(f"- {k}: {v}")
        parts.append("")

    parts.append("RESULTADO DAS REGRAS (parcial, pode estar incompleto):")
    parts.append(f"- intent detectado: {rule_result.intent.value} (confidence={rule_result.confidence:.2f})")
    if rule_result.location:
        parts.append(f"- location: {rule_result.location.zone}")
    if rule_result.ambiguities:
        parts.append(f"- ambiguidades: {rule_result.ambiguities}")
    parts.append("")
    parts.append(f"MENSAGEM RECEBIDA:\n{message}")
    return "\n".join(parts)


def _parse_llm_response(raw: str, original: str) -> NLUResult:
    """Parseia o JSON retornado pelo LLM e converte para NLUResult."""
    import json

    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.error("llm_json_parse_failed raw=%s", raw[:200])
        return NLUResult(intent=IntentType.UNKNOWN, confidence=0.0, raw_message=original)

    location = None
    if loc := data.get("location"):
        location = LocationHint(zone=loc.get("zone"), ref_text=loc.get("ref_text"))

    attraction_ref = None
    if ar := data.get("attraction_ref"):
        attraction_ref = AttractionRef(slug=ar.get("slug"), raw=ar.get("raw"))

    members = [
        MemberMention(role=m["role"], age=m.get("age"), height_cm=m.get("height_cm"))
        for m in data.get("members_mentioned", [])
    ]

    qa = None
    if raw_qa := data.get("question_aspect"):
        try:
            qa = QuestionAspect(raw_qa)
        except ValueError:
            pass

    try:
        intent = IntentType(data.get("intent", "UNKNOWN"))
    except ValueError:
        intent = IntentType.UNKNOWN

    return NLUResult(
        intent=intent,
        confidence=float(data.get("confidence", 0.7)),
        raw_message=original,
        location=location,
        attraction_ref=attraction_ref,
        group_state=data.get("group_state", []),
        filter_override=data.get("filter_override"),
        members_mentioned=members,
        reported_wait_minutes=data.get("reported_wait_minutes"),
        question_aspect=qa,
        sentiment=data.get("sentiment"),
        ambiguities=data.get("ambiguities", []),
        needs_clarification=bool(data.get("needs_clarification", False)),
        clarification_question=data.get("clarification_question"),
    )


def _merge_results(rule: NLUResult, llm: NLUResult) -> NLUResult:
    """
    Combina resultado das regras com resultado do LLM.
    LLM prevalece em campos onde as regras retornaram None/vazio.
    Intenção do LLM prevalece apenas se confidence for maior.
    """
    from dataclasses import replace

    intent = llm.intent if llm.confidence > rule.confidence else rule.intent
    confidence = max(rule.confidence, llm.confidence)

    return NLUResult(
        intent=intent,
        confidence=min(0.99, confidence),
        raw_message=rule.raw_message,
        location=rule.location or llm.location,
        attraction_ref=rule.attraction_ref or llm.attraction_ref,
        group_state=rule.group_state or llm.group_state,
        filter_override=rule.filter_override or llm.filter_override,
        members_mentioned=rule.members_mentioned or llm.members_mentioned,
        reported_wait_minutes=rule.reported_wait_minutes or llm.reported_wait_minutes,
        question_aspect=rule.question_aspect or llm.question_aspect,
        sentiment=rule.sentiment or llm.sentiment,
        ambiguities=list(set(rule.ambiguities + llm.ambiguities)),
        needs_clarification=llm.needs_clarification,
        clarification_question=llm.clarification_question or rule.clarification_question,
    )


def _minimal_llm_prompt() -> str:
    return (
        "You are a message interpreter for a Disney park assistant for Brazilian families. "
        "Read the message and return JSON with: intent (CHECK_IN|GET_REC|EVAL_QUEUE|UPDATE_LOC|"
        "UPDATE_STATE|FILTER_REQ|MARK_DONE|QUESTION|UNKNOWN), confidence (0.0-1.0), "
        "raw_message, location {zone, ref_text}, attraction_ref {slug, raw}, "
        "group_state [], filter_override {}, members_mentioned [], "
        "reported_wait_minutes, question_aspect, sentiment, ambiguities [], "
        "needs_clarification, clarification_question. "
        "Return ONLY valid JSON. Never invent data not present in the message."
    )


def _empty_result(message: str) -> NLUResult:
    return NLUResult(
        intent=IntentType.UNKNOWN,
        confidence=0.0,
        raw_message=message,
        needs_clarification=True,
        clarification_question="Pode me contar o que vocês precisam?",
    )
