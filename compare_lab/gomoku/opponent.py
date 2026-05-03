from __future__ import annotations

import importlib.util
import inspect
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from compare_lab.gomoku.coords import coord_from_rowcol, extract_first_coord, format_move_history, rowcol_from_coord
from compare_lab.gomoku.prompts import build_turn_prompt


JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _load_module_from_file(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _extract_json_object(text: str) -> dict[str, Any] | None:
    match = JSON_RE.search(text)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def build_opponent_prompt(
    *,
    board_size: int,
    board: list[list[str]],
    move_history: list[dict[str, Any]],
    you_are_black: bool,
    game_no: int,
    notes: list[str],
    past_games: list[str],
) -> str:
    last_move = move_history[-1] if move_history else None
    return build_turn_prompt(
        game_no=game_no,
        board=board,
        move_history=move_history,
        last_move=last_move,
        you_are_black=you_are_black,
        extra_notes=notes,
    )


def _compact_summary(text: str) -> str:
    compact = " ".join((text or "").split())
    return compact[:220]


def _board_from_moves(board_size: int, move_history: list[dict[str, Any]]) -> list[list[str]]:
    board = [["" for _ in range(board_size)] for _ in range(board_size)]
    for move in move_history:
        board[move["row"]][move["col"]] = "X" if move["color"] == "black" else "O"
    return board


def _normalize_move_reply(raw: str, board_size: int) -> dict[str, Any] | None:
    data = _extract_json_object(raw)
    if isinstance(data, dict):
        if "row" in data and "col" in data:
            row = int(data["row"])
            col = int(data["col"])
            return {
                "row": row,
                "col": col,
                "coord": coord_from_rowcol(row, col, board_size),
                "summary": str(data.get("summary", "")).strip() or _compact_summary(raw),
                "_raw": raw,
            }
        if "coord" in data:
            coord = str(data["coord"]).strip().upper()
            row, col = rowcol_from_coord(coord, board_size)
            return {
                "row": row,
                "col": col,
                "coord": coord,
                "summary": str(data.get("summary", "")).strip() or _compact_summary(raw),
                "_raw": raw,
            }
    coord = extract_first_coord(raw, board_size)
    if coord is None:
        return None
    row, col = rowcol_from_coord(coord, board_size)
    return {
        "row": row,
        "col": col,
        "coord": coord,
        "summary": _compact_summary(raw),
        "_raw": raw,
    }


class BaseGomokuOpponent:
    label = "Opponent"

    def __init__(self) -> None:
        self.past_games: list[str] = []

    def choose_move(
        self,
        *,
        board_size: int,
        board_ascii: str,
        move_history: list[dict[str, Any]],
        you_are_black: bool,
        game_no: int,
        notes: list[str],
    ) -> dict[str, Any]:
        raise NotImplementedError

    def record_match_summary(self, summary: str) -> None:
        self.past_games.append(summary.strip())


class ModelGomokuOpponent(BaseGomokuOpponent):
    def __init__(
        self,
        agent_root: Path,
        *,
        config_key: str = "native_oai_config",
        model_name: str = "",
    ) -> None:
        super().__init__()
        self.agent_root = agent_root
        self.config_key = config_key
        self.model_name = model_name
        self.label = model_name
        self._session = self._build_session()

    def _build_session(self):
        sys.modules.pop("mykey", None)
        llmcore = _load_module_from_file(
            f"compare_lab_llmcore_{self.agent_root.name}_{int(time.time() * 1000)}",
            self.agent_root / "llmcore.py",
        )
        old_path = list(sys.path)
        try:
            sys.path.insert(0, str(self.agent_root))
            mykeys, _ = llmcore.reload_mykeys()
        finally:
            sys.path[:] = old_path
        if self.config_key not in mykeys:
            raise KeyError(f"Opponent config {self.config_key!r} not found in {self.agent_root / 'mykey.py'}")
        cfg = dict(mykeys[self.config_key])
        if self.model_name:
            cfg["model"] = self.model_name
        cfg["stream"] = False
        cfg["max_retries"] = max(1, int(cfg.get("max_retries", 1)))
        cfg["read_timeout"] = max(60, int(cfg.get("read_timeout", 120)))
        label_model = self.model_name or cfg.get("model", "default-model")
        cfg["name"] = f"opponent-{label_model}"
        if "native" in self.config_key and "oai" in self.config_key:
            session = llmcore.NativeOAISession(cfg)
        elif "native" in self.config_key and "claude" in self.config_key:
            session = llmcore.NativeClaudeSession(cfg)
        elif "oai" in self.config_key:
            session = llmcore.LLMSession(cfg)
        else:
            session = llmcore.ClaudeSession(cfg)
        self.label = label_model
        session.system = (
            "You are a dedicated gomoku opponent. "
            "Try hard to win. "
            "Reply only with one human coordinate like H8 and one brief reason. "
            "Do not output JSON unless explicitly asked."
        )
        return session

    def _ask_text(self, prompt: str) -> str:
        ask = getattr(self._session, "ask")
        sig = inspect.signature(ask)
        if "stream" in sig.parameters:
            result = ask(prompt, stream=False)
        else:
            result = ask({"role": "user", "content": [{"type": "text", "text": prompt}]})
        if isinstance(result, str):
            return result
        if hasattr(result, "__iter__"):
            return "".join(str(chunk) for chunk in result)
        return str(result)

    def choose_move(
        self,
        *,
        board_size: int,
        board_ascii: str,
        move_history: list[dict[str, Any]],
        you_are_black: bool,
        game_no: int,
        notes: list[str],
    ) -> dict[str, Any]:
        board = _board_from_moves(board_size, move_history)
        prompt = build_opponent_prompt(
            board_size=board_size,
            board=board,
            move_history=move_history,
            you_are_black=you_are_black,
            game_no=game_no,
            notes=notes,
            past_games=self.past_games,
        )
        raw = self._ask_text(prompt)
        data = _normalize_move_reply(raw, board_size)
        if data is None:
            repair = self._ask_text(
                "你上一条回复无效。请只回复一个合法坐标（如 H8）和一句极短理由，不要输出 JSON。"
            )
            data = _normalize_move_reply(repair, board_size)
            raw = repair if data is not None else raw
        if data is None:
            raise ValueError(f"Opponent output is not a valid gomoku move: {raw[:400]}")
        return data


class ExternalMailboxGomokuOpponent(BaseGomokuOpponent):
    def __init__(
        self,
        mailbox_root: Path,
        *,
        side_id: str,
        label: str = "Codex (GPT-5.4 medium)",
        timeout_sec: int = 1800,
        poll_sec: float = 0.5,
    ) -> None:
        super().__init__()
        self.mailbox_root = mailbox_root
        self.side_id = side_id
        self.label = label
        self.timeout_sec = timeout_sec
        self.poll_sec = poll_sec
        self.requests_dir = mailbox_root / side_id / "requests"
        self.replies_dir = mailbox_root / side_id / "replies"
        self.requests_dir.mkdir(parents=True, exist_ok=True)
        self.replies_dir.mkdir(parents=True, exist_ok=True)

    def choose_move(
        self,
        *,
        board_size: int,
        board_ascii: str,
        move_history: list[dict[str, Any]],
        you_are_black: bool,
        game_no: int,
        notes: list[str],
    ) -> dict[str, Any]:
        ply = len(move_history) + 1
        request_id = f"game_{game_no:02d}_ply_{ply:03d}"
        request_path = self.requests_dir / f"{request_id}.json"
        reply_path = self.replies_dir / f"{request_id}.json"
        if reply_path.exists():
            reply_path.unlink()
        payload = {
            "request_id": request_id,
            "game_no": game_no,
            "ply": ply,
            "side_id": self.side_id,
            "you_are_black": you_are_black,
            "label": self.label,
            "board_size": board_size,
            "board_ascii": board_ascii,
            "coord_history": format_move_history(move_history[-10:], board_size=board_size),
            "move_history": move_history,
            "notes": notes,
            "past_games": self.past_games[-4:],
            "bridge_mode": "coord_text_to_json_reply",
            "subagent_expected_output": {"coord": "H8", "reason": "一句短理由"},
            "reply_schema": {"row": "int", "col": "int", "coord": "optional str", "summary": "str"},
            "request_path": str(request_path),
            "reply_path": str(reply_path),
            "watcher_contract": {
                "mode": "codex_watcher_loop",
                "side_id": self.side_id,
                "request_glob": str(self.requests_dir / "*.json"),
                "reply_dir": str(self.replies_dir),
                "reply_format": {"coord": "H8", "summary": "一句短理由"},
                "atomic_write_required": True,
                "poll_seconds": self.poll_sec,
                "process_oldest_first": True,
                "ignore_if_reply_exists": True,
            },
        }
        board = _board_from_moves(board_size, move_history)
        payload["prompt"] = build_opponent_prompt(
            board_size=board_size,
            board=board,
            move_history=move_history,
            you_are_black=you_are_black,
            game_no=game_no,
            notes=notes,
            past_games=self.past_games,
        )
        request_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        deadline = time.time() + self.timeout_sec
        while time.time() < deadline:
            if reply_path.exists():
                raw = reply_path.read_text(encoding="utf-8")
                data = _extract_json_object(raw)
                if data is None:
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        data = raw
                normalized = _normalize_move_reply(raw if isinstance(data, str) else json.dumps(data, ensure_ascii=False), board_size)
                if normalized is None:
                    raise ValueError(f"External opponent reply invalid for {request_id}: {raw[:400]}")
                return normalized
            time.sleep(self.poll_sec)
        raise TimeoutError(f"Timed out waiting for external opponent reply: {reply_path}")


GomokuOpponent = ModelGomokuOpponent
