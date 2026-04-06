from dataclasses import dataclass, field
from typing import Optional
from ..enums import AttractionType, IntensityLevel, ParkArea, TimeOfDay, LightningLaneType

# Score mínimo aceitável de base_priority_score para ser considerado "ícone do parque"
ICON_THRESHOLD = 0.85

# Duração mínima (min) para calcular penalidade de eficiência (duração vs. fila)
EFFICIENCY_MIN_DURATION = 3


@dataclass
class Attraction:
    """
    Cadastro completo de uma atração do parque.

    Campos de scoring (base_priority_score, tags, ideal_profiles,
    best_time_of_day, avg_wait_by_period) alimentam diretamente as
    cinco dimensões do motor de score (D1–D5).
    """

    # ── Identidade ─────────────────────────────────────────────────────────────
    attraction_id: str           # slug canônico: "seven_dwarfs_mine_train"
    park_id: str                 # "magic_kingdom"
    name: str                    # nome oficial em inglês
    name_pt: str                 # como o brasileiro chama
    area: ParkArea               # land dentro do parque
    type: AttractionType         # ride | show | character_meet | parade | experience
    intensity: IntensityLevel    # low | moderate | high | extreme
    description_pt: str          # descrição curta para o usuário (≤ 80 chars)

    # ── Operacional ────────────────────────────────────────────────────────────
    min_height_cm: int           # 0 = sem restrição — hard filter no rules_engine
    duration_minutes: int        # duração da experiência (sem fila)
    is_indoor: bool              # com AC — ativa bônus em dias quentes
    rain_sensitive: bool         # fecha com chuva — hard filter situacional
    suitable_for_infants: bool   # bebês de colo permitidos
    rider_swap: bool             # troca de passageiro disponível

    # ── Scoring ────────────────────────────────────────────────────────────────
    base_priority_score: float   # 0.0–1.0: popularidade/valor percebido → D5
    tags: list[str] = field(default_factory=list)
    # Tags usadas pelo motor:
    #   thrill, dark, spinning, water, classic, character, scenic,
    #   outdoor, indoor_ac, slow, seated, walking, iconic, infantil

    ideal_profiles: list[str] = field(default_factory=list)
    # Perfis P1–P7 para quem esta atração pontua bem em D3

    best_time_of_day: list[TimeOfDay] = field(default_factory=list)
    # Horários onde D4 retorna 100 pts

    avoid_time_of_day: list[TimeOfDay] = field(default_factory=list)
    # Horários onde D4 retorna 30 pts (penalidade)

    avg_wait_by_period: dict[str, int] = field(default_factory=dict)
    # {"rope_drop": 20, "morning": 60, ...} — fallback quando não há fila real

    # ── Estratégico / localização ───────────────────────────────────────────────
    location_zone: str = ""                          # referência textual de posição
    adjacent_areas: list[str] = field(default_factory=list)   # areas a ≤ 5 min
    nearby_attractions: list[str] = field(default_factory=list)  # slugs a ≤ 3 min → D5 cluster
    strategic_notes: str = ""                        # dica usada na justificativa

    lightning_lane: LightningLaneType = LightningLaneType.NONE
    active: bool = True

    def __post_init__(self) -> None:
        if not (0.0 <= self.base_priority_score <= 1.0):
            raise ValueError(
                f"base_priority_score must be between 0.0 and 1.0, got {self.base_priority_score}"
            )
        if self.duration_minutes < 1:
            raise ValueError(f"duration_minutes must be at least 1, got {self.duration_minutes}")

    # ── Interface para o motor de score ────────────────────────────────────────

    def allows_height(self, height_cm: int) -> bool:
        """True se um membro com esta altura pode fazer a atração."""
        return self.min_height_cm == 0 or height_cm >= self.min_height_cm

    def historical_wait(self, period: str) -> int:
        """Tempo histórico de fila para o período dado. Fallback: 30 min."""
        return self.avg_wait_by_period.get(period, 30)

    def is_icon(self) -> bool:
        """True se é considerada atração icônica do parque (bônus no scoring)."""
        return self.base_priority_score >= ICON_THRESHOLD

    def efficiency_ratio(self, wait_minutes: int) -> float:
        """
        Razão duração/fila. Valores abaixo de 0.05 indicam custo de tempo alto
        (ex: 2 min de atração / 45 min de fila = 0.044 → penalidade aplicada).
        """
        if wait_minutes == 0:
            return 1.0
        return self.duration_minutes / wait_minutes

    def is_good_for_heat(self) -> bool:
        """Atração adequada para dias de calor intenso."""
        return self.is_indoor or "water" in self.tags

    def has_tag(self, tag: str) -> bool:
        return tag in self.tags

    def blocks_member(self, height_cm: Optional[int]) -> bool:
        """True se a restrição de altura bloqueia um membro específico."""
        if self.min_height_cm == 0:
            return False
        if height_cm is None:
            return False
        return height_cm < self.min_height_cm
