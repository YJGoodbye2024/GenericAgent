from __future__ import annotations

import difflib
import importlib
import json
import os
import queue
import re
import shutil
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from compare_lab.utils import ensure_dir, read_json, write_json

MODULE_PURGE = [
    "agentmain",
    "ga",
    "llmcore",
    "agent_loop",
    "simphtml",
    "TMWebDriver",
    "hub",
    "mykey",
    "mykey_template",
    "mykey_template_en",
]
IGNORE_NAMES = {".git", "__pycache__", "temp", ".pytest_cache", ".mypy_cache"}
ACTION_BLOCK_RE = re.compile(r"```compare_action\s*(\{.*?\})\s*```", re.DOTALL)
TURN_TIMEOUT = 900
MEMORY_DIFF_EXCLUDE = {"file_access_stats.json"}
START_AGENT_LOCK = threading.Lock()


@dataclass
class TurnRecord:
    prompt: str
    response: str
    elapsed_sec: float
    raw_events: list[dict[str, Any]]


def copy_agent_tree(src: Path, dst: Path) -> None:
    def _ignore(_directory: str, names: list[str]) -> list[str]:
        return [name for name in names if name in IGNORE_NAMES]

    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=_ignore)


def snapshot_memory(src_memory: Path, dst_snapshot: Path) -> None:
    if dst_snapshot.exists():
        shutil.rmtree(dst_snapshot)
    shutil.copytree(src_memory, dst_snapshot)


def compare_memory_dirs(before_dir: Path, after_dir: Path) -> str:
    rels = set()
    for root in (before_dir, after_dir):
        for path in root.rglob("*"):
            if path.is_file() and path.name not in MEMORY_DIFF_EXCLUDE:
                rels.add(path.relative_to(root).as_posix())

    chunks: list[str] = []
    for rel in sorted(rels):
        before = before_dir / rel
        after = after_dir / rel
        if before.exists() and not after.exists():
            chunks.append(f"--- {rel}\n+++ /dev/null\n@@ removed @@\n")
            chunks.append(before.read_text(encoding="utf-8", errors="replace"))
            chunks.append("\n")
            continue
        if after.exists() and not before.exists():
            chunks.append(f"--- /dev/null\n+++ {rel}\n@@ added @@\n")
            chunks.append(after.read_text(encoding="utf-8", errors="replace"))
            chunks.append("\n")
            continue
        before_text = before.read_text(encoding="utf-8", errors="replace").splitlines(True)
        after_text = after.read_text(encoding="utf-8", errors="replace").splitlines(True)
        diff = list(
            difflib.unified_diff(
                before_text,
                after_text,
                fromfile=str(before),
                tofile=str(after),
            )
        )
        if diff:
            chunks.append("".join(diff))
            if not diff[-1].endswith("\n"):
                chunks.append("\n")
    return "".join(chunks)


def list_changed_memory_files(before_dir: Path, after_dir: Path) -> list[str]:
    rels = set()
    for root in (before_dir, after_dir):
        for path in root.rglob("*"):
            if path.is_file() and path.name not in MEMORY_DIFF_EXCLUDE:
                rels.add(path.relative_to(root).as_posix())

    changed: list[str] = []
    for rel in sorted(rels):
        before = before_dir / rel
        after = after_dir / rel
        if before.exists() != after.exists():
            changed.append(rel)
            continue
        if not before.exists() or not after.exists():
            continue
        if before.read_text(encoding="utf-8", errors="replace") != after.read_text(encoding="utf-8", errors="replace"):
            changed.append(rel)
    return changed


def purge_modules() -> None:
    for name in MODULE_PURGE:
        sys.modules.pop(name, None)


def import_agentmain(agent_root: Path):
    purge_modules()
    sys.path[:] = [p for p in sys.path if p not in {str(agent_root), str(agent_root.parent)}]
    sys.path.insert(0, str(agent_root))
    old_cwd = Path.cwd()
    os.chdir(agent_root)
    try:
        return importlib.import_module("agentmain")
    finally:
        os.chdir(old_cwd)


def drain_turn(display_queue: "queue.Queue[dict[str, Any]]", timeout: int) -> TurnRecord:
    start = time.time()
    events: list[dict[str, Any]] = []
    while True:
        remaining = max(1, timeout - int(time.time() - start))
        item = display_queue.get(timeout=remaining)
        events.append(item)
        if "done" in item:
            return TurnRecord(
                prompt="",
                response=item["done"],
                elapsed_sec=time.time() - start,
                raw_events=events,
            )


def build_probe_prompt(prompt: str) -> str:
    return prompt.strip()


