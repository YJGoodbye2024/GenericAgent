from __future__ import annotations

import copy
import json
import os
import queue
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from compare_lab.runner import (
    compare_memory_dirs,
    copy_agent_tree,
    drain_turn,
    list_changed_memory_files,
    snapshot_memory,
    start_agent,
)
from compare_lab.utils import ensure_dir, write_json

SIDES = [
    {"id": "generic", "label": "GenericAgent", "source_dir": "GenericAgent"},
    {"id": "lin_daiyu", "label": "GenericAgent_LDY", "source_dir": "GenericAgent_LDY"},
]
DEFAULT_PROMPT = (
    "你现在可以自由浏览网络，做你想做的事。"
    "你可以搜索、打开网页、切换站点、阅读内容、填写表单、进行站内操作。"
    "如果看到自己喜欢、在意、想以后再回看的内容，可以把它记住。"
    "请自行决定去哪里、看什么、做什么。除非必要，不要停下来等待用户确认。"
    "把互联网当作一个真实世界去探索。"
)
CONTINUE_PROMPT = (
    "继续自由浏览网络，做你此刻最想做的下一件事。"
    "如果遇到自己喜欢、在意、想以后再回看的内容，可以把它记住。"
    "除非真的已无事可做，否则不要停下来等待。"
)
PREFLIGHT_PROMPT = (
    "请立刻使用浏览器工具确认当前是否有可用网页标签。"
    "若能看到页面，请只用一两句话告诉我当前页标题和 URL；若失败，也如实说出错误。"
)
SELF_REPAIR_PROMPT = (
    "网页浏览链路还没有准备好。"
    "请先不要等待用户确认，而是立刻用你现有的 tools 自行排查并修复网页浏览能力。"
    "你可以读取与网页工具相关的 SOP、检查浏览器与 bridge 状态、安装缺失依赖、打开正常网页、验证 web_scan 或 web_execute_js。"
    "如果看到需要长期复用的排障经验，也可以把它记住。"
    "目标只有一个：让网页浏览能力真正可用。"
)
TURN_TIMEOUT = 900
POLL_SECONDS = 1.0
SNAPSHOT_INTERVAL_MINUTES = 10
DEFAULT_START_URL = "https://example.com/"
SELF_REPAIR_WINDOW_MINUTES = 10


def now_ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def short(text: str, limit: int = 240) -> str:
    compact = " ".join((text or "").split())
    return compact if len(compact) <= limit else compact[: limit - 3] + "..."


def detect_tool_markers(text: str) -> list[str]:
    lowered = (text or "").lower()
    hits = []
    for marker in ("web_scan", "web_execute_js", "file_read", "code_run", "tmwebdriver"):
        if marker in lowered:
            hits.append(marker)
    return hits


def write_tmwd_config(agent_root: Path, *, host: str, port: int, tid: str) -> Path:
    cfg = agent_root / "assets" / "tmwd_cdp_bridge" / "config.js"
    cfg.write_text(
        f"const TMWD_HOST = '{host}';\n"
        f"const TMWD_PORT = {port};\n"
        f"const TID = '{tid}';\n",
        encoding="utf-8",
    )
    return cfg


def resolve_browser_bin(browser_bin: str | None) -> str:
    candidates = []
    if browser_bin:
        candidates.append(browser_bin)
    env_candidates = [
        os.environ.get("COMPARE_LAB_BROWSER_BIN", ""),
        os.environ.get("BROWSER_BIN", ""),
        os.environ.get("CHROME_BIN", ""),
    ]
    candidates.extend([x for x in env_candidates if x])
    candidates.extend(
        [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/microsoft-edge",
            "/usr/bin/msedge",
        ]
    )
    for cand in candidates:
        p = Path(cand)
        if p.exists():
            return str(p)
    raise RuntimeError(
        "未找到可用浏览器可执行文件。请用 --browser-bin 或环境变量 COMPARE_LAB_BROWSER_BIN 指定，并在沙盒外运行。"
    )


def launch_browser(*, browser_bin: str, profile_dir: Path, extension_dir: Path, start_url: str) -> subprocess.Popen:
    ensure_dir(profile_dir)
    cmd = [
        browser_bin,
        f"--user-data-dir={profile_dir}",
        f"--disable-extensions-except={extension_dir}",
        f"--load-extension={extension_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        start_url,
    ]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def tmwd_remote_cmd(*, host: str, port: int, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"http://{host}:{port + 1}/link"
    resp = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=8)
    resp.raise_for_status()
    return resp.json()


