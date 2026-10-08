# ruff: noqa: E501
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from html import escape
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FixtureAuditRow:
    competition: str
    fixture: str
    kickoff: datetime
    terminal_state: str
    reasons: tuple[str, ...] = ()
    odds_status: str = "NOT_EVALUATED"
    model_status: str = "NO_QUALIFIED_MODEL"
    dependency_state: str = "CLEAR"


@dataclass(frozen=True, slots=True)
class ModelHealthRow:
    algorithm: str
    version: str | None
    state: str
    parent_version: str | None = None
    training_cutoff: datetime | None = None
    training_rows: int = 0
    validation_rows: int = 0
    test_rows: int = 0
    new_rows: int = 0
    log_loss: float | None = None
    brier: float | None = None
    rps: float | None = None
    ece: float | None = None
    calibration_state: str = "NOT_REQUIRED"
    drift_state: str = "NO_SIGNAL"
    next_trigger: str = "NOT_SCHEDULED"


@dataclass(frozen=True, slots=True)
class OpportunityRow:
    rank: int
    competition: str
    kickoff: datetime
    fixture: str
    market: str
    selection: str
    model_probability: float
    model_fair_odds: float
    minimum_odds: float
    reference_odds: float | None
    bookmaker: str | None
    reference_observed_at: datetime | None
    reference_age_minutes: float | None
    market_probability: float | None
    reference_edge: float | None
    robust_edge: float | None
    reference_expected_return: float | None
    uncertainty: float
    reference_state: str
    decision: str
    snapshot_count: int = 0
    price_movement: float | None = None
    bookmaker_dispersion: float | None = None
    execution_edge: float | None = None


@dataclass(frozen=True, slots=True)
class DailyAnalysisReport:
    start_date: date
    end_date: date
    generated_at: datetime
    fixtures: tuple[FixtureAuditRow, ...]
    markets_analyzed: int = 0
    qualified_opportunities: int = 0
    data_health: str = "UNKNOWN"
    odds_health: str = "UNKNOWN"
    model_health: str = "UNKNOWN"
    provider_quota: str = "UNKNOWN"
    model_versions: tuple[str, ...] = ()
    provider: str = "API-Football"
    production_mode: str = "production"
    last_data_update: datetime | None = None
    last_odds_update: datetime | None = None
    admitted_leagues: int = 0
    observation_leagues: int = 0
    eligible_fixtures: int = 0
    model_rows: tuple[ModelHealthRow, ...] = ()
    opportunities: tuple[OpportunityRow, ...] = ()
    price_targets: tuple[OpportunityRow, ...] = ()
    bankroll_exposure: float | None = None
    reference_fixtures: int = 0
    no_reference_fixtures: int = 0
    median_reference_age_minutes: float | None = None
    newest_reference_age_minutes: float | None = None
    oldest_reference_age_minutes: float | None = None
    snapshots_collected_this_run: int = 0


