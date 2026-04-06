"""
response_templates.py — Templates e vocabulário do gerador de resposta.

Toda a variação linguística está aqui. O assembler (response_generator.py)
chama estas funções e nunca escreve texto diretamente.

CALIBRAÇÃO:
  - Adicione variantes nas listas de _VARIANTS para deixar as respostas
    menos repetitivas sem alterar a lógica do assembler.
  - Ajuste os limiares em _wait_label() e _walk_label() conforme feedback.
  - Novos contextos (novos parques, outros idiomas) = novo arquivo de templates.
"""

import random
from typing import Optional

from ..domain.models import Recommendation, AttractionScore
from ..domain.models.group import Group, GroupPreferences
from ..domain.models.context import OperationalContext
from ..domain.enums import ProfileType


# ─────────────────────────────────────────────────────────────────────────────
# NOMES CANÔNICOS DAS ATRAÇÕES
# ─────────────────────────────────────────────────────────────────────────────

ATTRACTION_NAMES: dict[str, str] = {
    "seven_dwarfs_mine_train":   "Seven Dwarfs Mine Train",
    "space_mountain":            "Space Mountain",
    "big_thunder_mountain":      "Big Thunder Mountain",
    "haunted_mansion":           "Haunted Mansion",
    "pirates_of_the_caribbean":  "Pirates of the Caribbean",
    "peter_pan_flight":          "Peter Pan's Flight",
    "buzz_lightyear":            "Buzz Lightyear's Space Ranger Spin",
    "tron_lightcycle_run":       "Tron Lightcycle/Run",
    "its_a_small_world":         "it's a small world",
    "dumbo":                     "Dumbo the Flying Elephant",
    "tiana_bayou_adventure":     "Tiana's Bayou Adventure",
    "jungle_cruise":             "Jungle Cruise",
}

def attraction_name(attraction_id: str) -> str:
    return ATTRACTION_NAMES.get(attraction_id, attraction_id.replace("_", " ").title())


# ─────────────────────────────────────────────────────────────────────────────
# FRASES DE MOTIVO (primary_reason → texto PT-BR)
# ─────────────────────────────────────────────────────────────────────────────

_REASON_PHRASES: dict[str, list[str]] = {
    "low_queue": [
        "Fila ótima agora — não perde essa janela.",
        "Tá com fila bem curta nesse momento.",
        "Boa hora pra essa atração — fila bem abaixo do normal.",
        "Fila rara pra esse brinquedo agora.",
    ],
    "must_do": [
        "Essa tava na lista de vocês — e a fila tá favorável.",
        "Era prioridade de vocês, e o horário tá bom.",
        "Não pode perder — e a fila tá ok agora.",
    ],
    "profile_match": [
        "Combina bem com o perfil do grupo.",
        "Ideal pro estilo de visita de vocês.",
        "Feita pra esse tipo de grupo.",
    ],
    "show_window": [
        "Janela perfeita — dá pra chegar confortavelmente.",
        "Tempo certo pra se posicionar antes do show.",
    ],
    "strategic_route": [
        "Fica no caminho certo pra próxima atração de vocês.",
        "Boa posição na rota — não gera desvio.",
    ],
    "end_of_day": [
        "Parque fecha em breve — hora de fechar com chave de ouro.",
        "Última chance boa antes de fechar.",
    ],
    "weather_refuge": [
        "Indoor com AC — boa escolha com esse calor.",
        "Climatizada — perfeito pra esse horário quente.",
    ],
}

def reason_phrase(reason: str, use_random: bool = False) -> str:
    phrases = _REASON_PHRASES.get(reason, ["Boa opção agora."])
    if use_random:
        return random.choice(phrases)
    return phrases[0]


# ─────────────────────────────────────────────────────────────────────────────
# RÓTULOS DE ESPERA E CAMINHADA
# ─────────────────────────────────────────────────────────────────────────────

def wait_label(minutes: int) -> str:
    """Converte minutos de fila em texto natural."""
    if minutes == 0:
        return "sem fila agora"
    if minutes <= 10:
        return f"~{minutes} min de fila (ótimo)"
    if minutes <= 20:
        return f"{minutes} min de fila"
    if minutes <= 35:
        return f"{minutes} min de fila"
    if minutes <= 60:
        return f"{minutes} min de fila (moderado)"
    return f"{minutes} min de fila (bastante)"


def walk_label(minutes: int) -> str:
    """Converte minutos de caminhada em texto natural."""
    if minutes <= 3:
        return "aqui do lado"
    if minutes <= 6:
        return f"{minutes} min a pé"
    if minutes <= 12:
        return f"uns {minutes} min caminhando"
    return f"{minutes} min a pé (um bom trecho)"


