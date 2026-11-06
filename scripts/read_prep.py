#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审校前置：先读懂，再动笔。

审校出错，多半不是"标点知识不够"，而是"没读懂这句在说什么"——
把留白补成直白、把方言改成普通话、把作者刻意的重复当错字、把伏笔当病句。
所以这一步在切卷之前跑：产出一份"可核对的理解材料"，人（或模型）在此基础上
写 `reading_brief.md`，之后每一卷审校都必须带着它。

产出（-o 指定目录，默认 _work/reading）：
  outline.md        全书统计 + 每章字数/段数/首句一行表
  roster.md         候选人物名（按"X说/X问/X道…"启发式抽取）+ 代词计数
  style.md          风格抽样：最长/最短/对话/破折号/省略号各 2 段，带章#段号
  reading_brief.md  理解模板（待填写；不填就等于没读）

用法:
    python scripts/read_prep.py _work/norm/chapters.json -o _work/reading
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys

CJK = "\u3400-\u4dbf\u4e00-\u9fff"
NAME_HINT = re.compile(rf"([{CJK}]{{2,3}})(?=说|问|道|笑|答|喊|叫|想|看|点头|摇头|皱眉)")
PRON = re.compile(r"她们|他们|她|他")
DIALOG = re.compile(r"[\"“「『]")


