"""
score_dimensions.py — As 5 dimensões do motor de score.

Cada função recebe (Attraction, DecisionContext) e retorna float 0–100.
São funções PURAS: sem I/O, sem efeitos colaterais, fáceis de testar.

CALIBRAÇÃO POR DIMENSÃO:
  D1 (fila):      ajuste MAX_WAIT_REFERENCE para mudar sensibilidade
  D2 (prox):      ajuste WALK_MINUTES e MAX_WALK_MINUTES
  D3 (perfil):    ajuste _INTENSITY_MAP e _TAG_SCORES
  D4 (horário):   ajuste TIME_MATCH_SCORE e TIME_AVOID_SCORE
  D5 (estratégia):ajuste BASE_SCORE_WEIGHT e CLUSTER_BONUS
"""

from ..domain.models import Attraction
from ..domain.enums import TimeOfDay
from .context_builder import DecisionContext


# ─────────────────────────────────────────────────────────────────────────────
# D1 — FILA ATUAL
# ─────────────────────────────────────────────────────────────────────────────

def d1_queue_score(attraction: Attraction, ctx: DecisionContext) -> float:
    """
    Score inversamente proporcional ao tempo de fila.
    Fila zero = 100. Fila igual ao máximo tolerado = 0.
    Curva linear — considere ajustar para curva quadrática se quiser
    penalizar filas médias mais fortemente.
    """
    current_wait = ctx.queue_snapshot.get(attraction.attraction_id)
    if current_wait is None:
        current_wait = attraction.historical_wait(ctx.time_of_day.value)

    # Respeita override de max_queue se presente
    max_tolerated = ctx.max_queue_minutes
    if ctx.filter_override:
        override_max = (
            ctx.filter_override.get("max_queue_minutes")
            if isinstance(ctx.filter_override, dict)
            else getattr(ctx.filter_override, "max_queue_minutes", None)
        )
        if override_max is not None:
            max_tolerated = min(max_tolerated, override_max)

    if max_tolerated <= 0:
        return 0.0
    if current_wait <= 0:
        return 100.0
    if current_wait >= max_tolerated:
        return 0.0

    return round(100.0 * (1.0 - current_wait / max_tolerated), 2)


# ─────────────────────────────────────────────────────────────────────────────
# D2 — PROXIMIDADE / CAMINHADA
# ─────────────────────────────────────────────────────────────────────────────

# Tempos de caminhada estimados entre áreas do Magic Kingdom (em minutos).
# Para calibrar: cronometre com um adulto em ritmo normal, adicione 30% para família.
WALK_MINUTES: dict[tuple[str, str], int] = {
    ("main_street", "adventureland"):    5,
    ("main_street", "tomorrowland"):     5,
    ("main_street", "fantasyland"):      8,
    ("main_street", "liberty_square"):   7,
    ("main_street", "frontierland"):     9,
    ("adventureland", "frontierland"):   3,
    ("adventureland", "liberty_square"): 6,
    ("frontierland", "liberty_square"):  3,
    ("frontierland", "fantasyland"):     7,
    ("liberty_square", "fantasyland"):   4,
    ("fantasyland", "tomorrowland"):     6,
    ("fantasyland", "storybook_circus"): 3,
    ("storybook_circus", "tomorrowland"):7,
    ("tomorrowland", "main_street"):     5,
}

MAX_WALK_MINUTES = 20   # caminhada acima disso recebe score mínimo
MIN_WALK_SCORE   = 10.0 # score mínimo mesmo para locais muito distantes


def estimate_walk_minutes(from_area: str, to_area: str) -> int:
    """
    Estima caminhada entre duas áreas. Bidirecional.
    Retorna 12 min como padrão para pares não mapeados.
    """
    if from_area == to_area:
        return 2
    key = (from_area, to_area)
    reverse_key = (to_area, from_area)
    return WALK_MINUTES.get(key, WALK_MINUTES.get(reverse_key, 12))


def d2_proximity_score(attraction: Attraction, ctx: DecisionContext) -> float:
    """
    Score inversamente proporcional ao tempo de caminhada.
    Mesma área = 90 pts. Máximo de distância = MIN_WALK_SCORE pts.
    """
    walk = estimate_walk_minutes(ctx.current_location_area, attraction.area.value)
    if walk >= MAX_WALK_MINUTES:
        return MIN_WALK_SCORE
    raw = 100.0 * (1.0 - walk / MAX_WALK_MINUTES)
    return round(max(MIN_WALK_SCORE, raw), 2)


# ─────────────────────────────────────────────────────────────────────────────
# D3 — ADERÊNCIA AO PERFIL
# ─────────────────────────────────────────────────────────────────────────────

# Intensidades preferidas por perfil. Ordem importa: mais restritivos à esquerda.
_INTENSITY_PREFERRED: dict[str, frozenset[str]] = {
    "P1": frozenset({"low"}),
    "P2": frozenset({"low", "moderate"}),
    "P3": frozenset({"moderate", "high"}),
    "P4": frozenset({"moderate", "high"}),
    "P5": frozenset({"low"}),
    "P6": frozenset({"low", "moderate"}),
    "P7": frozenset({"high", "extreme"}),
}

# Pontuação de intensidade: preferred=1.0, adjacente=0.6, incompatível=0.2
_INTENSITY_ADJACENT: dict[str, frozenset[str]] = {
    "P1": frozenset({"moderate"}),
    "P2": frozenset({"high"}),
    "P3": frozenset({"low", "extreme"}),
    "P4": frozenset({"low", "extreme"}),
    "P5": frozenset({"moderate"}),
    "P6": frozenset({"high"}),
    "P7": frozenset({"moderate"}),
}

