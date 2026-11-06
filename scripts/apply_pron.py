#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按白名单apply人称指代修订：只允许「代词 → 人名」或补「人名 + 说」，其余一律拒绝。

用法:
    python apply_pron.py _work/norm/chapters.json _work/pron_edits.json \
        -o _work/norm/chapters2.json --report _work/pron_applied.md \
        --names 甲 乙 丙

edits.json 形如:
[
  {"num": 19, "para": 2,
   "before": "甲冲乙摇摇头，她也没犹豫……",
   "after":  "甲冲乙摇摇头，丙也没犹豫……",
   "why": "第二个她指在场的丙"}
]

为什么要这么严：改指代最容易改错。脚本强制 before 与正文逐字一致，并把差异限制在
「代词↔人名」与「插入人名/人名+说」两类；不合规的条目列进 PROBLEMS，不写入。
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys

PRONOUNS = {"她", "他", "她们", "他们"}
SPEECH = {"说", "问", "答", "道", "曰", "喊", "叫", "笑", "叹"}
CJK = "\u3400-\u4dbf\u4e00-\u9fff"


def load(path: str):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("chapters") or []
    return data


def is_cjk(s: str) -> bool:
    return bool(s) and all(re.fullmatch(f"[{CJK}]", ch) for ch in s)


def check_edit(before: str, after: str, names: set[str]) -> tuple[bool, str]:
    """差异只允许两类：代词→人名；插入 人名(+说问答道)。"""
    sm = difflib.SequenceMatcher(None, before, after, autojunk=False)
    ops = [op for op in sm.get_opcodes() if op[0] != "equal"]
    if not ops:
        return False, "没有差异"
    for tag, i1, i2, j1, j2 in ops:
        old, new = before[i1:i2], after[j1:j2]
        if tag == "replace":
            if old not in PRONOUNS:
                return False, f"替换了非代词「{old}」"
            if new not in names and not (new in {"他们", "她们"} and old in {"他们", "她们"}):
                return False, f"替换目标不是名单里的人名「{new}」"
        elif tag == "insert":
            core = new.rstrip("：:，, 、")
            if core and core[-1] in SPEECH:
                core = core[:-1]
            # 允许插入完整人名，也允许插入「人名的一部分」（如 他→他甲 时差异里只有「甲」）
            ok = core in names or any(core and core in nm and nm in after for nm in names)
            if not ok:
                return False, f"插入了非人名内容「{new}」"
        else:  # delete
            return False, f"删除了内容「{old}」"
    return True, "ok"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("chapters")
    ap.add_argument("edits")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--report", default="")
    ap.add_argument("--names", nargs="+", required=True, help="允许出现的人名白名单")
    args = ap.parse_args()

    chapters = load(args.chapters)
    with open(args.edits, encoding="utf-8") as f:
        edits = json.load(f)
    if isinstance(edits, dict):
        edits = edits.get("edits") or []

    names = {x for a in args.names for x in re.split(r"[,，、\s]+", a) if x}
    by_num = {c.get("num"): c for c in chapters}

    applied, problems = [], []
    for e in edits:
        num, para = e.get("num"), int(e.get("para") or 0)
        ch = by_num.get(num)
        if not ch:
            problems.append((num, para, "章节不存在", e.get("why", "")))
            continue
        paras = ch["paragraphs"]
        if not (1 <= para <= len(paras)):
            problems.append((num, para, "段号越界", e.get("why", "")))
            continue
        cur = paras[para - 1]
        before = (e.get("before") or "").strip()
        after = (e.get("after") or "").strip()
        if cur != before:
            problems.append((num, para, "before 与当前正文不一致", e.get("why", "")))
            continue
        ok, why = check_edit(before, after, names)
        if not ok:
            problems.append((num, para, why, e.get("why", "")))
            continue
        paras[para - 1] = after
        applied.append((num, para, before, after, e.get("why", "")))

    # 有拒绝项时不要覆盖正式产物：写到 .partial 并显著标注，
    # 否则会出现“一半改动已落地、但调用方以为失败”的错觉。
    out_path = args.out if not problems else args.out + ".partial"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(chapters, f, ensure_ascii=False, indent=1)

    lines = ["# 人称指代修订记录", "",
             f"- 提交 {len(edits)} 条；应用 {len(applied)} 条；拒绝 {len(problems)} 条", ""]
    if applied:
        lines += ["| 章#段 | 原文 | 改后 | 理由 |", "|---|---|---|---|"]
        for num, para, b, a, why in applied:
            lines.append(f"| {num}#{para} | {b[:60]} | {a[:60]} | {why} |")
    if problems:
        lines += ["", "## 被拒绝（需人工处理）", "", "| 章#段 | 原因 | 备注 |", "|---|---|---|"]
        for num, para, why, note in problems:
            lines.append(f"| {num}#{para} | {why} | {note} |")
    text = "\n".join(lines) + "\n"
    print(text)
    if problems:
        print(f"!! 有 {len(problems)} 条被拒绝：未写入 {args.out}，结果另存为 {out_path}；"
              f"修正后重跑，或人工应用被拒项", file=sys.stderr)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(text)
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
