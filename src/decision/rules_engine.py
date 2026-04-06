"""
rules_engine.py — Filtros de exclusão aplicados antes do scoring.

ARQUITETURA DE FILTROS:
  Hard filters: eliminação binária — atração fora, sem exceção.
  Soft filters: eliminação condicional — pode ser mantida se grupo sinalizou interesse explícito.

ORDEM DE APLICAÇÃO (mais barato primeiro para short-circuit rápido):
  1. active          — campo booleano, O(1)
  2. already_done    — set lookup, O(1)
  3. closed          — set lookup, O(1)
  4. height          — comparação numérica, O(members)
  5. queue_max       — dict lookup + comparação, O(1)
  6. avoided_types   — set intersection, O(tags)
  7. member_restrictions — set intersection por membro
  8. filter_override — dict lookup, O(1)
  9. rain_closed     — bool check, O(1)
  10. soft_intensity  — condicional por perfil

ADICIONANDO UM NOVO FILTRO:
  1. Crie uma função _check_<nome>(attraction, ctx) -> str
     Retorna motivo se deve ser excluída, "" se passar.
  2. Adicione ao pipeline em apply_filters() na ordem correta.
  3. Adicione um teste em tests/unit/test_rules_engine.py.
"""

from dataclasses import dataclass, field
from ..domain.models import Attraction
from .context_builder import DecisionContext


@dataclass
class FilterResult:
    eligible: list[Attraction] = field(default_factory=list)
    excluded: list[tuple[Attraction, str]] = field(default_factory=list)

    @property
    def eligible_count(self) -> int:
        return len(self.eligible)

    @property
    def excluded_count(self) -> int:
        return len(self.excluded)

    def exclusion_summary(self) -> dict[str, int]:
        """Agrupa exclusões por motivo — útil para diagnóstico."""
        summary: dict[str, int] = {}
        for _, reason in self.excluded:
            # Normaliza motivos com valores variáveis: "queue_too_long_75min" → "queue_too_long"
            key = reason.split("_")[:-1] if reason[-1].isdigit() else reason.split("_")
            # Reconstrói key sem o sufixo numérico
            category = _categorize_reason(reason)
            summary[category] = summary.get(category, 0) + 1
        return summary


def apply_filters(attractions: list[Attraction], ctx: DecisionContext) -> FilterResult:
    """
    Pipeline de filtros. Retorna FilterResult com elegíveis e excluídas com motivo.

    Cada filtro é aplicado em sequência. Ao primeiro motivo de exclusão,
    a atração é descartada e passa-se para a próxima (short-circuit).
    """
    result = FilterResult()

    for attraction in attractions:
        reason = (
            _check_inactive(attraction)
            or _check_already_done(attraction, ctx)
            or _check_closed(attraction, ctx)
            or _check_height(attraction, ctx)
            or _check_queue_max(attraction, ctx)
            or _check_avoided_types(attraction, ctx)
            or _check_member_restrictions(attraction, ctx)
            or _check_filter_override(attraction, ctx)
            or _check_rain_closed(attraction, ctx)
            or _check_soft_intensity(attraction, ctx)
        )

        if reason:
            result.excluded.append((attraction, reason))
        else:
            result.eligible.append(attraction)

    return result


# ── Filtros individuais ────────────────────────────────────────────────────────

def _check_inactive(attraction: Attraction) -> str:
    return "inactive" if not attraction.active else ""


def _check_already_done(attraction: Attraction, ctx: DecisionContext) -> str:
    return "already_done" if attraction.attraction_id in ctx.done_attractions else ""


def _check_closed(attraction: Attraction, ctx: DecisionContext) -> str:
    return "temporarily_closed" if attraction.attraction_id in ctx.closed_attractions else ""


def _check_height(attraction: Attraction, ctx: DecisionContext) -> str:
    """
    Exclui se a menor criança do grupo não atinge a altura mínima.
    Se allow_group_split=True, a atração fica (adultos fazem, crianças ficam).
    """
    if ctx.allow_group_split:
        return ""
    if ctx.min_child_height is None:
        return ""
    if attraction.min_height_cm == 0:
        return ""
    if ctx.min_child_height < attraction.min_height_cm:
        return f"height_restriction_{attraction.min_height_cm}cm"
    return ""


