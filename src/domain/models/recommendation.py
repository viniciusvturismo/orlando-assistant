from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from ..enums import IntentType, QuestionAspect

# Score mínimo para a segunda opção ser incluída na resposta
SECONDARY_MIN_SCORE = 50.0

# Motivos primários reconhecidos pelo response_generator
VALID_PRIMARY_REASONS = frozenset({
    "low_queue",
    "must_do",
    "profile_match",
    "show_window",
    "strategic_route",
    "end_of_day",
    "weather_refuge",
})


@dataclass
class ScoreBreakdown:
    """
    Decomposição do score final por dimensão.

    Usada pelo response_generator para escolher a justificativa certa
    e pela camada de debug/análise para entender decisões do motor.
    """
    d1_queue: float = 0.0       # fila atual (peso 20–40%)
    d2_proximity: float = 0.0   # distância/caminhada (peso 15–30%)
    d3_profile: float = 0.0     # aderência ao perfil (peso 20–35%)
    d4_time: float = 0.0        # contexto de horário (peso 7–15%)
    d5_strategy: float = 0.0    # impacto estratégico (peso 3–20%)
    bonuses: float = 0.0        # bônus aplicados (must_do, fila caindo, ícone)
    penalties: float = 0.0      # penalidades (caminhada longa, horário ruim, etc.)

    @property
    def total(self) -> float:
        return round(
            self.d1_queue + self.d2_proximity + self.d3_profile
            + self.d4_time + self.d5_strategy + self.bonuses - self.penalties,
            2,
        )

    @property
    def dominant_dimension(self) -> str:
        """Dimensão com maior contribuição — orienta o primary_reason."""
        dims = {
            "d1_queue": self.d1_queue,
            "d2_proximity": self.d2_proximity,
            "d3_profile": self.d3_profile,
            "d4_time": self.d4_time,
            "d5_strategy": self.d5_strategy,
        }
        return max(dims, key=dims.get)

    def as_dict(self) -> dict:
        return {
            "d1_queue": self.d1_queue,
            "d2_proximity": self.d2_proximity,
            "d3_profile": self.d3_profile,
            "d4_time": self.d4_time,
            "d5_strategy": self.d5_strategy,
            "bonuses": self.bonuses,
            "penalties": self.penalties,
            "total": self.total,
        }


@dataclass
class AttractionScore:
    """
    Score calculado de uma atração candidata.

    Produzido pelo scoring_engine para cada atração elegível.
    O ranker seleciona primary e secondary a partir desta lista.
    """
    attraction_id: str
    name: str
    score: float                # 0.0–100.0 — score final após bônus/penalidades
    current_wait: int           # minutos de fila no momento (real ou histórico)
    walk_minutes: int           # tempo estimado de caminhada da localização atual

    # Justificativa estruturada — consumida pelo response_generator
    primary_reason: str         # deve ser um dos VALID_PRIMARY_REASONS
    supporting_reasons: list[str] = field(default_factory=list)
    context_note: Optional[str] = None   # dica estratégica (ex: "fila cresce após 14h")
    trade_off: Optional[str] = None      # desvantagem honesta (ex: "um pouco longe")

    score_breakdown: Optional[ScoreBreakdown] = None

    def __post_init__(self) -> None:
        if not (0.0 <= self.score <= 100.0):
            raise ValueError(f"score must be between 0.0 and 100.0, got {self.score}")

    @property
    def total_time_cost(self) -> int:
        """Custo total de tempo: caminhada + fila."""
        return self.walk_minutes + self.current_wait

    @property
    def is_strong_recommendation(self) -> bool:
        return self.score >= 75.0

    @property
    def has_valid_reason(self) -> bool:
        return self.primary_reason in VALID_PRIMARY_REASONS


