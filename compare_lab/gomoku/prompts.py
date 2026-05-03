from __future__ import annotations

from typing import Any

from compare_lab.gomoku.coords import format_move_history, render_board_for_agent


def board_ascii(board: list[list[str]], *, you_are_black: bool) -> str:
    return render_board_for_agent(board, you_are_black=you_are_black)


def last_move_text(last_move: dict[str, Any] | None) -> str:
    if not last_move:
        return "对手刚下：无"
    return f"对手刚下：{last_move['coord']} ({'黑' if last_move['color'] == 'black' else '白'})"


def build_turn_prompt(
    *,
    game_no: int,
    board: list[list[str]],
    move_history: list[dict[str, Any]],
    last_move: dict[str, Any] | None,
    you_are_black: bool,
    extra_notes: list[str] | None = None,
) -> str:
    notes = extra_notes or []
    recent = format_move_history(move_history[-10:], board_size=len(board))
    notes_block = ""
    if notes:
        notes_block = "补充说明：\n" + "\n".join(f"- {line}" for line in notes) + "\n"
    return (
        f"你正在进行五子棋第 {game_no} 局，棋盘为 15x15，无禁手。\n"
        f"你这一局执{'黑' if you_are_black else '白'}。\n"
        "如你认为需要借助已有能力，请自行决定。\n"
        "请努力尝试赢得这盘比赛，不要敷衍落子，也不要只求合法。\n"
        f"当前棋盘(你执{'黑' if you_are_black else '白'}, X=你, O=对手):\n```text\n{board_ascii(board, you_are_black=you_are_black)}\n```\n\n"
        f"{last_move_text(last_move)}\n"
        f"走子历史：{recent}\n"
        f"{notes_block}"
        "轮到你下子。请只输出两部分：\n"
        "1. 你的落子坐标（如 H9）\n"
        "2. 一句简短理由\n"
        "不要输出 JSON，不要输出 compare_action，不要自己做 row/col 转换。"
    )