def _check_queue_max(attraction: Attraction, ctx: DecisionContext) -> str:
    """
    Exclui se a fila atual supera o máximo tolerado.
    Sem dado de fila: usa histórico do período — não exclui por falta de dado.
    """
    current_wait = ctx.queue_snapshot.get(attraction.attraction_id)
    if current_wait is None:
        # Sem dado real — usa histórico; se histórico também supera, exclui
        historical = attraction.historical_wait(ctx.time_of_day.value)
        # Aplica folga de 20% ao histórico (pode estar desatualizado)
        if historical > ctx.max_queue_minutes * 1.2:
            return f"historical_queue_too_long_{historical}min"
        return ""
    if current_wait > ctx.max_queue_minutes:
        return f"queue_too_long_{current_wait}min"
    return ""


def _check_avoided_types(attraction: Attraction, ctx: DecisionContext) -> str:
    """Exclui se type ou qualquer tag da atração está na lista de evitados."""
    if attraction.type.value in ctx.avoid_types:
        return f"avoided_type_{attraction.type.value}"
    for tag in attraction.tags:
        if tag in ctx.avoid_types:
            return f"avoided_tag_{tag}"
    return ""


def _check_member_restrictions(attraction: Attraction, ctx: DecisionContext) -> str:
    """
    Exclui se qualquer tag da atração conflita com restrições individuais dos membros.
    Ex: membro com motion_sickness → exclui tag "spinning".
    """
    if not ctx.members:
        return ""
    attraction_tag_set = set(attraction.tags)
    for member in ctx.members:
        if hasattr(member, "restriction_tags"):
            conflicts = member.restriction_tags & attraction_tag_set
            if conflicts:
                tag = next(iter(conflicts))
                return f"member_restriction_{tag}"
    return ""


def _check_filter_override(attraction: Attraction, ctx: DecisionContext) -> str:
    """Aplica filtros temporários vindos de mensagem do usuário ('só indoor agora')."""
    if not ctx.filter_override:
        return ""
    override = ctx.filter_override

    intensity = override.get("intensity") if isinstance(override, dict) else getattr(override, "intensity", None)
    environment = override.get("environment") if isinstance(override, dict) else getattr(override, "environment", None)
    for_all = override.get("for_all_members", False) if isinstance(override, dict) else getattr(override, "for_all_members", False)

    if intensity == "low" and attraction.intensity.value in ("high", "extreme"):
        return "override_intensity_low"
    if intensity == "high" and attraction.intensity.value == "low":
        return "override_intensity_high"
    if environment == "indoor" and not attraction.is_indoor:
        return "override_indoor_only"
    if environment == "outdoor" and attraction.is_indoor:
        return "override_outdoor_only"
    if for_all and ctx.min_child_height is not None and attraction.min_height_cm > 0:
        if ctx.min_child_height < attraction.min_height_cm:
            return f"override_for_all_height_{attraction.min_height_cm}cm"

    return ""


def _check_rain_closed(attraction: Attraction, ctx: DecisionContext) -> str:
    """Exclui atrações rain_sensitive quando está chovendo."""
    if attraction.rain_sensitive and ctx.weather in ("rainy", "storm"):
        return "rain_sensitive_closed"
    return ""


def _check_soft_intensity(attraction: Attraction, ctx: DecisionContext) -> str:
    """
    Soft filter: exclui atrações 'extreme' quando há bebê/criança muito pequena
    E o grupo não marcou explicitamente como must_do.
    Não aplica se allow_group_split=True.
    """
    if ctx.allow_group_split:
        return ""
    if attraction.attraction_id in ctx.must_do_attractions:
        return ""
    if attraction.intensity.value != "extreme":
        return ""
    if ctx.min_child_height is not None and ctx.min_child_height < 90:
        return "soft_extreme_with_infant"
    return ""


def _categorize_reason(reason: str) -> str:
    """Normaliza motivo para agrupamento no exclusion_summary."""
    prefixes = [
        "height_restriction", "historical_queue_too_long", "queue_too_long",
        "avoided_type", "avoided_tag", "member_restriction", "override_for_all_height",
    ]
    for prefix in prefixes:
        if reason.startswith(prefix):
            return prefix
    return reason
