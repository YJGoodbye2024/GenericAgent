from __future__ import annotations

import argparse
from pathlib import Path

from compare_lab.gomoku.live import run_gomoku_live
from compare_lab.report import render_report
from compare_lab.runner import run_suite
from compare_lab.utils import repo_root
from compare_lab.web.live import run_web_live


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="compare_lab")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run a comparison suite.")
    run_p.add_argument("--run-id", required=True)
    run_p.add_argument(
        "--suite",
        default="compare_lab/scenarios/suite_default.json",
        help="Path to suite json, relative to repo root or absolute.",
    )
    run_p.add_argument("--llm-no", type=int, default=0)
    run_p.add_argument(
        "--only",
        help="Comma-separated scenario ids to run.",
    )

    report_p = sub.add_parser("report", help="Regenerate report for an existing run.")
    report_p.add_argument("--run-id", required=True)

    gomoku_p = sub.add_parser(
        "gomoku-live",
        help="Run the gomoku live comparison with dashboard. All preflight/debug/full gomoku runs must execute outside the sandbox.",
    )
    gomoku_p.add_argument("--run-id", required=True)
    gomoku_p.add_argument(
        "--agent-llm-no",
        type=int,
        default=1,
        help="Agent model slot. Default 1 = MiniMax-M2.7 in the current GenericAgent layouts.",
    )
    gomoku_p.add_argument("--port", type=int, default=8765)
    gomoku_p.add_argument(
        "--opponent-backend",
        choices=["api", "external", "watcher_api"],
        default="watcher_api",
        help="Opponent backend. Default watcher_api = local automatic watcher + API model opponent. external = Codex bridge mode.",
    )
    gomoku_p.add_argument("--opponent-model", default="", help="Only used when --opponent-backend=api.")
    gomoku_p.add_argument("--opponent-config", default="native_oai_config", help="Only used when --opponent-backend=api.")
    gomoku_p.add_argument("--opponent-timeout", type=int, default=1800)
    gomoku_p.add_argument("--max-ply", type=int, default=120)
    gomoku_p.add_argument("--round-count", type=int, default=12)

    web_p = sub.add_parser(
        "web-live",
        help="Run the real-network free-browsing comparison. Must execute outside the sandbox. Hard preflight errors fail immediately; soft web-tool issues get an agent self-repair window.",
    )
    web_p.add_argument("--run-id", required=True)
    web_p.add_argument("--llm-no", type=int, default=1, help="Agent model slot. Default 1 = MiniMax-M2.7.")
    web_p.add_argument("--duration-minutes", type=int, default=120)
    web_p.add_argument("--port", type=int, default=8766)
    web_p.add_argument("--browser-bin", default="", help="Browser executable path. Falls back to COMPARE_LAB_BROWSER_BIN / common absolute paths.")
    web_p.add_argument("--start-url", default="https://example.com/")
    return parser


def resolve_repo_path(path_str: str) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    return repo_root() / path


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = repo_root()

    if args.cmd == "run":
        suite_path = resolve_repo_path(args.suite)
        only_ids = set(filter(None, (args.only or "").split(","))) or None
        run_suite(root, args.run_id, suite_path, args.llm_no, only_ids=only_ids)
        render_report(root / "compare_lab" / "runs" / args.run_id)
        return 0

    if args.cmd == "report":
        render_report(root / "compare_lab" / "runs" / args.run_id)
        return 0

    if args.cmd == "gomoku-live":
        try:
            outcome = run_gomoku_live(
                root,
                run_id=args.run_id,
                agent_llm_no=args.agent_llm_no,
                port=args.port,
                opponent_model=args.opponent_model,
                opponent_config=args.opponent_config,
                opponent_backend=args.opponent_backend,
                opponent_timeout=args.opponent_timeout,
                max_ply=args.max_ply,
                round_count=args.round_count,
            )
        except RuntimeError as exc:
            print(f"Gomoku run failed: {exc}")
            return 1
        print(f"Live URL: {outcome['web_url']}")
        print(f"Static HTML: {outcome['static_html']}")
        return 0

    if args.cmd == "web-live":
        outcome = run_web_live(
            root,
            run_id=args.run_id,
            llm_no=args.llm_no,
            duration_minutes=args.duration_minutes,
            port=args.port,
            browser_bin=args.browser_bin,
            start_url=args.start_url,
        )
        print(f"Live URL: {outcome['web_url']}")
        print(f"Static HTML: {outcome['static_html']}")
        return 0

    parser.error("unknown command")
    return 2
