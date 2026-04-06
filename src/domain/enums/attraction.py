from enum import Enum


class AttractionType(str, Enum):
    RIDE = "ride"
    SHOW = "show"
    CHARACTER_MEET = "character_meet"
    PARADE = "parade"
    EXPERIENCE = "experience"


class IntensityLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    EXTREME = "extreme"


class LightningLaneType(str, Enum):
    NONE = "none"
    STANDARD = "standard"
    INDIVIDUAL = "individual"


class QuestionAspect(str, Enum):
    SCARE_FACTOR = "scare_factor"
    HEIGHT_REQ = "height_req"
    WETNESS = "wetness"
    DURATION = "duration"
    ACCESSIBILITY = "accessibility"
    INTENSITY_INFO = "intensity_info"
    WAIT_ESTIMATE = "wait_estimate"