def _number(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _model_rows(report: DailyAnalysisReport) -> str:
    if not report.model_rows:
        return '<tr><td colspan="14" class="empty">No model assessment has been persisted.</td></tr>'
    return "".join(
        "<tr>"
        f"<td>{escape(row.algorithm)}</td><td>{escape(row.version or '—')}</td>"
        f'<td><span class="state">{escape(row.state)}</span></td><td>{escape(row.parent_version or "—")}</td>'
        f"<td>{escape(row.training_cutoff.isoformat() if row.training_cutoff else '—')}</td>"
        f"<td>{row.training_rows}</td><td>{row.validation_rows}</td><td>{row.test_rows}</td><td>{row.new_rows}</td>"
        f"<td>{_number(row.log_loss)}</td><td>{_number(row.brier)}</td><td>{_number(row.rps)}</td>"
        f"<td>{escape(row.calibration_state)}</td><td>{escape(row.next_trigger)}</td></tr>"
        for row in report.model_rows
    )


def _opportunity_rows(report: DailyAnalysisReport) -> str:
    if not report.opportunities:
        return (
            '<tr><td colspan="19" class="empty">No conditional market opportunities. Football prices and execution '
            "targets remain available in the Market Board.</td></tr>"
        )
    return "".join(
        f'<tr data-league="{escape(row.competition)}" data-decision="{escape(row.decision)}">'
        f"<td>{row.rank}</td><td>{escape(row.competition)}</td><td>{escape(row.kickoff.isoformat())}</td>"
        f"<td>{escape(row.fixture)}</td><td>{escape(row.market)}</td><td>{escape(row.selection)}</td>"
        f"<td>{row.model_probability:.3f}</td><td>{row.model_fair_odds:.2f}</td><td>{row.minimum_odds:.2f}</td>"
        f"<td>{_number(row.reference_odds, 2)}</td><td>{escape(row.bookmaker or '—')}</td>"
        f"<td>{escape(row.reference_observed_at.isoformat() if row.reference_observed_at else '—')}</td>"
        f"<td>{_number(row.reference_age_minutes, 0)}m</td><td>{_number(row.market_probability)}</td>"
        f"<td>{_number(row.reference_edge)}</td><td>{_number(row.robust_edge)}</td>"
        f"<td>{_number(row.execution_edge)}</td><td>{escape(row.reference_state)}</td>"
        f"<td>{escape(row.decision)}</td></tr>"
        for row in report.opportunities
    )


def _price_target_rows(report: DailyAnalysisReport) -> str:
    return "".join(
        f"<tr><td>{escape(row.competition)}</td><td>{escape(row.fixture)}</td><td>{escape(row.market)}</td>"
        f"<td>{escape(row.selection)}</td><td>{row.model_probability:.3f}</td><td>{row.model_fair_odds:.2f}</td>"
        f"<td>{row.minimum_odds:.2f}</td><td>{_number(row.reference_odds, 2)}</td>"
        f"<td>{escape(row.bookmaker or '—')}</td><td>{_number(row.reference_age_minutes, 0)}m</td>"
        f"<td>{row.snapshot_count}</td><td>{_number(row.price_movement)}</td>"
        f"<td>{_number(row.bookmaker_dispersion)}</td><td>{escape(row.reference_state)}</td>"
        f"<td>{escape(row.decision)}</td></tr>"
        for row in report.price_targets
    )


def render_daily_analysis(report: DailyAnalysisReport, destination: Path) -> Path:
    analyzed = sum(row.terminal_state == "ANALYZED" for row in report.fixtures)
    decision_counts = {
        decision: sum(row.decision == decision for row in report.price_targets)
        for decision in ("BET_IF_PRICE_AVAILABLE", "WATCH", "NO_BET", "PRICE_TARGET")
    }
    fixture_rows = "".join(
        f'<tr data-league="{escape(row.competition)}" data-state="{escape(row.terminal_state)}">'
        f"<td>{escape(row.competition)}</td><td>{escape(row.fixture)}</td>"
        f"<td>{escape(row.kickoff.isoformat())}</td><td>{escape(row.terminal_state)}</td>"
        f"<td>{escape(row.odds_status)}</td><td>{escape(row.model_status)}</td>"
        f"<td>{escape(', '.join(row.reasons))}</td></tr>"
        for row in report.fixtures
    )
    research_panels = "".join(
        f"<details><summary><strong>{escape(row.fixture)}</strong><span>{escape(row.competition)} · "
        f'{escape(row.kickoff.isoformat())}</span><span class="state">{escape(row.terminal_state)}</span></summary>'
        '<div class="research-grid">'
        f"<section><h3>Match</h3><p>Dependency: {escape(row.dependency_state)}</p>"
        f"<p>Reasons: {escape(', '.join(row.reasons) or 'none')}</p></section>"
        f'<section><h3>Football state</h3><p class="muted">{escape("Fundamental probabilities persisted from the qualified point-in-time champion." if row.model_status.startswith("FUNDAMENTAL:") else "Not priced until a qualified point-in-time engine exists.")}</p></section>'
        f"<section><h3>Market</h3><p>Odds: {escape(row.odds_status)}</p></section>"
        f"<section><h3>Decision</h3><p>{escape(row.terminal_state)}</p></section></div></details>"
        for row in report.fixtures
    )
    warnings = []
    if report.model_health != "QUALIFIED":
        warnings.append(f"No actionable model: {report.model_health}")
    if report.no_reference_fixtures:
        warnings.append(
            f"No API-Football reference for {report.no_reference_fixtures} fixtures; price targets remain available"
        )
    warning_html = "".join(f'<div class="warning">{escape(item)}</div>' for item in warnings)
    leagues = sorted({row.competition for row in report.fixtures})
    league_options = "".join(f'<option value="{escape(item)}">{escape(item)}</option>' for item in leagues)
    embedded = json.dumps(asdict(report), default=str, ensure_ascii=False).replace("</", "<\\/")
    tabs = (
        ("overview", "Overview"),
        ("opportunities", "Top opportunities"),
        ("matches", "All matches"),
        ("market", "Market board"),
        ("models", "Model health"),
        ("data", "Data health"),
        ("audit", "Audit"),
    )
    nav = "".join(
        f'<button data-tab="{tab}" class="{"active" if tab == "overview" else ""}">{label}</button>'
        for tab, label in tabs
    )
    metrics = (
        ("Expected fixtures", len(report.fixtures)),
        ("Analyzed", analyzed),
        ("Conditional candidates", decision_counts["BET_IF_PRICE_AVAILABLE"]),
        ("Markets priced", report.markets_analyzed),
        ("Price targets only", decision_counts["PRICE_TARGET"]),
        ("Watch", decision_counts["WATCH"]),
        ("No bet", decision_counts["NO_BET"]),
        ("Admitted leagues", report.admitted_leagues),
        ("Observation leagues", report.observation_leagues),
        ("Eligible history", report.eligible_fixtures),
        ("Fixtures with references", report.reference_fixtures),
        ("Fixtures without references", report.no_reference_fixtures),
        ("Median reference age", f"{_number(report.median_reference_age_minutes, 0)}m"),
        ("Newest reference age", f"{_number(report.newest_reference_age_minutes, 0)}m"),
        ("Oldest reference age", f"{_number(report.oldest_reference_age_minutes, 0)}m"),
        ("Snapshots this run", report.snapshots_collected_this_run),
        ("Exposure", _number(report.bankroll_exposure)),
    )
    metric_html = "".join(
        f'<div class="metric"><span class="label">{label}</span><span class="value">{value}</span></div>'
        for label, value in metrics
    )
    market_rows = _price_target_rows(report)
    state_options = "".join(
        f"<option>{escape(state)}</option>" for state in sorted({row.terminal_state for row in report.fixtures})
    )
    title = f"Institutional football pricing · {report.start_date} to {report.end_date}"
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>
:root{{--bg:#0a101b;--panel:#111a28;--panel2:#162132;--line:#26354a;--ink:#e7edf7;--muted:#91a0b6;
--accent:#63a4ff;--warn:#e7b45d;--mono:ui-monospace,SFMono-Regular,Consolas,monospace}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:13px/1.45 Inter,system-ui,sans-serif}}
header{{padding:24px 30px 18px;border-bottom:1px solid var(--line);background:#0d1522;position:sticky;top:0;z-index:3}}
.brand{{letter-spacing:.13em;font-weight:750;font-size:12px;color:var(--accent)}}h1{{font-size:21px;margin:3px 0 10px}}
.meta,.board{{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:1px;background:var(--line)}}
.meta div,.metric{{background:var(--panel);padding:9px 11px}}.label{{display:block;color:var(--muted);font-size:10px;text-transform:uppercase}}
.value{{font:600 17px/1.3 var(--mono);font-variant-numeric:tabular-nums}}nav{{display:flex;gap:6px;padding:10px 30px;border-bottom:1px solid var(--line);overflow:auto}}
button,select{{background:var(--panel);color:var(--ink);border:1px solid var(--line);padding:7px 10px;border-radius:3px}}
button.active{{border-color:var(--accent);color:var(--accent)}}main{{padding:20px 30px 50px;max-width:1800px;margin:auto}}
.tab{{display:none}}.tab.active{{display:block}}h2{{font-size:14px;text-transform:uppercase;letter-spacing:.08em;margin:24px 0 10px}}
h3{{font-size:12px;text-transform:uppercase;color:var(--muted)}}.warning{{border-left:3px solid var(--warn);background:#2b2418;padding:9px 12px;margin:8px 0}}
.panel{{border:1px solid var(--line);background:var(--panel);padding:14px;margin-bottom:12px;overflow:auto}}
table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}}th{{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.05em;position:sticky;top:0;background:var(--panel2)}}
th,td{{text-align:left;padding:8px 9px;border-bottom:1px solid var(--line);white-space:nowrap}}tr:hover td{{background:#172438}}
.state{{font:600 11px var(--mono);color:var(--accent)}}.muted,.empty{{color:var(--muted)}}.empty{{padding:28px;text-align:center}}
details{{border:1px solid var(--line);background:var(--panel);margin:7px 0}}summary{{display:grid;grid-template-columns:2fr 2fr 1fr;gap:12px;padding:11px;cursor:pointer}}
.research-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1px;background:var(--line);border-top:1px solid var(--line)}}
.research-grid section{{background:var(--panel);padding:12px}}.filters{{display:flex;gap:8px;margin:8px 0 12px}}
@media(max-width:700px){{header,main{{padding-left:14px;padding-right:14px}}nav{{padding-left:14px}}summary{{grid-template-columns:1fr}}}}
</style></head><body><header><div class="brand">SPORTS ENGINE</div><h1>INSTITUTIONAL FOOTBALL PRICING</h1>
<div class="meta"><div><span class="label">Analysis range</span>{report.start_date} — {report.end_date}</div>
<div><span class="label">Generated</span>{escape(report.generated_at.isoformat())}</div>
<div><span class="label">Last data update</span>{escape(str(report.last_data_update or "—"))}</div>
<div><span class="label">Last odds update</span>{escape(str(report.last_odds_update or "—"))}</div>
<div><span class="label">Provider / mode</span>{escape(report.provider)} · {escape(report.production_mode)}</div>
<div><span class="label">Quota remaining</span>{escape(report.provider_quota)}</div>
<div><span class="label">Data health</span>{escape(report.data_health)}</div>
<div><span class="label">Model health</span>{escape(report.model_health)}</div></div></header>
<nav>{nav}</nav><main>{warning_html}<section id="overview" class="tab active"><h2>Executive market board</h2>
<div class="board">{metric_html}</div><div class="warning"><strong>MANUAL PRICE CONFIRMATION REQUIRED.</strong> Place only if your broker currently offers at least the displayed minimum acceptable odds. API-Football prices are reference observations, not guaranteed executable prices.</div><h2>Research state</h2><div class="panel">
<p>Football pricing and market reference are separate: eligible history is <strong>{report.eligible_fixtures}</strong>; model state is <strong>{escape(report.model_health)}</strong>; market references are <strong>{escape(report.odds_health)}</strong>. Execution edge remains unknown until an operator checks a broker.</p>
<p class="muted">No probability, price, or opportunity is inferred when persisted evidence is unavailable.</p></div></section>
<section id="opportunities" class="tab"><h2>Top conditional opportunities</h2><p class="muted">Reference edge compares the model with API-Football. Execution edge is unknown until the operator supplies an actual broker price.</p><div class="filters"><select id="league-filter"><option value="">All leagues</option>{league_options}</select><select id="decision-filter"><option value="">All decisions</option><option>BET_IF_PRICE_AVAILABLE</option><option>WATCH</option></select></div><div class="panel"><table id="opportunity-table"><thead><tr><th>Rank</th><th>League</th><th>Kickoff</th><th>Fixture</th><th>Market</th><th>Selection</th><th>Model p</th><th>Fair odds</th><th>Minimum odds</th><th>Latest best API reference</th><th>Reference bookmaker</th><th>Reference observed</th><th>Age</th><th>Market p</th><th>Reference edge</th><th>Robust estimate</th><th>Execution edge</th><th>Reference state</th><th>Decision</th></tr></thead><tbody>{_opportunity_rows(report)}</tbody></table></div></section>
<section id="matches" class="tab"><h2>Fixture research panels</h2>{research_panels or '<div class="panel empty">No expected fixtures in this range.</div>'}</section>
<section id="market" class="tab"><h2>Football price targets and API-Football references</h2><p class="muted">Latest-per-bookmaker references are used for comparison. Earlier snapshots contribute movement history only.</p><div class="panel"><table><thead><tr><th>Competition</th><th>Fixture</th><th>Market</th><th>Selection</th><th>Model p</th><th>Fair odds</th><th>Minimum odds</th><th>Latest best API reference</th><th>Bookmaker</th><th>Age</th><th>Snapshots</th><th>Movement</th><th>Dispersion</th><th>Reference state</th><th>Decision</th></tr></thead><tbody>{market_rows}</tbody></table></div></section>
<section id="models" class="tab"><h2>Model health and continuous learning</h2><div class="panel"><table><thead><tr><th>Algorithm</th><th>Version</th><th>State</th><th>Parent</th><th>Train cutoff</th><th>Train</th><th>Validation</th><th>Test</th><th>New</th><th>Log loss</th><th>Brier</th><th>RPS</th><th>Calibration</th><th>Next trigger</th></tr></thead><tbody>{_model_rows(report)}</tbody></table></div></section>
<section id="data" class="tab"><h2>Data health</h2><div class="board"><div class="metric"><span class="label">Eligible fixtures</span><span class="value">{report.eligible_fixtures}</span></div><div class="metric"><span class="label">Observation leagues</span><span class="value">{report.observation_leagues}</span></div><div class="metric"><span class="label">Odds health</span><span class="value">{escape(report.odds_health)}</span></div></div></section>
<section id="audit" class="tab"><h2>Full universe audit</h2><div class="filters"><select id="audit-league"><option value="">All leagues</option>{league_options}</select><select id="audit-state"><option value="">All states</option>{state_options}</select></div><div class="panel"><table id="audit-table"><thead><tr><th>Competition</th><th>Fixture</th><th>Kickoff</th><th>State</th><th>Odds</th><th>Model</th><th>Reasons</th></tr></thead><tbody>{fixture_rows}</tbody></table></div></section></main>
<script type="application/json" id="report-data">{embedded}</script><script>
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{{document.querySelectorAll('nav button,.tab').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.getElementById(b.dataset.tab).classList.add('active')}});
function filter(table,league,state){{document.querySelectorAll(table+' tbody tr[data-league]').forEach(r=>r.hidden=(league&&r.dataset.league!==league)||(state&&(r.dataset.state||r.dataset.decision)!==state))}}
document.getElementById('league-filter').onchange=e=>filter('#opportunity-table',e.target.value,document.getElementById('decision-filter').value);
document.getElementById('decision-filter').onchange=e=>filter('#opportunity-table',document.getElementById('league-filter').value,e.target.value);
document.getElementById('audit-league').onchange=e=>filter('#audit-table',e.target.value,document.getElementById('audit-state').value);
document.getElementById('audit-state').onchange=e=>filter('#audit-table',document.getElementById('audit-league').value,e.target.value);
</script></body></html>"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(document, encoding="utf-8")
    return destination
