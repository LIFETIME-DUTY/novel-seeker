#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""完整性核对：抓完的 chapters.json 到底全不全、有没有重号/断号/串章。

用法:
    python complete_check.py _work/raw/chapters.json
    python complete_check.py _work/raw/chapters.json --declared-chars 206862 --declared-chapters 58

检查项（任一 FAIL 都要回去补抓，不要带着疑点交付）:
  1. 章数 vs 站点声明（--declared-chapters，可给区间 "58" 或 "58-60"）
  2. 总字数 vs 站点声明（--declared-chars，容差默认 ±3%，只 WARN）
  3. 重号：display 或 num 重复（真实书里出现过"两个第37话"）
  4. 断号：正文的「第N章」序号不连续（WARN，番外/卷首语可能会跳）
  5. 重复标题：两章标题完全相同（WARN，多为抓串了）
  6. 空章 / 过短章（<100 字，WARN；<10 字，FAIL）
  7. 末三章标题打印出来（人工对照站点，最省事的"确实抓到底了"证据）

退出码: 0 = 没有 FAIL；1 = 有 FAIL。
"""
from __future__ import annotations

import argparse
import json
import re
import sys

CJK = r"\u3400-\u4dbf\u4e00-\u9fff"
NUM_RE = re.compile(r"^第\s*([0-9]+)\s*[章话回节]")


def load(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get("chapters") or []
    return data


def chars_of(ch: dict) -> int:
    return sum(len(re.sub(r"\s", "", p)) for p in ch.get("paragraphs") or [])


def parse_declared(text: str) -> tuple[int, int]:
    text = str(text).strip().replace(",", "")
    m = re.fullmatch(r"(\d+)\s*[-~]\s*(\d+)", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    v = int(text)
    return v, v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("chapters")
    ap.add_argument("--declared-chapters", default="", help="站点声明的章数，可写 58 或 58-60")
    ap.add_argument("--declared-chars", default="", help="站点声明的总字数，如 206862")
    ap.add_argument("--tolerance", type=float, default=0.03, help="字数容差（默认 ±3%%）")
    ap.add_argument("--allow-dup", action="store_true",
                    help="重号/断号只 WARN（默认 FAIL）；确认是原著编号重复时再用")
    args = ap.parse_args()

    chs = load(args.chapters)
    if not chs:
        print("FAIL: 没有章节")
        return 1

    fails: list[str] = []
    warns: list[str] = []
    total = sum(chars_of(c) for c in chs)

    print(f"章数: {len(chs)}")
    print(f"字数: {total}")
    print(f"末三章: " + " / ".join(
        f"{c.get('display') or c.get('num')} {c.get('title', '')}".strip() for c in chs[-3:]))

    # 1. 章数
    if args.declared_chapters:
        lo, hi = parse_declared(args.declared_chapters)
        if not (lo <= len(chs) <= hi):
            fails.append(f"章数 {len(chs)} 不在声明区间 {lo}-{hi}")
        else:
            print(f"章数核对: OK（声明 {lo}-{hi}）")

    # 2. 字数
    if args.declared_chars:
        target = int(str(args.declared_chars).replace(",", ""))
        delta = abs(total - target) / target
        msg = f"字数核对: 本站 {total} vs 声明 {target}（差 {total - target:+d}，{delta:.2%}）"
        if delta > args.tolerance:
            warns.append(msg + f"，超过容差 {args.tolerance:.0%}，查缺章/串章")
        else:
            print(msg)

    # 3. 重号
    seen: dict[str, int] = {}
    nums: dict[int, int] = {}
    for i, c in enumerate(chs, 1):
        d = (c.get("display") or "").strip()
        if d:
            seen[d] = seen.get(d, 0) + 1
        if isinstance(c.get("num"), int):
            nums[c["num"]] = nums.get(c["num"], 0) + 1
    for d, cnt in seen.items():
        if cnt > 1:
            msg = f"display 重复 {cnt} 次: {d}（用 build_book --renumber 重排）"
            (warns if args.allow_dup else fails).append(msg)
    for n, cnt in sorted(nums.items()):
        if cnt > 1:
            msg = f"num={n} 重复 {cnt} 次"
            (warns if args.allow_dup else fails).append(msg)

    # 4. 断号
    body_nums = [int(m.group(1)) for c in chs if (m := NUM_RE.match((c.get("display") or "").strip()))]
    if body_nums:
        lo, hi = min(body_nums), max(body_nums)
        missing = sorted(set(range(lo, hi + 1)) - set(body_nums))
        if missing:
            msg = f"正文序号不连续，缺: {missing[:20]}{' …' if len(missing) > 20 else ''}"
            (warns if args.allow_dup else fails).append(msg)

    # 5. 重复标题
    titles: dict[str, int] = {}
    for c in chs:
        t = (c.get("title") or "").strip()
        if t:
            titles[t] = titles.get(t, 0) + 1
    for t, cnt in titles.items():
        if cnt > 1:
            warns.append(f"标题重复 {cnt} 次: {t}")

    # 6. 空章/过短章
    for i, c in enumerate(chs, 1):
        n = chars_of(c)
        name = f"{c.get('display') or c.get('num')} {c.get('title', '')}".strip()
        if n < 10 and not c.get("note"):
            fails.append(f"第 {i} 章几乎没有正文（{n} 字）: {name}")
        elif n < 100:
            warns.append(f"第 {i} 章偏短（{n} 字）: {name}")

    for w in warns:
        print(f"WARN: {w}")
    for f in fails:
        print(f"FAIL: {f}")
    print("RESULT: " + ("FAIL" if fails else "PASS"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
