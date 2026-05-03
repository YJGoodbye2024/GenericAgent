from __future__ import annotations

import re
from typing import Any


COL_LABELS = "ABCDEFGHIJKLMNO"
COORD_RE = re.compile(r"\b([A-O](?:1[0-5]|[1-9]))\b", re.IGNORECASE)
SUMMARY_BLOCK_RE = re.compile(r"<summary>.*?</summary>", re.IGNORECASE | re.DOTALL)
BOLD_COORD_RE = re.compile(r"\*\*\s*([A-O](?:1[0-5]|[1-9]))\s*\*\*", re.IGNORECASE)


def coord_from_rowcol(row: int, col: int, board_size: int) -> str:
    return f"{COL_LABELS[col]}{board_size - row}"


def rowcol_from_coord(coord: str, board_size: int) -> tuple[int, int]:
    coord = coord.strip().upper()
    if len(coord) < 2:
        raise ValueError(f"Invalid coord: {coord!r}")
    col_label = coord[0]
    if col_label not in COL_LABELS[:board_size]:
        raise ValueError(f"Invalid col label: {coord!r}")
    row_label = int(coord[1:])
    if not (1 <= row_label <= board_size):
        raise ValueError(f"Invalid row label: {coord!r}")
    return board_size - row_label, COL_LABELS.index(col_label)


def extract_first_coord(text: str, board_size: int) -> str | None:
    source = text or ""
    cleaned = SUMMARY_BLOCK_RE.sub(" ", source)
    for pattern in (BOLD_COORD_RE, COORD_RE):
        for match in pattern.finditer(cleaned):
            coord = match.group(1).upper()
            try:
                rowcol_from_coord(coord, board_size)
            except ValueError:
                continue
            return coord
    for match in COORD_RE.finditer(source):
        coord = match.group(1).upper()
        try:
            rowcol_from_coord(coord, board_size)
        except ValueError:
            continue
        return coord
    return None


def render_board_for_agent(board: list[list[str]], *, you_are_black: bool) -> str:
    board_size = len(board)
    header = "   " + " ".join(COL_LABELS[:board_size])
    rows = [header]
    for row in range(board_size):
        rendered = []
        for cell in board[row]:
            if not cell:
                rendered.append(".")
            elif (cell == "X" and you_are_black) or (cell == "O" and not you_are_black):
                rendered.append("X")
            else:
                rendered.append("O")
        rows.append(f"{board_size - row:>2} " + " ".join(rendered))
    return "\n".join(rows)


def format_move_history(
    move_history: list[dict[str, Any]],
    *,
    board_size: int,
    black_label: str = "黑",
    white_label: str = "白",
) -> str:
    if not move_history:
        return "(开局)"
    return "→".join(
        f"{coord_from_rowcol(move['row'], move['col'], board_size)}({black_label if move['color'] == 'black' else white_label})"
        for move in move_history
    )