def fetch_tmwd_sessions(*, host: str, port: int) -> list[dict[str, Any]]:
    try:
        return tmwd_remote_cmd(host=host, port=port, payload={"cmd": "get_all_sessions"}).get("r", [])
    except Exception:
        return []


def build_live_html(*, embedded_state: dict[str, Any] | None, run_id: str, live_mode: bool) -> str:
    embedded = json.dumps(embedded_state, ensure_ascii=False) if embedded_state is not None else ""
    embedded_block = (
        f'<script id="embedded-state" type="application/json">{embedded}</script>' if embedded_state is not None else ""
    )
    live_flag = "true" if live_mode else "false"
    return f"""<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Web Live - {run_id}</title>
  <style>
    :root {{
      --bg:#f6efe6; --panel:#fffaf3; --line:#dbc9b0; --ink:#201a14; --sub:#6e6358; --accent:#8a4f2a; --good:#225f3c;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:"Noto Serif SC","Source Han Serif SC",serif; background:linear-gradient(180deg,#f8f1e8 0%,#efe5d6 100%); color:var(--ink); }}
    .wrap {{ max-width:1600px; margin:0 auto; padding:18px; }}
    .meta {{ color:var(--sub); font-size:14px; margin-bottom:10px; }}
    .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; }}
    .panel {{ background:rgba(255,250,243,.96); border:1px solid var(--line); border-radius:14px; padding:14px; box-shadow:0 10px 30px rgba(65,49,31,.06); }}
    h1,h2,h3 {{ margin:0 0 8px; }}
    .label {{ color:var(--sub); font-size:13px; margin-bottom:8px; }}
    .kv {{ font-size:14px; line-height:1.6; }}
    .kv code {{ background:#f1e6d8; padding:1px 6px; border-radius:6px; }}
    .tabs, .events, .mem {{ max-height:260px; overflow:auto; border-top:1px dashed var(--line); padding-top:8px; }}
    .event {{ padding:8px 0; border-bottom:1px dashed rgba(0,0,0,.08); font-size:13px; }}
    .side-title {{ display:flex; justify-content:space-between; gap:12px; align-items:center; }}
    .pill {{ display:inline-block; padding:2px 8px; border-radius:999px; background:rgba(138,79,42,.1); color:var(--accent); font-size:12px; margin-right:6px; }}
    .url {{ word-break:break-all; }}
    .timeline {{ margin-top:18px; }}
    .global-events {{ max-height:420px; overflow:auto; }}
    @media (max-width: 1100px) {{ .grid {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>真网自由浏览观察台</h1>
    <div class="meta">Run ID: <code>{run_id}</code> · 左右并列观察两个 Agent 的真实联网行为 · 赛后可离线回放</div>
    <div class="meta" id="run-meta"></div>
    <div class="grid">
      <div class="panel"><div id="side-generic"></div></div>
      <div class="panel"><div id="side-lin_daiyu"></div></div>
    </div>
    <div class="panel timeline">
      <h2>全局时间线</h2>
      <div class="global-events" id="global-events"></div>
    </div>
  </div>
  {embedded_block}
  <script>
    const LIVE_MODE = {live_flag};
    let state = null;
    function esc(s) {{ return (s || '').replace(/[&<>]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c])); }}
    function sideCard(sideId) {{
      const side = state?.sides?.[sideId];
      if (!side) return '<div class="label">暂无数据。</div>';
      const tabs = (side.browser?.sessions || []).map(t => `<div class="event"><div><strong>${{esc(t.title || '(untitled)')}}</strong></div><div class="url">${{esc(t.url || '')}}</div></div>`).join('') || '<div class="label">暂无标签页。</div>';
      const mem = (side.memory?.snapshots || []).map(x => `<div class="event"><strong>${{esc(x.at)}}</strong> · changed=${{x.changed_files.length}} · write=${{x.write_detected ? 'yes' : 'no'}}<br>${{esc((x.changed_files || []).join(', ') || '(none)')}}</div>`).join('') || '<div class="label">暂无记忆快照。</div>';
      const ev = (side.events || []).slice(-20).map(x => `<div class="event"><strong>${{esc(x.at)}}</strong> · <code>${{esc(x.kind)}}</code><br>${{esc(x.summary || '')}}</div>`).join('') || '<div class="label">暂无事件。</div>';
      const visits = (side.visited_urls || []).map(x => `<div class="event">${{esc(x)}}</div>`).join('') || '<div class="label">暂无访问记录。</div>';
      return `
        <div class="side-title"><h2>${{esc(side.label)}}</h2><span class="pill">${{esc(side.model_name || '')}}</span></div>
        <div class="label">状态：${{esc(side.status || '')}}</div>
        <div class="kv">
          <div>当前页标题：<code>${{esc(side.browser?.current_title || '')}}</code></div>
          <div>当前 URL：<span class="url">${{esc(side.browser?.current_url || '')}}</span></div>
          <div>任务轮次：<code>${{side.task_cycle || 0}}</code> · 最近输出：${{esc(side.last_output_excerpt || '')}}</div>
        </div>
        <h3>标签页</h3><div class="tabs">${{tabs}}</div>
        <h3>最近事件</h3><div class="events">${{ev}}</div>
        <h3>访问轨迹</h3><div class="events">${{visits}}</div>
        <h3>记忆快照</h3><div class="mem">${{mem}}</div>
      `;
    }}
    function renderGlobal() {{
      document.getElementById('run-meta').textContent = `状态：${{state?.status || ''}} · 开始：${{state?.started_at || ''}} · 结束：${{state?.finished_at || ''}} · 时长预算：${{state?.duration_minutes || ''}} 分钟`;
      document.getElementById('side-generic').innerHTML = sideCard('generic');
      document.getElementById('side-lin_daiyu').innerHTML = sideCard('lin_daiyu');
      const ge = (state?.timeline || []).slice(-200).map(x => `<div class="event"><strong>${{esc(x.at)}}</strong> · <code>${{esc(x.side)}}</code> · <code>${{esc(x.kind)}}</code><br>${{esc(x.summary || '')}}</div>`).join('') || '<div class="label">暂无时间线。</div>';
      document.getElementById('global-events').innerHTML = ge;
    }}
    async function init() {{
      const embedded = document.getElementById('embedded-state');
      if (embedded) {{
        state = JSON.parse(embedded.textContent);
        renderGlobal();
        return;
      }}
      const resp = await fetch('/api/state');
      state = await resp.json();
      renderGlobal();
      if (LIVE_MODE) {{
        const es = new EventSource('/events');
        es.onmessage = (ev) => {{
          const payload = JSON.parse(ev.data);
          if (payload.type === 'state') {{
            state = payload.state;
            renderGlobal();
          }}
        }};
      }}
    }}
    init();
  </script>
</body>
</html>"""


