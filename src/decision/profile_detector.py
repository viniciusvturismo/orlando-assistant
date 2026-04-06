from ..domain.models import Member
from ..domain.enums import ProfileType


def detect_profile(members: list[Member]) -> ProfileType:
    """Detecta o perfil do grupo com base na composição dos membros."""
    if not members:
        return ProfileType.P4

    ages = [m.age for m in members if m.age is not None]
    roles = [m.role for m in members]

    has_infant = any(m.role == "infant" for m in members)
    has_toddler = any(m.role == "child" and m.age is not None and m.age <= 5 for m in members)
    has_school_child = any(m.role == "child" and m.age is not None and 6 <= m.age <= 12 for m in members)
    has_teen = any(m.role == "child" and m.age is not None and 13 <= m.age <= 17 for m in members)
    has_senior = any(m.role == "senior" for m in members)
    has_mobility = any(m.mobility_restricted for m in members)

    adults = [m for m in members if m.role == "adult"]
    has_multiple_generations = has_senior and len(adults) >= 1 and (has_school_child or has_toddler)

    if has_infant or has_toddler:
        return ProfileType.P1

    if has_multiple_generations:
        return ProfileType.P6

    if has_school_child:
        return ProfileType.P2

    if has_teen:
        return ProfileType.P3

    if has_senior or has_mobility:
        return ProfileType.P5

    # Grupo de adultos — P4 é o padrão, P7 se sinalizarem alta intensidade
    return ProfileType.P4
