# ruff: noqa: E501
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from html import escape
from pathlib import Path
from typing import Any


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
    applicability: Any | None = None


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
    reasons: tuple[str, ...] = ()
    applicability_state: str = "OUT_OF_DOMAIN"
    applicability_level: str = "OUT_OF_DOMAIN"


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
    report_mode: str = "LIVE"
    source_live_run_id: str | None = None


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
            '<tr><td colspan="20" class="empty">No conditional market opportunities: no production- or shadow-qualified rows. Research signals remain '
            "available in the Market Board.</td></tr>"
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
        f"<td>{escape(row.decision)}</td><td>{escape(', '.join(row.reasons))}</td></tr>"
        for row in report.opportunities
    )


def _price_target_rows(report: DailyAnalysisReport) -> str:
    return "".join(
        f'<tr data-league="{escape(row.competition)}" data-market="{escape(row.market.split()[0])}" '
        f'data-decision="{escape(row.decision)}"><td>{escape(row.competition)}</td><td>{escape(row.fixture)}</td>'
        f"<td>{escape(row.market)}</td><td>{escape(row.selection)}</td>"
        f'<td><div class="probability"><span>{row.model_probability:.3f}</span><i style="--p:{row.model_probability:.4f}"></i></div></td>'
        f"<td>{row.model_fair_odds:.2f}</td>"
        f"<td>{row.minimum_odds:.2f}</td><td>{_number(row.reference_odds, 2)}</td>"
        f"<td>{escape(row.bookmaker or '—')}</td><td>{_number(row.reference_age_minutes, 0)}m</td>"
        f"<td>{row.snapshot_count}</td><td>{_number(row.price_movement)}</td>"
        f"<td>{_number(row.bookmaker_dispersion)}</td><td>{escape(row.reference_state)}</td>"
        f'<td><span class="decision-badge">{escape(row.decision)}</span></td>'
        f"<td>{escape(', '.join(row.reasons))}</td></tr>"
        for row in report.price_targets
    )


def _top_research_predictions(report: DailyAnalysisReport, limit: int = 10) -> tuple[OpportunityRow, ...]:
    """Rank one research selection per fixture without implying betting value."""
    tier = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "PRIOR_ONLY": 3, "OUT_OF_DOMAIN": 4}
    candidates = sorted(
        report.price_targets,
        key=lambda row: (
            tier.get(row.applicability_level, 5),
            -(row.model_probability - row.uncertainty),
            row.kickoff,
            row.fixture,
            row.market,
            row.selection,
        ),
    )
    selected: list[OpportunityRow] = []
    seen_fixtures: set[tuple[str, datetime]] = set()
    for row in candidates:
        fixture_key = (row.fixture, row.kickoff)
        if fixture_key in seen_fixtures:
            continue
        seen_fixtures.add(fixture_key)
        selected.append(row)
        if len(selected) >= limit:
            break
    return tuple(selected)


def _research_prediction_rows(report: DailyAnalysisReport) -> str:
    rows = _top_research_predictions(report)
    if not rows:
        return (
            '<tr><td colspan="12" class="empty">No research prediction is available.</td></tr>'
        )
    return "".join(
        f"<tr><td>{rank}</td><td>{escape(row.competition)}</td>"
        f"<td>{escape(row.kickoff.isoformat())}</td><td>{escape(row.fixture)}</td>"
        f"<td>{escape(row.market)}</td><td>{escape(row.selection)}</td>"
        f"<td>{row.model_probability:.3f}</td><td>{row.uncertainty:.3f}</td>"
        f"<td>{max(0.0, row.model_probability - row.uncertainty):.3f}</td>"
        f"<td>{escape(row.applicability_level)}</td><td>{escape(row.applicability_state)}</td>"
        f"<td>{escape(row.decision)}</td></tr>"
        for rank, row in enumerate(rows, start=1)
    )


