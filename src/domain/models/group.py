from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
from ..enums import ProfileType

# Roles válidos de membro — usados pelo rules_engine para validar restrições
VALID_ROLES = frozenset({"adult", "child", "senior", "infant"})

# Intensidades válidas para preferências do grupo
VALID_INTENSITIES = frozenset({"low", "moderate", "high", "mixed"})


@dataclass
class Member:
    """
    Representa um membro individual do grupo visitante.

    height_cm é obrigatório na prática para crianças, pois alimenta
    o hard filter de altura mínima no rules_engine. Para adultos é opcional.
    """
    role: str                          # adult | child | senior | infant
    age: Optional[int] = None          # anos completos
    height_cm: Optional[int] = None    # centímetros — crítico para crianças
    name: Optional[str] = None         # apelido para personalizar respostas

    # Restrições físicas — alimentam os soft filters e D3
    fear_of_dark: bool = False
    fear_of_heights: bool = False
    motion_sickness: bool = False      # exclui atrações com tag "spinning"
    mobility_restricted: bool = False  # filtra por acessibilidade

    def __post_init__(self) -> None:
        if self.role not in VALID_ROLES:
            raise ValueError(f"Invalid member role '{self.role}'. Must be one of {VALID_ROLES}")
        if self.age is not None and not (0 <= self.age <= 120):
            raise ValueError(f"Member age must be between 0 and 120, got {self.age}")
        if self.height_cm is not None and not (30 <= self.height_cm <= 280):
            raise ValueError(f"height_cm must be between 30 and 280, got {self.height_cm}")

    @property
    def is_child(self) -> bool:
        return self.role == "child"

    @property
    def needs_height_check(self) -> bool:
        """True se este membro pode ser bloqueado por restrição de altura."""
        return self.role in ("child", "infant") and self.height_cm is not None

    @property
    def restriction_tags(self) -> set[str]:
        """Tags de atrações que este membro não tolera."""
        tags = set()
        if self.motion_sickness:
            tags.add("spinning")
        if self.fear_of_dark:
            tags.add("dark")
        return tags


@dataclass
class GroupPreferences:
    """
    Preferências e prioridades do grupo para a visita.

    priority_order define a ordem de importância dos critérios
    usados em D3 (perfil) e D5 (estratégia) do motor de score.
    """
    pref_id: str
    group_id: str
    intensity_preference: str = "moderate"   # alimenta D3
    priority_order: list[str] = field(default_factory=list)      # ex: ["low_queue","iconic"]
    avoid_types: list[str] = field(default_factory=list)          # hard filter no rules_engine
    max_queue_minutes: int = 45               # hard filter no rules_engine
    must_do_attractions: list[str] = field(default_factory=list)  # bônus +15 no scoring
    skip_attractions: list[str] = field(default_factory=list)     # hard filter
    show_interest: bool = True                # ativa sugestão de shows no contexto
    meal_break_times: list[str] = field(default_factory=list)     # ex: ["12:30","17:00"]
    allow_group_split: bool = False           # habilita sugestão de divisão de grupo
    updated_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if self.intensity_preference not in VALID_INTENSITIES:
            raise ValueError(
                f"intensity_preference must be one of {VALID_INTENSITIES}, "
                f"got '{self.intensity_preference}'"
            )
        if not (5 <= self.max_queue_minutes <= 180):
            raise ValueError(f"max_queue_minutes must be between 5 and 180, got {self.max_queue_minutes}")

    def is_must_do(self, attraction_id: str) -> bool:
        return attraction_id in self.must_do_attractions

    def is_skipped(self, attraction_id: str) -> bool:
        return attraction_id in self.skip_attractions

    def type_is_avoided(self, tag_or_type: str) -> bool:
        return tag_or_type in self.avoid_types


@dataclass
class GroupProfile:
    """
    Visão consolidada do grupo para uso no motor de score.

    Agrega Group + GroupPreferences num objeto único que os
    services e o context_builder consomem sem acessar o banco novamente.
    """
    group_id: str
    whatsapp_number: str
    park_id: str
    visit_date: date
    profile_id: ProfileType
    members: list[Member]
    preferences: GroupPreferences
    language: str = "pt-BR"
    setup_complete: bool = False
    created_at: Optional[datetime] = None

    # ── Propriedades derivadas usadas pelo context_builder ─────────────────────

    @property
    def min_child_height(self) -> Optional[int]:
        """Menor altura entre as crianças do grupo. None se sem crianças com altura."""
        heights = [
            m.height_cm for m in self.members
            if m.height_cm is not None and m.role in ("child", "infant")
        ]
        return min(heights) if heights else None

    @property
    def has_young_children(self) -> bool:
        """True se há crianças de 5 anos ou menos no grupo."""
        return any(m.is_child and m.age is not None and m.age <= 5 for m in self.members)

    @property
    def has_mobility_restricted(self) -> bool:
        return any(m.mobility_restricted for m in self.members)

    @property
    def collective_restriction_tags(self) -> set[str]:
        """União de todas as tags de restrição dos membros."""
        tags: set[str] = set()
        for m in self.members:
            tags |= m.restriction_tags
        return tags

    @property
    def member_count(self) -> int:
        return len(self.members)

    @property
    def adult_count(self) -> int:
        return sum(1 for m in self.members if m.role == "adult")

    @property
    def child_ages(self) -> list[int]:
        return [m.age for m in self.members if m.is_child and m.age is not None]


@dataclass
class Group:
    """
    Entidade principal de grupo — persiste entre sessões pelo número WhatsApp.
    Usado diretamente pelos repositories; services constroem GroupProfile a partir dele.
    """
    group_id: str
    whatsapp_number: str
    park_id: str
    visit_date: date
    members: list[Member] = field(default_factory=list)
    language: str = "pt-BR"
    profile_id: Optional[ProfileType] = None
    setup_complete: bool = False
    created_at: Optional[datetime] = None

    @property
    def has_young_children(self) -> bool:
        return any(m.is_child and m.age is not None and m.age <= 5 for m in self.members)

    @property
    def min_child_height(self) -> Optional[int]:
        heights = [m.height_cm for m in self.members if m.height_cm is not None]
        return min(heights) if heights else None

    @property
    def member_count(self) -> int:
        return len(self.members)

    def to_profile(self, preferences: GroupPreferences) -> "GroupProfile":
        """Constrói o GroupProfile consolidado a partir do Group + suas preferências."""
        if self.profile_id is None:
            raise ValueError(f"Group {self.group_id} has no profile_id — run profile detection first")
        return GroupProfile(
            group_id=self.group_id,
            whatsapp_number=self.whatsapp_number,
            park_id=self.park_id,
            visit_date=self.visit_date,
            profile_id=self.profile_id,
            members=self.members,
            preferences=preferences,
            language=self.language,
            setup_complete=self.setup_complete,
            created_at=self.created_at,
        )
