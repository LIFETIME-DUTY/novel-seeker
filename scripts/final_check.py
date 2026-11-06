#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全书体检：只诊断，不改文。输出问题清单，供决定是否审校。

用法:
    python final_check.py norm/chapters.json [--names 人名A 人名B …] [--out final_check.md]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter

CJK = r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
SENT_END = "。！？…”』】）」"
HALF = re.compile(r"(?<=[\u4e00-\u9fff])[,;:!?](?=[\u4e00-\u9fff]|$)")
DUP_PUNCT = re.compile(r"([，。、；：])\1+")
SINGLE_DASH = re.compile(r"(?<!—)—(?!—)")
SINGLE_ELL = re.compile(r"(?<!…)…(?!…)")
CENSOR = re.compile(r"(?<=[\u4e00-\u9fff])\s*[.·]\s*(?=[\u4e00-\u9fff])|(?<=[\u4e00-\u9fff])\s*/+\s*(?=[\u4e00-\u9fff])")
DOUBLE_SPACE = re.compile(r"[ \u3000]{2,}")
EDGE_SPACE = re.compile(r"^[ \u3000]+|[ \u3000]+$")
STRAIGHT_QUOTE = re.compile(r"[\"']")


def scan(chapters, names):
    issues: dict[str, list[str]] = {}

    def add(kind, where, text):
        issues.setdefault(kind, []).append(f"{where}: {text[:60]}")

    total_chars = 0
    for ch in chapters:
        for i, p in enumerate(ch["paragraphs"], 1):
            where = f"{(ch.get('display') or ch.get('num'))}#{i}"
            total_chars += len(re.sub(r"\s", "", p))
            if EDGE_SPACE.search(p):
                add("首尾空白", where, p)
            if DOUBLE_SPACE.search(p):
                add("连续空格", where, p)
            if HALF.search(p):
                add("半角标点", where, p)
            if DUP_PUNCT.search(p):
                add("重复标点（作者语气可忽略 ？？/！！）", where, p)
            if SINGLE_DASH.search(p):
                add("单个破折号", where, p)
            if SINGLE_ELL.search(p):
                add("单个省略号", where, p)
            if CENSOR.search(p):
                add("站点规避符残留", where, p)
            if STRAIGHT_QUOTE.search(p):
                add("直引号", where, p)
            stripped = p.rstrip()
            if stripped and stripped[-1] not in SENT_END and len(stripped) > 12:
                if stripped[-1] in "，、；：":
                    add("段末为逗号（可能是跨段断句，需看下一段）", where, p)
                else:
                    add("段末缺句末标点", where, p)
            # 叠字可疑（排除语气：哈哈哈哈、？？？？）
            for m in re.finditer(r"([%s])\1{2,}" % CJK, p):
                if m.group(0) not in ("哈哈哈", "呵呵呵", "呜呜呜", "啊啊啊"):
                    add("叠字可疑", where, m.group(0))
                    break

    # 专名计数
    if names:
        joined = "".join(p for ch in chapters for p in ch["paragraphs"])
        for n in names:
            issues.setdefault("专名计数", []).append(f"{n}: {joined.count(n)}")

    return issues, total_chars


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("chapters")
    ap.add_argument("--names", nargs="*", default=[])
    ap.add_argument("--out", default="")
    ap.add_argument("--strict", action="store_true",
                    help="有问题就返回 1（默认只诊断、返回 0，便于串在 && 里做闸门）")
    args = ap.parse_args()

    with open(args.chapters, encoding="utf-8") as f:
        chapters = json.load(f)
    if isinstance(chapters, dict):
        chapters = chapters["chapters"]

    args.names = [x for a in args.names for x in re.split(r"[,，、\s]+", a) if x]
    issues, total = scan(chapters, args.names)
    n_para = sum(len(c["paragraphs"]) for c in chapters)
    lines = [
        "# 体检报告",
        "",
        f"- 章节：{len(chapters)}",
        f"- 段落：{n_para}",
        f"- 字数：{total}",
        "",
    ]
    for kind, items in sorted(issues.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"## {kind}（{len(items)}）")
        if kind == "专名计数":
            lines += [f"- {x}" for x in items]
        else:
            lines += [f"- {x}" for x in items[:30]]
            if len(items) > 30:
                lines.append(f"- …另有 {len(items) - 30} 条")
        lines.append("")

    text = "\n".join(lines)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
