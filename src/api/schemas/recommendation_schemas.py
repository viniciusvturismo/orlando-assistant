from pydantic import BaseModel, Field, field_validator
from typing import Optional


# ── Context request schemas ────────────────────────────────────────────────────

class FilterOverrideInput(BaseModel):
    """Filtro temporário aplicado à próxima recomendação."""
    intensity: Optional[str] = Field(
        None,
        pattern="^(low|moderate|high)$",
        description="Restringe intensidade: low | moderate | high",
    )
    environment: Optional[str] = Field(
        None,
        pattern="^(indoor|outdoor)$",
        description="Restringe ambiente: indoor | outdoor",
    )
    max_queue_minutes: Optional[int] = Field(
        None,
        ge=0,
        le=180,
        description="Sobrescreve o limite de fila apenas para a próxima sugestão",
    )
    for_all_members: bool = Field(
        False,
        description="Exige que todos os membros possam fazer a atração",
    )

    def to_domain(self):
        from ...domain.models.context import FilterOverride
        return FilterOverride(
            intensity=self.intensity,
            environment=self.environment,
            max_queue_minutes=self.max_queue_minutes,
            for_all_members=self.for_all_members,
        )


class CreateContextRequest(BaseModel):
    """Snapshot operacional do momento atual da visita."""
    current_location_area: str = Field(
        ...,
        description="Área atual do parque: fantasyland | tomorrowland | frontierland...",
    )
    queue_snapshot: dict[str, int] = Field(
        default_factory=dict,
        description="Mapa attraction_id → minutos de fila observados agora",
    )
    done_attractions: list[str] = Field(
        default_factory=list,
        description="Slugs das atrações já realizadas nesta visita",
    )
    closed_attractions: list[str] = Field(
        default_factory=list,
        description="Slugs das atrações fechadas/indisponíveis no momento",
    )
    weather: Optional[str] = Field(
        None,
        pattern="^(sunny|cloudy|rainy|storm)$",
        description="Condição climática atual",
    )
    group_states: list[str] = Field(
        default_factory=list,
        description="Estados ativos do grupo: tired | hungry | hot | wet | cranky",
    )
    filter_override: Optional[FilterOverrideInput] = Field(
        None,
        description="Filtro temporário para esta recomendação",
    )

    @field_validator("queue_snapshot")
    @classmethod
    def validate_queue_values(cls, v: dict) -> dict:
        for attraction_id, minutes in v.items():
            if minutes < 0:
                raise ValueError(f"Queue for '{attraction_id}' cannot be negative")
            if minutes > 300:
                raise ValueError(f"Queue of {minutes} min for '{attraction_id}' seems unrealistic")
        return v

    @field_validator("group_states")
    @classmethod
    def validate_states(cls, states: list[str]) -> list[str]:
        valid = {"tired", "hungry", "hot", "wet", "cranky", "needs_rest", "energized"}
        invalid = set(states) - valid
        if invalid:
            raise ValueError(f"Invalid group states: {invalid}. Valid: {valid}")
        return states


class UpdateLocationRequest(BaseModel):
    location_area: str = Field(
        ...,
        description="Slug da área atual: fantasyland | tomorrowland | frontierland...",
    )


class AddDoneRequest(BaseModel):
    attraction_id: str = Field(..., description="Slug da atração concluída")
    sentiment: Optional[str] = Field(
        None,
        pattern="^(positive|neutral|negative)$",
        description="Avaliação do usuário sobre a experiência",
    )


class UpdateQueuesRequest(BaseModel):
    queue_snapshot: dict[str, int] = Field(
        ...,
        description="Snapshot atualizado de filas: attraction_id → minutos",
    )

    @field_validator("queue_snapshot")
    @classmethod
    def validate_queue_values(cls, v: dict) -> dict:
        for k, minutes in v.items():
            if not (0 <= minutes <= 300):
                raise ValueError(f"Queue for '{k}' must be between 0 and 300 minutes")
        return v


# ── Context response schemas ───────────────────────────────────────────────────

class ContextResponse(BaseModel):
    """Confirmação de criação/atualização de contexto operacional."""
    context_id: str
    group_id: str
    time_of_day: str = Field(..., description="rope_drop | morning | midday | afternoon | evening | night")
    ready_to_recommend: bool
    attractions_remaining: Optional[int] = Field(
        None,
        description="Atrações elegíveis pelo perfil ainda não realizadas",
    )
    hours_until_close: Optional[float] = Field(None, description="Horas até o fechamento")
    expires_at: Optional[str] = Field(None, description="ISO timestamp de expiração do contexto")


# ── Recommendation request/response schemas ────────────────────────────────────

class RecommendRequest(BaseModel):
    """Solicita uma recomendação para o grupo com contexto ativo."""
    context_id: Optional[str] = Field(
        None,
        description="ID do contexto — se omitido usa o contexto ativo mais recente",
    )
    filter_override: Optional[FilterOverrideInput] = Field(
        None,
        description="Filtro pontual para esta recomendação",
    )
    generate_text: bool = Field(
        True,
        description="Se False, retorna apenas o score sem chamar o gerador de resposta",
    )
    user_message: str = Field(
        "",
        max_length=500,
        description="Mensagem original do usuário — usada para personalizar a resposta",
    )


