from ..domain.models import AttractionScore


def select_primary_and_secondary(
    ranked: list[AttractionScore],
) -> tuple[AttractionScore, AttractionScore | None]:
    """
    Seleciona primary e secondary respeitando a regra de diversidade de área.
    Secondary não pode ser da mesma área que primary, a menos que não haja alternativa.
    """
    if not ranked:
        raise ValueError("Ranked list is empty")

    primary = ranked[0]

    secondary = None
    for candidate in ranked[1:]:
        if candidate.score < 50:
            break
        # Tenta encontrar atração em área diferente
        # attraction_id contém o slug — área é derivada pelo repositório
        # Aqui comparamos pelo prefixo de área no slug como heurística MVP
        if not _same_area_heuristic(primary.attraction_id, candidate.attraction_id):
            secondary = candidate
            break

    # Fallback: segunda melhor independente de área
    if secondary is None and len(ranked) > 1 and ranked[1].score >= 50:
        secondary = ranked[1]

    return primary, secondary


def _same_area_heuristic(slug_a: str, slug_b: str) -> bool:
    """
    Heurística simples para MVP: agrupa por prefixo de área conhecido.
    Em produção, usar área da atração carregada do repositório.
    """
    area_groups = {
        "fantasyland": {"seven_dwarfs", "peter_pan", "its_a_small", "dumbo", "barnstormer", "princess"},
        "tomorrowland": {"space_mountain", "buzz_lightyear", "tron", "tomorrowland"},
        "frontierland": {"big_thunder", "tiana", "splash"},
        "adventureland": {"pirates", "jungle_cruise", "enchanted"},
        "liberty_square": {"haunted_mansion", "liberty_belle", "hall_of_presidents"},
    }
    for group in area_groups.values():
        a_in = any(slug_a.startswith(k) or k in slug_a for k in group)
        b_in = any(slug_b.startswith(k) or k in slug_b for k in group)
        if a_in and b_in:
            return True
    return False