@dataclass
class Recommendation:
    """
    Recomendação gerada pelo motor para um grupo em um contexto específico.

    Persiste no banco para auditoria, debug e análise de qualidade.
    O campo whatsapp_message é preenchido pelo response_generator após o scoring.
    """
    recommendation_id: str
    group_id: str
    context_id: str
    generated_at: datetime
    primary: AttractionScore
    secondary: Optional[AttractionScore]

    # Metadados do processo de decisão
    filters_applied: list[str] = field(default_factory=list)
    # ex: ["height_restriction_97cm", "already_done", "queue_too_long_80min"]

    candidates_evaluated: int = 0
    # quantas atrações foram avaliadas antes de chegar ao ranking final

    # Conteúdo
    user_message: str = ""          # mensagem original que gerou esta recomendação
    whatsapp_message: Optional[str] = None   # texto gerado pelo response_generator

    # Feedback (preenchido após o usuário responder)
    user_feedback: Optional[str] = None    # "accepted" | "rejected" | "modified"
    response_time_ms: Optional[int] = None

    @property
    def has_secondary(self) -> bool:
        return self.secondary is not None and self.secondary.score >= SECONDARY_MIN_SCORE

    @property
    def primary_attraction_id(self) -> str:
        return self.primary.attraction_id

    @property
    def score_gap(self) -> float:
        """Diferença de score entre primary e secondary. Indica clareza da decisão."""
        if not self.secondary:
            return 100.0
        return self.primary.score - self.secondary.score

    def to_summary(self) -> dict:
        """Resumo compacto para logging."""
        return {
            "rec_id": self.recommendation_id,
            "group_id": self.group_id,
            "primary": self.primary.attraction_id,
            "primary_score": self.primary.score,
            "secondary": self.secondary.attraction_id if self.secondary else None,
            "candidates": self.candidates_evaluated,
            "filters": len(self.filters_applied),
        }


# ── Modelos auxiliares do fluxo NLU ───────────────────────────────────────────

@dataclass
class LocationHint:
    """Localização extraída pelo NLU de uma mensagem do usuário."""
    zone: Optional[str]       # slug resolvido: "fantasyland"
    ref_text: Optional[str]   # texto original: "perto do castelo"

    @property
    def is_resolved(self) -> bool:
        return self.zone is not None


@dataclass
class AttractionRef:
    """Referência a uma atração extraída pelo NLU."""
    slug: Optional[str]   # slug canônico: "haunted_mansion"
    raw: Optional[str]    # texto original: "casa mal-assombrada"

    @property
    def is_identified(self) -> bool:
        return self.slug is not None


@dataclass
class MemberMention:
    """Membro mencionado numa mensagem — ex: 'minha filha de 7 anos'."""
    role: str
    age: Optional[int] = None
    height_cm: Optional[int] = None


@dataclass
class NLUResult:
    """
    Saída estruturada do interpretador de mensagens (NLU).

    Produzido por language/nlu.py e consumido pelo channel/message_router.py
    para decidir qual handler chamar e quais dados atualizar no contexto.
    """
    intent: IntentType
    confidence: float           # 0.0–1.0: certeza da classificação
    raw_message: str

    location: Optional[LocationHint] = None
    attraction_ref: Optional[AttractionRef] = None
    group_state: list[str] = field(default_factory=list)      # ["tired", "hungry"]
    filter_override: Optional[dict] = None
    members_mentioned: list[MemberMention] = field(default_factory=list)
    reported_wait_minutes: Optional[int] = None               # número explícito de minutos
    question_aspect: Optional[QuestionAspect] = None
    sentiment: Optional[str] = None                           # "positive"|"neutral"|"negative"
    ambiguities: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None

    @property
    def is_high_confidence(self) -> bool:
        return self.confidence >= 0.80

    @property
    def location_zone(self) -> Optional[str]:
        return self.location.zone if self.location else None

    @property
    def attraction_slug(self) -> Optional[str]:
        return self.attraction_ref.slug if self.attraction_ref else None
