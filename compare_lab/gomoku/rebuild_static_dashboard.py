from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from compare_lab.gomoku.coords import extract_first_coord
from compare_lab.gomoku.live import SIDES, write_static_dashboard
from compare_lab.utils import ensure_dir, read_json, write_json


def load_history_order(live_state: dict[str, Any]) -> dict[str, int]:
    history = live_state.get("history", [])
    order_map: dict[str, int] = {}
    for idx, item in enumerate(history, start=1):
        match_id = item.get("match_id")
        if match_id:
            order_map[match_id] = int(item.get("history_order") or idx)
    return order_map


def load_matches(matches_dir: Path, order_map: dict[str, int]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for path in sorted(matches_dir.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        record["history_order"] = order_map.get(record["match_id"], record.get("history_order") or 0)
        matches.append(record)
    matches.sort(key=lambda item: (item.get("history_order") or 10**9, item.get("game_no") or 10**9, item.get("agent_id") or ""))
    if not order_map:
        for idx, item in enumerate(matches, start=1):
            item["history_order"] = idx
    return matches


def build_live_slot(match: dict[str, Any]) -> dict[str, Any]:
    moves = match.get("moves", [])
    last_summary = moves[-1]["summary"] if moves else ""
    return {
        "match_id": match["match_id"],
        "agent_label": match["agent_label"],
        "opponent_label": match["opponent_label"],
        "game_no": match["game_no"],
        "board_size": match["board_size"],
        "agent_color": match["agent_color"],
        "opponent_color": match["opponent_color"],
        "status": f"finished:{match['result']}",
        "move_count": len(moves),
        "to_move_label": "-",
        "last_summary": last_summary,
        "moves": copy.deepcopy(moves),
    }


def audit_coordinates(history: list[dict[str, Any]]) -> dict[str, Any]:
    audited = 0
    mismatches: list[dict[str, Any]] = []
    skipped = 0
    for match in history:
        for move in match.get("moves", []):
            if move.get("actor") != "agent":
                continue
            raw = move.get("raw_response", "")
            if not raw.strip():
                skipped += 1
                continue
            extracted = extract_first_coord(raw, match.get("board_size", 15))
            if extracted is None:
                skipped += 1
                mismatches.append(
                    {
                        "match_id": match["match_id"],
                        "ply": move["ply"],
                        "recorded_coord": move["coord"],
                        "extracted_coord": None,
                        "reason": "no_coord_extracted",
                    }
                )
                continue
            audited += 1
            if extracted != move.get("coord"):
                mismatches.append(
                    {
                        "match_id": match["match_id"],
                        "ply": move["ply"],
                        "recorded_coord": move["coord"],
                        "extracted_coord": extracted,
                        "reason": "coord_mismatch",
                    }
                )
    if mismatches:
        summary = f"{audited} 手已审计，发现 {len(mismatches)} 处不一致，另有 {skipped} 手未能从原始回复提取坐标。"
    else:
        summary = f"{audited} 手已审计，0 处坐标不一致；另有 {skipped} 手无需或无法审计。"
    return {
        "audited_moves": audited,
        "skipped_moves": skipped,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "summary": summary,
    }


def build_state(run_root: Path) -> dict[str, Any]:
    web_dir = run_root / "web"
    live_state_path = web_dir / "live_state.json"
    live_state = read_json(live_state_path) if live_state_path.exists() else {}
    order_map = load_history_order(live_state)
    history = load_matches(run_root / "matches", order_map)
    opponent_label = (
        live_state.get("opponent_label")
        or (history[0].get("opponent_label") if history else "Opponent")
        or "Opponent"
    )
    live: dict[str, Any] = {}
    for side in SIDES:
        side_history = [item for item in history if item.get("agent_id") == side["id"]]
        if side_history:
            live[side["id"]] = build_live_slot(side_history[-1])
    coordinate_audit = audit_coordinates(history)
    state = {
        "run_id": live_state.get("run_id") or run_root.name,
        "opponent_label": opponent_label,
        "status": "finished_rebuilt",
        "current_round": max((item.get("game_no") or 0) for item in history) if history else 0,
        "live": live,
        "history": history,
        "started_at": live_state.get("started_at", ""),
        "finished_at": live_state.get("finished_at", ""),
        "preflight": live_state.get("preflight"),
        "coordinate_audit": coordinate_audit,
    }
    return state


def rebuild_static_dashboard(run_root: Path) -> dict[str, Any]:
    run_root = run_root.resolve()
    state = build_state(run_root)
    web_dir = ensure_dir(run_root / "web")
    final_state_path = web_dir / "final_state.json"
    write_json(final_state_path, state)
    html_path = write_static_dashboard(web_dir, state)
    return {
        "run_root": str(run_root),
        "final_state": str(final_state_path),
        "index_html": str(html_path),
        "history_count": len(state["history"]),
        "coordinate_audit": state["coordinate_audit"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild a static gomoku dashboard from existing match artifacts.")
    parser.add_argument("--run-root", required=True, help="Path to compare_lab/runs/<run_id>")
    args = parser.parse_args()
    result = rebuild_static_dashboard(Path(args.run_root))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
