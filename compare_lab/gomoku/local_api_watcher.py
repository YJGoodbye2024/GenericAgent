from __future__ import annotations

import argparse
import json
import os
import signal
import time
from pathlib import Path

from compare_lab.gomoku.opponent import ModelGomokuOpponent


STOP = False


def _handle_signal(signum, frame):  # noqa: ANN001, ARG001
    global STOP
    STOP = True


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def choose_pending_request(requests_dir: Path, replies_dir: Path) -> Path | None:
    pending = []
    for req in requests_dir.glob("*.json"):
        if not (replies_dir / req.name).exists():
            pending.append(req)
    if not pending:
        return None
    return sorted(pending)[0]


def process_one(opponent: ModelGomokuOpponent, req_path: Path, replies_dir: Path) -> None:
    payload = json.loads(req_path.read_text(encoding="utf-8"))
    reply_path = Path(payload.get("reply_path") or (replies_dir / req_path.name))
    data = opponent.choose_move(
        board_size=int(payload["board_size"]),
        board_ascii=payload["board_ascii"],
        move_history=list(payload["move_history"]),
        you_are_black=bool(payload["you_are_black"]),
        game_no=int(payload["game_no"]),
        notes=list(payload.get("notes", [])),
    )
    atomic_write_json(
        reply_path,
        {
            "coord": data["coord"],
            "summary": data.get("summary", ""),
        },
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="compare_lab.gomoku.local_api_watcher")
    p.add_argument("--agent-root", required=True)
    p.add_argument("--requests-dir", required=True)
    p.add_argument("--replies-dir", required=True)
    p.add_argument("--config-key", default="native_oai_config")
    p.add_argument("--model-name", default="")
    p.add_argument("--poll-seconds", type=float, default=0.5)
    return p


def main(argv: list[str] | None = None) -> int:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    args = build_parser().parse_args(argv)

    requests_dir = Path(args.requests_dir)
    replies_dir = Path(args.replies_dir)
    opponent = ModelGomokuOpponent(
        Path(args.agent_root),
        config_key=args.config_key,
        model_name=args.model_name,
    )

    while not STOP:
        req = choose_pending_request(requests_dir, replies_dir)
        if req is None:
            time.sleep(args.poll_seconds)
            continue
        try:
            process_one(opponent, req, replies_dir)
        except Exception as exc:  # noqa: BLE001
            err_path = replies_dir / (req.stem + ".error.txt")
            err_path.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
            time.sleep(args.poll_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
