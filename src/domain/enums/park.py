from enum import Enum


class ParkArea(str, Enum):
    MAIN_STREET = "main_street"
    ADVENTURELAND = "adventureland"
    FRONTIERLAND = "frontierland"
    LIBERTY_SQUARE = "liberty_square"
    FANTASYLAND = "fantasyland"
    TOMORROWLAND = "tomorrowland"
    STORYBOOK_CIRCUS = "storybook_circus"


class TimeOfDay(str, Enum):
    ROPE_DROP = "rope_drop"
    MORNING = "morning"
    MIDDAY = "midday"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    NIGHT = "night"


class WeatherCondition(str, Enum):
    SUNNY = "sunny"
    CLOUDY = "cloudy"
    RAINY = "rainy"
    STORM = "storm"


class GroupStateType(str, Enum):
    TIRED = "tired"
    HUNGRY = "hungry"
    HOT = "hot"
    WET = "wet"
    CRANKY = "cranky"
    NEEDS_REST = "needs_rest"
    ENERGIZED = "energized"