def render_daily_analysis(report: DailyAnalysisReport, destination: Path) -> Path:
    analyzed = sum(row.terminal_state == "ANALYZED" for row in report.fixtures)
    decision_counts = {
        decision: sum(row.decision == decision for row in report.price_targets)
        for decision in (
            "PRODUCTION_ACTIONABLE",
            "SHADOW_ACTIONABLE",
            "RESEARCH_VALUE_SIGNAL",
            "RESEARCH_ONLY",
            "PRICE_TARGET",
        )
    }
    fixture_rows = "".join(
        f'<tr data-league="{escape(row.competition)}" data-state="{escape(row.terminal_state)}">'
        f"<td>{escape(row.competition)}</td><td>{escape(row.fixture)}</td>"
        f"<td>{escape(row.kickoff.isoformat())}</td><td>{escape(row.terminal_state)}</td>"
        f"<td>{escape(row.odds_status)}</td><td>{escape(row.model_status)}</td>"
        f"<td>{escape(', '.join(row.reasons))}</td></tr>"
        for row in report.fixtures
    )

    def football_detail(row: FixtureAuditRow) -> str:
        item = row.applicability
        if item is None:
            return "Not priced until a qualified point-in-time engine exists."
        probabilities = item.probabilities
        return (
            f"Applicability: {item.level} ({item.state}) · {escape(row.model_status)}<br>"
            f"xG {item.expected_home_goals:.3f}–{item.expected_away_goals:.3f}; supremacy "
            f"{item.expected_home_goals - item.expected_away_goals:.3f}; total "
            f"{item.expected_home_goals + item.expected_away_goals:.3f}<br>"
            f"1X2 {probabilities['home']:.3f} / {probabilities['draw']:.3f} / {probabilities['away']:.3f}; "
            f"BTTS Y/N {probabilities['btts_yes']:.3f} / {probabilities['btts_no']:.3f}; "
            f"O/U2.5 {probabilities['over_2_5']:.3f} / {probabilities['under_2_5']:.3f}<br>"
            f"History H/A {item.home.observations}/{item.away.observations}; effective "
            f"{item.home.effective_observations:.2f}/{item.away.effective_observations:.2f}; "
            f"competition {item.competition_observations}<br>"
            f"Parameters H atk/def {item.home_attack:.3f}/{item.home_defence:.3f}; "
            f"A atk/def {item.away_attack:.3f}/{item.away_defence:.3f}; baseline "
            f"{item.competition_baseline:.3f}; home advantage {item.home_advantage:.3f}<br>"
            f"Decision gates: {escape(', '.join(item.reasons) or 'fixture evidence passed')}"
        )

    research_panels = "".join(
        f"<details><summary><strong>{escape(row.fixture)}</strong><span>{escape(row.competition)} · "
        f'{escape(row.kickoff.isoformat())}</span><span class="state">{escape(row.terminal_state)}</span></summary>'
        '<div class="research-grid">'
        f"<section><h3>Match</h3><p>Dependency: {escape(row.dependency_state)}</p>"
        f"<p>Reasons: {escape(', '.join(row.reasons) or 'none')}</p></section>"
        f'<section><h3>Football state</h3><p class="muted">{football_detail(row)}</p></section>'
        f"<section><h3>Market</h3><p>Odds: {escape(row.odds_status)}</p></section>"
        f"<section><h3>Decision</h3><p>{escape(row.terminal_state)}</p></section></div></details>"
        for row in report.fixtures
    )
    warnings = []
    if report.model_health not in {"QUALIFIED", "CHAMPION_QUALIFIED"}:
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
        ("research", "Top research"),
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
        ("Shadow qualified", decision_counts["SHADOW_ACTIONABLE"]),
        ("Production qualified", decision_counts["PRODUCTION_ACTIONABLE"]),
        ("Research value signals", decision_counts["RESEARCH_VALUE_SIGNAL"]),
        ("Market families priced", len({row.market.split()[0] for row in report.price_targets})),
        ("Market lines priced", len({(row.fixture, row.market) for row in report.price_targets})),
        ("Selections priced", report.markets_analyzed),
        ("Price targets only", decision_counts["PRICE_TARGET"]),
        ("Research only", decision_counts["RESEARCH_ONLY"]),
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
        f'<div class="metric"><span class="label">{label}</span>'
        f'<span class="value"{f" data-count={value}" if isinstance(value, int) else ""}>{value}</span></div>'
        for label, value in metrics
    )
    market_counts: dict[str, int] = {}
    for row in report.price_targets:
        family = row.market.split()[0]
        market_counts[family] = market_counts.get(family, 0) + 1
    largest_market = max(market_counts.values(), default=1)
    market_chart = (
        "".join(
            f'<div class="bar-row"><span>{escape(name.replace("_", " "))}</span><div class="bar-track">'
            f'<i style="--w:{count / largest_market:.4f}"></i></div><strong>{count}</strong></div>'
            for name, count in sorted(market_counts.items(), key=lambda item: (-item[1], item[0]))
        )
        or '<p class="empty">No market prices in this range.</p>'
    )
    total_decisions = max(1, len(report.price_targets))
    signal_share = 100 * decision_counts["RESEARCH_VALUE_SIGNAL"] / total_decisions
    shadow_share = 100 * decision_counts["SHADOW_ACTIONABLE"] / total_decisions
    production_share = 100 * decision_counts["PRODUCTION_ACTIONABLE"] / total_decisions
    decision_visual = (
        f'<div class="donut" style="--production:{production_share:.2f};--shadow:{shadow_share:.2f};'
        f'--signal:{signal_share:.2f}"><div><strong>{len(report.price_targets)}</strong><span>priced selections</span></div></div>'
    )
    market_rows = _price_target_rows(report)
    state_options = "".join(
        f"<option>{escape(state)}</option>" for state in sorted({row.terminal_state for row in report.fixtures})
    )
    title = f"Institutional football pricing · {report.start_date} to {report.end_date}"
    replay_banner = (
        '<div class="warning"><strong>OFFLINE REPLAY — NO PROVIDER CALLS MADE IN THIS RENDER.</strong></div>'
        if report.report_mode == "OFFLINE_REPLAY"
        else ""
    )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>