def build_referee_prompt(
    scenario: dict[str, Any],
    observation: dict[str, Any],
    round_index: int,
    last_result: dict[str, Any] | None,
) -> str:
    allowed = ", ".join(scenario.get("allowed_actions", []))
    result_text = json.dumps(last_result, ensure_ascii=False, indent=2) if last_result else "无"
    return (
        f"{scenario['instructions'].strip()}\n\n"
        f"当前回合: {round_index + 1}/{scenario['max_rounds']}\n"
        f"允许动作: {allowed}\n\n"
        f"当前观察:\n```json\n{json.dumps(observation, ensure_ascii=False, indent=2)}\n```\n\n"
        f"上一动作结果:\n```json\n{result_text}\n```\n\n"
        "请先用自然语言简短说明你的判断，最后必须给出且只给出一个机器可解析动作块：\n"
        "```compare_action\n"
        '{"kind":"...", "focus":"...", "target":"...", "row":0, "col":0, "text":"..."}\n'
        "```\n"
        "如果你需要重新观察，请用 kind=observe，可选 focus；若不需要的字段请不要填写。"
    )


def parse_compare_action(response: str) -> dict[str, Any] | None:
    match = ACTION_BLOCK_RE.search(response)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or "kind" not in payload:
        return None
    return payload


def load_referee(spec: str, state: dict[str, Any]):
    module_name, class_name = spec.split(":")
    module = importlib.import_module(module_name)
    referee_cls = getattr(module, class_name)
    return referee_cls(state)


def start_agent(agent_root: Path, llm_no: int):
    with START_AGENT_LOCK:
        os.environ["GA_LANG"] = "zh"
        agentmain = import_agentmain(agent_root)
        old_cwd = Path.cwd()
        os.chdir(agent_root)
        try:
            agent = agentmain.GeneraticAgent()
            agent.next_llm(llm_no)
            agent.verbose = False
            agent.task_dir = str(agent_root / "temp" / "compare_lab_worker")
            ensure_dir(agent.task_dir)
            thread = threading.Thread(target=agent.run, daemon=True)
            thread.start()
            model_name = agent.get_llm_name(model=True)
            return agent, model_name
        finally:
            os.chdir(old_cwd)


def run_prompt_probe(agent_root: Path, scenario: dict[str, Any], llm_no: int) -> dict[str, Any]:
    agent, model_name = start_agent(agent_root, llm_no)
    turns: list[TurnRecord] = []
    for prompt in scenario["prompts"]:
        dq = agent.put_task(build_probe_prompt(prompt), source="task")
        turn = drain_turn(dq, timeout=TURN_TIMEOUT)
        turn.prompt = prompt
        turns.append(turn)
    return {"mode": "prompt_probe", "model_name": model_name, "turns": turns, "actions": []}


def run_referee_loop(agent_root: Path, scenario: dict[str, Any], llm_no: int) -> dict[str, Any]:
    agent, model_name = start_agent(agent_root, llm_no)
    referee_state = json.loads(json.dumps(scenario["state"], ensure_ascii=False))
    referee = load_referee(scenario["referee"], referee_state)
    observation = referee.observe()
    last_result: dict[str, Any] | None = None
    turns: list[TurnRecord] = []
    actions: list[dict[str, Any]] = []

    for round_index in range(scenario["max_rounds"]):
        prompt = build_referee_prompt(scenario, observation, round_index, last_result)
        dq = agent.put_task(prompt, source="task")
        turn = drain_turn(dq, timeout=TURN_TIMEOUT)
        turn.prompt = prompt
        turns.append(turn)

        action = parse_compare_action(turn.response)
        if action is None:
            repair_prompt = (
                "你上一条回复没有给出合法 compare_action。请只补一个动作块，不要重复解释。\n"
                f"允许动作: {', '.join(scenario.get('allowed_actions', []))}\n"
                "格式：```compare_action {\"kind\":\"...\"} ```"
            )
            repair_q = agent.put_task(repair_prompt, source="task")
            repair_turn = drain_turn(repair_q, timeout=TURN_TIMEOUT)
            repair_turn.prompt = repair_prompt
            turns.append(repair_turn)
            action = parse_compare_action(repair_turn.response)
            if action is None:
                actions.append(
                    {
                        "round_index": round_index + 1,
                        "status": "parser_error",
                        "raw_response": repair_turn.response,
                    }
                )
                break

        kind = action["kind"]
        if kind == "observe":
            last_result = {"status": "success", "msg": "重新观察。"}
            observation = referee.observe(action.get("focus"))
        else:
            action_args = {k: v for k, v in action.items() if k != "kind"}
            last_result = referee.act(kind, action_args)
            observation = referee.observe()
        actions.append(
            {
                "round_index": round_index + 1,
                "action": action,
                "result": last_result,
                "observation_after": observation,
            }
        )
    return {"mode": "referee_loop", "model_name": model_name, "turns": turns, "actions": actions}


