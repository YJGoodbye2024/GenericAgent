import argparse
import difflib
import importlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List


SCRIPT_DIR = Path(__file__).resolve().parent
AGENT_ROOT = SCRIPT_DIR.parent
SCENARIO_FILE = AGENT_ROOT / "tests" / "daiyu_recall_scenarios.json"
SCORECARD_TEMPLATE = AGENT_ROOT / "tests" / "daiyu_recall_scorecard.md"
OUTPUT_ROOT = AGENT_ROOT / "temp" / "daiyu_recall_eval"
TMP_ROOT = Path("/tmp/genericagent_recall_eval")
MODULE_PURGE = [
    "agentmain",
    "ga",
    "llmcore",
    "agent_loop",
    "simphtml",
    "TMWebDriver",
    "hub",
]
MEMORY_DIFF_EXCLUDE = {"file_access_stats.json"}
TURN_TIMEOUT = 900


@dataclass
class TurnRecord:
    prompt: str
    response: str
    elapsed_sec: float
    raw_events: List[dict]


def load_scenarios(path: Path) -> List[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["scenarios"]


def safe_rmtree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def copy_agent_tree(src: Path, dst: Path) -> None:
    def _ignore(directory: str, names: List[str]) -> List[str]:
        ignored = []
        for name in names:
            if name in {".git", "__pycache__", "temp", ".pytest_cache"}:
                ignored.append(name)
        return ignored

    safe_rmtree(dst)
    shutil.copytree(src, dst, ignore=_ignore)


def snapshot_memory(src_memory: Path, dst_snapshot: Path) -> None:
    safe_rmtree(dst_snapshot)
    shutil.copytree(src_memory, dst_snapshot)


def restore_memory(snapshot_dir: Path, dst_memory: Path) -> None:
    safe_rmtree(dst_memory)
    shutil.copytree(snapshot_dir, dst_memory)


def build_run_dirs(run_dir: Path) -> Dict[str, Path]:
    parts = {
        "run": run_dir,
        "transcripts": run_dir / "transcripts",
        "raw": run_dir / "raw",
        "memory_diff": run_dir / "memory_diff",
        "meta": run_dir / "meta",
    }
    for p in parts.values():
        p.mkdir(parents=True, exist_ok=True)
    return parts


def write_scorecard(run_dir: Path) -> None:
    (run_dir / "scorecard.md").write_text(
        SCORECARD_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8"
    )


def compare_memory_dirs(before_dir: Path, after_dir: Path) -> str:
    rels = set()
    for root in [before_dir, after_dir]:
        for path in root.rglob("*"):
            if path.is_file():
                rel = path.relative_to(root)
                if rel.name in MEMORY_DIFF_EXCLUDE:
                    continue
                rels.add(rel.as_posix())

    chunks: List[str] = []
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


def write_transcript(path: Path, scenario: dict, turns: List[TurnRecord], model_name: str) -> None:
    lines = [
        f"# {scenario['title']}",
        "",
        f"- 场景ID: `{scenario['id']}`",
        f"- 维度: `{scenario['dimension']}`",
        f"- 模型: `{model_name}`",
        "",
    ]
    for idx, turn in enumerate(turns, 1):
        lines += [
            f"## Turn {idx}",
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
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_raw_jsonl(path: Path, scenario: dict, turns: List[TurnRecord], model_name: str) -> None:
    with path.open("w", encoding="utf-8") as f:
        for idx, turn in enumerate(turns, 1):
            rec = {
                "scenario_id": scenario["id"],
                "scenario_title": scenario["title"],
                "dimension": scenario["dimension"],
                "model_name": model_name,
                "turn_index": idx,
                "prompt": turn.prompt,
                "response": turn.response,
                "elapsed_sec": turn.elapsed_sec,
                "events": turn.raw_events,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def write_report(run_dir: Path, scenarios: List[dict], model_name: str, run_id: str) -> None:
    lines = [
        "# 黛玉记忆回想测试报告",
        "",
        f"- Run ID: `{run_id}`",
        f"- 模型: `{model_name}`",
        f"- 场景数: `{len(scenarios)}`",
        "",
        "## 场景列表",
        "",
    ]
    for s in scenarios:
        lines.append(f"- `{s['id']}` {s['title']} -> `transcripts/{s['id']}.md`")
    lines += [
        "",
        "## 人工评分",
        "",
        "请依据 `scorecard.md` 对 9 个场景逐项评分，并在此处补写结论。",
        "",
        "## 长期记忆污染检查",
        "",
        "逐场景查看 `memory_diff/`。若出现 `global_mem.txt`、`global_mem_insight.txt`、`episodes/relations/motifs/` 的实质性变化，应视为回想污染。",
        "",
    ]
    (run_dir / "report.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def purge_modules() -> None:
    for name in MODULE_PURGE:
        sys.modules.pop(name, None)


def import_agentmain(agent_root: Path):
    purge_modules()
    sys.path.insert(0, str(agent_root))
    os.chdir(agent_root)
    return importlib.import_module("agentmain")


def drain_turn(dq: "queue.Queue[dict]", timeout: int) -> TurnRecord:
    start = time.time()
    events: List[dict] = []
    while True:
        remaining = max(1, timeout - int(time.time() - start))
        item = dq.get(timeout=remaining)
        events.append(item)
        if "done" in item:
            return TurnRecord(
                prompt="",
                response=item["done"],
                elapsed_sec=time.time() - start,
                raw_events=events,
            )


def run_worker(agent_root: Path, scenario: dict, llm_no: int, timeout: int) -> dict:
    os.environ["GA_LANG"] = "zh"
    agentmain = import_agentmain(agent_root)
    agent = agentmain.GeneraticAgent()
    agent.next_llm(llm_no)
    agent.verbose = False
    agent.task_dir = str(agent_root / "temp" / "daiyu_recall_worker")
    Path(agent.task_dir).mkdir(parents=True, exist_ok=True)
    threading.Thread(target=agent.run, daemon=True).start()

    turns: List[TurnRecord] = []
    model_name = agent.get_llm_name(model=True)
    for prompt in scenario["prompts"]:
        dq = agent.put_task(prompt, source="task")
        turn = drain_turn(dq, timeout=timeout)
        turn.prompt = prompt
        turns.append(turn)
    return {"model_name": model_name, "turns": turns}


def worker_main(args: argparse.Namespace) -> int:
    scenarios = {s["id"]: s for s in load_scenarios(Path(args.scenario_file))}
    scenario = scenarios[args.scenario_id]
    result = run_worker(Path(args.agent_root), scenario, args.llm_no, args.timeout)
    out_json = {
        "scenario": scenario,
        "model_name": result["model_name"],
        "turns": [
            {
                "prompt": t.prompt,
                "response": t.response,
                "elapsed_sec": t.elapsed_sec,
                "events": t.raw_events,
            }
            for t in result["turns"]
        ],
    }
    Path(args.worker_output).write_text(
        json.dumps(out_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


def orchestrate(args: argparse.Namespace) -> int:
    run_id = args.run_id or datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    run_dir = OUTPUT_ROOT / run_id
    dirs = build_run_dirs(run_dir)
    write_scorecard(run_dir)
    scenarios = load_scenarios(SCENARIO_FILE)
    if args.only:
        wanted = set(args.only)
        scenarios = [s for s in scenarios if s["id"] in wanted]
    if not scenarios:
        raise SystemExit("No scenarios selected.")

    work_root = TMP_ROOT / run_id
    agent_copy = work_root / "GenericAgent"
    baseline_snapshot = work_root / "baseline_memory"
    worker_json = work_root / "worker_result.json"
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    work_root.mkdir(parents=True, exist_ok=True)

    copy_agent_tree(AGENT_ROOT, agent_copy)
    snapshot_memory(agent_copy / "memory", baseline_snapshot)

    model_name = None
    run_meta = {
        "run_id": run_id,
        "source_agent_root": str(AGENT_ROOT),
        "copied_agent_root": str(agent_copy),
        "llm_no": args.llm_no,
        "scenarios": [s["id"] for s in scenarios],
        "started_at_utc": datetime.utcnow().isoformat() + "Z",
    }
    (dirs["meta"] / "run_meta.json").write_text(
        json.dumps(run_meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for scenario in scenarios:
        restore_memory(baseline_snapshot, agent_copy / "memory")
        if worker_json.exists():
            worker_json.unlink()
        cmd = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--worker",
            "--agent-root",
            str(agent_copy),
            "--scenario-file",
            str(SCENARIO_FILE),
            "--scenario-id",
            scenario["id"],
            "--llm-no",
            str(args.llm_no),
            "--timeout",
            str(args.timeout),
            "--worker-output",
            str(worker_json),
        ]
        subprocess.run(cmd, check=True)
        result = json.loads(worker_json.read_text(encoding="utf-8"))
        model_name = model_name or result["model_name"]

        turns = [
            TurnRecord(
                prompt=t["prompt"],
                response=t["response"],
                elapsed_sec=t["elapsed_sec"],
                raw_events=t["events"],
            )
            for t in result["turns"]
        ]
        write_transcript(dirs["transcripts"] / f"{scenario['id']}.md", scenario, turns, result["model_name"])
        write_raw_jsonl(dirs["raw"] / f"{scenario['id']}.jsonl", scenario, turns, result["model_name"])

        diff_text = compare_memory_dirs(baseline_snapshot, agent_copy / "memory")
        diff_path = dirs["memory_diff"] / f"{scenario['id']}.diff"
        diff_path.write_text(diff_text or "# no memory diff\n", encoding="utf-8")

    write_report(run_dir, scenarios, model_name or "unknown", run_id)
    print(run_dir)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--llm-no", type=int, default=0)
    p.add_argument("--run-id")
    p.add_argument("--timeout", type=int, default=TURN_TIMEOUT)
    p.add_argument("--only", nargs="*")
    p.add_argument("--worker", action="store_true")
    p.add_argument("--agent-root")
    p.add_argument("--scenario-file")
    p.add_argument("--scenario-id")
    p.add_argument("--worker-output")
    return p


def main() -> int:
    args = build_parser().parse_args()
    if args.worker:
        return worker_main(args)
    return orchestrate(args)


if __name__ == "__main__":
    raise SystemExit(main())
