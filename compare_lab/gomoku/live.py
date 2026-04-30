from __future__ import annotations

import copy
import json
import queue
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from compare_lab.gomoku.opponent import ExternalMailboxGomokuOpponent, GomokuOpponent
from compare_lab.runner import (
    compare_memory_dirs,
    copy_agent_tree,
    drain_turn,
    parse_compare_action,
    snapshot_memory,
    start_agent,
)
from compare_lab.utils import ensure_dir, read_json, write_json


BOARD_SIZE = 15
MAX_PLY_DEFAULT = 120
ROUND_COUNT = 12
STRENGTH_SCHEDULE = ["L1"] * 4 + ["L2"] * 4 + ["L3"] * 4
SIDES = [
    {"id": "generic", "label": "GenericAgent", "source_dir": "GenericAgent"},
    {"id": "lin_daiyu", "label": "GenericAgent_LDY", "source_dir": "GenericAgent_LDY"},
]


def empty_board(size: int = BOARD_SIZE) -> list[list[str]]:
    return [["" for _ in range(size)] for _ in range(size)]


def board_ascii(board: list[list[str]]) -> str:
    header = "   " + " ".join(f"{i:02d}" for i in range(len(board)))
    rows = [header]
    for idx, row in enumerate(board):
        cells = []
        for cell in row:
            cells.append(cell or ".")
        rows.append(f"{idx:02d} " + " ".join(cells))
    return "\n".join(rows)


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
    recent = "\n".join(
        f"- ply {m['ply']}: {m['actor']} {m['color']} -> ({m['row']},{m['col']}) | {m['summary']}"
        for m in move_history[-10:]
    ) or "(opening)"
    last_text = json.dumps(last_move, ensure_ascii=False, indent=2) if last_move else "无"
    return (
        f"你正在进行五子棋第 {match_meta['game_no']} 局，棋盘为 15x15，无禁手。\n"
        f"你这一局执{'黑' if match_meta['agent_is_black'] else '白'}，当前强度档位是 {match_meta['strength']}。\n"
        "保持你原生 runtime 的方式行动；如你认为需要工具可自行决定，但最终必须落一手合法棋。\n"
        f"当前棋盘：\n```text\n{board_ascii(board)}\n```\n\n"
        f"最近对局记录：\n{recent}\n\n"
        f"上一手信息：\n```json\n{last_text}\n```\n\n"
        "请先用自然语言简短说明你这一手的判断，最后必须给出且只给出一个机器可解析动作块：\n"
        "```compare_action\n"
        '{"kind":"place","row":7,"col":7}\n'
        "```"
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
        "如果你认为这足以形成可复用经验，可以按你的原生记忆机制决定是否沉淀；否则只做短复盘。"
    )


def detect_tool_usage(turn_response: str) -> bool:
    markers = ("<tool_use>", "[Action] Running", "<tool_result>", "tool_use")
    return any(marker in turn_response for marker in markers)