# ─────────────────────────────────────────────────────────────────────────────
# PERSONALIZAÇÃO POR PERFIL
# ─────────────────────────────────────────────────────────────────────────────

_PROFILE_CLOSINGS: dict[str, list[str]] = {
    "P1": [
        "Me avisa quando saírem que sugiro o próximo!",
        "Qualquer dúvida é só chamar.",
    ],
    "P2": [
        "Me avisa quando saírem que sugerimos o próximo!",
        "As crianças vão gostar — me conta depois!",
    ],
    "P3": [
        "Bora! Me avisa quando saírem.",
        "Me conta como foi!",
    ],
    "P4": [
        "Me avisa quando saírem para planejar o próximo.",
        "Qualquer dúvida é só chamar.",
    ],
    "P5": [
        "Sem pressa — me avisa quando estiverem prontos.",
        "Qualquer dúvida é só chamar.",
    ],
    "P6": [
        "Me avisa quando saírem que sugiro o próximo passo.",
        "Qualquer dúvida é só chamar.",
    ],
    "P7": [
        "Bora lá! Me avisa quando saírem.",
        "Me conta como foi!",
    ],
}

def closing_phrase(profile_id: str, use_random: bool = False) -> str:
    phrases = _PROFILE_CLOSINGS.get(profile_id, ["Me avisa quando saírem!"])
    if use_random:
        return random.choice(phrases)
    return phrases[0]


# ─────────────────────────────────────────────────────────────────────────────
# FRASES DE CONTEXTO COMPLEMENTAR
# ─────────────────────────────────────────────────────────────────────────────

def supporting_phrase(reasons: list[str], weather: Optional[str] = None) -> Optional[str]:
    """
    Gera frase de apoio baseada nos supporting_reasons do score.
    Retorna None se nenhuma razão de apoio for relevante para o texto.
    """
    if "indoor_ac" in reasons and weather == "sunny":
        return "Climatizada — ótima pra esse calor."
    if "very_short_queue" in reasons:
        return "Fila praticamente inexistente agora."
    if "rider_swap_available" in reasons:
        return "Rider swap disponível se alguém não atingir a altura."
    if "best_time_now" in reasons:
        return "Melhor horário do dia pra essa atração."
    if "nearby" in reasons:
        return None  # proximidade já aparece na linha de localização
    return None


def trade_off_phrase(trade_off: Optional[str]) -> Optional[str]:
    """Retorna trade-off formatado ou None. Nunca inventa texto."""
    if not trade_off:
        return None
    return f"⚠️ {trade_off.capitalize()}."


def context_note_phrase(note: Optional[str]) -> Optional[str]:
    """Retorna nota estratégica formatada ou None."""
    if not note:
        return None
    # Limita a primeira frase da nota para não poluir a mensagem
    first_sentence = note.split(".")[0].strip()
    if first_sentence:
        return first_sentence
    return None


# ─────────────────────────────────────────────────────────────────────────────
# FRASES ESPECIAIS POR SITUAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

def state_acknowledgment(active_states: list[str]) -> Optional[str]:
    """Reconhece o estado do grupo antes de recomendar."""
    if "tired" in active_states and "hungry" in active_states:
        return "Hora de recarregar primeiro! Mas quando estiverem prontos:"
    if "tired" in active_states:
        return "Entendido, ritmo mais tranquilo. Sugiro:"
    if "hot" in active_states:
        return "Com esse calor, melhor algo indoor:"
    if "hungry" in active_states:
        return "Depois de comer, aproveita essa janela:"
    return None


def end_of_day_prefix(hours_until_close: float) -> Optional[str]:
    if hours_until_close <= 1.0:
        return "Última hora! Ainda dá:"
    if hours_until_close <= 2.0:
        return "Parque fecha em breve. Aproveita:"
    return None


def check_in_greeting(profile_id: str, member_summary: str) -> str:
    """Saudação de boas-vindas no check-in."""
    base = "Que emoção! Bem-vindos ao Magic Kingdom!"
    question = (
        "Pra eu ajudar certinho — as crianças têm alguma restrição de altura "
        "ou tem alguma atração que vocês não podem deixar de fazer?"
        if "P1" in profile_id or "P2" in profile_id or "P6" in profile_id
        else "Pra eu ajudar certinho — tem alguma atração que vocês não podem deixar de fazer?"
    )
    return f"{base}\n\n{question}"


def mark_done_acknowledgment(attraction_id: str, sentiment: Optional[str]) -> str:
    """Confirmação após atração concluída."""
    name = attraction_name(attraction_id)
    if sentiment == "positive":
        return f"Que ótimo! {name} anotado. Próxima sugestão:"
    if sentiment == "negative":
        return f"Entendido, {name} anotado — pulamos na próxima vez. Continuando:"
    return f"{name} anotado. Próxima sugestão:"
