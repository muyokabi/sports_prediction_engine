from dataclasses import dataclass, field


@dataclass(slots=True)
class JobSummary:
    requests_used: int = 0
    fixtures_discovered: int = 0
    fixtures_updated: int = 0
    fixtures_enriched: int = 0
    fixtures_quarantined: int = 0
    odds_snapshots_written: int = 0
    predictions_generated: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
