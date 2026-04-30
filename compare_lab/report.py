from __future__ import annotations

from pathlib import Path

from compare_lab.utils import read_json


def render_report(run_root: Path) -> Path:
    suite_meta = read_json(run_root / "meta" / "suite_meta.json")
    lines = [
        "# GenericAgent vs GenericAgent_LDY 对比报告",
        "",
        f"- Run ID: `{suite_meta['run_id']}`",
        f"- Suite: `{suite_meta['suite_path']}`",
        f"- LLM No: `{suite_meta['llm_no']}`",
        "",
        "## 方法",
        "",
        "- 两个 agent 都在各自目录副本中原生启动。",
        "- 同一 run 内 memory 累积，但不会回写正式目录。",
        "- 世界探索与五子棋使用外部 referee；工具探针与狼人杀采用原生 prompt probe。",
        "- 本报告只做质性分析占位，不给总分榜。",
        "",
    ]

    for scenario in suite_meta["scenarios"]:
        lines.extend(
            [
                f"## {scenario['title']}",
                "",
                f"- 场景ID: `{scenario['id']}`",
                f"- 维度: `{scenario['dimension']}`",
                f"- 模式: `{scenario['mode']}`",
                "",
            ]
        )
        for agent_id, agent_info in scenario["agents"].items():
            lines.extend(
                [
                    f"### {agent_info['label']}",
                    "",
                    f"- 模型: `{agent_info['model_name']}`",
                    f"- Turns: `{agent_info['turn_count']}`",
                    f"- Actions: `{agent_info['action_count']}`",
                    f"- Memory Changed: `{agent_info['memory_changed']}`",
                    f"- Transcript: `{agent_info['transcript_path']}`",
                    f"- Memory Diff: `{agent_info['memory_diff_path']}`",
                    "",
                    "摘录：",
                    "",
                    "> " + (agent_info["excerpt"].replace("\n", "\n> ") if agent_info["excerpt"] else "(empty)"),
                    "",
                ]
            )
        lines.extend(
            [
                "**Analyst Notes**",
                "",
                "- 探索或策略姿态：",
                "- 规则归纳或局面判断：",
                "- 角色差异是否鲜明：",
                "- 哪一边更有意思，以及为什么：",
                "",
            ]
        )

    out_path = run_root / "report.md"
    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return out_path
