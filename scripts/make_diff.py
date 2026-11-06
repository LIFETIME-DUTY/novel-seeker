#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审校 diff 归档：把"改了哪一段、改成什么、为什么算这一类"落成一份可核查的报告。

用法:
    python make_diff.py _work/norm/chapters.json _work/proof/merged.json \
        -o _work/proof/diff.md [--json _work/proof/diff.json]

为什么必须有：交付时说"只改了标点"是空的，这份文件是唯一证据；出争议时能逐条回看。
分类是启发式的，只用于快速扫读，判不准的会落在「其他」里。
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys

CJK = "\u3400-\u4dbf\u4e00-\u9fff"
PUNCT = set("，。、；：？！…—“”‘’（）《》〈〉「」『』【】·～-—＊　")
PRON = set("她他她们他们")


def load(path: str):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("chapters") or []
    return data


def only_punct_diff(a: str, b: str) -> bool:
    strip = lambda s: "".join(c for c in s if c not in PUNCT)
    return strip(a) == strip(b)


def is_pron_change(a: str, b: str) -> bool:
    """只有 她/他/她们/他们 被换成人名，或补了人名。"""
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    ops = [op for op in sm.get_opcodes() if op[0] != "equal"]
    if not ops:
        return False
    for tag, i1, i2, j1, j2 in ops:
        old, new = a[i1:i2], b[j1:j2]
        if tag == "replace" and old in PRON:
            continue
        if tag == "insert" and new and all(re.fullmatch(f"[{CJK}]", ch) for ch in new):
            continue
        return False
    return True


def classify(a: str, b: str) -> str:
    if only_punct_diff(a, b):
        return "标点"
    if is_pron_change(a, b):
        return "指代"
    if not re.search(r"[，。、；：？！…]", a) and re.search(r"[，。、；：？！…]", b):
        return "断句"
    sim = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
    if sim >= 0.82 and abs(len(a) - len(b)) <= 6:
        return "字词"
    return "其他"


def inline_diff(a: str, b: str) -> str:
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out.append(a[i1:i2])
        elif tag == "replace":
            out.append(f"[-{a[i1:i2]}-][+{b[j1:j2]}+]")
        elif tag == "delete":
            out.append(f"[-{a[i1:i2]}-]")
        elif tag == "insert":
            out.append(f"[+{b[j1:j2]}+]")
    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("before_json")
    ap.add_argument("after_json")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--json", default="")
    ap.add_argument("--max-per-chapter", type=int, default=40, help="每章最多列多少条（其余只统计）")
    args = ap.parse_args()

    before = {c.get("num"): c for c in load(args.before_json)}
    after = {c.get("num"): c for c in load(args.after_json)}
    if set(before) != set(after):
        print("ERROR: 两稿章节集合不同", file=sys.stderr)
        return 1

    records, per_ch, totals = [], {}, {}
    total_paras = 0
    for num in sorted(before):
        bp = before[num].get("paragraphs") or []
        ap_ = after[num].get("paragraphs") or []
        total_paras += len(bp)
        if len(bp) != len(ap_):
            print(f"ERROR: 第 {num} 章段数不同 {len(bp)} → {len(ap_)}", file=sys.stderr)
            return 1
        n = 0
        for i, (a, b) in enumerate(zip(bp, ap_), 1):
            if a == b:
                continue
            n += 1
            kind = classify(a, b)
            totals[kind] = totals.get(kind, 0) + 1
            records.append({"num": num, "para": i, "kind": kind,
                            "before": a, "after": b, "diff": inline_diff(a, b)})
        if n:
            per_ch[num] = (n, len(bp))

    changed = len(records)
    lines = ["# 审校 diff（逐段）", "",
             f"- 原稿：`{args.before_json}`　审校稿：`{args.after_json}`",
             f"- 段落总数 {total_paras}；改动 {changed} 段（{changed / max(1, total_paras) * 100:.1f}%）",
             f"- 类型分布：" + "、".join(f"{k} {v}" for k, v in sorted(totals.items(), key=lambda x: -x[1])),
             "",
             "> `[-…-]` = 删掉的字，`[+…+]` = 加上的字。分类是启发式的，只用于扫读。", ""]
    if per_ch:
        lines += ["| 章 | 改动/总段 |", "|---|---|"]
        for num, (n, t) in sorted(per_ch.items()):
            lines.append(f"| 第 {num} 章 | {n}/{t}（{n / t * 100:.0f}%） |")
        lines.append("")

    cur = None
    shown = 0
    skipped = 0
    for r in records:
        if cur != r["num"]:
            if skipped:
                lines.append(f"- …（另有 {skipped} 条，见 diff.json）")
                skipped = 0
            cur = r["num"]
            shown = 0
            lines += [f"## 第 {cur} 章", ""]
        if shown >= args.max_per_chapter:
            skipped += 1
            continue
        shown += 1
        lines.append(f"- **{r['num']}#{r['para']}** ［{r['kind']}］{r['diff']}")
    if skipped:
        lines.append(f"- …（另有 {skipped} 条，见 diff.json）")
    text = "\n".join(lines) + "\n"
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=1)
    print(f"OK: {changed} 段改动 / {total_paras} 段 → {args.out}")
    print("类型:", dict(sorted(totals.items(), key=lambda x: -x[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
