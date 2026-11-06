#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""确定性排版规范化：只做可枚举、可回归的清理，不做任何改写。

用法:
    python normalize.py raw/chapters.json -o norm/chapters.json [--report report.txt] [--strict]

设计原则（重要）：
  * 只还原**明确的**站点规避写法（白名单整词 + 章节编号里插点），不做"凡汉字之间的点/斜杠都删"。
  * 其它「汉字.汉字」「汉字/汉字」「汉字·汉字」一律**不动**，只列进候选清单交模型/人工判断。
  * 段末标点不删（「」。」「……。」都是作者写法），只收敛重复标点。
  * 插图路径保持原样（相对路径相对「源 JSON 所在目录」），由 build_book 负责重定基。

输入/输出都是 chapters 列表：
    [{"num":1,"title":"…","display":"第1章","paragraphs":["…"]}, …]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata

CJK = r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
CJK_RE = re.compile(f"[{CJK}]")
ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff\u00ad"), None)

# ---- 站点规避写法：只认这些完整词（字与字之间允许夹 . ． · / ／ 和空白） ----
# 例：傻.逼 / 傻//逼 / 做 爱 / 高／潮
SEP = r"[\s.．·/／]*"
SENSITIVE_WORDS = [
    ("傻", "逼"), ("做", "爱"), ("鸡", "巴"), ("屌", "丝"), ("逗", "逼"),
    ("他", "妈"), ("你", "妈"), ("妈", "的"), ("操", "你"), ("日", "你"),
    ("嫖", "娼"), ("卖", "淫"), ("吸", "毒"), ("贩", "毒"), ("革", "命"),
    ("下", "身"), ("肉", "体"), ("情", "欲"), ("乱", "性"), ("高", "潮"),
    ("荡", "妇"), ("赤", "裸"), ("色", "情"), ("强", "奸"), ("轮", "奸"),
    ("自", "慰"), ("阴", "道"), ("阴", "茎"), ("乳", "房"), ("骚", "货"),
    ("婊", "子"), ("贱", "人"), ("淫", "荡"), ("炮", "友"), ("约", "炮"),
]
SENSITIVE_RES = [
    (re.compile(a + SEP + b), a + b) for a, b in SENSITIVE_WORDS
]
# 反向的保护规则：像「他/她」「和/或」「玛丽·雪莱」这类并列/外文名，绝不删分隔符
PROTECTED_SLASH = re.compile(r"(?<=[\u4e00-\u9fff])/+(?=[\u4e00-\u9fff])")

# ---- 章节编号里插点：第一.章 / 第1.章 / 第 12 ．章 ----
CN = "0-9〇零一二三四五六七八九十百千两"
CHAPTER_DOT_RES = [
    (re.compile(rf"第\s*([{CN}]+)\s*[.．·]\s*([{CN}]+)\s*([章话回节])"), r"第\1\2\3"),
    (re.compile(rf"第\s*([{CN}]+)\s*[.．·]\s*([章话回节])"), r"第\1\2"),
]

# 候选（不自动处理，交模型判断）：汉字之间的点/斜杠/间隔号
CANDIDATE_RES = [
    re.compile(f"(?<=[{CJK}])[.．·](?=[{CJK}])"),
    re.compile(f"(?<=[{CJK}])[/／](?=[{CJK}])"),
]


def fix_straight_quotes(s: str) -> str:
    """直引号 → 中文引号：只有当整段含汉字、且引号成对时才动（英文引文不动）。"""
    if s.count('"') % 2 or not CJK_RE.search(s):
        return s
    out, opening = [], True
    for ch in s:
        if ch == '"':
            out.append("“" if opening else "”")
            opening = not opening
        else:
            out.append(ch)
    return "".join(out)


def denoise(text: str) -> str:
    """只做安全的清理：零宽字符、NBSP、重复省略号/破折号、半角标点邻近汉字。"""
    s = text.translate(ZERO_WIDTH)
    s = unicodedata.normalize("NFC", s)
    s = s.replace("\u00a0", " ")
    s = s.replace("\u3000\u3000", "\u3000")
    s = s.strip()

    s = fix_straight_quotes(s)

    # 省略号 / 破折号统一
    s = s.replace("….", "……")
    s = s.replace("…．", "……")
    s = re.sub(r"…{2,}", "……", s)
    s = re.sub(r"\.{3,}", "……", s)
    s = re.sub(r"—{3,}", "——", s)
    s = re.sub(r"--+", "——", s)

    # 半角标点 → 全角（仅紧邻汉字时），英文句子内部不动
    s = re.sub(f"(?<=[{CJK}])\\s*,\\s*", "，", s)
    s = re.sub(f"\\s*,\\s*(?=[{CJK}])", "，", s)
    s = re.sub(f"(?<=[{CJK}])\\s*;\\s*", "；", s)
    s = re.sub(f"\\s*;\\s*(?=[{CJK}])", "；", s)
    s = re.sub(f"(?<=[{CJK}])\\s*:\\s*", "：", s)
    s = re.sub(f"\\s*:\\s*(?=[{CJK}])", "：", s)
    s = re.sub(f"(?<=[{CJK}])\\s*\\?\\s*", "？", s)
    s = re.sub(f"\\s*\\?\\s*(?=[{CJK}])", "？", s)
    s = re.sub(f"(?<=[{CJK}])\\s*!\\s*", "！", s)
    s = re.sub(f"\\s*!\\s*(?=[{CJK}])", "！", s)
    s = re.sub(f"([{CJK}])\\.(?!\\d)", r"\1。", s)
    s = re.sub(f"\\s*\\.\\s*(?=[{CJK}])", "。", s)

    # 中文之间的多余空格 / 标点两侧空格
    s = re.sub(f"(?<=[{CJK}])\\s+(?=[{CJK}])", "", s)
    s = re.sub(r"[ \t]+(?=[，。、！？；：」』】）》])", "", s)
    s = re.sub(r"(?<=[「『【《（])[ \t]+", "", s)

    # 只收敛重复标点（？？？ ！！！！ 是作者语气，保留）
    s = re.sub(r"。{2,}", "。", s)
    s = re.sub(r"，{2,}", "，", s)

    return s.strip()


