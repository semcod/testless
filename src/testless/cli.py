"""CLI entry-point for testless."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from testless.config import load_config


@click.group()
@click.option("--config", "-c", default=None, help="Path to .testless.yml config file.")
@click.pass_context
def main(ctx: click.Context, config: str | None) -> None:
    """testless — analyze test value, coverage, duplication, and generate LLM planfiles."""
    try:
        from testless.autoupdate import check_for_updates
        check_for_updates("testless")
    except Exception:
        pass
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config(config)


# ---------------------------------------------------------------------------
# pretest scan
# ---------------------------------------------------------------------------

@main.command()
@click.argument("test_paths", nargs=-1, type=click.Path())
@click.option("--source", "-s", multiple=True, help="Source package or directory to measure coverage for.")
@click.option("--python", default=None, help="Python executable to run pytest with.")
@click.option("--out", default=None, help="Override coverage output directory.")
@click.pass_context
def scan(
    ctx: click.Context,
    test_paths: tuple[str, ...],
    source: tuple[str, ...],
    python: str | None,
    out: str | None,
) -> None:
    """Run pytest with coverage contexts and collect test metadata."""
    from testless.collect.pytest_runner import run_pytest

    cfg = ctx.obj["config"]
    coverage_dir = out or cfg.coverage_dir
    target_dirs = list(test_paths) if test_paths else cfg.test_dirs
    target_packages = list(source) if source else cfg.packages

    click.echo(f"Running pytest with coverage contexts → {coverage_dir}")
    tests, cov_json = run_pytest(
        packages=target_packages,
        test_dirs=target_dirs,
        coverage_dir=coverage_dir,
        extra_args=cfg.pytest_args,
        python_executable=python,
    )
    click.echo(f"Collected {len(tests)} tests. Coverage JSON: {cov_json}")


# ---------------------------------------------------------------------------
# pretest duplicates
# ---------------------------------------------------------------------------

@main.command()
@click.option("--min-overlap", default=None, type=float, help="Minimum duplicate score (0–1).")
@click.option("--coverage-json", default=None, help="Path to coverage.json (default: auto-detect).")
@click.pass_context
def duplicates(ctx: click.Context, min_overlap: float | None, coverage_json: str | None) -> None:
    """Detect duplicate tests based on coverage overlap, AST similarity, and fixture use."""
    from testless.analyze.duplicate_tests import find_duplicates
    from testless.collect.coverage_loader import load_coverage_json
    from testless.collect.fixture_index import FixtureIndex
    from testless.models.findings import AnalysisReport, TestMeta
    from testless.reporters.console import print_report

    cfg = ctx.obj["config"]
    min_score = min_overlap if min_overlap is not None else cfg.min_duplicate_score

    # Load coverage
    cov_path = coverage_json or str(Path(cfg.coverage_dir) / "coverage.json")
    cov_map = load_coverage_json(cov_path)

    # Build minimal test list from coverage map contexts
    all_node_ids: set[str] = set()
    for fc in cov_map.files.values():
        for tests_list in fc.line_to_tests.values():
            all_node_ids.update(tests_list)

    tests = [
        TestMeta(
            node_id=nid,
            file=nid.split("::")[0],
            name=nid.split("::")[-1],
        )
        for nid in sorted(all_node_ids)
    ]

    fixture_index = FixtureIndex()
    for td in cfg.test_dirs:
        if Path(td).exists():
            fixture_index.scan_directory(td)

    dups = find_duplicates(tests, cov_map, fixture_index, min_score=min_score)

    report = AnalysisReport(duplicates=dups, tests=tests)
    print_report(report)

    if dups:
        sys.exit(1)


# ---------------------------------------------------------------------------
# pretest missing
# ---------------------------------------------------------------------------

@main.command()
@click.option(
    "--services",
    "-s",
    multiple=True,
    help="Source directories to scan for endpoints/services.",
)
@click.pass_context
def missing(ctx: click.Context, services: tuple[str, ...]) -> None:
    """Suggest missing smoke, e2e, contract, and TestQL tests."""
    from testless.analyze.missing_tests import find_missing_tests
    from testless.collect.endpoint_inventory import EndpointInventory
    from testless.models.findings import AnalysisReport
    from testless.reporters.console import print_report

    cfg = ctx.obj["config"]
    dirs = list(services) if services else cfg.packages or ["."]

    inventory = EndpointInventory()
    for d in dirs:
        if Path(d).exists():
            inventory.scan_directory(d)
        else:
            click.echo(f"Warning: directory not found: {d}", err=True)

    missing_findings = find_missing_tests([], inventory.endpoints, inventory.services)
    report = AnalysisReport(missing_tests=missing_findings)
    print_report(report)


# ---------------------------------------------------------------------------
# pretest planfiles
# ---------------------------------------------------------------------------

@main.command()
@click.option("--out", default=None, help="Output directory for planfile YAML files.")
@click.option("--coverage-json", default=None, help="Path to coverage.json.")
@click.option(
    "--services",
    "-s",
    multiple=True,
    help="Source directories to scan for endpoints/services.",
)
@click.option("--with-prompts", is_flag=True, default=False, help="Embed LLM system prompts.")
@click.pass_context
def planfiles(
    ctx: click.Context,
    out: str | None,
    coverage_json: str | None,
    services: tuple[str, ...],
    with_prompts: bool,
) -> None:
    """Generate planfile YAML tickets for LLM from all findings."""
    from testless.analyze.dead_tests import find_dead_tests
    from testless.analyze.duplicate_tests import find_duplicates
    from testless.analyze.missing_tests import find_missing_tests
    from testless.analyze.refactor_candidates import find_refactor_candidates
    from testless.collect.coverage_loader import load_coverage_json
    from testless.collect.endpoint_inventory import EndpointInventory
    from testless.collect.fixture_index import FixtureIndex
    from testless.models.findings import AnalysisReport, TestMeta
    from testless.tickets.builder import build_planfiles
    from testless.tickets.prompts import attach_prompt
    from testless.tickets.serializer import write_planfiles, write_summary_json

    cfg = ctx.obj["config"]
    output_dir = out or cfg.planfiles_dir

    # Load coverage
    cov_path = coverage_json or str(Path(cfg.coverage_dir) / "coverage.json")
    cov_map = load_coverage_json(cov_path)

    all_node_ids: set[str] = set()
    for fc in cov_map.files.values():
        for tests_list in fc.line_to_tests.values():
            all_node_ids.update(tests_list)

    tests = [
        TestMeta(
            node_id=nid,
            file=nid.split("::")[0],
            name=nid.split("::")[-1],
        )
        for nid in sorted(all_node_ids)
    ]

    fixture_index = FixtureIndex()
    for td in cfg.test_dirs:
        if Path(td).exists():
            fixture_index.scan_directory(td)

    dirs = list(services) if services else cfg.packages or ["."]
    inventory = EndpointInventory()
    for d in dirs:
        if Path(d).exists():
            inventory.scan_directory(d)

    report = AnalysisReport(
        duplicates=find_duplicates(tests, cov_map, fixture_index, min_score=cfg.min_duplicate_score),
        dead_tests=find_dead_tests(tests, cov_map),
        missing_tests=find_missing_tests(tests, inventory.endpoints, inventory.services),
        refactor_candidates=find_refactor_candidates(tests),
        tests=tests,
    )

    tickets = build_planfiles(report)
    if with_prompts:
        tickets = [attach_prompt(t) for t in tickets]

    written = write_planfiles(tickets, output_dir)
    write_summary_json(tickets, output_dir)

    click.echo(f"Generated {len(written)} planfile(s) in {output_dir}/")


# ---------------------------------------------------------------------------
# pretest doctor
# ---------------------------------------------------------------------------

@main.command()
@click.argument("question", required=False)
@click.option("--coverage-json", default=None, help="Path to coverage.json.")
@click.option(
    "--services",
    "-s",
    multiple=True,
    help="Source directories to scan for endpoints/services.",
)
@click.pass_context
def doctor(
    ctx: click.Context,
    question: str | None,
    coverage_json: str | None,
    services: tuple[str, ...],
) -> None:
    """Answer questions about test health (what to remove, add, or fix)."""
    from testless.analyze.dead_tests import find_dead_tests
    from testless.analyze.duplicate_tests import find_duplicates
    from testless.analyze.missing_tests import find_missing_tests
    from testless.analyze.refactor_candidates import find_refactor_candidates
    from testless.collect.coverage_loader import load_coverage_json
    from testless.collect.endpoint_inventory import EndpointInventory
    from testless.collect.fixture_index import FixtureIndex
    from testless.models.findings import AnalysisReport, TestMeta
    from testless.reporters.console import print_report

    cfg = ctx.obj["config"]

    cov_path = coverage_json or str(Path(cfg.coverage_dir) / "coverage.json")
    cov_map = load_coverage_json(cov_path)

    all_node_ids: set[str] = set()
    for fc in cov_map.files.values():
        for tests_list in fc.line_to_tests.values():
            all_node_ids.update(tests_list)

    tests = [
        TestMeta(
            node_id=nid,
            file=nid.split("::")[0],
            name=nid.split("::")[-1],
        )
        for nid in sorted(all_node_ids)
    ]

    fixture_index = FixtureIndex()
    for td in cfg.test_dirs:
        if Path(td).exists():
            fixture_index.scan_directory(td)

    dirs = list(services) if services else cfg.packages or ["."]
    inventory = EndpointInventory()
    for d in dirs:
        if Path(d).exists():
            inventory.scan_directory(d)

    report = AnalysisReport(
        duplicates=find_duplicates(tests, cov_map, fixture_index, min_score=cfg.min_duplicate_score),
        dead_tests=find_dead_tests(tests, cov_map),
        missing_tests=find_missing_tests(tests, inventory.endpoints, inventory.services),
        refactor_candidates=find_refactor_candidates(tests),
        tests=tests,
    )

    if question:
        q = question.lower()
        click.echo(click.style(f"\nQuestion: {question}\n", bold=True))
        if any(kw in q for kw in ("usuń", "remove", "delete", "usunąć")):
            click.echo("Tests to consider removing:")
            for d in report.dead_tests:
                click.echo(f"  • {d.node_id} — {d.reason}")
            for dup in report.duplicates:
                click.echo(f"  • {dup.test_b} — duplicate of {dup.test_a} (score={dup.score:.2f})")
            if not report.dead_tests and not report.duplicates:
                click.echo("  Nothing to remove — suite looks clean.")
        elif any(kw in q for kw in ("dodaj", "add", "missing", "brakuje")):
            click.echo("Tests to consider adding:")
            for m in report.missing_tests:
                click.echo(f"  • [{m.test_type}] {m.target}: {m.description}")
            if not report.missing_tests:
                click.echo("  No obvious missing tests detected.")
        else:
            print_report(report)
    else:
        print_report(report)


if __name__ == "__main__":
    main()

