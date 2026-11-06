#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合并分卷审校稿为全书 JSON（并校验结构）。

用法:
    python merge_parts.py _work/proof/out -o _work/proof/merged.json --src _work/norm/chapters.json

目录结构约定:
    _work/proof/out/p0/ch001.json   # 主编黄金范例
    _work/proof/out/p1/ch003.json … # 各分卷，文件名 chNNN.json
每份 JSON: {"num":1,"title":"回国","display":"第1章","paragraphs":["…"]}
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

try:
    from _common import STRUCT_FIELDS
except ImportError:  # 直接拷走单文件运行时兜底
    STRUCT_FIELDS = ("part", "figures", "note")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--src", default="", help="源 chapters.json，用于校验段数/标题/顺序")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.out_dir, "*", "ch*.json")))
    if not files:
        print("ERROR: 没找到分卷稿")
        return 1

    chapters = {}
    for path in files:
        with open(path, encoding="utf-8") as f:
            ch = json.load(f)
        num = ch["num"]
        if num in chapters:
            print(f"ERROR: 第 {num} 章重复（{path}）")
            return 1
        chapters[num] = ch

    src = {}
    if args.src:
        with open(args.src, encoding="utf-8") as f:
            src_list = json.load(f)
        if isinstance(src_list, dict):
            src_list = src_list["chapters"]
        src = {c["num"]: c for c in src_list}
        missing = sorted(set(src) - set(chapters))
        extra = sorted(set(chapters) - set(src))
        if missing:
            print("ERROR: 缺章", missing)
            return 1
        if extra:
            print("ERROR: 多章", extra)
            return 1

    out = []
    changed = 0
    order = list(src) if src else sorted(chapters)
    for num in order:
        ch = chapters[num]
        paras = ch["paragraphs"]
        for i, p in enumerate(paras, 1):
            if "\n" in p:
                print(f"ERROR: 第 {num} 章第 {i} 段含换行")
                return 1
            if not p.strip():
                print(f"ERROR: 第 {num} 章第 {i} 段为空")
                return 1
        if num in src:
            if len(paras) != len(src[num]["paragraphs"]):
                print(f"ERROR: 第 {num} 章段数 {len(src[num]['paragraphs'])} -> {len(paras)}")
                return 1
            if src[num].get("title") and ch.get("title") != src[num]["title"]:
                print(f"ERROR: 第 {num} 章标题被改动（标题不在审校范围内）: "
                      f"{src[num]['title']!r} -> {ch.get('title')!r}")
                return 1
            changed += sum(1 for a, b in zip(paras, src[num]["paragraphs"]) if a != b)
        ch.setdefault("display", src.get(num, {}).get("display", ""))
        # 分卷稿通常只带 num/title/display/paragraphs；结构化字段从源稿继承，
        # 否则合并后会丢部/卷、插图、作者有话要说。
        for key in STRUCT_FIELDS:
            if key in src.get(num, {}) and key not in ch:
                ch[key] = src[num][key]
            elif key in src.get(num, {}) and key in ch and ch[key] != src[num][key]:
                print(f"WARN: 第 {num} 章的 {key} 与源稿不同（结构字段不应被审校改动）")
        ch["chars"] = len(re.sub(r"\s", "", "".join(paras)))
        out.append(ch)

    total = sum(c["chars"] for c in out)
    n_para = sum(len(c["paragraphs"]) for c in out)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"OK: {len(out)} 章 / {n_para} 段 / {total} 字 / 改动 {changed} 段")
    return 0


if __name__ == "__main__":
    sys.exit(main())
