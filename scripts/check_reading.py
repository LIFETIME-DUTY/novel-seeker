#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 reading_brief.md 是不是真的读了（切卷前的闸门）。

规则：
- 九节里，除「留白清单」外，任何一节还空着（只剩模板占位 `{…}`）→ FAIL，不许开改。
- 「留白清单」允许写"本书几乎没有明显留白"，但**必须写明判断依据**——因为
  留白不是每本书都有，可"没想过"和"想过、结论是没有"是两件事。留空 → WARN。

用法:
    python scripts/check_reading.py _work/reading/reading_brief.md
退出码：0 = 可以开改（可能有 WARN）；1 = 还不能开改。
"""
from __future__ import annotations

import argparse
import re
import sys

# 节标题里的关键词 → 规范名
SECTIONS = [
    ("一句话", "1. 一句话"),
    ("主线", "2. 主线"),
    ("人物", "3. 人物表"),
    ("叙述方式", "4. 叙述方式"),
    ("语言与语气", "5. 语言与语气"),
    ("意象", "6. 反复意象/母题"),
    ("留白", "7. 留白清单"),
    ("红线", "8. 本作审校红线"),
    ("自检", "9. 三句自检"),
]
BLANK_HINT = re.compile(r"^\s*\{.*\}\s*$")
NO_BLANK_HINTS = ("没有", "无明", "几乎没", "基本没", "不构成留白", "不涉及留白", "无明显")


def split_sections(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    cur = None
    buf: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if cur is not None:
                out[cur] = "\n".join(buf).strip()
            cur = line[3:].strip()
            buf = []
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        out[cur] = "\n".join(buf).strip()
    return out


def pick(sections: dict[str, str], keyword: str) -> str:
    for title, body in sections.items():
        if keyword in title:
            return body
    return ""


def is_filled(body: str) -> bool:
    body = re.sub(r"^[>\-\*\s]+", "", body or "", flags=re.M)
    body = body.strip()
    if not body:
        return False
    if BLANK_HINT.match(body):
        return False
    # 只剩表格分隔行 / 表头也算空
    lines = [ln for ln in body.splitlines() if ln.strip() and not set(ln.strip()) <= set("|-: ")]
    if len(lines) <= 1 and lines and lines[0].startswith("|"):
        return False
    return len(re.sub(r"\s", "", body)) >= 5


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("brief")
    args = ap.parse_args()

    try:
        with open(args.brief, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        print(f"FAIL: 找不到 {args.brief}——先跑 read_prep.py 再填")
        return 1

    sections = split_sections(text)
    if not sections:
        print("FAIL: 文件里没有可识别的小节（应保留模板里的 `## 1. 一句话` 这类标题）")
        return 1

    missing, warn = [], []
    for keyword, label in SECTIONS:
        body = pick(sections, keyword)
        if not is_filled(body):
            if keyword == "留白":
                warn.append(
                    f"{label}：空着。留白不是每本书都有，但**必须想过**——"
                    "若确实没有，请写一句「本书几乎没有明显留白」+ 依据（例如：叙述直给、结尾闭合）；"
                    "若有，请写清哪些地方作者选择不写透。"
                )
            else:
                missing.append(label)

    if missing:
        print("FAIL: 以下小节还没填（只剩模板占位）：")
        for m in missing:
            print("  -", m)
        print("\n填完再切卷。读不懂的节，回去读，不要开始改。")
        return 1

    blank_body = pick(sections, "留白")
    declared_none = is_filled(blank_body) and any(k in blank_body for k in NO_BLANK_HINTS)

    print("PASS: reading_brief 九节已填，可以开改。")
    if declared_none:
        print("   · 留白清单：已声明「本书几乎没有明显留白」，接受（判断依据要写在那一条里）。")
    if warn:
        print("\nWARN（不阻塞，但请补）：")
        for w in warn:
            print("  -", w)
        print("\n提示：判断留白的方法是问「这段作者为什么不多写一句？」"
              "——答案若是「想留想象空间 / 故意不说破 / 让读者自己补」，那就是留白，别去补。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
