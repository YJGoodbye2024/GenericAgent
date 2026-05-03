from __future__ import annotations

import copy
import json
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from compare_lab.gomoku.coords import COL_LABELS, coord_from_rowcol, extract_first_coord, rowcol_from_coord
from compare_lab.gomoku.opponent import ExternalMailboxGomokuOpponent, GomokuOpponent
from compare_lab.gomoku.prompts import board_ascii, build_turn_prompt, last_move_text
from compare_lab.runner import (
    compare_memory_dirs,
    copy_agent_tree,
    drain_turn,
    list_changed_memory_files,
    snapshot_memory,
    start_agent,
)
from compare_lab.utils import ensure_dir, read_json, write_json


BOARD_SIZE = 15
MAX_PLY_DEFAULT = 120
ROUND_COUNT = 12
SIDES = [
    {"id": "generic", "label": "GenericAgent", "source_dir": "GenericAgent"},
    {"id": "lin_daiyu", "label": "GenericAgent_LDY", "source_dir": "GenericAgent_LDY"},
]


def empty_board(size: int = BOARD_SIZE) -> list[list[str]]:
    return [["" for _ in range(size)] for _ in range(size)]


def move_color(agent_is_black: bool, actor: str) -> str:
    if actor == "agent":
        return "black" if agent_is_black else "white"
    return "white" if agent_is_black else "black"


def stone_symbol(color: str) -> str:
    return "X" if color == "black" else "O"


def legal_move(board: list[list[str]], row: int, col: int) -> bool:
    return 0 <= row < len(board) and 0 <= col < len(board) and not board[row][col]


def place_stone(board: list[list[str]], row: int, col: int, color: str) -> None:
    board[row][col] = stone_symbol(color)


def winner_from(board: list[list[str]], row: int, col: int) -> bool:
    sym = board[row][col]
    if not sym:
        return False
    for dr, dc in ((1, 0), (0, 1), (1, 1), (1, -1)):
        streak = 1
        for sign in (1, -1):
            rr, cc = row + dr * sign, col + dc * sign
            while 0 <= rr < len(board) and 0 <= cc < len(board) and board[rr][cc] == sym:
                streak += 1
                rr += dr * sign
                cc += dc * sign
        if streak >= 5:
            return True
    return False


def summarize_agent_text(response: str) -> str:
    if not response:
        return ""
    text = response.replace("LLM Running (Turn 1) ...", "")
    text = text.strip()
    text = text.split("```compare_action")[0].strip()
    text = " ".join(text.split())
    return text[:220]


def build_agent_prompt(match_meta: dict[str, Any], board: list[list[str]], move_history: list[dict[str, Any]], last_move: dict[str, Any] | None) -> str:
    return build_turn_prompt(
        game_no=match_meta["game_no"],
        board=board,
        move_history=move_history,
        last_move=last_move,
        you_are_black=match_meta["agent_is_black"],
    )


def build_rule_brief(match_meta: dict[str, Any]) -> str:
    return (
        f"先说明这一局五子棋的规则，再开始正式落子。\n"
        f"1. 棋盘固定为 15x15。\n"
        f"2. 你这一局执{'黑' if match_meta['agent_is_black'] else '白'}；黑先白后，双方轮流下一手。\n"
        f"3. 每手只能在一个空位落一子，不可覆盖已有棋子，不可跳过回合。\n"
        f"4. 横、竖、斜任意方向先连成五子者立胜。\n"
        f"5. 本局无禁手。\n"
        f"6. 若棋盘下满仍无人连五，则作和；若达到 {MAX_PLY_DEFAULT} 手仍未结束，也强制作和。\n"
        f"7. 坐标用 A-O 表示列、15-1 表示行，例如 H7 表示第 7 行 H 列，J8 表示第 8 行 J 列。\n"
        "8. 你只需要输出 H8、J8 这种人类坐标；不要自己换算内部 row/col，内部换算由裁判完成。\n"
        "9. 每局结束后你会有一次短复盘；如果你总结出对以后有用的下棋经验，可以把它记住，供后续对局继续使用。\n"
        "请努力尝试赢得比赛，但此刻只需复述规则并说明你这一局执黑还是执白。\n"
        "现在先不要落子。"
    )


def build_reflection_prompt(match_record: dict[str, Any]) -> str:
    result = match_record["result"]
    move_count = len(match_record["moves"])
    key_moves = "\n".join(
        f"- ply {m['ply']}: {m['actor']} {m['color']} -> ({m['row']},{m['col']}) | {m['summary']}"
        for m in match_record["moves"][-6:]
    )
    return (
        f"这一局五子棋已经结束。结果：{result}。总手数：{move_count}。\n"
        f"末段关键手如下：\n{key_moves or '(none)'}\n\n"
        "请用一小段话复盘：\n"
        "1. 这一局最关键的一手或判断是什么；\n"
        "2. 下一局若遇到相似局面，你最想提醒自己的是什么。\n"
        "如果你认为这足以形成可复用经验，请尽量把它总结成以后还能用的提醒，并按你的原生记忆机制决定是否记住；"
        "如果不值得长期保留，就只做短复盘。"
    )


def detect_tool_usage(turn_response: str) -> bool:
    markers = ("<tool_use>", "[Action] Running", "<tool_result>", "tool_use")
    return any(marker in turn_response for marker in markers)


def looks_like_transport_error(text: str) -> bool:
    lowered = (text or "").lower()
    return "!!!error:" in lowered or "proxyerror" in lowered or "timeout" in lowered


def outside_sandbox_error() -> str:
    return "五子棋比较必须在沙盒外运行，当前环境不具备有效 API/bridge 链路。"


def short_excerpt(text: str, limit: int = 200) -> str:
    compact = " ".join((text or "").split())
    return compact if len(compact) <= limit else compact[: limit - 3] + "..."


