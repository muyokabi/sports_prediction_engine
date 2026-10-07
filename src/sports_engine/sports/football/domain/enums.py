from enum import StrEnum


class FixtureStatus(StrEnum):
    TBD = "TBD"
    NS = "NS"
    LIVE_FIRST_HALF = "1H"
    HALF_TIME = "HT"
    LIVE_SECOND_HALF = "2H"
    EXTRA_TIME = "ET"
    BREAK_TIME = "BT"
    PENALTIES = "P"
    SUSPENDED = "SUSP"
    INTERRUPTED = "INT"
    FINISHED = "FT"
    FINISHED_EXTRA_TIME = "AET"
    FINISHED_PENALTIES = "PEN"
    POSTPONED = "PST"
    CANCELLED = "CANC"
    ABANDONED = "ABD"
    TECHNICAL_LOSS = "AWD"
    WALKOVER = "WO"


FINAL_STATUSES = frozenset({"FT", "AET", "PEN"})