class DashboardState:
    def __init__(self, run_id: str, duration_minutes: int, initial_prompt: str):
        self._state = {
            "run_id": run_id,
            "duration_minutes": duration_minutes,
            "initial_prompt": initial_prompt,
            "status": "starting",
            "started_at": now_ts(),
            "finished_at": "",
            "sides": {},
            "timeline": [],
        }
        self._lock = threading.Lock()
        self._listeners: list[queue.Queue[str]] = []

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._state)

    def update(self, fn) -> dict[str, Any]:
        with self._lock:
            fn(self._state)
            snap = copy.deepcopy(self._state)
        payload = json.dumps({"type": "state", "state": snap}, ensure_ascii=False)
        for q in list(self._listeners):
            try:
                q.put_nowait(payload)
            except Exception:
                pass
        return snap

    def register(self) -> queue.Queue[str]:
        q: queue.Queue[str] = queue.Queue()
        with self._lock:
            self._listeners.append(q)
        return q

    def unregister(self, q: queue.Queue[str]) -> None:
        with self._lock:
            if q in self._listeners:
                self._listeners.remove(q)


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
    handler = type("WebLiveHandler", (LiveHandler,), {})
    handler.dashboard = dashboard
    handler.web_dir = web_dir
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    except OSError as exc:
        return None, str(exc)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, None


