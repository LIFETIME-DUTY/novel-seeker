#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分卷审校的机器校验：挡「改了原意」这类事故。

用法:
    python check_part.py _work/proof/out/p1 3-15 [--names 人名 …] [--src _work/norm/chapters.json]

规则（任一 ERROR 即 FAIL）:
  - 章数、段数、段内换行、空段
  - 数字出现次数、英文 token、专名计数不变
  - 汉字数骤减 >15%
  - 相似度 <0.55（整段重写）ERROR；<0.8 HEAVY（需人工复核）
WARN: 单段长度比 <0.8 或 >1.3；整章 0 改动或改动 >75%
"""
from __future__ import annotations

import argparse
import difflib
import glob
import json
import os
import re
import sys
from collections import Counter

try:
    from _common import STRUCT_FIELDS
except ImportError:  # 直接拷走单文件运行时兜底
    STRUCT_FIELDS = ("part", "figures", "note")

DEFAULT_NAMES: list[str] = []  # 传 --names 人名A 人名B …；空则不检查人名计数


def han(s: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", s))


def toks(s: str):
    digits = re.findall(r"\d+", s)
    latin = re.findall(r"[A-Za-z]+", s)
    return Counter(digits), Counter(latin)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("part_dir")
    ap.add_argument("range", help="如 3-15")
    ap.add_argument("--src", default="", help="源 chapters.json（给了就逐段比对）")
    ap.add_argument("--names", nargs="*", default=DEFAULT_NAMES)
    args = ap.parse_args()

    lo, hi = [int(x) for x in re.split(r"[-–—~]", args.range.strip())]
    corpus = {}
    if args.src:
        with open(args.src, encoding="utf-8") as f:
            src = json.load(f)
        if isinstance(src, dict):
            src = src["chapters"]
        for ch in src:
            corpus[ch["num"]] = ch

    # 人名参数可能被写成 "甲,乙" / "甲、乙"
    names: list[str] = []
    for raw in args.names:
        names.extend(x for x in re.split(r"[,，、;；\s]+", raw) if x)

    errors, heavy, warns = [], [], []
    files = sorted(glob.glob(os.path.join(args.part_dir, "ch*.json")))
    if not files:
        print(f"ERROR: {args.part_dir} 下没有 ch*.json")
        return 1

    present = set()
    for path in files:
        with open(path, encoding="utf-8") as f:
            present.add(json.load(f)["num"])
    expected = {n for n in corpus if lo <= n <= hi} if corpus else {n for n in present if lo <= n <= hi}
    missing = sorted(expected - present)
    if missing:
        errors.append(f"分卷缺章: {missing[:20]}{' …' if len(missing) > 20 else ''}")

    changed_total = 0
    paras_total = 0
    for path in files:
        with open(path, encoding="utf-8") as f:
            ch = json.load(f)
        num = ch["num"]
        if not (lo <= num <= hi):
            errors.append(f"{os.path.basename(path)} num={num} 不在分卷范围 {lo}-{hi}")
        for i, p in enumerate(ch["paragraphs"], 1):
            if "\n" in p:
                errors.append(f"ch{num}#{i} 段内含换行")
            if not p.strip():
                errors.append(f"ch{num}#{i} 空段")
            paras_total += 1
            if num in corpus:
                orig = corpus[num]["paragraphs"][i - 1] if i <= len(corpus[num]["paragraphs"]) else ""
                if p != orig:
                    changed_total += 1
                    ratio = len(p) / max(1, len(orig))
                    hb, ha = han(orig), han(p)
                    sim = difflib.SequenceMatcher(None, orig, p).ratio()
                    if ha < hb * 0.85:
                        errors.append(f"ch{num}#{i} 汉字骤减 {hb}->{ha}")
                    if sim < 0.55:
                        errors.append(f"ch{num}#{i} 相似度 {sim:.2f}（疑似整段重写）")
                    elif sim < 0.8:
                        heavy.append(f"ch{num}#{i} 相似度 {sim:.2f}")
                    if ratio < 0.8 or ratio > 1.3:
                        warns.append(f"ch{num}#{i} 长度比 {ratio:.2f}（可能漏字/增写）")
                    d0, l0 = toks(orig)
                    d1, l1 = toks(p)
                    if d0 != d1:
                        errors.append(f"ch{num}#{i} 数字被改动")
                    if l0 != l1:
                        errors.append(f"ch{num}#{i} 英文 token 被改动")
                    for n in names:
                        if orig.count(n) != p.count(n):
                            errors.append(f"ch{num}#{i} 人名「{n}」计数变化")
        if num in corpus:
            if len(ch["paragraphs"]) != len(corpus[num]["paragraphs"]):
                errors.append(f"ch{num} 段数 {len(corpus[num]['paragraphs'])}->{len(ch['paragraphs'])}")
            # 结构字段（部/卷、插图、作者有话要说）不允许被审校改动；
            # 分卷稿里没写这些键是正常的（合并时会从源稿继承）。
            for key in STRUCT_FIELDS:
                if key in corpus[num] and key in ch and ch[key] != corpus[num][key]:
                    errors.append(f"ch{num} 的 {key} 被改动（结构字段不应由审校触碰）")

    print(f"章数: {len(files)}  段落: {paras_total}  改动: {changed_total}")
    for x in errors:
        print("ERROR:", x)
    for x in heavy:
        print("HEAVY:", x)
    for x in warns:
        print("WARN:", x)
    ok = not errors and not heavy
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
