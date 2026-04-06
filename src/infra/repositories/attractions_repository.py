import json
import logging
from pathlib import Path
from typing import Optional

from ...domain.models import Attraction
from ...domain.enums import AttractionType, IntensityLevel, ParkArea, TimeOfDay, LightningLaneType

logger = logging.getLogger(__name__)

SEEDS_PATH = Path(__file__).parent.parent.parent.parent / "data" / "seeds"


class AttractionsRepository:
    """
    Carrega o catálogo de atrações do JSON seed em memória.
    Read-only em runtime. Suporta reload sem restart.
    """

    def __init__(self):
        self._attractions: dict[str, Attraction] = {}
        self._load_all()

    def _load_all(self) -> None:
        seed_file = SEEDS_PATH / "magic_kingdom_attractions.json"
        if not seed_file.exists():
            logger.warning("Seed file not found: %s", seed_file)
            return

        with open(seed_file, encoding="utf-8") as f:
            data = json.load(f)

        loaded = 0
        for slug, raw in data.get("mk_attractions", {}).items():
            try:
                attraction = self._deserialize(slug, raw)
                self._attractions[slug] = attraction
                loaded += 1
            except Exception as e:
                logger.error("Failed to load attraction %s: %s", slug, e)

        logger.info("Loaded %d attractions from seed", loaded)

    def _deserialize(self, slug: str, raw: dict) -> Attraction:
        return Attraction(
            attraction_id=slug,
            park_id=raw.get("park_id", "magic_kingdom"),
            name=raw["name"],
            name_pt=raw.get("name_pt", raw["name"]),
            area=ParkArea(raw["area"]),
            type=AttractionType(raw["type"]),
            intensity=IntensityLevel(raw["intensity"]),
            description_pt=raw.get("description_pt", ""),
            min_height_cm=raw.get("min_height_cm", 0),
            duration_minutes=raw.get("duration_minutes", 5),
            is_indoor=raw.get("is_indoor", False),
            rain_sensitive=raw.get("rain_sensitive", False),
            suitable_for_infants=raw.get("suitable_for_infants", False),
            rider_swap=raw.get("rider_swap", False),
            base_priority_score=raw.get("base_priority_score", 0.5),
            tags=raw.get("tags", []),
            ideal_profiles=raw.get("ideal_profiles", []),
            best_time_of_day=[TimeOfDay(t) for t in raw.get("best_time_of_day", [])],
            avoid_time_of_day=[TimeOfDay(t) for t in raw.get("avoid_time_of_day", [])],
            avg_wait_by_period=raw.get("avg_wait_by_period", {}),
            location_zone=raw.get("location_zone", ""),
            adjacent_areas=raw.get("adjacent_areas", []),
            nearby_attractions=raw.get("nearby_attractions", []),
            strategic_notes=raw.get("strategic_notes", ""),
            lightning_lane=LightningLaneType(raw.get("lightning_lane", "none")),
            active=raw.get("active", True),
        )

    def get_all_active(self) -> list[Attraction]:
        return [a for a in self._attractions.values() if a.active]

    def get_by_id(self, attraction_id: str) -> Optional[Attraction]:
        return self._attractions.get(attraction_id)

    def filter_by_area(self, area: ParkArea) -> list[Attraction]:
        return [a for a in self.get_all_active() if a.area == area]

    def filter_by_profile(self, profile_id: str) -> list[Attraction]:
        return [a for a in self.get_all_active() if profile_id in a.ideal_profiles]

    def reload(self) -> int:
        self._attractions.clear()
        self._load_all()
        return len(self._attractions)


# Singleton
_repo: Optional[AttractionsRepository] = None


def get_attractions_repository() -> AttractionsRepository:
    global _repo
    if _repo is None:
        _repo = AttractionsRepository()
    return _repo