class ScoreBreakdownResponse(BaseModel):
    """Decomposição do score por dimensão — usado para debug e transparência."""
    d1_queue: float = Field(..., description="Contribuição da dimensão fila (D1)")
    d2_proximity: float = Field(..., description="Contribuição da dimensão proximidade (D2)")
    d3_profile: float = Field(..., description="Contribuição da dimensão perfil (D3)")
    d4_time: float = Field(..., description="Contribuição da dimensão horário (D4)")
    d5_strategy: float = Field(..., description="Contribuição da dimensão estratégia (D5)")
    bonuses: float = Field(..., description="Bônus aplicados (must_do, ícone, fila caindo)")
    penalties: float = Field(..., description="Penalidades aplicadas (caminhada, horário ruim)")
    total: float = Field(..., description="Score final 0.0–100.0")

    @classmethod
    def from_domain(cls, breakdown) -> "ScoreBreakdownResponse":
        return cls(
            d1_queue=breakdown.d1_queue,
            d2_proximity=breakdown.d2_proximity,
            d3_profile=breakdown.d3_profile,
            d4_time=breakdown.d4_time,
            d5_strategy=breakdown.d5_strategy,
            bonuses=breakdown.bonuses,
            penalties=breakdown.penalties,
            total=breakdown.total,
        )


class AttractionScoreResponse(BaseModel):
    """Score calculado de uma atração candidata."""
    attraction_id: str
    name: str
    score: float = Field(..., ge=0.0, le=100.0)
    current_wait: int = Field(..., description="Minutos de fila agora (real ou histórico)")
    walk_minutes: int = Field(..., description="Minutos estimados de caminhada")
    primary_reason: str = Field(..., description="Motivo principal da recomendação")
    supporting_reasons: list[str] = Field(default_factory=list)
    context_note: Optional[str] = Field(None, description="Dica estratégica para o usuário")
    trade_off: Optional[str] = Field(None, description="Desvantagem honesta, se houver")
    score_breakdown: Optional[ScoreBreakdownResponse] = None

    @classmethod
    def from_domain(cls, scored) -> "AttractionScoreResponse":
        return cls(
            attraction_id=scored.attraction_id,
            name=scored.name,
            score=scored.score,
            current_wait=scored.current_wait,
            walk_minutes=scored.walk_minutes,
            primary_reason=scored.primary_reason,
            supporting_reasons=scored.supporting_reasons,
            context_note=scored.context_note,
            trade_off=scored.trade_off,
            score_breakdown=(
                ScoreBreakdownResponse.from_domain(scored.score_breakdown)
                if scored.score_breakdown else None
            ),
        )


class RecommendationResponse(BaseModel):
    """Recomendação completa retornada pela API."""
    recommendation_id: str
    primary: AttractionScoreResponse
    secondary: Optional[AttractionScoreResponse] = Field(
        None,
        description="Segunda opção — None se nenhuma alternativa viável (score ≥ 50)",
    )
    filters_applied: list[str] = Field(
        default_factory=list,
        description="Filtros que excluíram atrações antes do scoring",
    )
    candidates_evaluated: int = Field(
        0,
        description="Número de atrações avaliadas pelo motor",
    )
    whatsapp_message: Optional[str] = Field(
        None,
        description="Mensagem pronta para enviar via WhatsApp em PT-BR",
    )

    @classmethod
    def from_domain(cls, rec) -> "RecommendationResponse":
        return cls(
            recommendation_id=rec.recommendation_id,
            primary=AttractionScoreResponse.from_domain(rec.primary),
            secondary=(
                AttractionScoreResponse.from_domain(rec.secondary)
                if rec.secondary else None
            ),
            filters_applied=rec.filters_applied,
            candidates_evaluated=rec.candidates_evaluated,
            whatsapp_message=rec.whatsapp_message,
        )


class AttractionResponse(BaseModel):
    """Dados públicos de uma atração do catálogo."""
    attraction_id: str
    name: str
    name_pt: str
    area: str
    type: str
    intensity: str
    description_pt: str
    min_height_cm: int
    duration_minutes: int
    is_indoor: bool
    rain_sensitive: bool
    suitable_for_infants: bool
    rider_swap: bool
    tags: list[str]
    base_priority_score: float
    best_time_of_day: list[str]
    location_zone: str
    strategic_notes: str
    active: bool

    @classmethod
    def from_domain(cls, attraction) -> "AttractionResponse":
        return cls(
            attraction_id=attraction.attraction_id,
            name=attraction.name,
            name_pt=attraction.name_pt,
            area=attraction.area.value,
            type=attraction.type.value,
            intensity=attraction.intensity.value,
            description_pt=attraction.description_pt,
            min_height_cm=attraction.min_height_cm,
            duration_minutes=attraction.duration_minutes,
            is_indoor=attraction.is_indoor,
            rain_sensitive=attraction.rain_sensitive,
            suitable_for_infants=attraction.suitable_for_infants,
            rider_swap=attraction.rider_swap,
            tags=attraction.tags,
            base_priority_score=attraction.base_priority_score,
            best_time_of_day=[t.value for t in attraction.best_time_of_day],
            location_zone=attraction.location_zone,
            strategic_notes=attraction.strategic_notes,
            active=attraction.active,
        )
