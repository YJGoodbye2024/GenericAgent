from __future__ import annotations

import re
from pathlib import Path


THIS_DIR = Path(__file__).resolve().parent
GENERIC_AGENT_ROOT = THIS_DIR.parent
REPO_ROOT = GENERIC_AGENT_ROOT.parent
HONGLou_DIR = REPO_ROOT / "honglou"
READING_DIR = GENERIC_AGENT_ROOT / "memory" / "L4_raw_sessions" / "canon_reading"
EVIDENCE_DIR = GENERIC_AGENT_ROOT / "memory" / "L4_raw_sessions" / "canon_evidence"


def title_of(text: str, fallback: str) -> str:
    first = text.splitlines()[0].strip() if text.splitlines() else ""
    if first:
        return first
    return fallback


def normalize_newlines(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.rstrip() + "\n"


def build_reading(chapter_id: str, source_path: Path, raw_text: str) -> str:
    title = title_of(raw_text, f"### 第{chapter_id}回")
    relative = source_path.relative_to(REPO_ROOT).as_posix()
    return (
        f"# {title.lstrip('# ').strip()}\n\n"
        f"- chapter_id: `{chapter_id}`\n"
        f"- source: `{relative}`\n"
        f"- note: 本文件保留该回原文全文。关于“黛玉亲历 / 可被告知 / 生前不应直接知道”的边界，请结合同回 `canon_evidence/{chapter_id}.md` 使用。\n\n"
        "## 原文全文\n\n"
        f"{normalize_newlines(raw_text)}"
    )


def build_evidence(chapter_id: str, source_path: Path, raw_text: str) -> str:
    title = title_of(raw_text, f"### 第{chapter_id}回")
    relative = source_path.relative_to(REPO_ROOT).as_posix()
    is_posthumous = int(chapter_id) >= 99
    if is_posthumous:
        boundary = (
            "本回发生在黛玉辞世之后。全文保留为身后余波 / 后见背景，不得直接上升为她生前第一人称亲历。"
        )
    else:
        boundary = (
            "本回请在人工重读时继续细分：哪些段落属于黛玉亲历，哪些只可作被告知之事，哪些是读者或叙事者才知道而黛玉不应生前直知。"
        )

    return (
        f"# {title.lstrip('# ').strip()} 证据回链\n\n"
        f"- chapter_id: `{chapter_id}`\n"
        f"- source: `{relative}`\n"
        f"- reading_file: `memory/L4_raw_sessions/canon_reading/{chapter_id}.md`\n\n"
        "## 边界说明\n\n"
        f"{boundary}\n\n"
        "## direct_spans\n\n"
        "- 待人工补写：列出黛玉亲历 / 亲闻 / 亲见的关键段落，并标注其对哪些 episode / relation / motif 有支撑。\n\n"
        "## reported_spans\n\n"
        "- 待人工补写：列出黛玉可合理被告知的段落，并标注上升边界。\n\n"
        "## forbidden_spans\n\n"
        "- 待人工补写：列出读者知道但黛玉生前不能当成直接记忆的段落。\n\n"
        "## 关键证据摘录\n\n"
        "- 待人工补写：选择真正支撑上层记忆的高价值原文句段，而不是整章摘要。\n\n"
        "## 原文长度提示\n\n"
        f"- 当前源文本字符数：`{len(raw_text)}`\n"
    )


def main() -> None:
    READING_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    chapter_files = sorted(HONGLou_DIR.glob("[0-1][0-9][0-9].md"))
    if len(chapter_files) != 120:
        raise SystemExit(f"Expected 120 chapter files, found {len(chapter_files)}")

    for source_path in chapter_files:
        chapter_id = source_path.stem
        raw_text = source_path.read_text(encoding="utf-8")
        (READING_DIR / f"{chapter_id}.md").write_text(
            build_reading(chapter_id, source_path, raw_text), encoding="utf-8"
        )
        (EVIDENCE_DIR / f"{chapter_id}.md").write_text(
            build_evidence(chapter_id, source_path, raw_text), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