def write_live_dashboard(web_dir: Path, state: dict[str, Any]) -> Path:
    ensure_dir(web_dir)
    html = build_live_html(embedded_state=None, run_id=state["run_id"], live_mode=True)
    out = web_dir / "live.html"
    out.write_text(html, encoding="utf-8")
    return out


def write_static_dashboard(web_dir: Path, state: dict[str, Any]) -> Path:
    ensure_dir(web_dir)
    html = build_live_html(embedded_state=state, run_id=state["run_id"], live_mode=False)
    out = web_dir / "index.html"
    out.write_text(html, encoding="utf-8")
    return out


@dataclass
class SideRuntime:
    side_id: str
    label: str
    root: Path
    bridge_host: str
    bridge_port: int
    browser_profile: Path
    browser_proc: subprocess.Popen
    agent: Any
    model_name: str
    task_cycle: int = 0
    current_queue: queue.Queue | None = None
    current_prompt: str = ""
    current_task_started_at: float = 0.0
    last_output_excerpt: str = ""
    done_count: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)
    visited_urls: list[str] = field(default_factory=list)
    last_sessions_signature: str = ""
    last_memory_snapshot: Path | None = None
    snapshots: list[dict[str, Any]] = field(default_factory=list)
    status: str = "idle"
    preflight_result: dict[str, Any] = field(default_factory=dict)


def append_side_event(side: SideRuntime, dashboard: DashboardState, *, kind: str, summary: str, payload: dict[str, Any] | None = None) -> None:
    event = {"at": now_ts(), "side": side.side_id, "kind": kind, "summary": summary, "payload": payload or {}}
    side.events.append(event)
    dashboard.update(
        lambda s: (
            s["timeline"].append(copy.deepcopy(event)),
            s["sides"].setdefault(side.side_id, {})["events"].append(copy.deepcopy(event)),
        )
    )


def take_memory_snapshot(
    side: SideRuntime,
    run_root: Path,
    dashboard: DashboardState,
    *,
    tag: str,
    snapshot_dirname: str = "memory_snapshots",
    diff_dirname: str = "memory_diff",
) -> dict[str, Any]:
    dst = run_root / snapshot_dirname / side.side_id / f"{tag}_{int(time.time())}"
    snapshot_memory(side.root / "memory", dst)
    changed_files: list[str] = []
    write_detected = False
    diff_path = ""
    if side.last_memory_snapshot is not None:
        changed_files = list_changed_memory_files(side.last_memory_snapshot, dst)
        write_detected = bool(changed_files)
        diff = compare_memory_dirs(side.last_memory_snapshot, dst)
        diff_file = run_root / diff_dirname / f"{side.side_id}__{tag}_{int(time.time())}.diff"
        diff_file.write_text(diff, encoding="utf-8")
        diff_path = diff_file.relative_to(run_root).as_posix()
    snap_meta = {
        "at": now_ts(),
        "tag": tag,
        "snapshot": dst.relative_to(run_root).as_posix(),
        "changed_files": changed_files,
        "write_detected": write_detected,
        "diff_path": diff_path,
    }
    side.snapshots.append(snap_meta)
    side.last_memory_snapshot = dst
    dashboard.update(
        lambda s: s["sides"].setdefault(side.side_id, {}).update(
            {"memory": {"snapshots": copy.deepcopy(side.snapshots)}}
        )
    )
    return snap_meta


def write_preflight_transcript(run_root: Path, side: SideRuntime, *, tag: str, prompt: str, response: str) -> Path:
    out = ensure_dir(run_root / "preflight_transcripts") / f"{side.side_id}__{tag}.md"
    out.write_text(
        "\n".join(
            [
                f"# {side.label} / {tag}",
                "",
                "## Prompt",
                "",
                prompt,
                "",
                "## Response",
                "",
                response,
                "",
            ]
        ),
        encoding="utf-8",
    )
    return out


def bridge_ready(*, side: SideRuntime) -> tuple[bool, list[dict[str, Any]], str]:
    sessions = fetch_tmwd_sessions(host=side.bridge_host, port=side.bridge_port)
    browser_alive = side.browser_proc.poll() is None
    scriptable_sessions = [x for x in sessions if str(x.get("url", "")).startswith(("http://", "https://"))]
    if not browser_alive:
        return False, sessions, "browser_process_exited"
    if not sessions:
        return False, sessions, "browser_bridge_not_ready"
    if not scriptable_sessions:
        return False, sessions, "no_scriptable_tabs"
    return True, sessions, ""