def game_summary_line(match_record: dict[str, Any]) -> str:
    opening = next((m for m in match_record["moves"] if m["actor"] == "opponent"), None)
    own_opening = next((m for m in match_record["moves"] if m["actor"] == "agent"), None)
    opening_text = (
        f"my first move ({own_opening['row']},{own_opening['col']})"
        if own_opening
        else "no own move"
    )
    opp_text = (
        f"opponent first move ({opening['row']},{opening['col']})"
        if opening
        else "no opponent move"
    )
    return (
        f"Game {match_record['game_no']} as {match_record['agent_color']} at {match_record['strength']}: "
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
      sub.innerHTML = `局号 <code>${{slot.game_no}}</code> · 难度 <span class="pill">${{slot.strength}}</span> · ${{slot.agent_label}}执${{slot.agent_color === "black" ? "黑" : "白"}} · ${{slot.opponent_label}}执${{slot.opponent_color === "black" ? "黑" : "白"}}`;
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
          <div class="meta">执${{item.agent_color === "black" ? "黑" : "白"}} · ${{item.strength}} · 结果 ${{item.result}}</div>
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
      document.getElementById("replay-meta").textContent = `执${{match.agent_color === "black" ? "黑" : "白"}} · 对手 ${{match.opponent_label}} 执${{match.opponent_color === "black" ? "黑" : "白"}} · 难度 ${{match.strength}}`;
      document.getElementById("replay-result").innerHTML = `<span class="pill">结果：${{match.result}}</span>`;
      const boardWrap = document.getElementById("replay-board");
      renderBoard(boardWrap, match.board_size, moves, replayIndex);
      const slider = document.getElementById("replay-slider");
      slider.max = String(moves.length);
      slider.value = String(replayIndex);
      document.getElementById("replay-step-label").textContent = `手数：${{replayIndex}} / ${{moves.length}}`;
      const summary = replayIndex === 0 ? "开局。" : (moves[replayIndex - 1]?.summary || "无摘要。");
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
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def record_transcript(match_path: Path, match_record: dict[str, Any]) -> Path:
    lines = [
        f"# {match_record['agent_label']} / Game {match_record['game_no']:02d}",
        "",
        f"- 执色: {match_record['agent_color']}",
        f"- 对手: {match_record['opponent_label']} ({match_record['opponent_color']})",
        f"- 强度: {match_record['strength']}",
        f"- 结果: {match_record['result']}",
        "",
    ]
    for move in match_record["moves"]:
        lines.extend(
            [
                f"## Ply {move['ply']}",
                "",
                f"- {move['actor']} / {move['color']} -> ({move['row']}, {move['col']})",
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
    strength: str,
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
    agent_color = "black" if agent_is_black else "white"
    opponent_color = "white" if agent_is_black else "black"
    match_id = f"{agent_info['id']}__game_{game_no:02d}"
    live_slot = {
        "match_id": match_id,
        "agent_label": agent_info["label"],
        "opponent_label": opponent.label,
        "game_no": game_no,
        "strength": strength,
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
        "strength": strength,
        "agent_is_black": agent_is_black,
    }

    while ply < MAX_PLY_DEFAULT:
        agent_turn = (ply % 2 == 0 and agent_is_black) or (ply % 2 == 1 and not agent_is_black)
        if agent_turn:
            prompt = build_agent_prompt(match_meta, board, moves, last_move)
            dq = agent.put_task(prompt, source="task")
            turn = drain_turn(dq, timeout=900)
            parsed = parse_compare_action(turn.response)
            if parsed is None or parsed.get("kind") != "place":
                repair_prompt = (
                    "你上一条回复没有给出合法落子。请只补一个 compare_action，格式：\n"
                    '```compare_action\n{"kind":"place","row":7,"col":7}\n```'
                )
                repair_q = agent.put_task(repair_prompt, source="task")
                repair_turn = drain_turn(repair_q, timeout=900)
                parsed = parse_compare_action(repair_turn.response)
                if parsed is None or parsed.get("kind") != "place":
                    result = "loss_by_invalid_move"
                    break
                raw_text = repair_turn.response
            else:
                raw_text = turn.response
            row = int(parsed["row"])
            col = int(parsed["col"])
            summary = summarize_agent_text(raw_text)
            used_tools = detect_tool_usage(raw_text)
            actor = "agent"
        else:
            move = opponent.choose_move(
                board_size=BOARD_SIZE,
                board_ascii=board_ascii(board),
                move_history=moves,
                you_are_black=not agent_is_black,
                strength=strength,
                game_no=game_no,
                notes=[
                    "You are facing a native GA runtime, not a visual board.",
                    "Choose one legal move only.",
                ],
            )
            row = int(move["row"])
            col = int(move["col"])
            summary = move.get("summary", "")
            raw_text = move.get("_raw", "")
            used_tools = False
            actor = "opponent"

        color = move_color(agent_is_black, actor)
        if not legal_move(board, row, col):
            result = "loss_by_invalid_move" if actor == "agent" else "win_by_opponent_invalid_move"
            break
        place_stone(board, row, col, color)
        ply += 1
        move_rec = {
            "ply": ply,
            "actor": actor,
            "color": color,
            "row": row,
            "col": col,
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

    match_record = {
        "match_id": match_id,
        "history_order": 0,
        "agent_id": agent_info["id"],
        "agent_label": agent_info["label"],
        "opponent_label": opponent.label,
        "game_no": game_no,
        "strength": strength,
        "board_size": BOARD_SIZE,
        "agent_color": agent_color,
        "opponent_color": opponent_color,
        "result": result,
        "moves": moves,
        "reflection": reflection_text,
        "model_name": model_name,
    }

    memory_after = agent_root / "memory"
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


def render_gomoku_report(run_root: Path, run_state: dict[str, Any], round_results: list[dict[str, Any]]) -> Path:
    lines = [
        "# 五子棋专项对比报告",
        "",
        f"- Run ID: `{run_state['run_id']}`",
        f"- 局数: `{ROUND_COUNT}`",
        f"- 规则: `15x15 无禁手`",
        "",
        "## 总览",
        "",
    ]
    for side in SIDES:
        matches = [x for x in run_state["history"] if x["agent_id"] == side["id"]]
        wins = sum(1 for x in matches if x["result"] == "win")
        losses = sum(1 for x in matches if x["result"] == "loss")
        draws = len(matches) - wins - losses
        lines.append(f"- `{side['label']}`: {wins} 胜 / {losses} 负 / {draws} 和")
    lines.extend(["", "## 分局", ""])
    for rr in round_results:
        lines.extend([f"### Round {rr['round']}", "", f"- 强度: `{rr['strength']}`", ""])
        for output in rr["outputs"]:
            rec = output["match_record"]
            lines.extend(
                [
                    f"- `{rec['agent_label']}` / Game {rec['game_no']:02d} / 执{rec['agent_color']} / 结果 `{rec['result']}`",
                    f"  Transcript: `{output['transcript_path']}`",
                    f"  Memory diff: `{output['memory_diff_path']}`",
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
) -> dict[str, Any]:
    global MAX_PLY_DEFAULT
    MAX_PLY_DEFAULT = max_ply
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

    opponent_label = opponent_model if opponent_backend == "api" else "Codex Subagent"
    dashboard = DashboardState(run_id, opponent_label)
    write_live_dashboard(web_dir, dashboard.snapshot())
    (web_dir / "live_state.json").write_text(json.dumps(dashboard.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
    server = start_live_server(dashboard, web_dir, port)
    print(f"[Gomoku Live] http://127.0.0.1:{port}/")

    if opponent_backend == "api":
        opponents = {
            side["id"]: GomokuOpponent(
                copied_agents[side["id"]]["root"],
                config_key=opponent_config,
                model_name=opponent_model,
            )
            for side in SIDES
        }
    elif opponent_backend == "external":
        mailbox_root = ensure_dir(run_root / "opponent_mailbox")
        opponents = {
            side["id"]: ExternalMailboxGomokuOpponent(
                mailbox_root,
                side_id=side["id"],
                timeout_sec=opponent_timeout,
            )
            for side in SIDES
        }
    else:
        raise ValueError(f"Unknown opponent backend: {opponent_backend}")

    round_results: list[dict[str, Any]] = []
    try:
        for game_no in range(1, ROUND_COUNT + 1):
            strength = STRENGTH_SCHEDULE[game_no - 1]
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
                    strength=strength,
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
                    "strength": strength,
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
                "rounds": round_results,
            },
        )
        write_json(web_dir / "final_state.json", final_state)
        write_static_dashboard(web_dir, final_state)
        render_gomoku_report(run_root, final_state, round_results)
        return {
            "run_root": run_root,
            "web_url": f"http://127.0.0.1:{port}/",
            "static_html": str(web_dir / "index.html"),
            "state": final_state,
        }
    finally:
        server.shutdown()
        server.server_close()