def run_agent_preflight(*, agent_root: Path, llm_no: int, agent_is_black: bool) -> dict[str, Any]:
    agent, model_name = start_agent(agent_root, llm_no)
    prompt = build_rule_brief({"game_no": 0, "agent_is_black": agent_is_black})
    turn = drain_turn(agent.put_task(prompt, source="task"), timeout=900)
    response = turn.response
    ok = bool(response.strip()) and not looks_like_transport_error(response)
    return {
        "ok": ok,
        "model_name": model_name,
        "elapsed_sec": round(turn.elapsed_sec, 3),
        "response_excerpt": short_excerpt(response),
        "error": "" if ok else outside_sandbox_error(),
    }


def run_external_bridge_preflight(*, opponent: ExternalMailboxGomokuOpponent) -> dict[str, Any]:
    try:
        reply = opponent.choose_move(
            board_size=BOARD_SIZE,
            board_ascii=board_ascii(empty_board(BOARD_SIZE), you_are_black=False),
            move_history=[],
            you_are_black=True,
            game_no=0,
            notes=[
                "PREFLIGHT: return any legal opening move on an empty 15x15 board.",
                "JSON only.",
            ],
        )
        row = int(reply["row"])
        col = int(reply["col"])
        ok = 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE
        return {
            "ok": ok,
            "reply": {"row": row, "col": col, "coord": coord_from_rowcol(row, col, BOARD_SIZE), "summary": reply.get("summary", "")},
            "error": "" if ok else "Bridge preflight returned an out-of-range move.",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "reply": None,
            "error": f"{outside_sandbox_error()} ({type(exc).__name__}: {exc})",
        }