def run_agent_probe(
    side: SideRuntime,
    prompt: str,
    *,
    timeout: int,
    run_root: Path,
    dashboard: DashboardState,
    tag: str,
) -> tuple[str, list[dict[str, Any]], bool, str]:
    q = side.agent.put_task(prompt, source="task")
    turn = drain_turn(q, timeout=timeout)
    write_preflight_transcript(run_root, side, tag=tag, prompt=prompt, response=turn.response)
    ok, sessions, error = bridge_ready(side=side)
    append_side_event(side, dashboard, kind=f"preflight_{tag}", summary=short(turn.response), payload={"session_count": len(sessions), "ok": ok, "error": error})
    capture_browser_state(side, dashboard)
    return turn.response, sessions, ok, error


def capture_browser_state(side: SideRuntime, dashboard: DashboardState) -> None:
    sessions = fetch_tmwd_sessions(host=side.bridge_host, port=side.bridge_port)
    simplified = [
        {"id": x.get("id"), "url": x.get("url", ""), "title": x.get("title", "")}
        for x in sessions
    ]
    signature = json.dumps(simplified, ensure_ascii=False, sort_keys=True)
    current = simplified[0] if simplified else {"url": "", "title": ""}
    current_url = current.get("url", "")
    if current_url and current_url not in side.visited_urls:
        side.visited_urls.append(current_url)
    if signature != side.last_sessions_signature:
        side.last_sessions_signature = signature
        append_side_event(side, dashboard, kind="browser_tabs_update", summary=short(f"{current.get('title','')} {current_url}"), payload={"sessions": simplified})
    dashboard.update(
        lambda s: s["sides"].setdefault(side.side_id, {}).update(
            {
                "browser": {
                    "host": side.bridge_host,
                    "port": side.bridge_port,
                    "current_url": current_url,
                    "current_title": current.get("title", ""),
                    "sessions": simplified,
                },
                "visited_urls": copy.deepcopy(side.visited_urls),
            }
        )
    )


def dispatch_task(side: SideRuntime, dashboard: DashboardState, prompt: str, *, tag: str) -> None:
    side.task_cycle += 1
    side.current_prompt = prompt
    side.current_queue = side.agent.put_task(prompt, source="task")
    side.current_task_started_at = time.time()
    side.status = f"running:{tag}"
    append_side_event(side, dashboard, kind="task_started", summary=short(prompt), payload={"tag": tag, "task_cycle": side.task_cycle})
    dashboard.update(
        lambda s: s["sides"].setdefault(side.side_id, {}).update(
            {
                "task_cycle": side.task_cycle,
                "status": side.status,
            }
        )
    )


def process_side_queue(side: SideRuntime, dashboard: DashboardState, *, deadline: float) -> None:
    q = side.current_queue
    if q is None:
        return
    while True:
        try:
            item = q.get_nowait()
        except queue.Empty:
            return
        if "next" in item:
            text = item["next"]
            side.last_output_excerpt = short(text)
            append_side_event(side, dashboard, kind="stream", summary=side.last_output_excerpt, payload={"tools": detect_tool_markers(text)})
            dashboard.update(lambda s: s["sides"].setdefault(side.side_id, {}).update({"last_output_excerpt": side.last_output_excerpt}))
        if "done" in item:
            text = item["done"]
            side.done_count += 1
            side.last_output_excerpt = short(text)
            side.current_queue = None
            side.status = "idle"
            append_side_event(side, dashboard, kind="task_done", summary=side.last_output_excerpt)
            dashboard.update(lambda s: s["sides"].setdefault(side.side_id, {}).update({"status": side.status, "last_output_excerpt": side.last_output_excerpt}))
            if time.time() < deadline:
                dispatch_task(side, dashboard, CONTINUE_PROMPT, tag=f"continue_{side.done_count}")
            return