# Tags que adicionam pontos em D3 por perfil
_TAG_POSITIVE: dict[str, frozenset[str]] = {
    "P1": frozenset({"character", "indoor_ac", "slow", "infantil", "seated", "classic"}),
    "P2": frozenset({"iconic", "family", "classic", "thrill", "dark"}),
    "P3": frozenset({"thrill", "iconic", "dark", "extreme", "outdoor"}),
    "P4": frozenset({"iconic", "classic", "thrill", "scenic"}),
    "P5": frozenset({"slow", "seated", "indoor_ac", "scenic", "classic"}),
    "P6": frozenset({"classic", "scenic", "slow", "seated", "indoor_ac", "character"}),
    "P7": frozenset({"thrill", "extreme", "iconic", "dark", "outdoor"}),
}

# Tags que reduzem pontos em D3 por perfil (incompatibilidade forte)
_TAG_NEGATIVE: dict[str, frozenset[str]] = {
    "P1": frozenset({"thrill", "extreme", "spinning", "outdoor"}),
    "P2": frozenset({"infantil"}),
    "P3": frozenset({"infantil", "slow"}),
    "P4": frozenset({"infantil"}),
    "P5": frozenset({"thrill", "extreme", "spinning", "outdoor"}),
    "P6": frozenset({"extreme", "spinning"}),
    "P7": frozenset({"infantil", "slow", "seated"}),
}


def d3_profile_score(attraction: Attraction, ctx: DecisionContext) -> float:
    """
    Score de aderência ao perfil. Composto de três sub-scores:
      - Intensidade (peso 50%): preferred/adjacent/incompatible
      - Ideal profiles (peso 30%): se a atração lista este perfil
      - Tags (peso 20%): positivas somam, negativas reduzem

    Resultado: 0–100, nunca negativo.
    """
    profile_id = ctx.profile_id
    tag_set = set(attraction.tags)

    # Sub-score de intensidade (0–100)
    preferred = _INTENSITY_PREFERRED.get(profile_id, frozenset())
    adjacent  = _INTENSITY_ADJACENT.get(profile_id, frozenset())
    intensity  = attraction.intensity.value
    if intensity in preferred:
        intensity_score = 100.0
    elif intensity in adjacent:
        intensity_score = 60.0
    else:
        intensity_score = 20.0

    # Sub-score de ideal_profiles (0–100)
    profile_score = 90.0 if profile_id in attraction.ideal_profiles else 40.0

    # Sub-score de tags (0–100): começa em 50, +10 por tag positiva, -20 por negativa
    pos_hits = len(tag_set & _TAG_POSITIVE.get(profile_id, frozenset()))
    neg_hits = len(tag_set & _TAG_NEGATIVE.get(profile_id, frozenset()))
    tag_score = max(0.0, min(100.0, 50.0 + pos_hits * 10.0 - neg_hits * 20.0))

    total = (intensity_score * 0.50) + (profile_score * 0.30) + (tag_score * 0.20)
    return round(min(100.0, max(0.0, total)), 2)


# ─────────────────────────────────────────────────────────────────────────────
# D4 — CONTEXTO DE HORÁRIO
# ─────────────────────────────────────────────────────────────────────────────

TIME_MATCH_SCORE = 100.0  # melhor horário para a atração
TIME_AVOID_SCORE = 25.0   # pior horário para a atração
TIME_NEUTRAL_SCORE = 65.0 # horário indiferente


def d4_time_score(attraction: Attraction, ctx: DecisionContext) -> float:
    """
    Score de adequação do horário atual à atração.
    Usa best_time_of_day e avoid_time_of_day do cadastro.
    """
    current = ctx.time_of_day
    if current in attraction.best_time_of_day:
        return TIME_MATCH_SCORE
    if current in attraction.avoid_time_of_day:
        return TIME_AVOID_SCORE
    return TIME_NEUTRAL_SCORE


# ─────────────────────────────────────────────────────────────────────────────
# D5 — IMPACTO ESTRATÉGICO
# ─────────────────────────────────────────────────────────────────────────────

BASE_SCORE_WEIGHT = 60.0   # peso do base_priority_score na dimensão (0–60)
CLUSTER_BONUS    = 35.0    # bônus se atração fica próxima às must-do restantes
ADJACENT_BONUS   = 15.0    # bônus menor se está na área adjacente às must-do


def d5_strategy_score(attraction: Attraction, ctx: DecisionContext) -> float:
    """
    Score de impacto estratégico na rota.
    Combina popularidade base com bônus de cluster (proximidade a must-do restantes).

    Cluster bonus: se a atração está nas nearby_attractions de uma must-do ainda pendente,
    isso significa que ir até ela não adiciona desvio significativo.
    """
    # Componente base: popularidade/valor percebido da atração
    base = attraction.base_priority_score * BASE_SCORE_WEIGHT

    # Cluster: verifica se atração está próxima das must-do restantes
    remaining_must_do = {
        a for a in ctx.must_do_attractions if a not in ctx.done_attractions
    }
    cluster = 0.0
    if remaining_must_do:
        nearby_set = set(attraction.nearby_attractions)
        # Bônus máximo se alguma must-do pendente é vizinha desta atração
        if nearby_set & remaining_must_do:
            cluster = CLUSTER_BONUS
        # Bônus menor se está na mesma área das must-do pendentes
        elif attraction.area.value in ctx.must_do_areas:
            cluster = ADJACENT_BONUS

    return round(min(100.0, base + cluster), 2)
