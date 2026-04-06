from enum import Enum


class IntentType(str, Enum):
    CHECK_IN = "CHECK_IN"
    GET_REC = "GET_REC"
    EVAL_QUEUE = "EVAL_QUEUE"
    UPDATE_LOC = "UPDATE_LOC"
    UPDATE_STATE = "UPDATE_STATE"
    FILTER_REQ = "FILTER_REQ"
    MARK_DONE = "MARK_DONE"
    QUESTION = "QUESTION"
    UNKNOWN = "UNKNOWN"