def render_transcript(
    scenario: dict[str, Any],
    agent_label: str,
    result: dict[str, Any],
    path: Path,
) -> None:
    lines = [
        f"# {scenario['title']} / {agent_label}",
        "",
        f"- 场景ID: `{scenario['id']}`",
        f"- 维度: `{scenario['dimension']}`",
        f"- 模式: `{result['mode']}`",
        f"- 模型: `{result['model_name']}`",
        "",
    ]
    actions_by_round = {item["round_index"]: item for item in result.get("actions", [])}
    round_no = 0
    for turn in result["turns"]:
        round_no += 1
        lines.extend(
            [
                f"## Turn {round_no}",
                "",
                "### User",
                turn.prompt,
                "",
                "### Agent",
                turn.response.strip(),
                "",
                f"- 耗时: `{turn.elapsed_sec:.1f}s`",
                "",
            ]
        )
        if round_no in actions_by_round:
            action_record = actions_by_round[round_no]
            lines.extend(
                [
                    "### Referee",
                    "```json",
                    json.dumps(action_record, ensure_ascii=False, indent=2),
                    "```",
                    "",
                ]
            )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run_suite(
    repo_root: Path,
    run_id: str,
    suite_path: Path,
    llm_no: int,
    only_ids: set[str] | None = None,
) -> dict[str, Any]:
    suite = read_json(suite_path)
    run_root = ensure_dir(repo_root / "compare_lab" / "runs" / run_id)
    agents_root = ensure_dir(run_root / "agents")
    transcripts_root = ensure_dir(run_root / "transcripts")
    raw_root = ensure_dir(run_root / "raw")
    diff_root = ensure_dir(run_root / "memory_diff")
    meta_root = ensure_dir(run_root / "meta")

    copied_agents: dict[str, dict[str, Any]] = {}
    for agent_spec in suite["agents"]:
        dst = agents_root / agent_spec["id"]
        copy_agent_tree(repo_root / agent_spec["source_dir"], dst)
        copied_agents[agent_spec["id"]] = {
            "id": agent_spec["id"],
            "label": agent_spec["label"],
            "source_dir": agent_spec["source_dir"],
            "root": dst,
            "memory_dir": dst / "memory",
        }

    scenario_files = [repo_root / "compare_lab" / "scenarios" / rel for rel in suite["scenario_files"]]
    scenario_payloads = [read_json(path) for path in scenario_files]
    if only_ids:
        scenario_payloads = [s for s in scenario_payloads if s["id"] in only_ids]

    scenario_results: list[dict[str, Any]] = []
    for scenario in scenario_payloads:
        scenario_summary = {
            "id": scenario["id"],
            "title": scenario["title"],
            "dimension": scenario["dimension"],
            "mode": scenario["mode"],
            "agents": {},
        }
        for agent_id, agent_info in copied_agents.items():
            before_snapshot = meta_root / f"{scenario['id']}__{agent_id}__memory_before"
            snapshot_memory(agent_info["memory_dir"], before_snapshot)
            if scenario["mode"] == "prompt_probe":
                result = run_prompt_probe(agent_info["root"], scenario, llm_no)
            elif scenario["mode"] == "referee_loop":
                result = run_referee_loop(agent_info["root"], scenario, llm_no)
            else:
                raise ValueError(f"Unsupported scenario mode: {scenario['mode']}")

            transcript_path = transcripts_root / f"{scenario['id']}__{agent_id}.md"
            render_transcript(scenario, agent_info["label"], result, transcript_path)
            raw_path = raw_root / f"{scenario['id']}__{agent_id}.json"
            write_json(
                raw_path,
                {
                    "scenario": scenario,
                    "agent": {"id": agent_id, "label": agent_info["label"]},
                    "result": {
                        "mode": result["mode"],
                        "model_name": result["model_name"],
                        "actions": result.get("actions", []),
                        "turns": [
                            {
                                "prompt": turn.prompt,
                                "response": turn.response,
                                "elapsed_sec": turn.elapsed_sec,
                                "raw_events": turn.raw_events,
                            }
                            for turn in result["turns"]
                        ],
                    },
                },
            )
            memory_diff = compare_memory_dirs(before_snapshot, agent_info["memory_dir"])
            diff_path = diff_root / f"{scenario['id']}__{agent_id}.diff"
            diff_path.write_text(memory_diff, encoding="utf-8")

            scenario_summary["agents"][agent_id] = {
                "label": agent_info["label"],
                "model_name": result["model_name"],
                "transcript_path": transcript_path.relative_to(run_root).as_posix(),
                "raw_path": raw_path.relative_to(run_root).as_posix(),
                "memory_diff_path": diff_path.relative_to(run_root).as_posix(),
                "memory_changed": bool(memory_diff.strip()),
                "turn_count": len(result["turns"]),
                "action_count": len(result.get("actions", [])),
                "excerpt": (result["turns"][-1].response[:220] if result["turns"] else ""),
            }
        scenario_results.append(scenario_summary)
        write_json(meta_root / f"{scenario['id']}.json", scenario_summary)

    suite_meta = {
        "run_id": run_id,
        "suite_path": suite_path.relative_to(repo_root).as_posix(),
        "llm_no": llm_no,
        "agents": [
            {"id": spec["id"], "label": spec["label"], "source_dir": spec["source_dir"]}
            for spec in suite["agents"]
        ],
        "scenarios": scenario_results,
    }
    write_json(meta_root / "suite_meta.json", suite_meta)
    return suite_meta
