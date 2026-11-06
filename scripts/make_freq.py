#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统计常用字基准，供「伪文本」判真使用。

用法:
    python make_freq.py 一本正常的书.txt -o freq_common.json [--top 1500]

原理：正常中文小说里，top-1500 汉字能覆盖 90%+ 的字；反爬塞回来的随机汉字串覆盖率通常 <0.4。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("book")
    ap.add_argument("-o", "--out", default="freq_common.json")
    ap.add_argument("--top", type=int, default=1500)
    args = ap.parse_args()

    with open(args.book, encoding="utf-8", errors="ignore") as f:
        text = f.read()
    chars = re.findall(r"[\u4e00-\u9fff]", text)
    counter = Counter(chars)
    top = [c for c, _ in counter.most_common(args.top)]
    payload = {
        "source": args.book,
        "total_cjk": len(chars),
        "distinct": len(counter),
        "top": top,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    coverage = sum(counter[c] for c in top) / max(1, len(chars))
    print(f"常用字基准: {len(top)} 字, 覆盖率 {coverage:.3f} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
