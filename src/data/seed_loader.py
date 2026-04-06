"""
seed_loader.py — Carrega os dados de seed em objetos de domínio prontos para uso.

Uso nos testes:
    from src.data.seed_loader import load_test_scenario, list_scenarios

    scenario = load_test_scenario("ctx_morning_busy")
    group    = scenario.group
    prefs    = scenario.preferences
    context  = scenario.context
    attractions = scenario.attractions
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Optional

SEEDS_DIR = Path(__file__).parent.parent.parent / "data" / "seeds"


@dataclass
class TestScenario:
    label: str
    scenario_description: str
    group_id: str
    group: object          # Group domain object
    preferences: object    # GroupPreferences domain object
    context: object        # OperationalContext domain object
    attractions: list      # list[Attraction]


# ── Public API ─────────────────────────────────────────────────────────────────

def load_test_scenario(context_id: str) -> TestScenario:
    """
    Carrega um cenário completo pelo context_id.
    Retorna TestScenario com grupo, preferências, contexto e atrações prontos.
    """
    contexts = _load_json("test_contexts.json")["test_contexts"]
    if context_id not in contexts:
        available = list(contexts.keys())
        raise KeyError(f"Context '{context_id}' not found. Available: {available}")

    ctx_raw = contexts[context_id]
    groups = _load_json("test_groups.json")["test_groups"]
    group_id = ctx_raw["group_id"]

    if group_id not in groups:
        raise KeyError(f"Group '{group_id}' referenced in context '{context_id}' not found")

    group_raw = groups[group_id]
    attractions = load_attractions()

    group, prefs = _build_group(group_raw)
    context = _build_context(ctx_raw)

    return TestScenario(
        label=ctx_raw.get("_label", context_id),
        scenario_description=ctx_raw.get("_scenario", ""),
        group_id=group_id,
        group=group,
        preferences=prefs,
        context=context,
        attractions=attractions,
    )


def load_all_scenarios() -> dict[str, TestScenario]:
    """Carrega todos os cenários de teste."""
    contexts = _load_json("test_contexts.json")["test_contexts"]
    return {ctx_id: load_test_scenario(ctx_id) for ctx_id in contexts}


def load_attractions() -> list:
    """Carrega o catálogo completo de atrações do Magic Kingdom."""
    from src.infra.repositories.attractions_repository import AttractionsRepository
    repo = AttractionsRepository()
    return repo.get_all_active()


def list_scenarios() -> list[dict]:
    """Lista os cenários disponíveis com seus metadados."""
    contexts = _load_json("test_contexts.json")["test_contexts"]
    return [
        {
            "context_id": ctx_id,
            "label": ctx_raw.get("_label", ctx_id),
            "scenario": ctx_raw.get("_scenario", ""),
            "group_id": ctx_raw["group_id"],
            "time": ctx_raw["current_datetime"],
            "location": ctx_raw["current_location_area"],
            "weather": ctx_raw.get("weather"),
            "active_states": ctx_raw.get("active_states", []),
        }
        for ctx_id, ctx_raw in contexts.items()
    ]


def list_groups() -> list[dict]:
    """Lista os grupos de teste disponíveis."""
    groups = _load_json("test_groups.json")["test_groups"]
    return [
        {
            "group_id": gid,
            "label": g.get("_label", gid),
            "profile_id": g["profile_id"],
            "members": len(g["members"]),
        }
        for gid, g in groups.items()
    ]


# ── Builders internos ──────────────────────────────────────────────────────────

def _build_group(raw: dict):
    """Constrói Group + GroupPreferences a partir do dict do seed."""
    from src.domain.models.group import Group, Member, GroupPreferences
    from src.domain.enums import ProfileType

    members = [
        Member(
            role=m["role"],
            age=m.get("age"),
            height_cm=m.get("height_cm"),
            name=m.get("name"),
            fear_of_dark=m.get("fear_of_dark", False),
            fear_of_heights=m.get("fear_of_heights", False),
            motion_sickness=m.get("motion_sickness", False),
            mobility_restricted=m.get("mobility_restricted", False),
        )
        for m in raw["members"]
    ]

    group = Group(
        group_id=raw["group_id"],
        whatsapp_number=raw["whatsapp_number"],
        park_id=raw["park_id"],
        visit_date=date.fromisoformat(raw["visit_date"]),
        members=members,
        language=raw.get("language", "pt-BR"),
        profile_id=ProfileType(raw["profile_id"]),
        setup_complete=raw.get("setup_complete", True),
    )

    p = raw["preferences"]
    prefs = GroupPreferences(
        pref_id=p["pref_id"],
        group_id=raw["group_id"],
        intensity_preference=p.get("intensity_preference", "moderate"),
        priority_order=p.get("priority_order", []),
        avoid_types=p.get("avoid_types", []),
        max_queue_minutes=p.get("max_queue_minutes", 45),
        must_do_attractions=p.get("must_do_attractions", []),
        skip_attractions=p.get("skip_attractions", []),
        show_interest=p.get("show_interest", True),
        meal_break_times=p.get("meal_break_times", []),
        allow_group_split=p.get("allow_group_split", False),
    )

    return group, prefs


def _build_context(raw: dict):
    """Constrói OperationalContext a partir do dict do seed."""
    from src.domain.models.context import OperationalContext, FilterOverride
    from src.domain.enums import WeatherCondition, GroupStateType

    weather = None
    if raw.get("weather"):
        try:
            weather = WeatherCondition(raw["weather"])
        except ValueError:
            pass

    states = []
    for s in raw.get("active_states", []):
        try:
            states.append(GroupStateType(s))
        except ValueError:
            pass

    fo = None
    if raw.get("filter_override"):
        f = raw["filter_override"]
        fo = FilterOverride(
            intensity=f.get("intensity"),
            environment=f.get("environment"),
            max_queue_minutes=f.get("max_queue_minutes"),
            for_all_members=f.get("for_all_members", False),
        )

    return OperationalContext(
        context_id=raw["context_id"],
        group_id=raw["group_id"],
        current_park_id=raw["current_park_id"],
        current_datetime=datetime.fromisoformat(raw["current_datetime"]),
        current_location_area=raw["current_location_area"],
        queue_snapshot=raw.get("queue_snapshot", {}),
        queue_snapshot_at=datetime.fromisoformat(raw["queue_snapshot_at"])
            if raw.get("queue_snapshot_at") else None,
        done_attractions=raw.get("done_attractions", []),
        closed_attractions=raw.get("closed_attractions", []),
        active_states=states,
        filter_override=fo,
        weather=weather,
        crowd_level=raw.get("crowd_level"),
        special_event=raw.get("special_event"),
    )


def _load_json(filename: str) -> dict:
    path = SEEDS_DIR / filename
    with open(path, encoding="utf-8") as f:
        return json.load(f)