def load(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get("chapters") or []
    return data


def chars_of(ch: dict) -> int:
    return sum(len(re.sub(r"\s", "", p)) for p in ch.get("paragraphs") or [])


def one_line(s: str, n: int = 28) -> str:
    s = (s or "").strip().replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"


def build_outline(chs: list[dict]) -> str:
    total_chars = sum(chars_of(c) for c in chs)
    total_paras = sum(len(c.get("paragraphs") or []) for c in chs)
    dlg = sum(1 for c in chs for p in (c.get("paragraphs") or []) if DIALOG.search(p))
    lines = [
        "# 全书概览（机器生成，供阅读时对照）",
        "",
        f"- 章数：{len(chs)}　总字数：{total_chars}　总段数：{total_paras}",
        f"- 含引号的段：{dlg}（{dlg / total_paras * 100:.1f}%）"
        f"　平均段长：{total_chars / max(1, total_paras):.1f} 字",
        f"- 首章：{one_line((chs[0].get('paragraphs') or [''])[0], 60)}" if chs else "",
        "",
        "| 章 | 标题 | 字数 | 段数 | 首句 |",
        "|---|---|---|---|---|",
    ]
    for c in chs:
        paras = c.get("paragraphs") or [""]
        lines.append(
            f"| {c.get('num')} | {c.get('title') or ''} | {chars_of(c)} | {len(paras)} | {one_line(paras[0])} |"
        )
    return "\n".join(x for x in lines if x is not None) + "\n"


def build_roster(chs: list[dict]) -> str:
    hits: dict[str, int] = {}
    chap_of: dict[str, set] = {}
    for c in chs:
        for p in c.get("paragraphs") or []:
            for m in NAME_HINT.finditer(p):
                n = m.group(1)
                hits[n] = hits.get(n, 0) + 1
                chap_of.setdefault(n, set()).add(c.get("num"))
    cand = sorted(((n, k) for n, k in hits.items() if k >= 3), key=lambda x: -x[1])[:60]
    pron = {k: 0 for k in ("她", "他", "她们", "他们")}
    for c in chs:
        for p in c.get("paragraphs") or []:
            for m in PRON.finditer(p):
                pron[m.group(0)] = pron.get(m.group(0), 0) + 1
    lines = [
        "# 候选人物名（按「X说/X问/X道…」启发式抽取，需人工确认）",
        "",
        "> 这张表只用来帮你回忆「谁在场」。**不要**把所有候选都当人物名——"
        "常见误抽：然而说、忽然问、于是道。以书中实际出场的为准，确认后写进 `reading_brief.md`。",
        "",
        "| 候选 | 出现次数 | 分布章 |",
        "|---|---|---|",
    ]
    for n, k in cand:
        cs = sorted(x for x in chap_of[n] if x is not None)
        span = f"{cs[0]}–{cs[-1]}（{len(cs)} 章）" if cs else ""
        lines.append(f"| {n} | {k} | {span} |")
    lines += ["", "## 代词计数（判断叙述人称用）", ""]
    lines += [f"- {k}：{v}" for k, v in pron.items()]
    return "\n".join(lines) + "\n"


def build_style(chs: list[dict]) -> str:
    buckets = {"最长段": [], "最短段": [], "含对话": [], "含破折号": [], "含省略号": []}
    rows = []
    for c in chs:
        for i, p in enumerate(c.get("paragraphs") or [], 1):
            rows.append((c.get("num"), i, p))
    by_len = sorted(rows, key=lambda r: len(r[2]))
    buckets["最短段"] = [r for r in by_len if len(r[2]) >= 8][:2]
    buckets["最长段"] = list(reversed(by_len))[:2]
    for key, rx in (("含对话", DIALOG), ("含破折号", re.compile("——")), ("含省略号", re.compile("……"))):
        picked = [r for r in rows if rx.search(r[2])]
        step = max(1, len(picked) // 2) if picked else 1
        buckets[key] = picked[::step][:2]
    lines = ["# 风格抽样（读这几段，记住作者的句子长相）", ""]
    for key, items in buckets.items():
        lines += [f"## {key}", ""]
        for num, i, p in items:
            lines += [f"- `{num}#{i}`：{p[:160]}", ""]
    return "\n".join(lines)


BRIEF_TEMPLATE = """# 理解备忘（reading_brief）

> **这是审校的前置条件，不是可选项。** 每一卷的分卷任务都必须带上这份备忘。
> 填不出来的项，就先回去读，不要开始切卷。

## 1. 一句话
{一句话说清这本书写的是什么：谁、想要什么、被什么挡住、最后怎样}

## 2. 主线（三到五段）
{按时间顺序，不写评价，只写发生了什么}

## 3. 人物
| 名字 | 性别 | 身份/关系 | 说话与行为特征 | 结局 |
|---|---|---|---|---|
|  |  |  |  |  |

## 4. 叙述方式
- 人称：{第一人称 / 第三人称限知 / 全知}
- 视角切换规则：{跟谁走？什么时候切？}
- 时间线：{顺叙 / 倒叙 / 双线，有无时间跳跃}

## 5. 语言与语气
- 句子长短倾向：{长句连绵 / 短句断行 / 混用}
- 对话习惯：{不加引号 / 用「」 / 用“”；是否常有独句成段}
- 用词偏好：{方言、口语、书面、行业词，各举例}
- 标点习惯：{大量省略号？破折号代替逗号？问号叠用？}
- **刻意重复**：{哪些重复是风格，不是错字，例如叠词、口头禅、同句反复}

## 6. 反复出现的意象 / 母题
{列出 3–5 个，并写明它们出现的章节，审校时不要把它们"修掉"}

## 7. 留白清单（最容易被我"补"坏的地方）
{作者明确不写透的地方：没说出口的话、跳过的场景、开放式结尾。逐条列出，注明章#段。
 留白不是每本书都有——若确实没有，写一句「本书几乎没有明显留白」+ 依据（叙述直给/结尾闭合/心理活动全交代），
 不要空着。判断法：问「这段作者为什么不多写一句？」答案若是"想留想象空间/故意不说破/让读者自己补"，那就是留白。}

## 8. 本作审校红线
{针对这本书的具体禁忌，例如：不改方言词、不补对话引号、不把倒叙理顺、不解释隐喻}

## 9. 读完之后的三句话自检
- 我能用一句话说清这本书在写什么吗？
- 我能说清每个代词最可能指谁吗？
- 我知道哪些"看起来像错"的地方其实是作者的选择吗？
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("chapters")
    ap.add_argument("-o", "--outdir", default="_work/reading")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的 reading_brief.md（会先备份 .bak）")
    args = ap.parse_args()

    chs = load(args.chapters)
    if not chs:
        print("ERROR: 没有章节", file=sys.stderr)
        return 2
    os.makedirs(args.outdir, exist_ok=True)
    files = {
        "outline.md": build_outline(chs),
        "roster.md": build_roster(chs),
        "style.md": build_style(chs),
        "reading_brief.md": BRIEF_TEMPLATE,
    }
    kept = []
    for name, text in files.items():
        path = os.path.join(args.outdir, name)
        # reading_brief 是人手填的：默认绝不覆盖，否则填了九节重跑一次就没了
        protect = name == "reading_brief.md"
        if os.path.exists(path) and not args.force:
            kept.append(name)
            continue
        if protect and os.path.exists(path) and args.force:
            shutil.copyfile(path, path + ".bak")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    print(f"已生成 {args.outdir}/")
    for name in files:
        if name in kept:
            print(f"  {name}（已存在，跳过；要重写加 --force）")
        else:
            print(f"  {name}")
    if "reading_brief.md" in kept:
        print("注意：reading_brief.md 已存在，保留你填过的内容（不会覆盖）。")
    print("\n下一步：亲自读一遍（至少读首章、末章、每卷首尾、以及 style.md 里抽的段落），"
          "把 reading_brief.md 填满；填不出就不要开始切卷。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
