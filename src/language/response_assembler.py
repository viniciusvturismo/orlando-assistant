"""
response_assembler.py — Monta a mensagem de WhatsApp a partir da recomendação.

v1.1 — Correções de qualidade de texto:
  F3: must_do_tight_queue → frase honesta ("vale esperar os X min")
  F4: split_height_warning → nota específica com alturas concretas
  F2: context_note redundante já tratada no scoring_engine (não gera mais)
  Novo: rare_window → frase específica de urgência
"""

from typing import Optional
from ..domain.models import Recommendation, AttractionScore
from ..domain.models.group import Group
from ..domain.models.context import OperationalContext
from .response_templates import (
    attraction_name, reason_phrase, wait_label, walk_label,
    closing_phrase, supporting_phrase, trade_off_phrase,
    context_note_phrase, state_acknowledgment, end_of_day_prefix,
    check_in_greeting, mark_done_acknowledgment,
)


def assemble_get_rec(
    rec: Recommendation,
    group: Group,
    context: OperationalContext,
    prefix: Optional[str] = None,
) -> str:
    profile_id = group.profile_id.value if group.profile_id else "P4"
    active_states = [s.value if hasattr(s, "value") else s for s in context.active_states]
    weather = context.weather.value if context.weather else None
    primary = rec.primary

    lines: list[str] = []

    if prefix:
        lines.append(prefix)
        lines.append("")

    # [A] Opção principal
    p_name = attraction_name(primary.attraction_id)
    p_wait = wait_label(primary.current_wait)
    p_walk = walk_label(primary.walk_minutes)
    lines.append(f"✅ {p_name}")
    lines.append(f"{p_wait} · {p_walk}")

    # [B] Opção secundária
    if rec.secondary and rec.secondary.score >= 50.0:
        sec = rec.secondary
        s_name = attraction_name(sec.attraction_id)
        s_wait = wait_label(sec.current_wait)
        lines.append("")
        lines.append(f"🔄 Alternativa: {s_name}")
        lines.append(s_wait)

    # [C] Motivo
    lines.append("")
    reason_text = _build_reason_phrase(primary, context)
    lines.append(f"💡 {reason_text}")

    # Nota estratégica (já filtrada no scoring_engine para não ser redundante)
    note = context_note_phrase(primary.context_note)
    if note:
        lines.append(note)

    # Trade-off honesto
    tf = trade_off_phrase(primary.trade_off)
    if tf:
        lines.append(tf)

    # v1.1 F4 — rider swap personalizado com alturas concretas
    split_warn = _build_split_warning(primary)
    if split_warn:
        lines.append(split_warn)
    else:
        # Razão de apoio genérica (só se não for redundante com split_warn)
        supp = supporting_phrase(primary.supporting_reasons, weather)
        if supp:
            lines.append(supp)

    # [D] Localização + CTA
    location_hint = _location_hint(primary, context)
    closing = closing_phrase(profile_id)
    lines.append("")
    if location_hint:
        lines.append(f"📍 {location_hint} {closing}")
    else:
        lines.append(f"📍 {closing}")

    return "\n".join(lines)


def assemble_check_in(group: Group) -> str:
    profile_id = group.profile_id.value if group.profile_id else "P4"
    members = group.members
    adults = sum(1 for m in members if m.role == "adult")
    children = [m for m in members if m.role == "child"]
    summary_parts = []
    if adults:
        summary_parts.append(f"{adults} adulto{'s' if adults > 1 else ''}")
    if children:
        ages = [str(c.age) for c in children if c.age]
        if ages:
            summary_parts.append(f"criança{'s' if len(children) > 1 else ''} de {', '.join(ages)} anos")
    summary = ", ".join(summary_parts) or "grupo"
    return check_in_greeting(profile_id, summary)


def assemble_mark_done(
    rec: Recommendation,
    group: Group,
    context: OperationalContext,
    attraction_id: str,
    sentiment: Optional[str],
) -> str:
    ack = mark_done_acknowledgment(attraction_id, sentiment)
    rec_text = assemble_get_rec(rec, group, context)
    return f"{ack}\n\n{rec_text}"


def assemble_eval_queue(
    rec: Recommendation,
    group: Group,
    context: OperationalContext,
    reported_wait: int,
    max_queue: int,
) -> str:
    primary = rec.primary
    p_name = attraction_name(primary.attraction_id)
    if reported_wait <= max_queue * 0.8:
        verdict = f"{reported_wait} min tá bom pra {p_name}."
        return f"✅ {verdict}\n\n{assemble_get_rec(rec, group, context)}"
    else:
        verdict = f"{reported_wait} min tá alto pra {p_name}."
        return f"⏱️ {verdict} Tem opção melhor agora:\n\n{assemble_get_rec(rec, group, context)}"


def assemble_update_state(
    active_states: list[str],
    rec: Optional[Recommendation],
    group: Group,
    context: OperationalContext,
) -> str:
    comfort_states = {"tired", "hungry", "hot", "cranky", "needs_rest"}
    is_comfort = bool(set(active_states) & comfort_states)

    if "hungry" in active_states and not rec:
        return (
            "Hora de recarregar! 🍕\n\n"
            "Procura um lugar com AC pra comer tranquilo. "
            "Quando estiverem prontos, me avisa que sugiro o próximo."
        )
    if is_comfort and not rec:
        return (
            "Tudo bem, dá pra dar uma pausa.\n\n"
            "Quando estiverem prontos, me avisa onde estão "
            "que sugiro algo mais tranquilo pra retomar."
        )

    prefix = state_acknowledgment(active_states)
    if rec:
        return assemble_get_rec(rec, group, context, prefix=prefix)
    return "Me avisa quando estiverem prontos que sugerimos o próximo passo!"