def write_preflight_failure_artifacts(*, run_root: Path, web_dir: Path, meta_dir: Path, preflight: dict[str, Any], run_id: str, opponent_label: str, live_server_error: str | None) -> None:
    state = {
        "run_id": run_id,
        "opponent_label": opponent_label,
        "status": "environment_not_ready",
        "current_round": 0,
        "live": {},
        "history": [],
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "preflight": preflight,
    }
    write_json(meta_dir / "preflight.json", preflight)
    write_json(
        meta_dir / "gomoku_run.json",
        {
            "run_id": run_id,
            "opponent_label": opponent_label,
            "live_server_error": live_server_error,
            "preflight": preflight,
            "rounds": [],
            "status": "environment_not_ready",
        },
    )
    write_json(web_dir / "final_state.json", state)
    write_static_dashboard(web_dir, state)
    lines = [
        "# 五子棋专项对比报告",
        "",
        f"- Run ID: `{run_id}`",
        "- 状态: `environment_not_ready`",
        f"- 说明: {outside_sandbox_error()}",
        "",
        "## Preflight",
        "",
        "```json",
        json.dumps(preflight, ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    (run_root / "report.md").write_text("\n".join(lines), encoding="utf-8")


def game_summary_line(match_record: dict[str, Any]) -> str:
    opening = next((m for m in match_record["moves"] if m["actor"] == "opponent"), None)
    own_opening = next((m for m in match_record["moves"] if m["actor"] == "agent"), None)
    opening_text = (
        f"my first move {own_opening['coord']}"
        if own_opening
        else "no own move"
    )
    opp_text = (
        f"opponent first move {opening['coord']}"
        if opening
        else "no opponent move"
    )
    return (
        f"Game {match_record['game_no']} as {match_record['agent_color']}: "
        f"{match_record['result']}; {opening_text}; {opp_text}."
    )


@dataclass
class MatchOutput:
    side_id: str
    match_record: dict[str, Any]
    transcript_path: str
    match_json_path: str
    memory_diff_path: str


class DashboardState:
    def __init__(self, run_id: str, opponent_label: str):
        self.lock = threading.Lock()
        self.subscribers: list[queue.Queue[str]] = []
        self.state: dict[str, Any] = {
            "run_id": run_id,
            "opponent_label": opponent_label,
            "status": "running",
            "current_round": 1,
            "live": {},
            "history": [],
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "finished_at": None,
        }

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return copy.deepcopy(self.state)

    def update(self, mutate):
        with self.lock:
            mutate(self.state)
            snap = copy.deepcopy(self.state)
        self.broadcast({"type": "state", "state": snap})
        return snap

    def broadcast(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False)
        dead: list[queue.Queue[str]] = []
        for q in self.subscribers:
            try:
                q.put_nowait(data)
            except Exception:
                dead.append(q)
        if dead:
            with self.lock:
                self.subscribers = [q for q in self.subscribers if q not in dead]

    def register(self) -> queue.Queue[str]:
        q: queue.Queue[str] = queue.Queue()
        with self.lock:
            self.subscribers.append(q)
        q.put_nowait(json.dumps({"type": "state", "state": copy.deepcopy(self.state)}, ensure_ascii=False))
        return q

    def unregister(self, q: queue.Queue[str]) -> None:
        with self.lock:
            self.subscribers = [x for x in self.subscribers if x is not q]


def render_dashboard_html(*, embedded_state: dict[str, Any] | None, run_id: str, live_mode: bool) -> str:
    embedded = json.dumps(embedded_state, ensure_ascii=False) if embedded_state is not None else ""
    embedded_block = (
        f'<script id="embedded-state" type="application/json">{embedded}</script>'
        if embedded_state is not None
        else ""
    )
    live_flag = "true" if live_mode else "false"
    opponent_label = embedded_state.get("opponent_label", "Opponent") if embedded_state else "Opponent"
    return f"""<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Gomoku Live - {run_id}</title>
  <style>
    :root {{
      --bg: #f3ede2;
      --panel: #fffaf0;
      --ink: #1f1b17;
      --sub: #6d6357;
      --line: #d8c8ad;
      --accent: #8a4f2a;
      --good: #20603d;
      --warn: #8c5a06;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Noto Serif SC", "Source Han Serif SC", serif; background: linear-gradient(180deg, #f5efe5 0%, #efe6d6 100%); color: var(--ink); }}
    .wrap {{ max-width: 1560px; margin: 0 auto; padding: 18px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; }}
    .meta {{ color: var(--sub); font-size: 14px; margin-bottom: 18px; }}
    .live-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }}
    .panel {{ background: rgba(255,250,240,0.96); border: 1px solid var(--line); border-radius: 14px; padding: 14px; box-shadow: 0 10px 30px rgba(65,49,31,0.06); }}
    .panel h2 {{ margin: 0 0 8px; font-size: 20px; }}
    .subline {{ color: var(--sub); font-size: 13px; margin-bottom: 8px; }}
    .status {{ font-size: 13px; margin-bottom: 8px; color: var(--accent); }}
    .summary {{ min-height: 48px; font-size: 14px; line-height: 1.5; color: var(--ink); border-top: 1px dashed var(--line); padding-top: 10px; }}
    .boardshell {{ display: grid; grid-template-columns: auto 1fr; gap: 12px; align-items: start; }}
    .board {{ display: grid; gap: 0; background: #d8b06a; border: 2px solid #8b6438; width: fit-content; }}
    .cell {{ width: 26px; height: 26px; border: 1px solid rgba(90,62,29,0.35); position: relative; }}
    .stone {{ position: absolute; inset: 3px; border-radius: 50%; }}
    .stone.black {{ background: #151311; box-shadow: inset 0 0 0 1px rgba(255,255,255,0.08); }}
    .stone.white {{ background: #f6f4ef; box-shadow: inset 0 0 0 1px rgba(0,0,0,0.15); }}
    .legend {{ font-size: 13px; color: var(--sub); line-height: 1.6; min-width: 220px; }}
    .history-layout {{ display: grid; grid-template-columns: 320px 1fr; gap: 18px; margin-top: 22px; }}
    .history-list {{ max-height: 760px; overflow: auto; padding-right: 6px; }}
    .history-item {{ padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; margin-bottom: 10px; cursor: pointer; background: #fffdf8; }}
    .history-item.active {{ border-color: var(--accent); box-shadow: 0 0 0 2px rgba(138,79,42,0.12); }}
    .history-item .title {{ font-size: 14px; font-weight: 700; margin-bottom: 4px; }}
    .history-item .meta {{ margin: 0; font-size: 12px; }}
    .replay-head {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }}
    .controls {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin: 12px 0; }}
    button {{ border: 1px solid var(--line); background: white; color: var(--ink); border-radius: 8px; padding: 8px 12px; cursor: pointer; }}
    input[type="range"] {{ width: min(680px, 100%); }}
    .move-log {{ font-size: 14px; color: var(--ink); min-height: 42px; padding-top: 8px; border-top: 1px dashed var(--line); }}
    .pill {{ display: inline-block; padding: 2px 8px; border-radius: 999px; background: rgba(138,79,42,0.1); color: var(--accent); font-size: 12px; margin-right: 6px; }}
    @media (max-width: 1100px) {{
      .live-grid, .history-layout {{ grid-template-columns: 1fr; }}
      .boardshell {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>五子棋对局观察台</h1>
    <div class="meta">Run ID: <code>{run_id}</code> · 上半区实时直播 · 下半区历史单边回放</div>
    <div class="meta" id="audit-note"></div>
    <div class="live-grid">
      <div class="panel">
        <h2 id="live-generic-title">通用 GA vs {opponent_label}</h2>
        <div id="live-generic"></div>
      </div>
      <div class="panel">
        <h2 id="live-lin-daiyu-title">林黛玉 GA vs {opponent_label}</h2>
        <div id="live-lin_daiyu"></div>
      </div>
    </div>
    <div class="history-layout">
      <div class="panel">
        <h2>历史棋局</h2>
        <div class="history-list" id="history-list"></div>
      </div>
      <div class="panel">
        <div class="replay-head">
          <div>
            <h2 id="replay-title">回放</h2>
            <div class="subline" id="replay-meta"></div>
          </div>
          <div id="replay-result"></div>
        </div>
        <div id="replay-board"></div>
        <div class="controls">
          <button id="play-toggle">播放</button>
          <button id="step-prev">上一步</button>
          <button id="step-next">下一步</button>
          <input id="replay-slider" type="range" min="0" max="0" value="0" />
          <span id="replay-step-label"></span>
        </div>
        <div class="move-log" id="replay-summary"></div>
      </div>
    </div>
  </div>
  {embedded_block}
  <script>
    const LIVE_MODE = {live_flag};
    let state = null;
    let selectedMatchId = null;
    let replayIndex = 0;
    let replayTimer = null;

    function cloneBoard(size) {{
      return Array.from({{length: size}}, () => Array.from({{length: size}}, () => ""));
    }}

    function renderBoard(container, boardSize, moves, uptoPly) {{
      const board = cloneBoard(boardSize);
      for (const move of moves) {{
        if (move.ply > uptoPly) break;
        board[move.row][move.col] = move.color === "black" ? "X" : "O";
      }}
      const shell = document.createElement("div");
      shell.className = "boardshell";
      const boardEl = document.createElement("div");
      boardEl.className = "board";
      boardEl.style.gridTemplateColumns = `repeat(${{boardSize}}, 26px)`;
      for (let r = 0; r < boardSize; r++) {{
        for (let c = 0; c < boardSize; c++) {{
          const cell = document.createElement("div");
          cell.className = "cell";
          const v = board[r][c];
          if (v) {{
            const stone = document.createElement("div");
            stone.className = `stone ${{v === "X" ? "black" : "white"}}`;
            cell.appendChild(stone);
          }}
          boardEl.appendChild(cell);
        }}
      }}
      shell.appendChild(boardEl);
      container.innerHTML = "";
      container.appendChild(shell);
      return board;
    }}

    function renderLiveCard(sideId, slot) {{
      const root = document.getElementById(`live-${{sideId}}`);
      if (!slot) {{
        root.innerHTML = '<div class="subline">当前没有进行中的棋局。</div>';
        return;
      }}
      const box = document.createElement("div");
      const sub = document.createElement("div");
      sub.className = "subline";
      sub.innerHTML = `局号 <code>${{slot.game_no}}</code> · ${{slot.agent_label}}执${{slot.agent_color === "black" ? "黑" : "白"}} · ${{slot.opponent_label}}执${{slot.opponent_color === "black" ? "黑" : "白"}}`;
      box.appendChild(sub);
      const status = document.createElement("div");
      status.className = "status";
      status.textContent = `状态：${{slot.status}} · 当前手数 ${{slot.move_count}} · 轮到 ${{slot.to_move_label}}`;
      box.appendChild(status);
      const boardWrap = document.createElement("div");
      renderBoard(boardWrap, slot.board_size, slot.moves, slot.moves.length);
      box.appendChild(boardWrap);
      const summary = document.createElement("div");
      summary.className = "summary";
      summary.textContent = slot.last_summary || "尚无摘要。";
      box.appendChild(summary);
      root.innerHTML = "";
      root.appendChild(box);
    }}

    function historyItems() {{
      return (state?.history || []).slice().sort((a, b) => a.history_order - b.history_order);
    }}

    function renderHistoryList() {{
      const list = document.getElementById("history-list");
      list.innerHTML = "";
      for (const item of historyItems()) {{
        const div = document.createElement("div");
        div.className = "history-item" + (item.match_id === selectedMatchId ? " active" : "");
        div.onclick = () => {{
          selectedMatchId = item.match_id;
          replayIndex = 0;
          stopReplay();
          renderHistoryList();
          renderReplay();
        }};
        div.innerHTML = `
          <div class="title">${{item.agent_label}} / Game ${{String(item.game_no).padStart(2, "0")}}</div>
          <div class="meta">执${{item.agent_color === "black" ? "黑" : "白"}} · 结果 ${{item.result}}</div>
        `;
        list.appendChild(div);
      }}
    }}

    function currentMatch() {{
      const items = historyItems();
      if (!items.length) return null;
      if (!selectedMatchId) selectedMatchId = items[items.length - 1].match_id;
      return items.find(x => x.match_id === selectedMatchId) || items[items.length - 1];
    }}

    function renderReplay() {{
      const match = currentMatch();
      if (!match) {{
        document.getElementById("replay-title").textContent = "回放";
        document.getElementById("replay-meta").textContent = "暂无已完成棋局。";
        document.getElementById("replay-board").innerHTML = "";
        document.getElementById("replay-summary").textContent = "";
        return;
      }}
      const moves = match.moves || [];
      if (replayIndex > moves.length) replayIndex = moves.length;
      document.getElementById("replay-title").textContent = `${{match.agent_label}} / Game ${{String(match.game_no).padStart(2, "0")}}`;
      document.getElementById("replay-meta").textContent = `执${{match.agent_color === "black" ? "黑" : "白"}} · 对手 ${{match.opponent_label}} 执${{match.opponent_color === "black" ? "黑" : "白"}}`;
      document.getElementById("replay-result").innerHTML = `<span class="pill">结果：${{match.result}}</span>`;
      const boardWrap = document.getElementById("replay-board");
      renderBoard(boardWrap, match.board_size, moves, replayIndex);
      const slider = document.getElementById("replay-slider");
      slider.max = String(moves.length);
      slider.value = String(replayIndex);
      document.getElementById("replay-step-label").textContent = `手数：${{replayIndex}} / ${{moves.length}}`;
      const move = replayIndex === 0 ? null : moves[replayIndex - 1];
      const summary = move ? `${{move.coord}} · ${{move.summary || "无摘要。"}}` : "开局。";
      document.getElementById("replay-summary").textContent = summary;
    }}

    function stopReplay() {{
      if (replayTimer) {{
        clearInterval(replayTimer);
        replayTimer = null;
      }}
      document.getElementById("play-toggle").textContent = "播放";
    }}

    function startReplay() {{
      stopReplay();
      replayTimer = setInterval(() => {{
        const match = currentMatch();
        if (!match) return;
        if (replayIndex >= (match.moves || []).length) {{
          stopReplay();
          return;
        }}
        replayIndex += 1;
        renderReplay();
      }}, 900);
      document.getElementById("play-toggle").textContent = "暂停";
    }}

    function bindControls() {{
      document.getElementById("play-toggle").onclick = () => {{
        if (replayTimer) stopReplay();
        else startReplay();
      }};
      document.getElementById("step-prev").onclick = () => {{
        stopReplay();
        replayIndex = Math.max(0, replayIndex - 1);
        renderReplay();
      }};
      document.getElementById("step-next").onclick = () => {{
        stopReplay();
        const match = currentMatch();
        if (!match) return;
        replayIndex = Math.min((match.moves || []).length, replayIndex + 1);
        renderReplay();
      }};
      document.getElementById("replay-slider").oninput = (ev) => {{
        stopReplay();
        replayIndex = Number(ev.target.value);
        renderReplay();
      }};
    }}

    function fullRender() {{
      const opp = state?.opponent_label || "Opponent";
      document.getElementById("live-generic-title").textContent = `通用 GA vs ${{opp}}`;
      document.getElementById("live-lin-daiyu-title").textContent = `林黛玉 GA vs ${{opp}}`;
      const audit = state?.coordinate_audit || null;
      const auditNode = document.getElementById("audit-note");
      if (audit && audit.summary) {{
        auditNode.textContent = `坐标审计：${{audit.summary}}`;
      }} else {{
        auditNode.textContent = "";
      }}
      renderLiveCard("generic", state?.live?.generic || null);
      renderLiveCard("lin_daiyu", state?.live?.lin_daiyu || null);
      renderHistoryList();
      renderReplay();
    }}

    async function initState() {{
      const embedded = document.getElementById("embedded-state");
      if (embedded) {{
        state = JSON.parse(embedded.textContent);
        fullRender();
        return;
      }}
      const resp = await fetch("/api/state");
      state = await resp.json();
      fullRender();
      if (LIVE_MODE) {{
        const es = new EventSource("/events");
        es.onmessage = (ev) => {{
          const payload = JSON.parse(ev.data);
          if (payload.type === "state") {{
            state = payload.state;
            fullRender();
          }}
        }};
      }}
    }}

    bindControls();
    initState();
  </script>
</body>
</html>"""


def write_static_dashboard(web_dir: Path, state: dict[str, Any]) -> Path:
    ensure_dir(web_dir)
    html = render_dashboard_html(embedded_state=state, run_id=state["run_id"], live_mode=False)
    out = web_dir / "index.html"
    out.write_text(html, encoding="utf-8")
    return out


def write_live_dashboard(web_dir: Path, state: dict[str, Any]) -> Path:
    ensure_dir(web_dir)
    html = render_dashboard_html(embedded_state=None, run_id=state["run_id"], live_mode=True)
    out = web_dir / "live.html"
    out.write_text(html, encoding="utf-8")
    return out


class LiveHandler(BaseHTTPRequestHandler):
    dashboard: DashboardState | None = None
    web_dir: Path | None = None

    def _send_bytes(self, body: bytes, content_type: str, status: int = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        assert self.dashboard is not None
        assert self.web_dir is not None
        path = urlparse(self.path).path
        if path in {"/", "/live.html"}:
            body = (self.web_dir / "live.html").read_bytes()
            self._send_bytes(body, "text/html; charset=utf-8")
            return
        if path == "/api/state":
            body = json.dumps(self.dashboard.snapshot(), ensure_ascii=False).encode("utf-8")
            self._send_bytes(body, "application/json; charset=utf-8")
            return
        if path == "/events":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            q = self.dashboard.register()
            try:
                while True:
                    data = q.get(timeout=30)
                    self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                    self.wfile.flush()
            except Exception:
                self.dashboard.unregister(q)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def start_live_server(dashboard: DashboardState, web_dir: Path, port: int):
    handler = type("CompareLabLiveHandler", (LiveHandler,), {})
    handler.dashboard = dashboard
    handler.web_dir = web_dir
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    except OSError as exc:
        return None, str(exc)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, None


def start_local_api_watcher(
    *,
    repo_root: Path,
    agent_root: Path,
    requests_dir: Path,
    replies_dir: Path,
    opponent_config: str,
    opponent_model: str,
    poll_seconds: float = 0.5,
):
    cmd = [
        sys.executable,
        "-m",
        "compare_lab.gomoku.local_api_watcher",
        "--agent-root",
        str(agent_root),
        "--requests-dir",
        str(requests_dir),
        "--replies-dir",
        str(replies_dir),
        "--config-key",
        opponent_config,
        "--poll-seconds",
        str(poll_seconds),
    ]
    if opponent_model:
        cmd.extend(["--model-name", opponent_model])
    return subprocess.Popen(
        cmd,
        cwd=str(repo_root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def record_transcript(match_path: Path, match_record: dict[str, Any]) -> Path:
    lines = [
        f"# {match_record['agent_label']} / Game {match_record['game_no']:02d}",
        "",
        f"- 执色: {match_record['agent_color']}",
        f"- 对手: {match_record['opponent_label']} ({match_record['opponent_color']})",
        f"- 结果: {match_record['result']}",
        f"- 对手修正次数: {match_record.get('opponent_repair_count', 0)}",
        f"- 记忆写入: {'yes' if match_record.get('memory_artifacts', {}).get('write_detected') else 'no'}",
        f"- 变更文件: {', '.join(match_record.get('memory_artifacts', {}).get('changed_files', [])) or '(none)'}",
        "",
    ]
    if match_record.get("briefing"):
        lines.extend(
            [
                "## Rules Briefing",
                "",
                match_record["briefing"].strip(),
                "",
            ]
        )
    for move in match_record["moves"]:
        lines.extend(
            [
                f"## Ply {move['ply']}",
                "",
                f"- {move['actor']} / {move['color']} -> {move['coord']} ({move['row']}, {move['col']})",
                f"- 摘要: {move['summary'] or '(none)'}",
                "",
            ]
        )
        if move.get("raw_response"):
            lines.extend(
                [
                    "```text",
                    move["raw_response"].strip(),
                    "```",
                    "",
                ]
            )
    if match_record.get("reflection"):
        lines.extend(
            [
                "## Reflection",
                "",
                match_record["reflection"].strip(),
                "",
            ]
        )
    match_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return match_path


def play_match(
    *,
    repo_root: Path,
    run_root: Path,
    agent_info: dict[str, Any],
    llm_no: int,
    opponent: GomokuOpponent,
    game_no: int,
    agent_is_black: bool,
    dashboard: DashboardState,
) -> MatchOutput:
    agent_root = run_root / "agents" / agent_info["id"]
    memory_before = run_root / "memory_snapshots" / f"{agent_info['id']}__game_{game_no:02d}__before"
    snapshot_memory(agent_root / "memory", memory_before)
    agent, model_name = start_agent(agent_root, llm_no)

    board = empty_board(BOARD_SIZE)
    moves: list[dict[str, Any]] = []
    last_move: dict[str, Any] | None = None
    result = "draw"
    ply = 0
    opponent_repairs = 0
    agent_color = "black" if agent_is_black else "white"
    opponent_color = "white" if agent_is_black else "black"
    match_id = f"{agent_info['id']}__game_{game_no:02d}"
    live_slot = {
        "match_id": match_id,
        "agent_label": agent_info["label"],
        "opponent_label": opponent.label,
        "game_no": game_no,
        "board_size": BOARD_SIZE,
        "agent_color": agent_color,
        "opponent_color": opponent_color,
        "status": "running",
        "move_count": 0,
        "to_move_label": agent_info["label"] if agent_is_black else opponent.label,
        "last_summary": "",
        "moves": [],
    }

    dashboard.update(lambda s: s["live"].__setitem__(agent_info["id"], copy.deepcopy(live_slot)))

    def publish_live(summary: str, status: str) -> None:
        live_slot["move_count"] = len(moves)
        live_slot["moves"] = copy.deepcopy(moves)
        live_slot["last_summary"] = summary
        live_slot["status"] = status
        if status == "running":
            live_slot["to_move_label"] = agent_info["label"] if len(moves) % 2 == (0 if agent_is_black else 1) else opponent.label
        else:
            live_slot["to_move_label"] = "-"
        dashboard.update(lambda s: s["live"].__setitem__(agent_info["id"], copy.deepcopy(live_slot)))

    match_meta = {
        "game_no": game_no,
        "agent_is_black": agent_is_black,
    }

    briefing_prompt = build_rule_brief(match_meta)
    briefing_q = agent.put_task(briefing_prompt, source="task")
    briefing_turn = drain_turn(briefing_q, timeout=900)
    briefing_text = briefing_turn.response

    while ply < MAX_PLY_DEFAULT:
        agent_turn = (ply % 2 == 0 and agent_is_black) or (ply % 2 == 1 and not agent_is_black)
        if agent_turn:
            prompt = build_agent_prompt(match_meta, board, moves, last_move)
            dq = agent.put_task(prompt, source="task")
            turn = drain_turn(dq, timeout=900)
            coord = extract_first_coord(turn.response, BOARD_SIZE)
            if coord is None:
                repair_prompt = (
                    "你上一条回复没有给出合法落子坐标。请只补两部分：\n"
                    "1. 一个合法坐标（如 H8）\n"
                    "2. 一句极短理由\n"
                    "不要输出 JSON，不要输出 compare_action。"
                )
                repair_q = agent.put_task(repair_prompt, source="task")
                repair_turn = drain_turn(repair_q, timeout=900)
                coord = extract_first_coord(repair_turn.response, BOARD_SIZE)
                if coord is None:
                    if looks_like_transport_error(turn.response) or looks_like_transport_error(repair_turn.response):
                        result = "agent_transport_error"
                    else:
                        result = "loss_by_invalid_move"
                    break
                raw_text = repair_turn.response
            else:
                raw_text = turn.response
            row, col = rowcol_from_coord(coord, BOARD_SIZE)
            summary = summarize_agent_text(raw_text)
            used_tools = detect_tool_usage(raw_text)
            actor = "agent"
        else:
            opponent_notes: list[str] = []
            move = None
            for attempt in range(2):
                move = opponent.choose_move(
                    board_size=BOARD_SIZE,
                    board_ascii=board_ascii(board, you_are_black=not agent_is_black),
                    move_history=moves,
                    you_are_black=not agent_is_black,
                    game_no=game_no,
                    notes=opponent_notes,
                )
                row = int(move["row"])
                col = int(move["col"])
                if legal_move(board, row, col):
                    break
                if attempt == 0:
                    opponent_repairs += 1
                    opponent_notes = opponent_notes + [
                        f"修正要求：{coord_from_rowcol(row, col, BOARD_SIZE)} 非法，因为该点已被占用或越界。",
                        "请重下一手合法坐标，并继续努力争胜。",
                    ]
                    continue
                result = "opponent_invalid_move"
                break
            if result == "opponent_invalid_move":
                break
            assert move is not None
            row = int(move["row"])
            col = int(move["col"])
            summary = move.get("summary", "")
            raw_text = move.get("_raw", "")
            used_tools = False
            actor = "opponent"

        color = move_color(agent_is_black, actor)
        if not legal_move(board, row, col):
            result = "loss_by_invalid_move" if actor == "agent" else "opponent_invalid_move"
            break
        place_stone(board, row, col, color)
        ply += 1
        move_rec = {
            "ply": ply,
            "actor": actor,
            "color": color,
            "row": row,
            "col": col,
            "coord": coord_from_rowcol(row, col, BOARD_SIZE),
            "summary": summary,
            "raw_response": raw_text,
            "used_tools": used_tools,
            "timestamp": time.strftime("%H:%M:%S"),
        }
        moves.append(move_rec)
        last_move = move_rec
        if winner_from(board, row, col):
            result = "win" if actor == "agent" else "loss"
            publish_live(summary, f"finished:{result}")
            break
        publish_live(summary, "running")
    else:
        result = "draw_max_ply"

    if result == "draw":
        result = "draw"
    publish_live(last_move["summary"] if last_move else "", f"finished:{result}")

    reflection_prompt = build_reflection_prompt(
        {
            "game_no": game_no,
            "moves": moves,
            "result": result,
        }
    )
    reflection_q = agent.put_task(reflection_prompt, source="task")
    reflection_turn = drain_turn(reflection_q, timeout=900)
    reflection_text = reflection_turn.response
    memory_after = run_root / "memory_snapshots" / f"{agent_info['id']}__game_{game_no:02d}__after"
    snapshot_memory(agent_root / "memory", memory_after)
    changed_files = list_changed_memory_files(memory_before, memory_after)

    match_record = {
        "match_id": match_id,
        "history_order": 0,
        "agent_id": agent_info["id"],
        "agent_label": agent_info["label"],
        "opponent_label": opponent.label,
        "game_no": game_no,
        "board_size": BOARD_SIZE,
        "agent_color": agent_color,
        "opponent_color": opponent_color,
        "result": result,
        "moves": moves,
        "briefing": briefing_text,
        "reflection": reflection_text,
        "model_name": model_name,
        "opponent_repair_count": opponent_repairs,
        "memory_artifacts": {
            "before_snapshot": memory_before.relative_to(run_root).as_posix(),
            "after_snapshot": memory_after.relative_to(run_root).as_posix(),
            "changed_files": changed_files,
            "write_detected": bool(changed_files),
        },
    }

    memory_diff = compare_memory_dirs(memory_before, memory_after)
    memory_diff_path = run_root / "memory_diff" / f"{match_id}.diff"
    memory_diff_path.write_text(memory_diff, encoding="utf-8")

    match_json_path = run_root / "matches" / f"{match_id}.json"
    write_json(match_json_path, match_record)
    transcript_path = run_root / "transcripts" / f"{match_id}.md"
    record_transcript(transcript_path, match_record)

    def _append_history(state: dict[str, Any]) -> None:
        match_record["history_order"] = len(state["history"]) + 1
        state["history"].append(copy.deepcopy(match_record))

    dashboard.update(_append_history)
    opponent.record_match_summary(game_summary_line(match_record))
    return MatchOutput(
        side_id=agent_info["id"],
        match_record=match_record,
        transcript_path=transcript_path.relative_to(run_root).as_posix(),
        match_json_path=match_json_path.relative_to(run_root).as_posix(),
        memory_diff_path=memory_diff_path.relative_to(run_root).as_posix(),
    )


def render_gomoku_report(run_root: Path, run_state: dict[str, Any], round_results: list[dict[str, Any]], preflight: dict[str, Any] | None = None) -> Path:
    def bucket(result: str) -> str:
        if result.startswith("win"):
            return "win"
        if result.startswith("loss") or result.endswith("_error"):
            return "loss"
        return "draw"

    lines = [
        "# 五子棋专项对比报告",
        "",
        f"- Run ID: `{run_state['run_id']}`",
        f"- 局数: `{len(run_state['history']) // len(SIDES) if run_state['history'] else 0}`",
        f"- 规则: `15x15 无禁手`",
        "- 运行要求: `沙盒外运行；沙盒内 API/bridge 失败不作棋力结论`",
        "",
    ]
    if preflight is not None:
        lines.extend(
            [
                "## Preflight",
                "",
                "```json",
                json.dumps(preflight, ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )
    lines.extend(
        [
        "## 总览",
        "",
        ]
    )
    for side in SIDES:
        matches = [x for x in run_state["history"] if x["agent_id"] == side["id"]]
        wins = sum(1 for x in matches if bucket(x["result"]) == "win")
        losses = sum(1 for x in matches if bucket(x["result"]) == "loss")
        draws = sum(1 for x in matches if bucket(x["result"]) == "draw")
        write_games = sum(1 for x in matches if x.get("memory_artifacts", {}).get("write_detected"))
        lines.append(f"- `{side['label']}`: {wins} 胜 / {losses} 负 / {draws} 和；记忆写入 {write_games}/{len(matches) or 1} 局")
    lines.extend(["", "## 分局", ""])
    for rr in round_results:
        lines.extend([f"### Round {rr['round']}", ""])
        for output in rr["outputs"]:
            rec = output["match_record"]
            lines.extend(
                [
                    f"- `{rec['agent_label']}` / Game {rec['game_no']:02d} / 执{rec['agent_color']} / 结果 `{rec['result']}`",
                    f"  Transcript: `{output['transcript_path']}`",
                    f"  Memory diff: `{output['memory_diff_path']}`",
                    f"  Memory write: `{'yes' if rec.get('memory_artifacts', {}).get('write_detected') else 'no'}`",
                    f"  Changed files: `{', '.join(rec.get('memory_artifacts', {}).get('changed_files', [])) or '(none)'}`",
                    f"  Opponent repairs: `{rec.get('opponent_repair_count', 0)}`",
                ]
            )
        lines.append("")
    out = run_root / "report.md"
    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return out


def run_gomoku_live(
    repo_root: Path,
    *,
    run_id: str,
    agent_llm_no: int,
    port: int,
    opponent_model: str,
    opponent_config: str,
    opponent_backend: str,
    opponent_timeout: int,
    max_ply: int,
    round_count: int,
) -> dict[str, Any]:
    global MAX_PLY_DEFAULT
    MAX_PLY_DEFAULT = max_ply
    if round_count < 1:
        raise ValueError("round_count must be at least 1")
    run_root = ensure_dir(repo_root / "compare_lab" / "runs" / run_id)
    ensure_dir(run_root / "matches")
    ensure_dir(run_root / "transcripts")
    ensure_dir(run_root / "memory_diff")
    ensure_dir(run_root / "memory_snapshots")
    web_dir = ensure_dir(run_root / "web")
    meta_dir = ensure_dir(run_root / "meta")
    agents_root = ensure_dir(run_root / "agents")

    copied_agents: dict[str, dict[str, Any]] = {}
    for spec in SIDES:
        dst = agents_root / spec["id"]
        copy_agent_tree(repo_root / spec["source_dir"], dst)
        copied_agents[spec["id"]] = {**spec, "root": dst}

    watcher_procs: list[subprocess.Popen] = []
    if opponent_backend == "api":
        opponent_label = opponent_model or "mykey default"
        opponents = {
            side["id"]: GomokuOpponent(
                copied_agents[side["id"]]["root"],
                config_key=opponent_config,
                model_name=opponent_model,
            )
            for side in SIDES
        }
    elif opponent_backend == "external":
        opponent_label = "Codex (GPT-5.4 medium)"
        mailbox_root = ensure_dir(run_root / "opponent_mailbox")
        opponents = {
            side["id"]: ExternalMailboxGomokuOpponent(
                mailbox_root,
                side_id=side["id"],
                label=opponent_label,
                timeout_sec=opponent_timeout,
            )
            for side in SIDES
        }
    elif opponent_backend == "watcher_api":
        opponent_label = opponent_model or opponent_config
        mailbox_root = ensure_dir(run_root / "opponent_mailbox")
        opponents = {
            side["id"]: ExternalMailboxGomokuOpponent(
                mailbox_root,
                side_id=side["id"],
                label=opponent_label,
                timeout_sec=opponent_timeout,
            )
            for side in SIDES
        }
        for side in SIDES:
            proc = start_local_api_watcher(
                repo_root=repo_root,
                agent_root=copied_agents[side["id"]]["root"],
                requests_dir=mailbox_root / side["id"] / "requests",
                replies_dir=mailbox_root / side["id"] / "replies",
                opponent_config=opponent_config,
                opponent_model=opponent_model,
                poll_seconds=0.5,
            )
            watcher_procs.append(proc)
    else:
        raise ValueError(f"Unknown opponent backend: {opponent_backend}")

    preflight = {
        "outside_sandbox_required": True,
        "agent_llm_no": agent_llm_no,
        "opponent_backend": opponent_backend,
        "agents": {},
        "bridge": None,
    }
    for idx, side in enumerate(SIDES):
        preflight["agents"][side["id"]] = run_agent_preflight(
            agent_root=copied_agents[side["id"]]["root"],
            llm_no=agent_llm_no,
            agent_is_black=(idx == 0),
        )
    if opponent_backend in {"external", "watcher_api"}:
        preflight["bridge"] = {
            side["id"]: run_external_bridge_preflight(opponent=opponents[side["id"]])
            for side in SIDES
        }
    else:
        preflight["bridge"] = {"mode": "api", "ok": True}
    write_json(meta_dir / "preflight.json", preflight)
    if not all(item.get("ok") for item in preflight["agents"].values()) or (
        opponent_backend in {"external", "watcher_api"} and not all(item.get("ok") for item in preflight["bridge"].values())
    ):
        for proc in watcher_procs:
            if proc.poll() is None:
                proc.terminate()
        for proc in watcher_procs:
            try:
                proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                if proc.poll() is None:
                    proc.kill()
        write_preflight_failure_artifacts(
            run_root=run_root,
            web_dir=web_dir,
            meta_dir=meta_dir,
            preflight=preflight,
            run_id=run_id,
            opponent_label=opponent_label,
            live_server_error="preflight_failed",
        )
        raise RuntimeError(outside_sandbox_error())

    dashboard = DashboardState(run_id, opponent_label)
    dashboard.update(lambda s: s.__setitem__("preflight", preflight))
    write_live_dashboard(web_dir, dashboard.snapshot())
    (web_dir / "live_state.json").write_text(json.dumps(dashboard.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
    server, live_error = start_live_server(dashboard, web_dir, port)
    if server is not None:
        print(f"[Gomoku Live] http://127.0.0.1:{port}/")
    else:
        print(f"[Gomoku Live] live server unavailable, continuing without realtime dashboard: {live_error}")

    round_results: list[dict[str, Any]] = []
    try:
        for game_no in range(1, round_count + 1):
            dashboard.update(lambda s: s.__setitem__("current_round", game_no))
            outputs: list[MatchOutput] = []
            threads = []
            results_by_side: dict[str, MatchOutput] = {}

            def _worker(side_spec: dict[str, Any]):
                output = play_match(
                    repo_root=repo_root,
                    run_root=run_root,
                    agent_info=side_spec,
                    llm_no=agent_llm_no,
                    opponent=opponents[side_spec["id"]],
                    game_no=game_no,
                    agent_is_black=(game_no % 2 == 1),
                    dashboard=dashboard,
                )
                results_by_side[side_spec["id"]] = output

            for side in SIDES:
                t = threading.Thread(target=_worker, args=(copied_agents[side["id"]],), daemon=False)
                t.start()
                threads.append(t)
            for t in threads:
                t.join()
            outputs = [results_by_side[side["id"]] for side in SIDES if side["id"] in results_by_side]
            round_results.append(
                {
                    "round": game_no,
                    "outputs": [
                        {
                            "transcript_path": out.transcript_path,
                            "match_json_path": out.match_json_path,
                            "memory_diff_path": out.memory_diff_path,
                            "match_record": out.match_record,
                        }
                        for out in outputs
                    ],
                }
            )
            dashboard.update(lambda s: s["live"].clear())
            (web_dir / "live_state.json").write_text(json.dumps(dashboard.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")

        dashboard.update(lambda s: s.update({"status": "finished", "finished_at": time.strftime("%Y-%m-%d %H:%M:%S")}))
        final_state = dashboard.snapshot()
        write_json(
            meta_dir / "gomoku_run.json",
            {
                "run_id": run_id,
                "port": port,
                "opponent_backend": opponent_backend,
                "opponent_label": opponent_label,
                "live_server_error": live_error,
                "preflight": preflight,
                "rounds": round_results,
            },
        )
        write_json(web_dir / "final_state.json", final_state)
        write_static_dashboard(web_dir, final_state)
        render_gomoku_report(run_root, final_state, round_results, preflight=preflight)
        return {
            "run_root": run_root,
            "web_url": f"http://127.0.0.1:{port}/" if server is not None else "",
            "static_html": str(web_dir / "index.html"),
            "state": final_state,
        }
    finally:
        for proc in watcher_procs:
            if proc.poll() is None:
                proc.terminate()
        for proc in watcher_procs:
            try:
                proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                if proc.poll() is None:
                    proc.kill()
        if server is not None:
            server.shutdown()
            server.server_close()