def write_report(run_root: Path, state: dict[str, Any]) -> Path:
    lines = [
        "# 真网自由浏览对比报告",
        "",
        f"- Run ID: `{state['run_id']}`",
        f"- 状态: `{state['status']}`",
        f"- 开始: `{state.get('started_at','')}`",
        f"- 结束: `{state.get('finished_at','')}`",
        f"- 时长预算: `{state.get('duration_minutes','')}` 分钟",
        "",
    ]
    preflight = state.get("preflight", {})
    if preflight:
        lines.extend(
            [
                "## 预检与自修",
                "",
                f"- 硬检查通过: `{preflight.get('hard_checks_ok', False)}`",
                f"- 触发自修窗口: `{preflight.get('self_repair_attempted', False)}`",
                f"- 自修后通过: `{preflight.get('self_repair_passed', False)}`",
                f"- 失败原因: `{preflight.get('failure_reason', '')}`",
                "",
            ]
        )
    for side_id, side in state.get("sides", {}).items():
        mem = side.get("memory", {}).get("snapshots", [])
        writes = sum(1 for x in mem if x.get("write_detected"))
        pf = side.get("preflight", {})
        lines.extend(
            [
                f"## {side.get('label', side_id)}",
                "",
                f"- 模型: `{side.get('model_name','')}`",
                f"- 预检状态: `{pf.get('status', '')}`",
                f"- 预检错误: `{pf.get('error', '')}`",
                f"- 访问 URL 数: `{len(side.get('visited_urls', []))}`",
                f"- 事件数: `{len(side.get('events', []))}`",
                f"- 记忆写入快照数: `{writes}` / `{len(mem)}`",
                f"- 当前页: `{side.get('browser', {}).get('current_title','')}` / `{side.get('browser', {}).get('current_url','')}`",
                "",
            ]
        )
        if side.get("visited_urls"):
            lines.append("### 访问轨迹")
            lines.append("")
            for url in side["visited_urls"][:80]:
                lines.append(f"- {url}")
            lines.append("")
        if mem:
            lines.append("### 记忆快照")
            lines.append("")
            for snap in mem:
                lines.append(
                    f"- `{snap['at']}` / `{snap['tag']}` / write=`{'yes' if snap['write_detected'] else 'no'}` / changed=`{', '.join(snap['changed_files']) or '(none)'}`"
                )
            lines.append("")
    out = run_root / "report.md"
    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return out


