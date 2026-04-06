from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from ..enums import WeatherCondition, GroupStateType

# Tempo máximo (horas) antes de um contexto ser considerado expirado
CONTEXT_TTL_HOURS = 24

# Janela (minutos) para um show ser considerado "iminente" e ganhar bônus
SHOW_IMMINENT_WINDOW_MINUTES = 40


@dataclass
class FilterOverride:
    """
    Filtro temporário aplicado apenas à próxima recomendação.

    Originado de mensagens como "queremos algo leve agora" ou
    "só indoor por favor" — não altera as preferências permanentes do grupo.
    """
    intensity: Optional[str] = None       # "low" | "moderate" | "high"
    environment: Optional[str] = None     # "indoor" | "outdoor"
    max_queue_minutes: Optional[int] = None
    for_all_members: bool = False          # exige que TODOS possam fazer
    scope: str = "next_only"              # "next_only" | "permanent"

    def __post_init__(self) -> None:
        valid_intensities = {None, "low", "moderate", "high"}
        if self.intensity not in valid_intensities:
            raise ValueError(f"FilterOverride.intensity must be one of {valid_intensities}")
        valid_envs = {None, "indoor", "outdoor"}
        if self.environment not in valid_envs:
            raise ValueError(f"FilterOverride.environment must be one of {valid_envs}")

    def is_active(self) -> bool:
        return any([self.intensity, self.environment, self.max_queue_minutes, self.for_all_members])


@dataclass
class ShowSlot:
    """
    Slot de show com horário específico.
    Usado para calcular bônus de janela de show em D4.
    """
    attraction_id: str
    next_show_at: datetime
    duration_minutes: int

    def minutes_until(self, now: datetime) -> int:
        delta = (self.next_show_at - now).total_seconds() / 60
        return max(0, int(delta))

    def is_imminent(self, now: datetime) -> bool:
        """True se o show começa dentro da janela de bônus."""
        return 0 <= self.minutes_until(now) <= SHOW_IMMINENT_WINDOW_MINUTES


@dataclass
class QueueEntry:
    """
    Entrada de fila com metadata de fonte e timestamp.
    Permite rastrear se o dado veio do usuário ou de API externa.
    """
    attraction_id: str
    wait_minutes: int
    reported_at: datetime
    source: str = "user"   # "user" | "api" | "mock"

    def is_stale(self, now: datetime, max_age_minutes: int = 30) -> bool:
        age = (now - self.reported_at).total_seconds() / 60
        return age > max_age_minutes


@dataclass
class OperationalContext:
    """
    Snapshot do estado da visita num momento específico.

    Criado a cada nova interação ou atualizado via patches.
    Imutável do ponto de vista do motor de score — o context_builder
    consome este objeto e produz o DecisionContext com pesos calculados.
    """

    # ── Identificação ──────────────────────────────────────────────────────────
    context_id: str
    group_id: str
    current_park_id: str
    current_datetime: datetime

    # ── Estado espacial ────────────────────────────────────────────────────────
    current_location_area: str       # slug da área: "fantasyland", "tomorrowland"

    # ── Estado de fila — coração do D1 ────────────────────────────────────────
    queue_snapshot: dict[str, int] = field(default_factory=dict)
    # attraction_id → minutos de espera; atualizado pelo usuário ou API
    queue_snapshot_at: Optional[datetime] = None

    # ── Histórico da visita — hard filter no rules_engine ─────────────────────
    done_attractions: list[str] = field(default_factory=list)
    closed_attractions: list[str] = field(default_factory=list)

    # ── Estado do grupo — ativa lógicas situacionais ───────────────────────────
    active_states: list[GroupStateType] = field(default_factory=list)
    # ex: [GroupStateType.TIRED, GroupStateType.HOT]
    # ativa: pesos de D1/D2 aumentados, sugestão de descanso

    # ── Filtro temporário — originado de mensagem do usuário ───────────────────
    filter_override: Optional[FilterOverride] = None

    # ── Shows agendados — alimentam D4 ────────────────────────────────────────
    active_shows: list[ShowSlot] = field(default_factory=list)

    # ── Contexto ambiental ────────────────────────────────────────────────────
    weather: Optional[WeatherCondition] = None
    crowd_level: Optional[str] = None     # "low" | "moderate" | "high" | "very_high"
    special_event: Optional[str] = None   # ex: "Mickey's Halloween Party"

    expires_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if self.expires_at is None:
            self.expires_at = self.current_datetime + timedelta(hours=CONTEXT_TTL_HOURS)

    # ── Interface para o motor de score ────────────────────────────────────────

    def get_queue(self, attraction_id: str) -> Optional[int]:
        """Retorna tempo de fila ou None se não houver dado."""
        return self.queue_snapshot.get(attraction_id)

    def is_done(self, attraction_id: str) -> bool:
        return attraction_id in self.done_attractions

    def is_closed(self, attraction_id: str) -> bool:
        return attraction_id in self.closed_attractions

    def has_state(self, state: GroupStateType) -> bool:
        return state in self.active_states

    def is_expired(self) -> bool:
        return self.expires_at is not None and datetime.utcnow() > self.expires_at

    def imminent_shows(self) -> list[ShowSlot]:
        """Shows com janela de bônus ativa agora."""
        return [s for s in self.active_shows if s.is_imminent(self.current_datetime)]

    def hours_until_close(self, close_hour: int = 22) -> float:
        close_dt = self.current_datetime.replace(hour=close_hour, minute=0, second=0)
        return max(0.0, (close_dt - self.current_datetime).total_seconds() / 3600)

    def add_done(self, attraction_id: str) -> None:
        if attraction_id not in self.done_attractions:
            self.done_attractions.append(attraction_id)

    def update_queue(self, attraction_id: str, minutes: int) -> None:
        self.queue_snapshot[attraction_id] = minutes
        self.queue_snapshot_at = datetime.utcnow()
