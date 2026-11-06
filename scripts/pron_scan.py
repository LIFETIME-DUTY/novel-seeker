#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""人称指代扫描：只出候选清单，不改文。

中文小说最难机器判的是「她/他」到底指谁。这个脚本不知道剧情，只做三件事：
  1. 用你给的性别名单，找出"代词与在场人物性别冲突"的段落（高危）。
  2. 找出"段落以代词开头、且上一句刚提到另一个同性人物"的位置（中危）。
  3. 列出「他们/她们」与段内出现的人物性别不一致的位置。

输出按等级排序的 Markdown 表；每条给出上下文，人只决定「改不改」。

用法:
    python pron_scan.py _work/norm/chapters.json \
        --female 甲 乙 --male 丙 丁 -o _work/pron_scan.md

    # 只扫指定章节范围
    python pron_scan.py chapters.json --female 甲 --male 丙 --range 20-45
"""
from __future__ import annotations

import argparse
import json
import re
import sys

CJK = "\u3400-\u4dbf\u4e00-\u9fff"
PRON = re.compile(r"她们|他们|她|他")  # 长词优先，否则 她们 只会匹配到 她
SHE = "她"
HE = "他"


def load(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get("chapters") or []
    return data


def ctx(text: str, idx: int, width: int = 22) -> str:
    a = max(0, idx - width)
    b = min(len(text), idx + width)
    return ("…" if a else "") + text[a:b] + ("…" if b < len(text) else "")


def names_in(text: str, names: list[str]) -> list[str]:
    return [n for n in names if n and n in text]


def scan(chapters: list[dict], female: list[str], male: list[str], lo: int, hi: int):
    rows = []  # (level, num, para, kind, why, ctx)
    all_names = female + male
    for ch in chapters:
        num = ch.get("num")
        if lo and num < lo:
            continue
        if hi and num > hi:
            continue
        paras = ch.get("paragraphs") or []
        last_named = ""  # 上一段最后一个被提到的人名
        last_gender = ""
        for i, p in enumerate(paras, 1):
            fs = names_in(p, female)
            ms = names_in(p, male)
            pron = PRON.findall(p)
            # A. 性别冲突：段内有异性名、没有同性名，却用了同性代词
            if fs and not ms:
                for m in re.finditer(r"(?<!其)他(?!们)", p):
                    rows.append(("L3", num, i, "男性代词出现在只有女性人物的段",
                                 f"在场女性={fs}", ctx(p, m.start())))
            if ms and not fs:
                for m in re.finditer(r"她", p):
                    rows.append(("L3", num, i, "女性代词出现在只有男性人物的段",
                                 f"在场男性={ms}", ctx(p, m.start())))
            # B. 他们/她们 与在场性别不符
            for m in re.finditer(r"(他们|她们)", p):
                if m.group(1) == "他们" and fs and not ms:
                    rows.append(("L2", num, i, "「他们」但本段只有女性名", f"{fs}", ctx(p, m.start())))
                if m.group(1) == "她们" and ms and not fs:
                    rows.append(("L2", num, i, "「她们」但本段只有男性名", f"{ms}", ctx(p, m.start())))
            # C. 段首代词 + 上一段提到另一个同性人物
            stripped = p.lstrip()
            if stripped[:1] in (SHE, HE) and last_named:
                same = (stripped[0] == SHE and last_gender == "F") or (stripped[0] == HE and last_gender == "M")
                if same:
                    rows.append(("L2", num, i, f"段首「{stripped[0]}」，上一段最后提到 {last_named}",
                                 "确认指代是否切换", p[:60]))
            # C2. L1：段首就是代词（不论上段提到谁）——全书常见，只做批量提示
            if stripped[:1] in (SHE, HE):
                rows.append(("L1", num, i, f"段首「{stripped[0]}」",
                             f"上段末人名={last_named or '无'}", p[:50]))
            # D. 段内无人名却出现代词（承接型，只做提示不逐条轰炸）
            if pron and not fs and not ms:
                rows.append(("L4", num, i, "段内无任何人名却有代词", "仅提示，多为承接上文",
                             ctx(p, p.find(pron[0]))))
            # 更新"最后提到的人名"（取段内最后出现位置最靠后的一个）
            best = ""
            best_pos = -1
            for n in all_names:
                pos = p.rfind(n)
                if pos > best_pos:
                    best_pos, best = pos, n
            if best:
                last_named = best
                last_gender = "F" if best in female else "M"
        # 段落无命中时不保留状态
    order = {"L3": 0, "L2": 1, "L1": 2, "L4": 3}
    rows.sort(key=lambda r: (order.get(r[0], 9), r[1], r[2]))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("chapters")
    ap.add_argument("--female", nargs="*", default=[], help="女性人物名，空格或逗号分隔")
    ap.add_argument("--male", nargs="*", default=[], help="男性人物名，空格或逗号分隔")
    ap.add_argument("--range", default="", help="只扫这一段章节，如 20-45")
    ap.add_argument("-o", "--out", default="")
    args = ap.parse_args()

    if not args.female and not args.male:
        print("ERROR: 至少给 --female 或 --male（人名清单），否则无法判断指代", file=sys.stderr)
        return 2
    args.female = [x for a in args.female for x in re.split(r"[,，、\s]+", a) if x]
    args.male = [x for a in args.male for x in re.split(r"[,，、\s]+", a) if x]

    lo = hi = 0
    if args.range:
        a, _, b = args.range.partition("-")
        lo, hi = int(a), int(b or a)

    chapters = load(args.chapters)
    rows = scan(chapters, args.female, args.male, lo, hi)

    counts = {}
    for r in rows:
        counts[r[0]] = counts.get(r[0], 0) + 1
    lines = ["# 人称指代扫描（候选，不是结论）", ""]
    lines.append(f"- 章节文件：`{args.chapters}`　扫描章节：{len(chapters)}")
    lines.append(f"- 女性人物：{'、'.join(args.female) or '（未给）'}；男性人物：{'、'.join(args.male) or '（未给）'}")
    lines.append(f"- 候选：L3 {counts.get('L3',0)} / L2 {counts.get('L2',0)} / L1 {counts.get('L1',0)} / L4 {counts.get('L4',0)}")
    lines += ["", "> L3 = 性别冲突（优先看）；L2 = 可能需点名；L1 = 段首代词（量大，抽样看）；L4 = 段内无人名的承接代词（多数正常）。",
              "> 改法只有两种：`她/他 → 人名`，或补「人名 + 说」。其余一律不改。", ""]
    cur = None
    for level, num, i, kind, why, c in rows:
        if cur != level:
            cur = level
            titles = {"L3": "L3 · 性别冲突", "L2": "L2 · 建议核对",
                      "L1": "L1 · 段首代词（抽样）", "L4": "L4 · 承接提示"}
            lines += [f"## {titles.get(level, level)}", "",
                      "| 章#段 | 现象 | 依据 | 上下文 |", "|---|---|---|---|"]
        why = (why or "").replace("|", "／")
        c = (c or "").replace("|", "／")
        lines.append(f"| {num}#{i} | {kind} | {why} | {c} |")
    text = "\n".join(lines) + "\n"
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