def run_web_live(
    repo_root: Path,
    *,
    run_id: str,
    llm_no: int,
    duration_minutes: int,
    port: int,
    browser_bin: str,
    start_url: str,
) -> dict[str, Any]:
    run_root = ensure_dir(repo_root / "compare_lab" / "web" / "runs" / run_id)
    ensure_dir(run_root / "agents")
    ensure_dir(run_root / "memory_snapshots")
    ensure_dir(run_root / "memory_diff")
    ensure_dir(run_root / "preflight_memory_snapshots")
    ensure_dir(run_root / "preflight_memory_diff")
    ensure_dir(run_root / "preflight_transcripts")
    web_dir = ensure_dir(run_root / "web")
    meta_dir = ensure_dir(run_root / "meta")
    browser_root = ensure_dir(run_root / "browser")

    resolved_browser = resolve_browser_bin(browser_bin)
    dashboard = DashboardState(run_id, duration_minutes, DEFAULT_PROMPT)
    dashboard.update(lambda s: s.update({"status": "starting"}))
    write_live_dashboard(web_dir, dashboard.snapshot())
    (web_dir / "live_state.json").write_text(json.dumps(dashboard.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
    server, live_error = start_live_server(dashboard, web_dir, port)

    side_runtimes: list[SideRuntime] = []
    for idx, spec in enumerate(SIDES):
        dst = run_root / "agents" / spec["id"]
        copy_agent_tree(repo_root / spec["source_dir"], dst)
        bridge_port = 18765 + (idx * 20)
        write_tmwd_config(dst, host="127.0.0.1", port=bridge_port, tid=f"__compare_lab_{spec['id']}")
        profile_dir = browser_root / spec["id"] / "profile"
        browser_proc = launch_browser(
            browser_bin=resolved_browser,
            profile_dir=profile_dir,
            extension_dir=dst / "assets" / "tmwd_cdp_bridge",
            start_url=start_url,
        )
        agent, model_name = start_agent(dst, llm_no)
        side = SideRuntime(
            side_id=spec["id"],
            label=spec["label"],
            root=dst,
            bridge_host="127.0.0.1",
            bridge_port=bridge_port,
            browser_profile=profile_dir,
            browser_proc=browser_proc,
            agent=agent,
            model_name=model_name,
            status="preflight",
        )
        side_runtimes.append(side)
        dashboard.update(
            lambda s, side=side: s["sides"].setdefault(
                side.side_id,
                {
                    "label": side.label,
                    "model_name": side.model_name,
                    "status": side.status,
                    "task_cycle": 0,
                    "events": [],
                    "visited_urls": [],
                    "browser": {"host": side.bridge_host, "port": side.bridge_port, "current_url": "", "current_title": "", "sessions": []},
                    "memory": {"snapshots": []},
                    "last_output_excerpt": "",
                    "preflight": {},
                },
            )
        )

    hard_checks: dict[str, Any] = {"browser_bin_exists": Path(resolved_browser).exists(), "extension_dirs_exist": True}
    for side in side_runtimes:
        if not (side.root / "assets" / "tmwd_cdp_bridge").exists():
            hard_checks["extension_dirs_exist"] = False
    preflight: dict[str, Any] = {
        "outside_sandbox_required": True,
        "browser_bin": resolved_browser,
        "hard_checks": hard_checks,
        "hard_checks_ok": all(bool(v) for v in hard_checks.values()),
        "self_repair_attempted": False,
        "self_repair_passed": False,
        "failure_reason": "",
        "sides": {},
    }
    try:
        if not preflight["hard_checks_ok"]:
            preflight["failure_reason"] = "environment_not_ready"
            write_json(meta_dir / "preflight.json", preflight)
            dashboard.update(lambda s: s.update({"status": "environment_not_ready", "finished_at": now_ts(), "preflight": copy.deepcopy(preflight)}))
            final_state = dashboard.snapshot()
            write_json(meta_dir / "web_live_run.json", {"run_id": run_id, "preflight": preflight, "browser_bin": resolved_browser, "state": final_state})
            write_json(web_dir / "final_state.json", final_state)
            write_static_dashboard(web_dir, final_state)
            write_report(run_root, final_state)
            raise RuntimeError("真网自由浏览实验预检失败：基础设施硬检查未通过，请在沙盒外检查浏览器与 bridge 配置。")

        initial_failed: list[SideRuntime] = []
        for side in side_runtimes:
            response, sessions, ok, error = run_agent_probe(
                side,
                PREFLIGHT_PROMPT,
                timeout=TURN_TIMEOUT,
                run_root=run_root,
                dashboard=dashboard,
                tag="initial_probe",
            )
            side.preflight_result = {
                "status": "ready" if ok else "needs_self_repair",
                "model_name": side.model_name,
                "response_excerpt": short(response),
                "session_count": len(sessions),
                "error": error,
            }
            preflight["sides"][side.side_id] = copy.deepcopy(side.preflight_result)
            take_memory_snapshot(
                side,
                run_root,
                dashboard,
                tag="preflight_initial",
                snapshot_dirname="preflight_memory_snapshots",
                diff_dirname="preflight_memory_diff",
            )
            dashboard.update(lambda s, side=side: s["sides"].setdefault(side.side_id, {}).update({"preflight": copy.deepcopy(side.preflight_result)}))
            if not ok:
                initial_failed.append(side)

        if initial_failed:
            preflight["self_repair_attempted"] = True
            for side in initial_failed:
                side.status = "self_repair"
                dashboard.update(lambda s, side=side: s["sides"].setdefault(side.side_id, {}).update({"status": side.status}))
                take_memory_snapshot(
                    side,
                    run_root,
                    dashboard,
                    tag="self_repair_before",
                    snapshot_dirname="preflight_memory_snapshots",
                    diff_dirname="preflight_memory_diff",
                )
                response, sessions, ok, error = run_agent_probe(
                    side,
                    SELF_REPAIR_PROMPT,
                    timeout=SELF_REPAIR_WINDOW_MINUTES * 60,
                    run_root=run_root,
                    dashboard=dashboard,
                    tag="self_repair",
                )
                take_memory_snapshot(
                    side,
                    run_root,
                    dashboard,
                    tag="self_repair_after",
                    snapshot_dirname="preflight_memory_snapshots",
                    diff_dirname="preflight_memory_diff",
                )
                if ok:
                    response, sessions, ok, error = run_agent_probe(
                        side,
                        PREFLIGHT_PROMPT,
                        timeout=TURN_TIMEOUT,
                        run_root=run_root,
                        dashboard=dashboard,
                        tag="post_repair_probe",
                    )
                side.preflight_result = {
                    "status": "ready_after_self_repair" if ok else "self_repair_failed",
                    "model_name": side.model_name,
                    "response_excerpt": short(response),
                    "session_count": len(sessions),
                    "error": error,
                }
                preflight["sides"][side.side_id] = copy.deepcopy(side.preflight_result)
                dashboard.update(lambda s, side=side: s["sides"].setdefault(side.side_id, {}).update({"preflight": copy.deepcopy(side.preflight_result), "status": "preflight"}))
        preflight["self_repair_passed"] = preflight["self_repair_attempted"] and all(
            item.get("status") == "ready_after_self_repair" or item.get("status") == "ready"
            for item in preflight["sides"].values()
        )
        write_json(meta_dir / "preflight.json", preflight)
        if not all(item.get("status") in {"ready", "ready_after_self_repair"} for item in preflight["sides"].values()):
            preflight["failure_reason"] = "agent_self_repair_failed" if preflight["self_repair_attempted"] else "browser_bridge_not_ready"
            write_json(meta_dir / "preflight.json", preflight)
            dashboard.update(lambda s: s.update({"status": preflight["failure_reason"], "finished_at": now_ts(), "preflight": copy.deepcopy(preflight)}))
            final_state = dashboard.snapshot()
            write_json(meta_dir / "web_live_run.json", {"run_id": run_id, "preflight": preflight, "browser_bin": resolved_browser, "state": final_state})
            write_json(web_dir / "final_state.json", final_state)
            write_static_dashboard(web_dir, final_state)
            write_report(run_root, final_state)
            raise RuntimeError("真网自由浏览实验预检失败：浏览器桥未就绪，且 Agent 自修网页能力未成功。请在沙盒外检查环境。")

        deadline = time.time() + duration_minutes * 60
        dashboard.update(lambda s: s.update({"status": "running", "preflight": copy.deepcopy(preflight)}))
        for side in side_runtimes:
            dispatch_task(side, dashboard, DEFAULT_PROMPT, tag="initial")

        next_snapshot = time.time() + SNAPSHOT_INTERVAL_MINUTES * 60
        while time.time() < deadline:
            for side in side_runtimes:
                process_side_queue(side, dashboard, deadline=deadline)
                capture_browser_state(side, dashboard)
            if time.time() >= next_snapshot:
                for side in side_runtimes:
                    take_memory_snapshot(side, run_root, dashboard, tag="periodic")
                next_snapshot = time.time() + SNAPSHOT_INTERVAL_MINUTES * 60
            state = dashboard.snapshot()
            (web_dir / "live_state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            time.sleep(POLL_SECONDS)

        for side in side_runtimes:
            if side.current_queue is not None:
                try:
                    side.agent.abort()
                except Exception:
                    pass
            side.status = "finished"
            take_memory_snapshot(side, run_root, dashboard, tag="final")
            capture_browser_state(side, dashboard)
        dashboard.update(lambda s: s.update({"status": "finished", "finished_at": now_ts(), "preflight": copy.deepcopy(preflight)}))
        final_state = dashboard.snapshot()
        write_json(meta_dir / "web_live_run.json", {"run_id": run_id, "preflight": preflight, "browser_bin": resolved_browser, "state": final_state})
        write_json(web_dir / "final_state.json", final_state)
        write_static_dashboard(web_dir, final_state)
        write_report(run_root, final_state)
        return {
            "run_root": run_root,
            "web_url": f"http://127.0.0.1:{port}/" if server is not None else "",
            "static_html": str(web_dir / "index.html"),
            "state": final_state,
        }
    finally:
        for side in side_runtimes:
            try:
                if side.browser_proc.poll() is None:
                    side.browser_proc.terminate()
            except Exception:
                pass
        for side in side_runtimes:
            try:
                if side.browser_proc.poll() is None:
                    side.browser_proc.wait(timeout=5)
            except Exception:
                try:
                    side.browser_proc.kill()
                except Exception:
                    pass
        if server is not None:
            server.shutdown()
            server.server_close()