:root{{--bg:#050812;--bg2:#091222;--panel:rgba(15,25,43,.78);--panel-solid:#101c30;--panel2:#14243d;--line:rgba(151,177,219,.16);--line-hot:rgba(83,222,204,.42);--ink:#f4f8ff;--muted:#91a4c0;--accent:#53decc;--accent2:#7897ff;--violet:#b28cff;--warn:#ffc96b;--danger:#ff7b91;--success:#6ee7a8;--shadow:0 24px 70px rgba(0,0,0,.34);--mono:ui-monospace,SFMono-Regular,Consolas,monospace}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;min-height:100vh;background:radial-gradient(circle at 12% -8%,rgba(83,222,204,.16),transparent 31%),radial-gradient(circle at 88% 4%,rgba(120,151,255,.18),transparent 34%),linear-gradient(155deg,var(--bg),var(--bg2) 56%,#050914);color:var(--ink);font:13px/1.55 Inter,"Segoe UI",system-ui,sans-serif;overflow-x:hidden}}
body:before{{content:"";position:fixed;inset:0;pointer-events:none;opacity:.28;background-image:linear-gradient(rgba(255,255,255,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.025) 1px,transparent 1px);background-size:42px 42px;mask-image:linear-gradient(to bottom,#000,transparent 78%);z-index:-1}}
.ambient{{position:absolute;border-radius:50%;filter:blur(80px);pointer-events:none;opacity:.22;animation:float 14s ease-in-out infinite alternate}}.ambient.a{{width:340px;height:340px;left:-120px;top:-120px;background:var(--accent)}}.ambient.b{{width:420px;height:420px;right:-150px;top:-180px;background:var(--accent2);animation-delay:-6s}}
header{{position:relative;isolation:isolate;padding:42px clamp(18px,4vw,64px) 24px;border-bottom:1px solid var(--line);overflow:hidden}}.hero{{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;max-width:1800px;margin:auto}}.brand{{display:flex;align-items:center;gap:9px;letter-spacing:.18em;font-weight:800;font-size:11px;color:var(--accent)}}.brand:before{{content:"";width:10px;height:10px;border:2px solid var(--accent);border-radius:50%;box-shadow:0 0 20px var(--accent);animation:pulse 2.5s ease-in-out infinite}}h1{{font-size:clamp(28px,4vw,54px);line-height:1.04;letter-spacing:-.04em;margin:11px 0 9px;max-width:850px}}.subtitle{{color:var(--muted);max-width:760px;font-size:14px;margin:0 0 24px}}.status-chip{{display:flex;align-items:center;gap:8px;white-space:nowrap;padding:9px 13px;border:1px solid var(--line-hot);background:rgba(83,222,204,.08);border-radius:999px;color:var(--accent);font:700 10px var(--mono);letter-spacing:.08em;text-transform:uppercase;box-shadow:0 0 40px rgba(83,222,204,.08)}}.status-chip:before{{content:"";width:7px;height:7px;border-radius:50%;background:var(--accent);box-shadow:0 0 12px var(--accent)}}
.meta,.board{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;background:var(--line);border:1px solid var(--line);border-radius:16px;overflow:hidden;box-shadow:var(--shadow);backdrop-filter:blur(18px)}}.meta{{max-width:1800px;margin:0 auto}}.meta div,.metric{{background:linear-gradient(145deg,rgba(18,31,52,.9),rgba(10,19,35,.8));padding:13px 14px}}.label{{display:block;color:var(--muted);font-size:9px;letter-spacing:.09em;text-transform:uppercase;margin-bottom:3px}}.value{{font:650 19px/1.3 var(--mono);font-variant-numeric:tabular-nums}}
nav{{position:sticky;top:0;z-index:10;display:flex;gap:6px;padding:10px clamp(14px,4vw,64px);border-bottom:1px solid var(--line);background:rgba(5,9,18,.74);backdrop-filter:blur(20px);overflow:auto;box-shadow:0 8px 30px rgba(0,0,0,.16)}}button,select,input{{font:inherit;background:rgba(17,29,49,.86);color:var(--ink);border:1px solid var(--line);padding:9px 12px;border-radius:9px;transition:.2s ease}}button{{cursor:pointer;color:var(--muted);white-space:nowrap}}button:hover,select:hover,input:hover{{border-color:rgba(83,222,204,.36);transform:translateY(-1px)}}button.active{{border-color:var(--line-hot);color:var(--accent);background:rgba(83,222,204,.1);box-shadow:inset 0 0 24px rgba(83,222,204,.05)}}button:focus-visible,select:focus-visible,input:focus-visible,summary:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}
main{{padding:24px clamp(14px,4vw,64px) 70px;max-width:1900px;margin:auto}}.tab{{display:none}}.tab.active{{display:block;animation:reveal .42s ease both}}h2{{font-size:13px;text-transform:uppercase;letter-spacing:.13em;margin:28px 0 11px;display:flex;align-items:center;gap:10px}}h2:after{{content:"";height:1px;flex:1;background:linear-gradient(90deg,var(--line),transparent)}}h3{{font-size:10px;letter-spacing:.11em;text-transform:uppercase;color:var(--muted)}}
.warning{{border:1px solid rgba(255,201,107,.22);border-left:3px solid var(--warn);background:linear-gradient(90deg,rgba(255,201,107,.12),rgba(255,201,107,.035));padding:11px 14px;margin:10px 0;border-radius:8px}}.panel{{border:1px solid var(--line);background:var(--panel);backdrop-filter:blur(15px);padding:14px;margin-bottom:14px;overflow:auto;border-radius:14px;box-shadow:var(--shadow)}}.visual-grid{{display:grid;grid-template-columns:minmax(250px,.68fr) minmax(320px,1.32fr);gap:14px;margin:14px 0}}.visual-card{{border:1px solid var(--line);background:linear-gradient(145deg,rgba(18,31,52,.82),rgba(9,17,31,.7));border-radius:16px;padding:18px;min-height:245px;box-shadow:var(--shadow)}}.visual-card h3{{margin:0 0 18px}}
.donut{{width:166px;aspect-ratio:1;border-radius:50%;margin:12px auto;display:grid;place-items:center;background:conic-gradient(var(--success) 0 calc(var(--production)*1%),var(--violet) 0 calc((var(--production) + var(--shadow))*1%),var(--accent) 0 calc((var(--production) + var(--shadow) + var(--signal))*1%),rgba(145,164,192,.16) 0);position:relative;box-shadow:0 0 55px rgba(83,222,204,.12)}}.donut:after{{content:"";position:absolute;inset:17px;border-radius:50%;background:#0c1628;border:1px solid var(--line)}}.donut div{{position:relative;z-index:1;text-align:center}}.donut strong{{display:block;font:700 27px var(--mono)}}.donut span{{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.09em}}.legend{{display:flex;justify-content:center;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:10px}}.legend i{{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:5px}}
.bar-row{{display:grid;grid-template-columns:130px 1fr 48px;gap:10px;align-items:center;margin:13px 0;color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.05em}}.bar-row strong{{font:650 12px var(--mono);color:var(--ink);text-align:right}}.bar-track{{height:8px;background:rgba(145,164,192,.1);border-radius:999px;overflow:hidden}}.bar-track i{{display:block;height:100%;width:calc(var(--w)*100%);background:linear-gradient(90deg,var(--accent2),var(--accent));border-radius:inherit;box-shadow:0 0 18px rgba(83,222,204,.35);transform-origin:left;animation:grow .8s cubic-bezier(.2,.8,.2,1) both}}
table{{width:100%;border-collapse:separate;border-spacing:0;font-variant-numeric:tabular-nums}}th{{color:var(--muted);font-size:9px;text-transform:uppercase;letter-spacing:.07em;position:sticky;top:0;background:#132039;z-index:1}}th,td{{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);white-space:nowrap}}tbody tr{{transition:.15s ease}}tbody tr:hover td{{background:rgba(83,222,204,.045)}}tbody tr:hover{{transform:translateY(-1px)}}.state{{font:650 10px var(--mono);color:var(--accent)}}.muted,.empty{{color:var(--muted)}}.empty{{padding:28px;text-align:center}}.decision-badge{{display:inline-flex;padding:4px 7px;border:1px solid var(--line);border-radius:999px;color:var(--accent);font:650 9px var(--mono);letter-spacing:.03em;background:rgba(83,222,204,.06)}}.probability{{display:grid;grid-template-columns:42px 68px;align-items:center;gap:6px;font-family:var(--mono)}}.probability i{{display:block;height:4px;border-radius:9px;background:linear-gradient(90deg,var(--accent2) 0 calc(var(--p)*100%),rgba(145,164,192,.14) 0)}}
details{{border:1px solid var(--line);background:var(--panel);margin:8px 0;border-radius:12px;overflow:hidden;transition:.2s ease}}details[open]{{border-color:rgba(83,222,204,.3);box-shadow:var(--shadow)}}summary{{display:grid;grid-template-columns:2fr 2fr 1fr;gap:12px;padding:13px 14px;cursor:pointer;list-style:none}}summary::-webkit-details-marker{{display:none}}summary:after{{content:"+";justify-self:end;color:var(--accent);font:600 18px var(--mono)}}details[open] summary:after{{content:"−"}}.research-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1px;background:var(--line);border-top:1px solid var(--line)}}.research-grid section{{background:rgba(12,22,39,.94);padding:14px}}.filters{{display:flex;gap:8px;margin:10px 0 14px;flex-wrap:wrap;align-items:center}}.filters input{{min-width:250px;flex:1}}.result-count{{margin-left:auto;color:var(--muted);font:600 10px var(--mono)}}
@keyframes reveal{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:none}}}}@keyframes grow{{from{{transform:scaleX(0)}}}}@keyframes pulse{{50%{{transform:scale(.72);opacity:.65}}}}@keyframes float{{to{{transform:translate3d(40px,30px,0) scale(1.08)}}}}
@media(max-width:900px){{.hero{{display:block}}.status-chip{{display:inline-flex;margin-bottom:18px}}.visual-grid{{grid-template-columns:1fr}}}}@media(max-width:700px){{header{{padding-top:28px}}summary{{grid-template-columns:1fr}}.meta,.board{{grid-template-columns:repeat(2,minmax(0,1fr))}}.bar-row{{grid-template-columns:105px 1fr 38px}}th,td{{padding:8px}}}}@media(prefers-reduced-motion:reduce){{*,*:before,*:after{{animation:none!important;scroll-behavior:auto!important;transition:none!important}}}}
</style></head><body><header><div class="ambient a"></div><div class="ambient b"></div><div class="hero"><div><div class="brand">SPORTS ENGINE · RESEARCH TERMINAL</div><h1>Football intelligence,<br>priced with evidence.</h1><p class="subtitle">A complete probability surface for every requested fixture—separated from market references, uncertainty, and execution governance.</p></div><div class="status-chip">{escape(report.model_health)}</div></div>
<div class="meta"><div><span class="label">Analysis range</span>{report.start_date} — {report.end_date}</div>
<div><span class="label">Generated</span>{escape(report.generated_at.isoformat())}</div>
<div><span class="label">Last data update</span>{escape(str(report.last_data_update or "—"))}</div>
<div><span class="label">Last odds update</span>{escape(str(report.last_odds_update or "—"))}</div>
<div><span class="label">Provider / mode</span>{escape(report.provider)} · {escape(report.production_mode)}</div>
<div><span class="label">Report mode</span>{escape(report.report_mode)}</div>
<div><span class="label">Source live run</span>{escape(report.source_live_run_id or "—")}</div>
<div><span class="label">Quota remaining</span>{escape(report.provider_quota)}</div>
<div><span class="label">Data health</span>{escape(report.data_health)}</div>
<div><span class="label">Model health</span>{escape(report.model_health)}</div></div></header>
<nav aria-label="Report sections">{nav}</nav><main>{replay_banner}{warning_html}<section id="overview" class="tab active"><h2>Executive market board</h2>
<div class="board">{metric_html}</div><div class="visual-grid"><div class="visual-card"><h3>Decision state</h3>{decision_visual}<div class="legend"><span><i style="background:var(--success)"></i>Production</span><span><i style="background:var(--violet)"></i>Shadow</span><span><i style="background:var(--accent)"></i>Research signal</span></div></div><div class="visual-card"><h3>Probability surface by market family</h3>{market_chart}</div></div><div class="warning"><strong>SHADOW ROWS ARE NOT BETTING PICKS. MANUAL PRICE CONFIRMATION REQUIRED.</strong> Use their minimum odds only for prospective paper tracking. Real-money consideration requires an explicit <code>PRODUCTION_ACTIONABLE / BET_IF_PRICE_AVAILABLE</code> decision plus a newly checked operator price. API-Football prices are reference observations, not guaranteed executable prices.</div><h2>Research state</h2><div class="panel">
<p>Football pricing and market reference are separate: eligible history is <strong>{report.eligible_fixtures}</strong>; model state is <strong>{escape(report.model_health)}</strong>; market references are <strong>{escape(report.odds_health)}</strong>. Execution edge remains unknown until an operator checks a broker.</p>
<p class="muted">No probability, price, or opportunity is inferred when persisted evidence is unavailable.</p></div></section>
<section id="research" class="tab"><h2>Top 10 research predictions by confidence</h2><p class="muted">Research ranking only—not a betting or value ranking. Applicability tier is considered first; within a tier, the confidence index is model probability minus the persisted uncertainty buffer. It is a transparent conservative index, not a confidence interval. One selection per fixture is shown to limit correlated duplication. Prior-only and out-of-domain rows may appear when stronger evidence is unavailable; their applicability is displayed and they remain non-actionable.</p><div class="panel"><table id="research-confidence-table"><thead><tr><th>Rank</th><th>League</th><th>Kickoff</th><th>Fixture</th><th>Market</th><th>Selection</th><th>Model p</th><th>Uncertainty buffer</th><th>Confidence index</th><th>Applicability</th><th>State</th><th>Governance</th></tr></thead><tbody>{_research_prediction_rows(report)}</tbody></table></div></section>
<section id="opportunities" class="tab"><h2>Top 10 decision candidates</h2><p class="muted">PRODUCTION_ACTIONABLE rows have passed every persisted evidence gate but still require a newly checked operator price. SHADOW_ACTIONABLE rows are prospective validation observations, not approved bets. Reference edge alone is not execution edge.</p><div class="filters"><select id="league-filter"><option value="">All leagues</option>{league_options}</select><select id="decision-filter"><option value="">All decisions</option><option>PRODUCTION_ACTIONABLE</option><option>SHADOW_ACTIONABLE</option></select></div><div class="panel"><table id="opportunity-table"><thead><tr><th>Rank</th><th>League</th><th>Kickoff</th><th>Fixture</th><th>Market</th><th>Selection</th><th>Model p</th><th>Fair odds</th><th>Minimum odds</th><th>Latest best API reference</th><th>Reference bookmaker</th><th>Reference observed</th><th>Age</th><th>Market p</th><th>Reference edge</th><th>Robust estimate</th><th>Execution edge</th><th>Reference state</th><th>Decision</th><th>Gate reasons</th></tr></thead><tbody>{_opportunity_rows(report)}</tbody></table></div></section>
<section id="matches" class="tab"><h2>Fixture research panels</h2>{research_panels or '<div class="panel empty">No expected fixtures in this range.</div>'}</section>
<section id="market" class="tab"><h2>Football price targets and API-Football references</h2><p class="muted">Latest-per-bookmaker references are used for comparison. Earlier snapshots contribute movement history only. Gate reasons explain why a row is not production-actionable.</p><div class="filters"><input id="market-search" type="search" placeholder="Search fixture, league or selection…" aria-label="Search market board"><select id="market-family"><option value="">All market families</option>{"".join(f"<option>{escape(name)}</option>" for name in sorted(market_counts))}</select><select id="market-decision"><option value="">All decision states</option>{"".join(f"<option>{escape(name)}</option>" for name in sorted({row.decision for row in report.price_targets}))}</select><span id="market-count" class="result-count">{len(report.price_targets)} rows</span></div><div class="panel"><table id="market-table"><thead><tr><th>Competition</th><th>Fixture</th><th>Market</th><th>Selection</th><th>Model p</th><th>Fair odds</th><th>Minimum odds</th><th>Latest best API reference</th><th>Bookmaker</th><th>Age</th><th>Snapshots</th><th>Movement</th><th>Dispersion</th><th>Reference state</th><th>Decision</th><th>Gate reasons</th></tr></thead><tbody>{market_rows}</tbody></table></div></section>
<section id="models" class="tab"><h2>Model health and continuous learning</h2><div class="panel"><table><thead><tr><th>Algorithm</th><th>Version</th><th>State</th><th>Parent</th><th>Train cutoff</th><th>Train</th><th>Validation</th><th>Test</th><th>New</th><th>Log loss</th><th>Brier</th><th>RPS</th><th>Calibration</th><th>Next trigger</th></tr></thead><tbody>{_model_rows(report)}</tbody></table></div></section>
<section id="data" class="tab"><h2>Data health</h2><div class="board"><div class="metric"><span class="label">Eligible fixtures</span><span class="value">{report.eligible_fixtures}</span></div><div class="metric"><span class="label">Observation leagues</span><span class="value">{report.observation_leagues}</span></div><div class="metric"><span class="label">Odds health</span><span class="value">{escape(report.odds_health)}</span></div></div></section>
<section id="audit" class="tab"><h2>Full universe audit</h2><div class="filters"><select id="audit-league"><option value="">All leagues</option>{league_options}</select><select id="audit-state"><option value="">All states</option>{state_options}</select></div><div class="panel"><table id="audit-table"><thead><tr><th>Competition</th><th>Fixture</th><th>Kickoff</th><th>State</th><th>Odds</th><th>Model</th><th>Reasons</th></tr></thead><tbody>{fixture_rows}</tbody></table></div></section></main>
<script type="application/json" id="report-data">{embedded}</script><script>
const activate=tab=>{{document.querySelectorAll('nav button,.tab').forEach(x=>x.classList.remove('active'));const button=document.querySelector(`nav button[data-tab="${{tab}}"]`);const panel=document.getElementById(tab);if(button&&panel){{button.classList.add('active');panel.classList.add('active');history.replaceState(null,'',`#${{tab}}`)}}}};
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>activate(b.dataset.tab));
if(location.hash)activate(location.hash.slice(1));
function filter(table,league,state){{document.querySelectorAll(table+' tbody tr[data-league]').forEach(r=>r.hidden=(league&&r.dataset.league!==league)||(state&&(r.dataset.state||r.dataset.decision)!==state))}}
document.getElementById('league-filter').onchange=e=>filter('#opportunity-table',e.target.value,document.getElementById('decision-filter').value);
document.getElementById('decision-filter').onchange=e=>filter('#opportunity-table',document.getElementById('league-filter').value,e.target.value);
document.getElementById('audit-league').onchange=e=>filter('#audit-table',e.target.value,document.getElementById('audit-state').value);
document.getElementById('audit-state').onchange=e=>filter('#audit-table',document.getElementById('audit-league').value,e.target.value);
function filterMarket(){{const query=document.getElementById('market-search').value.trim().toLowerCase();const family=document.getElementById('market-family').value;const decision=document.getElementById('market-decision').value;let visible=0;document.querySelectorAll('#market-table tbody tr').forEach(row=>{{const show=(!query||row.textContent.toLowerCase().includes(query))&&(!family||row.dataset.market===family)&&(!decision||row.dataset.decision===decision);row.hidden=!show;if(show)visible++}});document.getElementById('market-count').textContent=`${{visible}} rows`}}
['market-search','market-family','market-decision'].forEach(id=>document.getElementById(id).addEventListener(id==='market-search'?'input':'change',filterMarket));
document.addEventListener('keydown',event=>{{if(event.key==='/'&&!/input|select|textarea/i.test(document.activeElement.tagName)){{event.preventDefault();activate('market');document.getElementById('market-search').focus()}}}});
</script></body></html>"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(document, encoding="utf-8")
    return destination