def assemble_question(
    attraction_id: str,
    aspect: Optional[str],
    context_data: dict,
    current_wait: Optional[int] = None,
) -> str:
    name = attraction_name(attraction_id)
    lines = []
    aspect_handlers = {
        "height_req":    _answer_height,
        "wetness":       _answer_wetness,
        "scare_factor":  _answer_scare,
        "duration":      _answer_duration,
        "accessibility": _answer_accessibility,
        "intensity_info":_answer_intensity,
        "wait_estimate": _answer_wait_estimate,
    }
    if aspect and aspect in aspect_handlers:
        lines.append(aspect_handlers[aspect](name, context_data))
    else:
        desc = context_data.get("description_pt", "")
        note = context_data.get("strategic_notes", "")
        if desc:
            lines.append(f"{name} — {desc}")
        if note:
            lines.append(note.split(".")[0].strip() + ".")
    if current_wait is not None:
        lines.append(f"\nFila agora: {wait_label(current_wait)}")
    return "\n".join(lines) if lines else f"Não tenho dados detalhados sobre {name} agora."


# ── Helpers de motivo ─────────────────────────────────────────────────────────

def _build_reason_phrase(primary: AttractionScore, context: OperationalContext) -> str:
    """
    Gera a frase de motivo considerando os flags do BonusResult.
    v1.1: trata rare_window e must_do_tight_queue com frases específicas.
    """
    reason = primary.primary_reason
    current_wait = primary.current_wait
    max_queue = getattr(context, '_max_queue_ref', None)  # pode não estar disponível

    # v1.1 F3: must_do com fila no limite → texto honesto
    if getattr(primary, '_must_do_tight_queue', False):
        return f"Era prioridade de vocês — vale esperar os {current_wait} min."

    # v1.1: rare_window → urgência de janela
    if reason == "rare_window" or getattr(primary, '_rare_window', False):
        return "Janela rara — fila muito abaixo do normal. Aproveita agora!"

    return reason_phrase(reason)


def _build_split_warning(primary: AttractionScore) -> Optional[str]:
    """
    v1.1 F4: gera nota personalizada quando allow_split + criança abaixo da altura.
    Retorna None se não se aplica.
    """
    if not getattr(primary, '_split_height_warning', False):
        return None
    child_h = primary._split_child_height
    min_h = primary._split_min_height
    return (
        f"⚠️ Criança de {child_h}cm não pode entrar "
        f"(mínimo {min_h}cm). Rider swap disponível — "
        f"um adulto fica com ela enquanto os outros fazem."
    )


# ── Respostas de dúvida ───────────────────────────────────────────────────────

def _answer_height(name, data):
    min_h = data.get("min_height_cm", 0)
    return (f"{name} não tem restrição de altura — todo mundo pode entrar!"
            if min_h == 0 else f"{name} exige altura mínima de {min_h}cm.")

def _answer_wetness(name, data):
    molha = "water" in data.get("tags", [])
    return (f"{name} molha sim — leva uma capa ou troca antes se preferir."
            if molha else f"{name} não molha — fica tranquilo.")

def _answer_scare(name, data):
    intensity = data.get("intensity", "moderate")
    has_dark = "dark" in data.get("tags", [])
    if intensity in ("high", "extreme") and has_dark:
        return (f"{name} tem partes bem escuras e pode assustar crianças sensíveis. "
                "Pra crianças pequenas com medo de escuro, talvez seja melhor deixar pra outra visita.")
    if has_dark:
        return (f"{name} é escuro mas não é muito intenso. "
                "A maioria das crianças curte — depende da sensibilidade.")
    return f"{name} não é assustador — tranquilo pra família."

def _answer_duration(name, data):
    d = data.get("duration_minutes", 0)
    return (f"{name} dura cerca de {d} minutos (sem contar a fila)."
            if d else f"Não tenho a duração exata de {name} agora.")

def _answer_accessibility(name, data):
    note = data.get("strategic_notes", "")
    if "acessib" in note.lower() or "cadeirante" in note.lower():
        return f"{name}: {note.split('.')[0]}."
    return f"Para informações de acessibilidade de {name}, recomendo verificar com um cast member no local."

def _answer_intensity(name, data):
    labels = {"low":"bem tranquilo","moderate":"moderado","high":"intenso","extreme":"muito intenso"}
    return f"{name} é {labels.get(data.get('intensity','moderate'), 'moderado')}."

def _answer_wait_estimate(name, data):
    hist = data.get("avg_wait_by_period", {})
    if hist:
        m, a = hist.get("morning","?"), hist.get("afternoon","?")
        return f"{name}: fila típica de {m} min de manhã e {a} min à tarde."
    return f"Não tenho histórico de fila para {name} agora."


# ── Helper de localização ─────────────────────────────────────────────────────

def _location_hint(primary: AttractionScore, context: OperationalContext) -> Optional[str]:
    if primary.walk_minutes <= 3:
        return None
    return f"Fica a {walk_label(primary.walk_minutes)} de onde vocês estão."
