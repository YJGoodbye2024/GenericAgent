from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from compare_lab.gomoku.coords import rowcol_from_coord


def list_pending_requests(mailbox_root: Path, side_id: str) -> list[Path]:
    requests_dir = mailbox_root / side_id / "requests"
    replies_dir = mailbox_root / side_id / "replies"
    replied = {p.name for p in replies_dir.glob("*.json")}
    return sorted(p for p in requests_dir.glob("*.json") if p.name not in replied)


def load_request(request_path: Path) -> dict[str, Any]:
    return json.loads(request_path.read_text(encoding="utf-8"))


def validate_reply_payload(payload: dict[str, Any], *, board_size: int) -> tuple[int, int, str]:
    if not isinstance(payload, dict):
        raise ValueError("Reply payload must be a JSON object.")
    if "row" in payload and "col" in payload:
        row = int(payload["row"])
        col = int(payload["col"])
    elif "coord" in payload:
        row = col = -1
        row, col = rowcol_from_coord(str(payload["coord"]).strip().upper(), board_size)
    else:
        raise ValueError("Reply payload must contain row/col or coord.")
    if not (0 <= row < board_size and 0 <= col < board_size):
        raise ValueError(f"Move out of board range: ({row}, {col})")
    summary = str(payload.get("summary", "")).strip()
    return row, col, summary


def write_reply(reply_path: Path, *, row: int, col: int, summary: str) -> None:
    reply_path.parent.mkdir(parents=True, exist_ok=True)
    reply_path.write_text(
        json.dumps({"row": row, "col": col, "summary": summary}, ensure_ascii=False),
        encoding="utf-8",
    )
