from __future__ import annotations

import importlib.util
import json
import re
import sys
import time
from pathlib import Path
from typing import Any


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


def build_strength_guidance() -> str:
    return (
        "Strength guidance:\n"
        "- L1: value center and obvious blocks; avoid deep reading.\n"
        "- L2: handle one-step threats, value initiative, create pressure.\n"
        "- L3: prioritize sente, forced defense, and multi-step attack/defense balance.\n"
    )


def build_opponent_prompt(
    *,
    board_size: int,
    board_ascii: str,
    move_history: list[dict[str, Any]],
    you_are_black: bool,
    strength: str,
    game_no: int,
    notes: list[str],
    past_games: list[str],
) -> str:
    prior = "\n".join(f"- {line}" for line in past_games[-4:]) or "(none)"
    return (
        f"Gomoku game {game_no}, board size {board_size}x{board_size}, no forbidden moves.\n"
        f"You are {'black' if you_are_black else 'white'}.\n"
        f"Strength band: {strength}.\n"
        f"{build_strength_guidance()}"
        f"Past game notes:\n{prior}\n"
        f"Extra notes:\n" + ("\n".join(f"- {x}" for x in notes) if notes else "(none)") + "\n\n"
        "Current board ('.' empty, X black, O white):\n"
        f"{board_ascii}\n\n"
        "Recent moves:\n"
        + (
            "\n".join(
                f"- ply {m['ply']}: {m['actor']} {m['color']} -> ({m['row']},{m['col']})"
                for m in move_history[-8:]
            )
            if move_history
            else "(opening)"
        )
        + "\n\nReply with JSON only, for example:\n"
        '{"row":7,"col":7,"summary":"take central influence first"}'
    )


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
        strength: str,
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
        model_name: str = "gpt-5.4",
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
        cfg["model"] = self.model_name
        cfg["stream"] = False
        cfg["max_retries"] = max(1, int(cfg.get("max_retries", 1)))
        cfg["read_timeout"] = max(60, int(cfg.get("read_timeout", 120)))
        cfg["name"] = f"opponent-{self.model_name}"
        if "native" in self.config_key and "oai" in self.config_key:
            session = llmcore.NativeOAISession(cfg)
        elif "native" in self.config_key and "claude" in self.config_key:
            session = llmcore.NativeClaudeSession(cfg)
        elif "oai" in self.config_key:
            session = llmcore.LLMSession(cfg)
        else:
            session = llmcore.ClaudeSession(cfg)
        session.system = (
            "You are a dedicated gomoku opponent. "
            "Play to win within the requested strength band. "
            "Never use markdown fences. "
            "Always answer with a single JSON object containing row, col, and summary."
        )
        return session

    def choose_move(
        self,
        *,
        board_size: int,
        board_ascii: str,
        move_history: list[dict[str, Any]],
        you_are_black: bool,
        strength: str,
        game_no: int,
        notes: list[str],
    ) -> dict[str, Any]:
        prompt = build_opponent_prompt(
            board_size=board_size,
            board_ascii=board_ascii,
            move_history=move_history,
            you_are_black=you_are_black,
            strength=strength,
            game_no=game_no,
            notes=notes,
            past_games=self.past_games,
        )
        raw = self._session.ask(prompt, stream=False)
        data = _extract_json_object(raw)
        if data is None or "row" not in data or "col" not in data:
            repair = self._session.ask(
                "Your previous reply was invalid. Reply again with JSON only: "
                '{"row":0,"col":0,"summary":"..."}',
                stream=False,
            )
            data = _extract_json_object(repair)
            raw = repair if data is not None else raw
        if data is None or "row" not in data or "col" not in data:
            raise ValueError(f"Opponent output is not valid JSON move: {raw[:400]}")
        data["summary"] = str(data.get("summary", "")).strip()
        data["_raw"] = raw
        return data


class ExternalMailboxGomokuOpponent(BaseGomokuOpponent):
    def __init__(
        self,
        mailbox_root: Path,
        *,
        side_id: str,
        label: str = "Codex Subagent",
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
        strength: str,
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
            "strength": strength,
            "you_are_black": you_are_black,
            "label": self.label,
            "board_size": board_size,
            "board_ascii": board_ascii,
            "move_history": move_history,
            "notes": notes,
            "past_games": self.past_games[-4:],
            "prompt": build_opponent_prompt(
                board_size=board_size,
                board_ascii=board_ascii,
                move_history=move_history,
                you_are_black=you_are_black,
                strength=strength,
                game_no=game_no,
                notes=notes,
                past_games=self.past_games,
            ),
            "reply_schema": {"row": "int", "col": "int", "summary": "str"},
        }
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
                        data = None
                if not isinstance(data, dict) or "row" not in data or "col" not in data:
                    raise ValueError(f"External opponent reply invalid for {request_id}: {raw[:400]}")
                data["summary"] = str(data.get("summary", "")).strip()
                data["_raw"] = raw
                return data
            time.sleep(self.poll_sec)
        raise TimeoutError(f"Timed out waiting for external opponent reply: {reply_path}")


GomokuOpponent = ModelGomokuOpponent