def restore_sensitive(s: str) -> str:
    """按白名单还原站点规避写法；不碰其它分隔符。"""
    for pat, rep in SENSITIVE_RES:
        s = pat.sub(rep, s)
    for pat, rep in CHAPTER_DOT_RES:
        s = pat.sub(rep, s)
    return s


def find_candidates(s: str) -> list[str]:
    out = []
    for pat in CANDIDATE_RES:
        for m in pat.finditer(s):
            a, b = max(0, m.start() - 4), min(len(s), m.end() + 4)
            out.append(s[a:b])
    return out


def normalize_paragraph(text: str) -> str:
    # 先按白名单还原（否则 傻.逼 里的点会先被当句点改成 。），再做安全清理
    s = restore_sensitive(text)
    s = denoise(s)
    return s


def normalize_chapters(chapters: list[dict]) -> tuple[list[dict], dict]:
    report = {"paragraphs": 0, "changed": 0, "samples": [], "candidates": []}
    out = []
    for ci, ch in enumerate(chapters, 1):
        new_paras = []
        for p in ch.get("paragraphs", []):
            q = normalize_paragraph(p)
            report["paragraphs"] += 1
            for cand in find_candidates(q):
                if len(report["candidates"]) < 60:
                    report["candidates"].append(f"第{ci}章 #{len(new_paras) + 1}: {cand}")
            if q != p:
                report["changed"] += 1
                if len(report["samples"]) < 40:
                    report["samples"].append(("BEFORE: " + p, "AFTER : " + q))
            if q:
                new_paras.append(q)
        item = dict(ch)
        item["paragraphs"] = new_paras
        # “作者有话要说”也一并规范化（它不是段落，不计入段落数）
        if ch.get("note"):
            new_note = [normalize_paragraph(x) for x in ch["note"]]
            new_note = [x for x in new_note if x]
            item["note"] = new_note
            if new_note != ch["note"]:
                report["changed"] += 1
        # figures 原样保留（相对路径由 build_book 以源 JSON 目录重定基）
        item["chars"] = sum(len(re.sub(r"\s", "", x)) for x in new_paras)
        out.append(item)
    report["chapters"] = len(out)
    report["total_chars"] = sum(c["chars"] for c in out)
    return out, report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("chapters")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--report", default="")
    args = ap.parse_args()

    with open(args.chapters, encoding="utf-8") as f:
        data = json.load(f)
    chapters = data["chapters"] if isinstance(data, dict) else data

    out, report = normalize_chapters(chapters)
    # 插图路径：按「源 JSON 所在目录」转绝对，后续脚本换目录也不丢图；
    # build_book 会把它们改写进 OEBPS/images/figures/，成品里不会出现本机路径。
    import os
    base = os.path.dirname(os.path.abspath(args.chapters))
    for ch in out:
        for fig in ch.get("figures") or []:
            f = (fig.get("file") or "").replace("\\", "/")
            if f and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", f):
                if not os.path.isabs(f):
                    fig["file"] = os.path.normpath(os.path.join(base, f))
                else:
                    fig["file"] = os.path.normpath(f)
            elif f:
                fig["file"] = f
    payload = data if isinstance(data, dict) else out
    if isinstance(data, dict):
        meta = {k: v for k, v in data.items() if k != "chapters"}
        payload = dict(meta, chapters=out)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    lines = [
        f"章节: {report['chapters']}",
        f"段落: {report['paragraphs']}  改动: {report['changed']}",
        f"总字数: {report['total_chars']}",
        "",
        "== 改动样例（最多 40 条）==",
    ]
    for before, after in report["samples"]:
        lines += [before, after, "-"]
    if report["candidates"]:
        lines += ["", "== 待判断：汉字之间的点/斜杠（未自动处理）=="]
        lines += ["  " + c for c in report["candidates"]]
        lines += ["", "提示：这些可能是并列（他/她）、外文名间隔号（玛丽·雪莱）或站点规避（傻/逼）。",
                  "      模型/人工按上下文判断：属于规避的，逐条确认后手工改；不确定就保留。"]
    text = "\n".join(lines)
    print(text)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
