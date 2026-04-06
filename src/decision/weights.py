"""
weights.py — Configuração de pesos do motor de score.

COMO CALIBRAR:
  1. Edite PROFILE_WEIGHTS para ajustar o comportamento base por perfil.
  2. Edite SITUATIONAL_RULES para adicionar/modificar sobreposições situacionais.
  3. Os pesos de cada DimensionWeights DEVEM somar 1.0 (validado em __post_init__).
  4. Execute tests/unit/test_scoring_engine.py após qualquer alteração.
"""

from dataclasses import dataclass
from ..domain.enums import ProfileType


@dataclass(frozen=True)
class DimensionWeights:
    """
    Pesos das 5 dimensões do score. Imutável após construção.
    Soma deve ser 1.0. Cada raw score (0-100) é multiplicado pelo peso correspondente.
    """
    d1_queue: float      # fila atual: quanto menor, melhor
    d2_proximity: float  # distância/caminhada: quanto mais perto, melhor
    d3_profile: float    # aderência ao perfil do grupo
    d4_time: float       # adequação do horário do dia
    d5_strategy: float   # impacto estratégico na rota

    def __post_init__(self) -> None:
        total = self.d1_queue + self.d2_proximity + self.d3_profile + self.d4_time + self.d5_strategy
        if abs(total - 1.0) > 0.001:
            raise ValueError(
                f"DimensionWeights must sum to 1.0, got {total:.4f}. "
                f"d1={self.d1_queue}, d2={self.d2_proximity}, "
                f"d3={self.d3_profile}, d4={self.d4_time}, d5={self.d5_strategy}"
            )

    def as_dict(self) -> dict:
        return {
            "d1_queue": self.d1_queue, "d2_proximity": self.d2_proximity,
            "d3_profile": self.d3_profile, "d4_time": self.d4_time,
            "d5_strategy": self.d5_strategy,
        }

    def describe(self) -> str:
        return (
            f"D1(fila)={self.d1_queue:.0%} D2(prox)={self.d2_proximity:.0%} "
            f"D3(perfil)={self.d3_profile:.0%} D4(hora)={self.d4_time:.0%} "
            f"D5(estrat)={self.d5_strategy:.0%}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# CALIBRAÇÃO — Pesos base por perfil
# Altere aqui para rebalancear o comportamento por tipo de grupo.
# ─────────────────────────────────────────────────────────────────────────────

PROFILE_WEIGHTS: dict[str, DimensionWeights] = {
    # P1 — bebês/crianças pequenas: fila e proximidade dominam, rota irrelevante
    ProfileType.P1: DimensionWeights(d1_queue=0.40, d2_proximity=0.30, d3_profile=0.20, d4_time=0.07, d5_strategy=0.03),
    # P2 — família mista 6-12 anos: equilíbrio com ênfase leve em perfil
    ProfileType.P2: DimensionWeights(d1_queue=0.30, d2_proximity=0.20, d3_profile=0.28, d4_time=0.12, d5_strategy=0.10),
    # P3 — adolescentes: perfil domina (querem emoção), estratégia importa
    ProfileType.P3: DimensionWeights(d1_queue=0.25, d2_proximity=0.15, d3_profile=0.35, d4_time=0.10, d5_strategy=0.15),
    # P4 — adultos foco nos ícones: estratégia e horário têm mais peso
    ProfileType.P4: DimensionWeights(d1_queue=0.25, d2_proximity=0.18, d3_profile=0.25, d4_time=0.15, d5_strategy=0.17),
    # P5 — ritmo leve: igual P1 na prática
    ProfileType.P5: DimensionWeights(d1_queue=0.40, d2_proximity=0.30, d3_profile=0.20, d4_time=0.07, d5_strategy=0.03),
    # P6 — multigeracional: proximidade elevada (avós caminham menos)
    ProfileType.P6: DimensionWeights(d1_queue=0.30, d2_proximity=0.25, d3_profile=0.25, d4_time=0.12, d5_strategy=0.08),
    # P7 — adrenalina máxima: perfil e estratégia dominam, fila aceita
    ProfileType.P7: DimensionWeights(d1_queue=0.20, d2_proximity=0.15, d3_profile=0.35, d4_time=0.10, d5_strategy=0.20),
}

DEFAULT_WEIGHTS = DimensionWeights(d1_queue=0.30, d2_proximity=0.20, d3_profile=0.25, d4_time=0.15, d5_strategy=0.10)


# ─────────────────────────────────────────────────────────────────────────────
# CALIBRAÇÃO — Sobreposições situacionais
# Aplicadas em ordem de prioridade; a primeira que coincidir sobrescreve os pesos base.
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SituationalRule:
    name: str
    weights: DimensionWeights
    description: str


SITUATIONAL_RULES: list[SituationalRule] = [
    SituationalRule(
        name="end_of_day",
        weights=DimensionWeights(d1_queue=0.35, d2_proximity=0.25, d3_profile=0.25, d4_time=0.10, d5_strategy=0.05),
        description="Últimas 2h — fila e proximidade dominam, estratégia mínima",
    ),
    SituationalRule(
        name="heat_fatigue",
        weights=DimensionWeights(d1_queue=0.35, d2_proximity=0.30, d3_profile=0.20, d4_time=0.10, d5_strategy=0.05),
        description="Cansaço + calor — conforto absoluto",
    ),
    SituationalRule(
        name="fatigue",
        weights=DimensionWeights(d1_queue=0.35, d2_proximity=0.25, d3_profile=0.22, d4_time=0.12, d5_strategy=0.06),
        description="Grupo cansado — fila curta e proximidade elevadas",
    ),
    SituationalRule(
        name="heat",
        weights=DimensionWeights(d1_queue=0.32, d2_proximity=0.24, d3_profile=0.24, d4_time=0.12, d5_strategy=0.08),
        description="Calor forte — leve ênfase em proximidade e indoor",
    ),
]


def get_weights(profile_id: str, active_states: list[str], hours_until_close: float) -> DimensionWeights:
    """
    Retorna os pesos finais para este ciclo de scoring.
    Prioridade: regras situacionais > perfil > default.
    """
    if hours_until_close <= 2.0:
        return _rule("end_of_day").weights
    state_set = set(active_states)
    if "tired" in state_set and "hot" in state_set:
        return _rule("heat_fatigue").weights
    if "tired" in state_set:
        return _rule("fatigue").weights
    if "hot" in state_set:
        return _rule("heat").weights
    return PROFILE_WEIGHTS.get(profile_id, DEFAULT_WEIGHTS)


def get_weight_reason(profile_id: str, active_states: list[str], hours_until_close: float) -> str:
    """Descrição legível do motivo dos pesos escolhidos — útil para logging e debug."""
    if hours_until_close <= 2.0:
        return _rule("end_of_day").description
    state_set = set(active_states)
    if "tired" in state_set and "hot" in state_set:
        return _rule("heat_fatigue").description
    if "tired" in state_set:
        return _rule("fatigue").description
    if "hot" in state_set:
        return _rule("heat").description
    return f"Pesos base do perfil {profile_id}"


def _rule(name: str) -> SituationalRule:
    for r in SITUATIONAL_RULES:
        if r.name == name:
            return r
    raise KeyError(f"Situational rule '{name}' not found")
