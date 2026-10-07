from enum import StrEnum


class Endpoint(StrEnum):
    STATUS = "/status"
    LEAGUES = "/leagues"
    TEAMS = "/teams"
    SQUADS = "/players/squads"
    FIXTURES = "/fixtures"
    INJURIES = "/injuries"
    ODDS = "/odds"
    EVENTS = "/fixtures/events"
    STATISTICS = "/fixtures/statistics"
    LINEUPS = "/fixtures/lineups"
    PLAYERS = "/fixtures/players"
