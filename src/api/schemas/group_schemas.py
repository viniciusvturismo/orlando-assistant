from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, Self
from datetime import date
import re


# ── Request schemas ────────────────────────────────────────────────────────────

class MemberInput(BaseModel):
    """Schema de entrada para um membro do grupo."""
    role: str = Field(..., pattern="^(adult|child|senior|infant)$", description="Papel no grupo")
    age: Optional[int] = Field(None, ge=0, le=120, description="Idade em anos")
    height_cm: Optional[int] = Field(None, ge=30, le=280, description="Altura em centímetros")
    name: Optional[str] = Field(None, max_length=50, description="Apelido para personalizar respostas")
    fear_of_dark: bool = Field(False, description="Medo de escuro — filtra dark rides")
    fear_of_heights: bool = Field(False, description="Medo de altura")
    motion_sickness: bool = Field(False, description="Enjoo — filtra atrações com tag 'spinning'")
    mobility_restricted: bool = Field(False, description="Cadeirante ou dificuldade de locomoção")

    @model_validator(mode="after")
    def child_should_have_height(self) -> Self:
        if self.role == "child" and self.height_cm is None:
            # Avisa mas não bloqueia — altura pode ser informada depois
            pass
        return self

    def to_domain_member(self):
        """Converte para o dataclass de domínio Member."""
        from ...domain.models.group import Member
        return Member(
            role=self.role,
            age=self.age,
            height_cm=self.height_cm,
            name=self.name,
            fear_of_dark=self.fear_of_dark,
            fear_of_heights=self.fear_of_heights,
            motion_sickness=self.motion_sickness,
            mobility_restricted=self.mobility_restricted,
        )


class CreateGroupRequest(BaseModel):
    """Cria ou recupera um grupo pelo número de WhatsApp."""
    whatsapp_number: str = Field(
        ...,
        min_length=10,
        max_length=20,
        description="Número com código de país, ex: +5521999990000",
    )
    park_id: str = Field("magic_kingdom", description="ID do parque")
    visit_date: Optional[date] = Field(None, description="Data da visita (default: hoje)")
    language: str = Field("pt-BR", pattern="^[a-z]{2}-[A-Z]{2}$")

    @field_validator("whatsapp_number")
    @classmethod
    def normalize_phone(cls, v: str) -> str:
        digits = re.sub(r"\D", "", v)
        if len(digits) < 10:
            raise ValueError("Número de WhatsApp deve ter pelo menos 10 dígitos")
        return f"+{digits}" if not v.startswith("+") else v


class UpdateMembersRequest(BaseModel):
    """Atualiza (substitui) a lista de membros do grupo."""
    members: list[MemberInput] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Lista completa de membros — substitui os existentes",
    )

    @field_validator("members")
    @classmethod
    def must_have_at_least_one_adult(cls, members: list[MemberInput]) -> list[MemberInput]:
        if not any(m.role in ("adult", "senior") for m in members):
            raise ValueError("O grupo deve ter pelo menos um adulto ou idoso responsável")
        return members


class UpdatePreferencesRequest(BaseModel):
    """Define as preferências e prioridades do grupo para a visita."""
    intensity_preference: str = Field(
        "moderate",
        pattern="^(low|moderate|high|mixed)$",
        description="Intensidade preferida das atrações",
    )
    priority_order: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Ordem de prioridade: low_queue, iconic, thrill, character_meet, show...",
    )
    avoid_types: list[str] = Field(
        default_factory=list,
        max_length=15,
        description="Tags ou tipos de atração a evitar: spinning, dark, water, extreme...",
    )
    max_queue_minutes: int = Field(
        45,
        ge=5,
        le=180,
        description="Tempo máximo de fila aceitável em minutos",
    )
    must_do_attractions: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Slugs das atrações prioritárias — recebem bônus +15 no score",
    )
    skip_attractions: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Slugs das atrações que o grupo não quer fazer",
    )
    show_interest: bool = Field(True, description="Incluir shows e paradas nas sugestões")
    meal_break_times: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Horários de refeição reservados: ['12:30', '17:00']",
    )
    allow_group_split: bool = Field(
        False,
        description="Permite sugerir divisão do grupo quando há restrição de altura",
    )

    @field_validator("meal_break_times")
    @classmethod
    def validate_time_format(cls, times: list[str]) -> list[str]:
        pattern = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
        for t in times:
            if not pattern.match(t):
                raise ValueError(f"Horário '{t}' inválido. Use o formato HH:MM (ex: 12:30)")
        return times

    def to_domain_preferences(self, group_id: str, pref_id: str) -> object:
        """Converte para o dataclass GroupPreferences do domínio."""
        from ...domain.models.group import GroupPreferences
        return GroupPreferences(
            pref_id=pref_id,
            group_id=group_id,
            intensity_preference=self.intensity_preference,
            priority_order=self.priority_order,
            avoid_types=self.avoid_types,
            max_queue_minutes=self.max_queue_minutes,
            must_do_attractions=self.must_do_attractions,
            skip_attractions=self.skip_attractions,
            show_interest=self.show_interest,
            meal_break_times=self.meal_break_times,
            allow_group_split=self.allow_group_split,
        )


# ── Response schemas ───────────────────────────────────────────────────────────

class MemberResponse(BaseModel):
    """Membro do grupo na resposta da API."""
    role: str
    age: Optional[int]
    height_cm: Optional[int]
    name: Optional[str]
    motion_sickness: bool
    mobility_restricted: bool

    @classmethod
    def from_domain(cls, member) -> "MemberResponse":
        return cls(
            role=member.role,
            age=member.age,
            height_cm=member.height_cm,
            name=member.name,
            motion_sickness=member.motion_sickness,
            mobility_restricted=member.mobility_restricted,
        )


class GroupResponse(BaseModel):
    """Resposta padrão de criação/consulta de grupo."""
    group_id: str
    created: bool
    profile_id: Optional[str] = Field(None, description="P1–P7 detectado automaticamente")
    setup_complete: bool
    next_step: Optional[str] = Field(
        None,
        description="Próxima ação necessária: add_members | add_preferences | ready_to_recommend",
    )
    members_count: int = 0
    has_young_children: bool = False
    min_child_height: Optional[int] = None


class PreferencesResponse(BaseModel):
    """Confirmação de preferências salvas."""
    group_id: str
    preferences_saved: bool
    profile_id: Optional[str]
    setup_complete: bool
    next_step: Optional[str]
    weights_preview: Optional[dict] = Field(
        None,
        description="Pesos do motor que serão aplicados para este perfil",
    )

    @classmethod
    def from_group_and_weights(cls, group, weights=None) -> "PreferencesResponse":
        next_step = None if group.setup_complete else (
            "add_members" if not group.members else "add_preferences"
        )
        w_preview = None
        if weights:
            w_preview = {
                "d1_queue": weights.d1_queue,
                "d2_proximity": weights.d2_proximity,
                "d3_profile": weights.d3_profile,
                "d4_time": weights.d4_time,
                "d5_strategy": weights.d5_strategy,
            }
        return cls(
            group_id=group.group_id,
            preferences_saved=True,
            profile_id=group.profile_id.value if group.profile_id else None,
            setup_complete=group.setup_complete,
            next_step=next_step,
            weights_preview=w_preview,
        )
