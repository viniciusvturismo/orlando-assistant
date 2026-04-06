from ..domain.models import Recommendation


def build_fallback_message(rec: Recommendation) -> str:
    """
    Gera mensagem de fallback baseada nos dados estruturados da recomendação.
    Usado quando a Claude API falha — garante que o usuário sempre recebe uma resposta.
    """
    primary = rec.primary
    lines = [
        f"✅ {_format_name(primary.attraction_id)}",
        f"Fila: {primary.current_wait} min · {primary.walk_minutes} min a pé",
    ]

    if rec.secondary:
        sec = rec.secondary
        lines.append("")
        lines.append(f"🔄 Alternativa: {_format_name(sec.attraction_id)}")
        lines.append(f"Fila: {sec.current_wait} min")

    reason = _reason_to_pt(primary.primary_reason)
    lines.append("")
    lines.append(f"💡 {reason}")
    lines.append("")
    lines.append("📍 Me avisa quando saírem!")

    return "\n".join(lines)


def build_clarification_message(question: str) -> str:
    return question or "Pode me contar onde vocês estão ou o que querem fazer agora?"


def build_error_message() -> str:
    return "Ops, tive um probleminha aqui. Tenta de novo em um instante! 🙏"


def build_checkin_prompt() -> str:
    return (
        "Que emoção! 🎉 Bem-vindos ao Magic Kingdom!\n\n"
        "Pra eu ajudar direitinho — as crianças têm alguma restrição de altura "
        "ou tem alguma atração que vocês não podem deixar de fazer?"
    )


def _format_name(attraction_id: str) -> str:
    name_map = {
        "seven_dwarfs_mine_train": "Seven Dwarfs Mine Train",
        "space_mountain": "Space Mountain",
        "big_thunder_mountain": "Big Thunder Mountain Railroad",
        "haunted_mansion": "Haunted Mansion",
        "pirates_of_the_caribbean": "Pirates of the Caribbean",
        "peter_pan_flight": "Peter Pan's Flight",
        "buzz_lightyear": "Buzz Lightyear's Space Ranger Spin",
        "tron_lightcycle_run": "Tron Lightcycle/Run",
        "its_a_small_world": "it's a small world",
        "dumbo": "Dumbo the Flying Elephant",
        "tiana_bayou_adventure": "Tiana's Bayou Adventure",
    }
    return name_map.get(attraction_id, attraction_id.replace("_", " ").title())


def _reason_to_pt(reason: str) -> str:
    reasons = {
        "low_queue": "Fila ótima agora — aproveita!",
        "must_do": "Essa era a prioridade de vocês.",
        "profile_match": "Combina perfeitamente com o perfil do grupo.",
        "show_window": "Janela perfeita pra chegar a tempo.",
        "strategic_route": "Boa hora pra essa área.",
        "end_of_day": "Última chance antes de fechar!",
        "weather_refuge": "Indoor com AC — ótimo com esse calor.",
    }
    return reasons.get(reason, "Boa opção agora.")
