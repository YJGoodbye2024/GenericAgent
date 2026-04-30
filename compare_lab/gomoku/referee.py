from __future__ import annotations

from compare_lab.referees.base import SceneBroker


class GomokuBroker(SceneBroker):
    def _board(self) -> list[list[str]]:
        return self.state["world"]["board"]

    def _render(self) -> str:
        rows = []
        for idx, row in enumerate(self._board()):
            rows.append(f"{idx}: " + " ".join(cell or "." for cell in row))
        return "\n".join(rows)

    def observe(self, focus: str | None = None) -> dict:
        world = self.state["world"]
        return {
            "status": "success",
            "kind": "gomoku",
            "board": self._render(),
            "agent_symbol": world.get("agent_symbol", "X"),
            "opponent_symbol": world.get("opponent_symbol", "O"),
            "objective": world.get("objective", "选择这一手最合适的落子。"),
            "notes": world.get("notes", []),
            "reference_moves": world.get("reference_moves", []),
            "focus": focus,
        }

    def act(self, action: str, args: dict | None = None) -> dict:
        args = args or {}
        if action != "place":
            return {"status": "error", "msg": "五子棋场景只接受 place 动作。"}
        row = args.get("row")
        col = args.get("col")
        if row is None or col is None:
            return {"status": "error", "msg": "place 需要 row 与 col。"}
        board = self._board()
        if not (0 <= row < len(board) and 0 <= col < len(board)):
            return {"status": "error", "msg": "坐标越界。"}
        if board[row][col]:
            return {"status": "error", "msg": "该位置已有棋子。"}
        board[row][col] = self.state["world"].get("agent_symbol", "X")
        self.log("place", {"row": row, "col": col})
        recommended = [tuple(x) for x in self.state["world"].get("reference_moves", [])]
        return {
            "status": "success",
            "msg": "落子已记录。",
            "board": self._render(),
            "placed": [row, col],
            "recommended": [list(x) for x in recommended],
            "is_reference_move": (row, col) in recommended,
        }
