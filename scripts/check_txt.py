#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 txt 与 epub 是不是同一本书：章节数、每章标题、每章段落逐行一致。

用法:
    python check_txt.py "书名.txt" "书名.epub"

为什么需要它：build_book 会同时产出 txt 和 epub，但“两份内容一致”很容易被口号化——
txt 里多/少一段、epub 用了 note 标记而 txt 没写，都不会被结构校验发现。

判据:
  - 章节标题（h1/h2/h3 文字 or 首个 `第N章/番外` 行）必须按顺序一一对应
  - 每章正文段落逐行相等（txt 一行一段；epub 取 <p>，跳过 <figure> 图注）
  - epub 的「作者有话要说」在 txt 里必须是独占一行的 `【作者有话要说】` + 原文段落
  - txt 不得出现 epub 里没有的正文行（前页/分隔线/页脚白名单除外）

退出码: 0 一致；1 有差异。
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

XHTML = "{http://www.w3.org/1999/xhtml}"
CHAP_FILE = re.compile(r"^OEBPS/text/ch(\d+)\.xhtml$")
HEAD_RE = re.compile(r"^(第\s*[\d〇零一二三四五六七八九十百]+\s*[章话回节]|番外)")
NOTE_MARK = "【作者有话要说】"
SEP_RE = re.compile(r"^[=\-—＊*·•◇❖]{3,}$")


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def epub_chapters(path: str) -> list[dict]:
    z = zipfile.ZipFile(path)
    files = sorted((int(m.group(1)), n) for n in z.namelist() if (m := CHAP_FILE.match(n)))
    out = []
    for _, name in files:
        root = ET.fromstring(z.read(name))
        head = ""
        for tag in ("h1", "h2", "h3"):
            for el in root.iter(XHTML + tag):
                head = " ".join("".join(el.itertext()).split())
                if head:
                    break
            if head:
                break
        body, note = [], []
        skip = set()
        for tag in ("figure", "aside"):
            for el in root.iter(XHTML + tag):
                for p in el.iter(XHTML + "p"):
                    skip.add(id(p))
        for p in root.iter(XHTML + "p"):
            if id(p) in skip:
                continue
            txt = "".join(p.itertext()).strip()
            cls = p.get("class") or ""
            if not txt or "author-note-h" in cls or txt.strip("【】") == "作者有话要说":
                continue
            body.append(txt)
        for aside in root.iter(XHTML + "aside"):
            for p in aside.iter(XHTML + "p"):
                cls = p.get("class") or ""
                txt = "".join(p.itertext()).strip()
                # “作者有话要说”标题行不算正文（txt 里用统一的【作者有话要说】标记）
                if txt and not txt.strip("【】") == "作者有话要说" and "author-note-h" not in cls:
                    note.append(txt)
        out.append({"file": name, "head": head, "body": body, "note": note})
    return out


def txt_chapters(path: str) -> list[tuple[str, list[str]]]:
    with open(path, encoding="utf-8-sig") as f:
        lines = [x.rstrip("\n") for x in f]
    idx = [i for i, ln in enumerate(lines) if HEAD_RE.match(ln.strip())]
    out = []
    for k, i in enumerate(idx):
        end = idx[k + 1] if k + 1 < len(idx) else len(lines)
        paras = [ln.strip() for ln in lines[i + 1:end]
                 if ln.strip() and not re.match(r"^〔.+〕$", ln.strip())]
        out.append((lines[i].strip(), paras))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("txt")
    ap.add_argument("epub")
    args = ap.parse_args()

    ep = epub_chapters(args.epub)
    tx = txt_chapters(args.txt)
    errs: list[str] = []
    if not ep:
        print("FAIL: epub 里没找到章节文件")
        return 1
    if not tx:
        print("FAIL: txt 里没找到章节标题行")
        return 1
    if len(ep) != len(tx):
        errs.append(f"章节数不一致：epub {len(ep)} 章，txt {len(tx)} 章")

    bad = 0
    for i, (e, (thead, tparas)) in enumerate(zip(ep, tx), 1):
        if e["head"] and norm(e["head"]) != norm(thead):
            errs.append(f"第 {i} 章标题不一致：epub「{e['head']}」vs txt「{thead}」")
        want = list(e["body"])
        if e["note"]:
            want += [NOTE_MARK] + list(e["note"])
        if want != tparas:
            bad += 1
            first = next((k for k, (a, b) in enumerate(zip(want, tparas)) if a != b), None)
            if first is None:
                errs.append(f"第 {i} 章段落数不一致：epub {len(want)} 段，txt {len(tparas)} 段")
            else:
                errs.append(
                    f"第 {i} 章第 {first + 1} 段不一致：epub「{want[first][:40]}」"
                    f"vs txt「{tparas[first][:40]}」")

    print(f"epub 章节: {len(ep)}  txt 章节: {len(tx)}  段落不一致章数: {bad}")
    for e in errs[:10]:
        print("FAIL: " + e)
    if len(errs) > 10:
        print(f"FAIL: …另有 {len(errs) - 10} 条")
    print("RESULT: " + ("FAIL" if errs else "PASS"))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
